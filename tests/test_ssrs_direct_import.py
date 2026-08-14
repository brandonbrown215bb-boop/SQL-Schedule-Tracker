# tests/test_ssrs_direct_import.py
"""Tests for direct SSRS single-report import (unit_state in SCHDetailingReport)."""

import csv
import sqlite3

import pytest

from automation.create_db import create_database
from automation.import_atomsvc import merge_summary_states_into_csv
from automation.import_csv import run_import


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test_schedule.db")
    create_database(db_path)
    return db_path


def test_detailing_report_with_line_item_state_exact_header(temp_db, tmp_path):
    """Verify SCHDetailingReport CSV containing exact 'LineItemState' header imports unit_state directly."""
    csv_path = str(tmp_path / "detailing_live_header.csv")
    fieldnames = [
        "DeptDueDate",
        "COMNumber",
        "ManufacturingLocation",
        "JobName",
        "TopLevelNumber",
        "Description",
        "LineItemState",
        "BuildDate",
    ]
    rows = [
        {
            "DeptDueDate": "01/02/2026",
            "COMNumber": "19895",
            "ManufacturingLocation": "Hattiesburg",
            "JobName": "40948 Wisconsin History Center",
            "TopLevelNumber": "5E6301170601",
            "Description": "Test Unit Description",
            "LineItemState": "Done",
            "BuildDate": "01/27/2026",
        },
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    stats = run_import(csv_path, temp_db)
    assert stats["inserted"] == 1

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT com_number, unit_state FROM units WHERE com_number='19895'")
    row = cursor.fetchone()
    conn.close()

    assert row == ("19895", "Done")


def test_detailing_report_with_line_item_state_desc(temp_db, tmp_path):
    """Verify SCHDetailingReport CSV containing LineItemStateDesc imports unit_state directly."""
    csv_path = str(tmp_path / "detailing_with_state.csv")
    fieldnames = [
        "COMNumber",
        "JobName",
        "TopLevelNumber",
        "Description",
        "DeptDueDate",
        "LineItemStateDesc",
    ]
    rows = [
        {
            "COMNumber": "1001",
            "JobName": "Test Job 1",
            "TopLevelNumber": "TL-100",
            "Description": "Unit 1",
            "DeptDueDate": "09/15/2026",
            "LineItemStateDesc": "Fab-Eng",
        },
        {
            "COMNumber": "1002",
            "JobName": "Test Job 2",
            "TopLevelNumber": "TL-200",
            "Description": "Unit 2",
            "DeptDueDate": "09/20/2026",
            "LineItemStateDesc": "Pre-Eng",
        },
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    stats = run_import(csv_path, temp_db)
    assert stats["inserted"] == 2

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT com_number, unit_state FROM units ORDER BY com_number")
    db_rows = cursor.fetchall()
    conn.close()

    assert db_rows == [("1001", "Fab-Eng"), ("1002", "Pre-Eng")]


def test_detailing_report_with_unit_state_column(temp_db, tmp_path):
    """Verify SCHDetailingReport CSV containing UnitState column imports unit_state directly."""
    csv_path = str(tmp_path / "detailing_with_unitstate.csv")
    fieldnames = [
        "COMNumber",
        "JobName",
        "TopLevelNumber",
        "Description",
        "DeptDueDate",
        "UnitState",
    ]
    rows = [
        {
            "COMNumber": "2001",
            "JobName": "Test Job 3",
            "TopLevelNumber": "TL-300",
            "Description": "Unit 3",
            "DeptDueDate": "10/01/2026",
            "UnitState": "Done",
        },
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    stats = run_import(csv_path, temp_db)
    assert stats["inserted"] == 1

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT com_number, unit_state FROM units WHERE com_number='2001'")
    row = cursor.fetchone()
    conn.close()

    assert row == ("2001", "Done")


def test_import_does_not_overwrite_existing_unit_state_with_null(temp_db, tmp_path):
    """Verify an import with empty LineItemStateDesc does NOT wipe existing unit_state in DB."""
    # Insert initial row with unit_state = "Fab-Lock"
    conn = sqlite3.connect(temp_db)
    conn.execute(
        "INSERT INTO units (com_number, job_name, unit_state, detailing_due_date) VALUES ('3001', 'Job 300', 'Fab-Lock', '2026-10-10')"
    )
    conn.commit()
    conn.close()

    # Import CSV with empty LineItemStateDesc column
    csv_path = str(tmp_path / "update_empty_state.csv")
    fieldnames = ["COMNumber", "JobName", "DeptDueDate", "LineItemStateDesc"]
    rows = [{"COMNumber": "3001", "JobName": "Job 300 Updated", "DeptDueDate": "10/10/2026", "LineItemStateDesc": ""}]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    stats = run_import(csv_path, temp_db)
    assert stats["updated"] == 1

    # Verify unit_state was preserved as Fab-Lock
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT unit_state, job_name FROM units WHERE com_number='3001'")
    unit_state, job_name = cursor.fetchone()
    conn.close()

    assert job_name == "Job 300 Updated"
    assert unit_state == "Fab-Lock"


def test_merge_summary_states_normalized_com(tmp_path):
    """Verify merge_summary_states_into_csv matches COM numbers across formatting differences."""
    detailing_path = str(tmp_path / "detailing.csv")
    summary_path = str(tmp_path / "summary.csv")

    with open(detailing_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["COMNumber", "JobName"])
        writer.writeheader()
        writer.writerow({"COMNumber": "COM-4001", "JobName": "Job 4"})

    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["COMNumber1", "LineItemState"])
        writer.writeheader()
        writer.writerow({"COMNumber1": "4001", "LineItemState": "Pre-Load"})

    merge_summary_states_into_csv(detailing_path, summary_path)

    with open(detailing_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        merged_rows = list(reader)

    assert len(merged_rows) == 1
    assert merged_rows[0]["LineItemStateDesc"] == "Pre-Load"
