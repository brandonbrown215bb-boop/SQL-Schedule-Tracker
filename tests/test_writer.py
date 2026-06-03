# tests/test_writer.py
"""Tests for data/writer.py — save_unit (SQLite)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from data.models import Unit
from data.writer import save_unit


@pytest.fixture
def unit_to_save():
    return Unit(
        com_number="14201",
        job_name="Test Job",
        contract_number="CN-001",
        description="Test",
        detailer="Carl M",
        checking_status="",
        department_hours=40.0,
        percent_complete=50.0,
        actual_hours=20.0,
        target_department_hours=40.0,
        iec_internal_hours=0.0,
        unit_detailing_start_date=date(2025, 6, 1),
        unit_moved_to_checking_date=None,
        unit_detailing_completion_date=None,
    )


class TestSaveUnit:
    def test_updates_existing_row(self, db_with_units, unit_to_save):
        save_unit(db_with_units, unit_to_save)
        conn = sqlite3.connect(db_with_units)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM units WHERE com_number = '14201'")
        row = cur.fetchone()
        conn.close()
        assert row["detailer"] == "Carl M"
        assert row["department_hours"] == 40.0

    def test_percent_complete_divided_by_100(self, db_with_units, unit_to_save):
        """Writer stores percent as 0-1 decimal in DB."""
        save_unit(db_with_units, unit_to_save)
        conn = sqlite3.connect(db_with_units)
        cur = conn.execute("SELECT percent_complete FROM units WHERE com_number = '14201'")
        val = cur.fetchone()[0]
        conn.close()
        assert val == pytest.approx(0.5)

    def test_dates_stored_as_iso(self, db_with_units, unit_to_save):
        save_unit(db_with_units, unit_to_save)
        conn = sqlite3.connect(db_with_units)
        cur = conn.execute(
            "SELECT unit_detailing_start_date FROM units WHERE com_number = '14201'"
        )
        val = cur.fetchone()[0]
        conn.close()
        assert val == "2025-06-01"

    def test_null_dates_stored_as_null(self, db_with_units, unit_to_save):
        save_unit(db_with_units, unit_to_save)
        conn = sqlite3.connect(db_with_units)
        cur = conn.execute(
            "SELECT unit_moved_to_checking_date FROM units WHERE com_number = '14201'"
        )
        val = cur.fetchone()[0]
        conn.close()
        assert val is None

    def test_com_number_not_found_raises(self, db_path, unit_to_save):
        """Saving a COM that doesn't exist in DB raises ConcurrentEditError."""
        import pytest

        from data.writer import ConcurrentEditError
        with pytest.raises(ConcurrentEditError, match="was modified by another user"):
            save_unit(db_path, unit_to_save)
