# tests/test_reload_performance.py
"""Benchmark test for SQLite load performance.

AC#1: Loading 1000+ rows from SQLite completes within 1 second.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from data.loader import load_units


@pytest.fixture
def large_db(tmp_path):
    """Create a 1000-row SQLite database for benchmarking."""
    db_file = tmp_path / "bench.db"
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
            dr_checks TEXT DEFAULT '',
            dvl_checks TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            status_color TEXT DEFAULT 'gray',
            manufacturing_location TEXT DEFAULT '',
            build_cycle TEXT DEFAULT '',
            department_hours REAL DEFAULT 0.0,
            target_dept_hours REAL DEFAULT 0.0,
            iec_internal_hours REAL DEFAULT 0.0,
            percent_complete REAL DEFAULT 0.0,
            actual_hours REAL DEFAULT 0.0,
            detailing_due_date TEXT,
            dept_due_date_previous TEXT,
            build_date TEXT,
            unit_detailing_start_date TEXT,
            unit_moved_to_checking_date TEXT,
            unit_detailing_completion_date TEXT,
            working_days_in_checking INTEGER,
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
    for i in range(1000):
        conn.execute(
            "INSERT INTO units (com_number, detailer, department_hours, percent_complete, "
            "detailing_due_date, build_date) VALUES (?, ?, ?, ?, ?, ?)",
            (str(10000 + i), "Carl M", 40.0, 0.5, "2025-07-15", "2025-08-01"),
        )
    conn.commit()
    conn.close()
    return str(db_file)


class TestReloadPerformance:
    def test_load_under_1_second(self, large_db):
        """AC: Loading 1000 rows from SQLite completes within 1 second."""
        t0 = time.perf_counter()
        units = load_units(large_db)
        elapsed = time.perf_counter() - t0
        assert len(units) == 1000
        assert elapsed < 1.0, f"Load took {elapsed:.3f}s, expected < 1.0s"
