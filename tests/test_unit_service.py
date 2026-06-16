"""Tests for services/unit_service.py — UnitService.

Tests are pure Python — no QApplication required.
Uses in-memory SQLite fixtures shared with the existing test suite.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from data.models import Unit
from services.unit_service import DueDateChange, UnitService
from services.validation import ValidationError

# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def svc(db_path) -> UnitService:
    """UnitService using the shared db_path fixture."""
    return UnitService(db_path)


@pytest.fixture
def svc_with_units(db_with_units) -> UnitService:
    """UnitService with a populated database."""
    return UnitService(db_with_units)


@pytest.fixture
def existing_unit(db_with_units) -> Unit:
    """A unit that already exists in the db_with_units fixture."""
    conn = sqlite3.connect(db_with_units)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM units WHERE com_number = '14201'").fetchone()
    conn.close()
    from data.db import row_to_unit

    return row_to_unit(row)


# ── Load tests ──────────────────────────────────────────────────────


class TestLoadAll:
    def test_load_empty_db(self, svc):
        units = svc.load_all()
        assert units == []

    def test_load_returns_units(self, svc_with_units):
        units = svc_with_units.load_all()
        assert len(units) == 3

    def test_load_ordered_by_due_date(self, svc_with_units):
        units = svc_with_units.load_all()
        due_dates = [u.detailing_due_date for u in units]
        assert due_dates == sorted(due_dates)

    def test_load_with_detailer_schedules(self, db_with_units):
        schedules = {"Carl M": [0, 1, 2, 3], "Matthew E": [1, 2, 3, 4]}
        svc = UnitService(db_with_units, detailer_schedules=schedules)
        units = svc.load_all()
        for u in units:
            if u.detailer == "Carl M":
                assert u.working_days == [0, 1, 2, 3]
            elif u.detailer == "Matthew E":
                assert u.working_days == [1, 2, 3, 4]


# ── Get by COM tests ────────────────────────────────────────────────


class TestGetByCom:
    def test_get_existing_unit(self, svc_with_units):
        unit = svc_with_units.get_by_com("14201")
        assert unit is not None
        assert unit.com_number == "14201"

    def test_get_nonexistent_returns_none(self, svc_with_units):
        unit = svc_with_units.get_by_com("NONEXISTENT")
        assert unit is None

    def test_get_preserves_all_fields(self, svc_with_units):
        unit = svc_with_units.get_by_com("14201")
        assert unit.job_name == "Job A"
        assert unit.detailer == "Carl M"


# ── Save tests ──────────────────────────────────────────────────────


class TestSave:
    def test_save_updates_existing_unit(self, svc_with_units, existing_unit):
        existing_unit.job_name = "Modified Job Name"
        svc_with_units.save(existing_unit)
        result = svc_with_units.get_by_com("14201")
        assert result is not None
        assert result.job_name == "Modified Job Name"

    def test_save_sets_updated_at(self, svc_with_units, existing_unit):
        svc_with_units.save(existing_unit)
        assert existing_unit.updated_at != ""

    def test_save_percent_complete_scale(self, svc_with_units, existing_unit):
        """Writer stores percent_complete as 0-1 decimal."""
        existing_unit.percent_complete = 75.0
        svc_with_units.save(existing_unit)
        conn = sqlite3.connect(svc_with_units.db_path)
        row = conn.execute(
            "SELECT percent_complete FROM units WHERE com_number = '14201'"
        ).fetchone()
        conn.close()
        assert row[0] == pytest.approx(0.75)

    def test_save_audit_trail_created(self, svc_with_units, existing_unit):
        existing_unit.detailer = "Brandon B"
        svc_with_units.save(existing_unit)
        trail = svc_with_units.get_audit_trail(com_number="14201")
        assert len(trail) >= 1
        detailer_entry = next((e for e in trail if e["field_name"] == "detailer"), None)
        assert detailer_entry is not None
        assert detailer_entry["new_value"] == "Brandon B"

    def test_save_validates_percent_complete(self, svc_with_units, existing_unit):
        """Save must reject percent_complete > 100 via the validation layer."""
        existing_unit.percent_complete = 150.0
        with pytest.raises(ValidationError):
            svc_with_units.save(existing_unit)

    def test_save_validates_negative_hours(self, svc_with_units, existing_unit):
        """Save must reject negative department_hours via the validation layer."""
        existing_unit.department_hours = -10.0
        with pytest.raises(ValidationError):
            svc_with_units.save(existing_unit)

    def test_save_runs_pre_save_hooks(self, svc_with_units, existing_unit):
        """Save must run registered pre-save hooks and return warnings."""
        from services.pre_save_hooks import PreSaveHookRegistry, date_order_hook

        registry = PreSaveHookRegistry()
        registry.register("date_order", date_order_hook, priority=10)
        svc_with_units._hook_registry = registry

        # Set dates out of order to trigger a warning
        existing_unit.unit_detailing_start_date = date(2025, 6, 1)
        existing_unit.unit_detailing_completion_date = date(2025, 5, 1)

        # Save should succeed (warning, not error) — the hook returns warnings
        svc_with_units.save(existing_unit)
        # The save should complete without exception; warnings are logged

    def test_save_pre_save_hook_blocks_on_fatal(self, svc_with_units, existing_unit):
        """A pre-save hook that raises ValidationError must block the save."""
        from services.pre_save_hooks import PreSaveHookRegistry

        def fatal_hook(u, ctx):
            raise ValidationError(["Fatal hook error"])

        registry = PreSaveHookRegistry()
        registry.register("fatal", fatal_hook, priority=1)
        svc_with_units._hook_registry = registry

        with pytest.raises(ValidationError):
            svc_with_units.save(existing_unit)


# ── Fingerprint tests ───────────────────────────────────────────────


class TestFingerprint:
    def test_same_unit_same_fingerprint(self, existing_unit):
        fp1 = UnitService.compute_fingerprint(existing_unit)
        fp2 = UnitService.compute_fingerprint(existing_unit)
        assert fp1 == fp2

    def test_different_units_different_fingerprint(self, existing_unit):
        fp1 = UnitService.compute_fingerprint(existing_unit)
        other = Unit(
            com_number="99002",
            job_name="Different",
            contract_number="CT-200",
            description="Different",
            detailer="Bob",
            checking_status="",
        )
        fp2 = UnitService.compute_fingerprint(other)
        assert fp1 != fp2

    def test_fingerprint_changes_with_edit(self, existing_unit):
        fp1 = UnitService.compute_fingerprint(existing_unit)
        modified = Unit(
            com_number="99999",  # different COM to avoid cache
            job_name="Modified Job",
            contract_number=existing_unit.contract_number,
            description=existing_unit.description,
            detailer=existing_unit.detailer,
            checking_status=existing_unit.checking_status,
            department_hours=existing_unit.department_hours,
            actual_hours=existing_unit.actual_hours,
            target_department_hours=existing_unit.target_department_hours,
            iec_internal_hours=existing_unit.iec_internal_hours,
            percent_complete=existing_unit.percent_complete,
        )
        fp2 = UnitService.compute_fingerprint(modified)
        assert fp1 != fp2


# ── Identicals tests ────────────────────────────────────────────────


class TestIdenticals:
    def test_single_unit_unchanged(self, existing_unit):
        units = [existing_unit]
        UnitService.apply_identicals(units)
        # Single unit — no identicals to apply
        assert not existing_unit.is_non_primary_identical

    def test_two_identicals_primary_keeps_hours(self):
        primary = Unit(
            com_number="A001",
            job_name="Job",
            contract_number="CT-100",
            description="Desc",
            detailer="Alice",
            checking_status="",
            target_department_hours=40.0,
            detailing_due_date=date(2025, 7, 1),
        )
        secondary = Unit(
            com_number="A002",
            job_name="Job",
            contract_number="CT-100",
            description="Desc",
            detailer="Bob",
            checking_status="",
            target_department_hours=40.0,
            detailing_due_date=date(2025, 7, 15),
        )
        units = [primary, secondary]
        UnitService.apply_identicals(units)

        assert primary.target_department_hours == 40.0
        assert not primary.is_non_primary_identical
        assert secondary.target_department_hours == 0.0
        assert secondary.is_non_primary_identical

    def test_empty_contract_skipped(self):
        unit = Unit(
            com_number="B001",
            job_name="Job",
            contract_number="",
            description="Desc",
            detailer="Alice",
            checking_status="",
            target_department_hours=40.0,
        )
        UnitService.apply_identicals([unit])
        assert unit.target_department_hours == 40.0


# ── Due date change detection tests ─────────────────────────────────


class TestDetectDueDateChanges:
    def test_no_changes(self):
        u1 = Unit(
            com_number="C001",
            job_name="Job",
            contract_number="CT",
            description="Desc",
            detailer="Alice",
            checking_status="",
            detailing_due_date=date(2025, 7, 15),
        )
        changes = UnitService.detect_changed_due_dates([u1], [u1])
        assert len(changes) == 0

    def test_detected_change(self):
        old = Unit(
            com_number="C001",
            job_name="Job",
            contract_number="CT",
            description="Desc",
            detailer="Alice",
            checking_status="",
            detailing_due_date=date(2025, 7, 15),
        )
        new = Unit(
            com_number="C001",
            job_name="Job",
            contract_number="CT",
            description="Desc",
            detailer="Alice",
            checking_status="",
            detailing_due_date=date(2025, 8, 1),
        )
        changes = UnitService.detect_changed_due_dates([old], [new])
        assert len(changes) == 1
        assert isinstance(changes[0], DueDateChange)
        assert changes[0].previous_due_date == date(2025, 7, 15)
        assert changes[0].unit.due_date_changed is True
        assert changes[0].unit.previous_detailing_due_date == date(2025, 7, 15)

    def test_new_unit_not_a_change(self):
        old = Unit(
            com_number="C001",
            job_name="Job",
            contract_number="CT",
            description="Desc",
            detailer="Alice",
            checking_status="",
            detailing_due_date=date(2025, 7, 15),
        )
        new_unit = Unit(
            com_number="C002",
            job_name="New",
            contract_number="CT",
            description="Desc",
            detailer="Alice",
            checking_status="",
            detailing_due_date=date(2025, 9, 1),
        )
        changes = UnitService.detect_changed_due_dates([old], [old, new_unit])
        assert len(changes) == 0

    def test_null_to_date_is_a_change(self):
        old = Unit(
            com_number="C001",
            job_name="Job",
            contract_number="CT",
            description="Desc",
            detailer="Alice",
            checking_status="",
            detailing_due_date=None,
        )
        new = Unit(
            com_number="C001",
            job_name="Job",
            contract_number="CT",
            description="Desc",
            detailer="Alice",
            checking_status="",
            detailing_due_date=date(2025, 7, 15),
        )
        changes = UnitService.detect_changed_due_dates([old], [new])
        assert len(changes) == 1
        assert changes[0].previous_due_date is None

    def test_multiple_changes(self):
        old_units = [
            Unit(
                com_number="D001",
                job_name="Job1",
                contract_number="CT",
                description="Desc",
                detailer="Alice",
                checking_status="",
                detailing_due_date=date(2025, 7, 1),
            ),
            Unit(
                com_number="D002",
                job_name="Job2",
                contract_number="CT",
                description="Desc",
                detailer="Alice",
                checking_status="",
                detailing_due_date=date(2025, 8, 1),
            ),
        ]
        new_units = [
            Unit(
                com_number="D001",
                job_name="Job1",
                contract_number="CT",
                description="Desc",
                detailer="Alice",
                checking_status="",
                detailing_due_date=date(2025, 7, 15),  # changed
            ),
            Unit(
                com_number="D002",
                job_name="Job2",
                contract_number="CT",
                description="Desc",
                detailer="Alice",
                checking_status="",
                detailing_due_date=date(2025, 8, 15),  # changed
            ),
        ]
        changes = UnitService.detect_changed_due_dates(old_units, new_units)
        assert len(changes) == 2


# ── Audit trail tests ──────────────────────────────────────────────


class TestAuditTrail:
    def test_get_trail_for_com(self, svc_with_units, existing_unit):
        existing_unit.detailer = "Brandon B"
        svc_with_units.save(existing_unit)
        trail = svc_with_units.get_audit_trail(com_number="14201")
        assert len(trail) >= 1

    def test_get_all_trail(self, svc_with_units, existing_unit):
        existing_unit.detailer = "Brandon B"
        svc_with_units.save(existing_unit)
        trail = svc_with_units.get_audit_trail()
        assert len(trail) >= 1

    def test_get_trail_limit(self, svc_with_units, existing_unit):
        existing_unit.detailer = "Brandon B"
        svc_with_units.save(existing_unit)
        trail = svc_with_units.get_audit_trail(com_number="14201", limit=1)
        assert len(trail) <= 1

    def test_get_trail_empty_db(self, svc):
        trail = svc.get_audit_trail()
        assert trail == []


# ── Property tests ─────────────────────────────────────────────────


class TestProperties:
    def test_db_path_property(self, svc):
        assert svc.db_path == svc._db_path

    def test_default_detailer_schedules(self, db_path):
        svc = UnitService(db_path)
        assert svc._detailer_schedules == {}

    def test_custom_detailer_schedules(self, db_path):
        schedules = {"Alice": [0, 1, 2, 3]}
        svc = UnitService(db_path, detailer_schedules=schedules)
        assert svc._detailer_schedules == schedules
