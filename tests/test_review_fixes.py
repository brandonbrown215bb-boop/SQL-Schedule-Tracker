# tests/test_review_fixes.py
"""Regression tests for the 2026-10 performance/multi-user review fixes."""

import csv
import random
import sqlite3
from datetime import date, timedelta

import pytest

from automation.create_db import create_database
from automation.import_csv import run_import
from data.models import _working_days_between

FIELDS = ["COMNumber", "JobName", "DeptDueDate", "DepartmentHours", "PercentComplete"]


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test_schedule.db")
    create_database(db_path)
    return db_path


def _write_csv(path, rows, fieldnames=FIELDS):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _updated_at(db_path, com):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT updated_at FROM units WHERE com_number = ?", (com,)).fetchone()[0]
    finally:
        conn.close()


def test_reimporting_same_csv_leaves_rows_untouched(temp_db, tmp_path):
    """Unchanged rows must keep updated_at so open edits elsewhere don't conflict."""
    csv_path = str(tmp_path / "ssrs.csv")
    rows = [
        {"COMNumber": "5001", "JobName": "Job A", "DeptDueDate": "11/02/2026",
         "DepartmentHours": "40", "PercentComplete": "0"},
        {"COMNumber": "5002", "JobName": "Job B", "DeptDueDate": "11/09/2026",
         "DepartmentHours": "12.5", "PercentComplete": "0"},
    ]
    _write_csv(csv_path, rows)
    assert run_import(csv_path, temp_db)["inserted"] == 2
    # First update pass fills computed columns (target/remaining hours).
    run_import(csv_path, temp_db)
    before = _updated_at(temp_db, "5001")

    stats = run_import(csv_path, temp_db)
    assert stats["unchanged"] == 2
    assert stats["updated"] == 0
    assert _updated_at(temp_db, "5001") == before

    rows[0]["JobName"] = "Job A Renamed"
    _write_csv(csv_path, rows)
    stats = run_import(csv_path, temp_db)
    assert stats["updated"] == 1
    assert stats["unchanged"] == 1
    assert _updated_at(temp_db, "5001") != before


def test_import_rejects_file_without_com_column(temp_db, tmp_path):
    """An SSRS error page saved as CSV must fail loudly, not 'succeed' with 0 rows."""
    bad = tmp_path / "error.csv"
    bad.write_text("<html><body>401 Unauthorized</body></html>\n", encoding="utf-8")
    with pytest.raises(ValueError, match="COMNumber"):
        run_import(str(bad), temp_db)


def test_working_days_closed_form_matches_day_loop():
    def reference(start, end, weekdays):
        count, d = 0, start + timedelta(days=1)
        while d <= end:
            count += d.weekday() in weekdays
            d += timedelta(days=1)
        return count

    rng = random.Random(42)
    for _ in range(2000):
        start = date(2026, 1, 1) + timedelta(days=rng.randint(0, 700))
        end = start + timedelta(days=rng.randint(-10, 400))
        weekdays = rng.choice([[0, 1, 2, 3], [1, 2, 3, 4], [0, 1, 2, 3, 4], []])
        assert _working_days_between(start, end, weekdays) == reference(start, end, weekdays)


def test_save_without_edits_writes_no_noise_audit_rows(db_path, tmp_path):
    """NULL vs ''/0 and identical target hours must not create audit entries."""
    from data.db import get_db, log_field_changes

    conn = get_db(db_path)
    conn.execute("INSERT INTO units (com_number, notes, actual_hours) VALUES ('7001', NULL, NULL)")
    conn.commit()
    old_row = conn.execute("SELECT * FROM units WHERE com_number = '7001'").fetchone()
    changes = log_field_changes(
        conn, "7001", old_row, {"notes": "", "actual_hours": 0.0}, saved_by="tester"
    )
    assert changes == 0
