# tests/test_loader.py
"""Tests for data/loader.py — load_units, unit_fingerprint."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from data.loader import load_units, unit_fingerprint
from data.models import Unit


# ── load_units ────────────────────────────────────────────────────


class TestLoadUnits:
    def test_loads_all_rows(self, db_with_units):
        units = load_units(db_with_units)
        assert len(units) == 3

    def test_com_numbers_present(self, db_with_units):
        units = load_units(db_with_units)
        coms = {u.com_number for u in units}
        assert coms == {"14201", "14202", "14203"}

    def test_percent_complete_scaled_to_100(self, db_with_units):
        """DB stores 0-1, loader must return 0-100."""
        units = load_units(db_with_units)
        by_com = {u.com_number: u for u in units}
        assert by_com["14201"].percent_complete == 50.0
        assert by_com["14202"].percent_complete == 25.0
        assert by_com["14203"].percent_complete == 100.0

    def test_dates_parsed_correctly(self, db_with_units):
        units = load_units(db_with_units)
        u = next(u for u in units if u.com_number == "14201")
        assert u.detailing_due_date == date(2025, 7, 15)
        assert u.build_date == date(2025, 8, 1)

    def test_empty_db_returns_empty_list(self, db_path):
        units = load_units(db_path)
        assert units == []

    def test_null_dates_become_none(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO units (com_number, detailing_due_date, build_date) "
            "VALUES (?, ?, ?)",
            ("99999", None, None),
        )
        conn.commit()
        conn.close()
        units = load_units(db_path)
        assert len(units) == 1
        assert units[0].detailing_due_date is None
        assert units[0].build_date is None


# ── unit_fingerprint ─────────────────────────────────────────────


class TestFingerprint:
    def test_same_unit_same_fingerprint(self, sample_unit):
        fp1 = unit_fingerprint(sample_unit)
        fp2 = unit_fingerprint(sample_unit)
        assert fp1 == fp2

    def test_different_unit_different_fingerprint(self, sample_unit, overdue_unit):
        fp1 = unit_fingerprint(sample_unit)
        fp2 = unit_fingerprint(overdue_unit)
        assert fp1 != fp2

    def test_modified_field_changes_fingerprint(self, sample_unit):
        fp1 = unit_fingerprint(sample_unit)
        sample_unit.percent_complete = 75.0
        fp2 = unit_fingerprint(sample_unit)
        assert fp1 != fp2
