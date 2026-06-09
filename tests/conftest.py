"""Shared fixtures for the test suite."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest
from PyQt5.QtWidgets import QApplication

from data.models import Unit

_app = None


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for the test session."""
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


# ── Unit fixtures ────────────────────────────────────────────────


@pytest.fixture
def sample_unit() -> Unit:
    """A typical in-progress unit."""
    return Unit(
        com_number="14201",
        job_name="Test Job",
        contract_number="CN-001",
        description="Test Description",
        detailer="Carl M",
        checking_status="",
        status_color="yellow",
        department_hours=40.0,
        target_department_hours=40.0,
        iec_internal_hours=0.0,
        percent_complete=50.0,
        actual_hours=20.0,
        working_days=[0, 1, 2, 3],
        detailing_due_date=date(2025, 7, 15),
        build_date=date(2025, 8, 1),
        unit_detailing_start_date=date(2025, 6, 1),
        unit_moved_to_checking_date=None,
        unit_detailing_completion_date=None,
        dept_due_date_previous=None,
    )


@pytest.fixture
def overdue_unit() -> Unit:
    """A unit past its due date with incomplete work."""
    return Unit(
        com_number="14202",
        job_name="Overdue Job",
        contract_number="CN-002",
        description="Overdue",
        detailer="Carl M",
        checking_status="",
        status_color="red",
        department_hours=80.0,
        percent_complete=25.0,
        detailing_due_date=date.today() - timedelta(days=5),
        build_date=date.today() + timedelta(days=30),
    )


@pytest.fixture
def completed_unit() -> Unit:
    """A 100% complete unit."""
    return Unit(
        com_number="14203",
        job_name="Done Job",
        contract_number="CN-003",
        description="Complete",
        detailer="Carl M",
        checking_status="",
        status_color="green",
        department_hours=40.0,
        percent_complete=100.0,
        detailing_due_date=date.today() + timedelta(days=30),
        build_date=date(2025, 7, 1),
        unit_detailing_start_date=date(2025, 5, 1),
        unit_detailing_completion_date=date(2025, 5, 30),
    )


# ── SQLite fixtures ──────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path):
    """Create a minimal SQLite database with the units schema."""
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            com_number TEXT UNIQUE NOT NULL,
            job_name TEXT DEFAULT '',
            top_level_number TEXT DEFAULT '',
            description TEXT DEFAULT '',
            detailer TEXT DEFAULT '',
            checking_status TEXT DEFAULT '',
            manufacturing_location TEXT DEFAULT '',
            build_cycle TEXT DEFAULT '',
            department_hours REAL DEFAULT 0.0,
            target_dept_hours REAL DEFAULT 0.0,
            iec_internal_hours REAL DEFAULT 0.0,
            percent_complete REAL DEFAULT 0.0,
            actual_hours REAL DEFAULT 0.0,
            notes TEXT DEFAULT '',
            status_color TEXT DEFAULT 'gray',
            remaining_hours REAL DEFAULT 0.0,
            detailing_due_date TEXT,
            dept_due_date_previous TEXT,
            build_date TEXT,
            unit_detailing_start_date TEXT,
            unit_moved_to_checking_date TEXT,
            unit_detailing_completion_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS detailers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_order INTEGER DEFAULT 0,
            working_weekdays TEXT DEFAULT '[0,1,2,3]'
        );
        CREATE TABLE IF NOT EXISTS default_schedule (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            working_weekdays TEXT DEFAULT '[0,1,2,3]'
        );
        INSERT OR IGNORE INTO default_schedule (id, working_weekdays) VALUES (1, '[0,1,2,3]');
    """)
    conn.commit()
    conn.close()
    return str(db_file)


@pytest.fixture
def db_with_units(db_path):
    """SQLite database with a few sample units."""
    conn = sqlite3.connect(db_path)
    conn.executemany("""
        INSERT INTO units (com_number, job_name, detailer, department_hours, percent_complete,
                          detailing_due_date, build_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        ("14201", "Job A", "Carl M", 40.0, 0.50, "2025-07-15", "2025-08-01"),
        ("14202", "Job B", "Matthew E", 80.0, 0.25, "2025-06-01", "2025-07-01"),
        ("14203", "Job C", "Carl M", 40.0, 1.00, "2025-05-01", "2025-06-01"),
    ])
    conn.commit()
    conn.close()
    return db_path
