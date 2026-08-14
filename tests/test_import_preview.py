# tests/test_import_preview.py
"""Unit tests for automation.import_preview (Import diff engine)."""

import csv
import sqlite3

import pytest

from automation.import_preview import compute_diff, format_change_summary
from services.import_service import ImportService


@pytest.fixture
def temp_csv_and_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    csv_path = str(tmp_path / "import.csv")

    # Create DB schema
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE units (
            com_number TEXT PRIMARY KEY,
            job_name TEXT,
            top_level_number TEXT,
            description TEXT,
            detailing_due_date TEXT,
            build_date TEXT,
            department_hours REAL,
            percent_complete REAL,
            remaining_hours REAL,
            working_days_in_checking INTEGER,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Insert initial DB row
    conn.execute(
        """
        INSERT INTO units (com_number, job_name, detailing_due_date, percent_complete, department_hours)
        VALUES ('100', 'Existing Job', '2026-08-01', 0.5, 40.0)
        """
    )
    # Insert initial DB row with NULL percent_complete
    conn.execute(
        """
        INSERT INTO units (com_number, job_name, detailing_due_date, percent_complete, department_hours)
        VALUES ('200', 'Null Pct Job', '2026-08-01', NULL, 30.0)
        """
    )
    conn.commit()
    conn.close()

    # Create CSV file with:
    # 1. Existing row 100 with changed due date (and percent_complete present in DB, testing sqlite3.Row handling)
    # 2. Existing row 200 with NULL percent_complete in DB
    # 3. New row 300
    headers = [
        "COMNumber", "JobName", "TopLevelNumber", "Description",
        "DeptDueDate", "BuildDate", "DepartmentHours", "PercentComplete"
    ]
    rows = [
        ["100", "Existing Job", "TL-100", "Desc 100", "2026-08-15", "2026-09-01", "40", "0.5"],
        ["200", "Null Pct Job", "TL-200", "Desc 200", "2026-08-01", "2026-09-01", "30", "0.0"],
        ["300", "Brand New Job", "TL-300", "Desc 300", "2026-08-20", "2026-09-10", "25", "0.0"],
    ]

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    return csv_path, db_path


def test_compute_diff_no_row_get_error(temp_csv_and_db):
    """Verify compute_diff runs without throwing 'sqlite3.Row object has no attribute get'."""
    csv_path, db_path = temp_csv_and_db

    diff = compute_diff(csv_path, db_path)

    assert len(diff.new_rows) == 1
    assert diff.new_rows[0].com_number == "300"

    assert len(diff.updated_rows) == 2
    updated_coms = {r.com_number for r in diff.updated_rows}
    assert updated_coms == {"100", "200"}

    # 100 should show detailing_due_date change (and not crash on percent_complete)
    com100_diff = next(r for r in diff.updated_rows if r.com_number == "100")
    changed_fields = [c["field"] for c in com100_diff.changes]
    assert "detailing_due_date" in changed_fields


def test_import_service_diff_before_import(temp_csv_and_db):
    """Verify ImportService.diff_before_import calls compute_diff correctly."""
    csv_path, db_path = temp_csv_and_db
    svc = ImportService(db_path)

    diff = svc.diff_before_import(csv_path)

    assert len(diff.new_rows) == 1
    assert diff.new_rows[0].com_number == "300"


def test_format_change_summary():
    """Verify format_change_summary helper."""
    c1 = {"field": "job_name", "old": None, "new": "Test"}
    c2 = {"field": "job_name", "old": "Old", "new": None}
    c3 = {"field": "job_name", "old": "Old", "new": "New"}

    assert "(empty) → Test" in format_change_summary(c1)
    assert "Old → (empty)" in format_change_summary(c2)
    assert "Old → New" in format_change_summary(c3)
