"""Import parsing edge cases and preview/import agreement."""

from __future__ import annotations

import sqlite3

import pytest

from automation.import_csv import _parse_week_ending, csv_dict_reader, parse_row, run_import
from automation.import_preview import compute_diff
from services.sanitizer import InputSanitizer

HEADER = "COMNumber,JobName,DeptDueDate,BuildDate,AssyCycle,DepartmentHours,PercentComplete,WeekEndingFriday"


# ── Sanitizer ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    ["1/15/2026 12:00:00 AM", "1/15/2026 3:45 PM", "2026-01-15T00:00:00", "2026-01-15 00:00:00.000", "1/15/2026"],
)
def test_clean_date_ignores_time_of_day(raw):
    assert InputSanitizer.clean_date(raw) == "2026-01-15"


def test_clean_date_still_rejects_garbage():
    with pytest.raises(ValueError):
        InputSanitizer.clean_date("eta 3/4")


@pytest.mark.parametrize("raw, expected", [("3", 3), ("3.0", 3), (" 12 ", 12), ("1,200", 1200), ("", None)])
def test_clean_int(raw, expected):
    assert InputSanitizer.clean_int(raw) == expected


def test_clean_int_rejects_fractions():
    with pytest.raises(ValueError):
        InputSanitizer.clean_int("3.5")


@pytest.mark.parametrize(
    "raw", ["1/16/2026", "1/16/2026 12:00:00 AM", "Week Ending: 1/16/2026", "WE: 1/16/2026 12:00:00 AM"]
)
def test_week_ending_variants(raw):
    assert _parse_week_ending(raw) == "2026-01-16"


# ── Encodings ─────────────────────────────────────────────────────────

ROW = "1001,Café Job,1/15/2026,2/1/2026,3,40,50,1/16/2026"


@pytest.mark.parametrize(
    "encoding, text",
    [
        ("utf-8", f"{HEADER}\n{ROW}\n"),
        ("utf-8-sig", f"{HEADER}\n{ROW}\n"),
        ("cp1252", f"{HEADER}\n{ROW}\n"),
        ("utf-16", f"{HEADER}\n{ROW}\n".replace(",", "\t")),
    ],
)
def test_csv_reader_handles_encodings(tmp_path, encoding, text):
    path = tmp_path / "export.csv"
    path.write_bytes(text.encode(encoding))
    rows = list(csv_dict_reader(str(path)))
    assert len(rows) == 1
    data = parse_row(rows[0])
    assert data["com_number"] == "1001"
    assert data["job_name"] == "Café Job"
    assert data["build_cycle"] == 3


# ── Preview vs. import ────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE units (
            com_number TEXT PRIMARY KEY, manufacturing_location TEXT, job_name TEXT,
            top_level_number TEXT, description TEXT, detailing_due_date TEXT,
            dept_due_date_previous TEXT, build_date TEXT, build_cycle INTEGER,
            department_hours REAL, percent_complete REAL, week_ending_friday TEXT,
            unit_state TEXT, target_dept_hours REAL, iec_internal_hours REAL,
            remaining_hours REAL, working_days_in_checking INTEGER,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO units (com_number, job_name, detailing_due_date, build_date, build_cycle,"
        " department_hours, percent_complete, week_ending_friday, unit_state,"
        " target_dept_hours, iec_internal_hours, remaining_hours)"
        " VALUES ('1001', 'Job A', '2026-01-15', '2026-02-01', 3, 40.0, 0.5, '2026-01-16', 'Released',"
        " 40.0, 0.0, 20.0)"
    )
    conn.commit()
    conn.close()
    return path


def _write_csv(tmp_path, rows: list[str], header: str = HEADER + ",LineItemStateDesc") -> str:
    path = tmp_path / "import.csv"
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return str(path)


def test_preview_lists_bad_row_as_error_and_keeps_going(tmp_path, db_path):
    csv_path = _write_csv(
        tmp_path,
        [
            "1001,Job A,1/15/2026,2/1/2026,3,40,50,1/16/2026,Released",
            "1002,Bad Date,not a date,2/1/2026,3,40,0,1/16/2026,Released",
            "1003,New Job,1/20/2026 12:00:00 AM,2/1/2026,4.0,25,0,1/23/2026,Released",
        ],
    )
    diff = compute_diff(csv_path, db_path)
    assert [r.com_number for r in diff.errors] == ["1002"]
    assert "DeptDueDate" in diff.errors[0].changes[0]["new"]
    assert [r.com_number for r in diff.new_rows] == ["1003"]
    assert [r.com_number for r in diff.unchanged_rows] == ["1001"]

    stats = run_import(csv_path, db_path)
    assert stats["errors"] == 1
    assert stats["inserted"] == 1
    assert stats["unchanged"] == 1


def test_preview_reports_fields_it_used_to_miss(tmp_path, db_path):
    # Only build_cycle and week_ending_friday change
    csv_path = _write_csv(tmp_path, ["1001,Job A,1/15/2026,2/1/2026,5,40,50,1/23/2026,Released"])
    diff = compute_diff(csv_path, db_path)
    assert len(diff.updated_rows) == 1
    fields = {c["field"] for c in diff.updated_rows[0].changes}
    assert fields == {"build_cycle", "week_ending_friday"}


def test_preview_ignores_empty_unit_state_and_float_noise(tmp_path, db_path):
    # "40.0" vs 40, and empty state (the import never clears unit_state)
    csv_path = _write_csv(tmp_path, ["1001,Job A,1/15/2026,2/1/2026,3,40.0,50,1/16/2026,"])
    diff = compute_diff(csv_path, db_path)
    assert [r.com_number for r in diff.unchanged_rows] == ["1001"]


def test_preview_rejects_non_ssrs_file(tmp_path, db_path):
    path = tmp_path / "error.csv"
    path.write_text("<html>Report server error</html>\n", encoding="utf-8")
    with pytest.raises(ValueError, match="COMNumber"):
        compute_diff(str(path), db_path)
