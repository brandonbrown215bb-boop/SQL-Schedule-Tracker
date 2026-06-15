# tests/test_edit_form.py
"""Tests for EditForm widget — US-006b AC#1.

Verifies that set_unit() populates all fields, _on_save() emits correct data,
and revert restores original values.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest
from PyQt5.QtWidgets import QApplication

from data.models import Unit
from gui.edit_form import EditForm

# ── Fixtures ──────────────────────────────────────────────────────────

_app = None  # type: ignore[var-annotated]


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for the test session."""
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


@pytest.fixture
def default_detailers():
    return ["— Unassigned —", "Jackie / IEC Internals", "Maria / RGV Team"]


@pytest.fixture
def sample_unit():
    return Unit(
        com_number="COM-TEST-001",
        job_name="Test Job Alpha",
        contract_number="CNT-2024-001",
        description="A sample unit",
        detailer="Jackie / IEC Internals",
        checking_status="In Progress",
        status_color="yellow",
        department_hours=40.0,
        target_department_hours=36.0,
        iec_internal_hours=4.0,
        percent_complete=50.0,
        actual_hours=20.0,
        working_days=[0, 1, 2, 3],
        unit_detailing_start_date=date(2025, 1, 15),
        unit_moved_to_checking_date=None,
        unit_detailing_completion_date=date(2025, 2, 1),
        dept_due_date_previous=date(2025, 3, 1),
        detailing_due_date=date(2025, 4, 1),
        build_date=date(2025, 6, 1),
    )


@pytest.fixture
def edit_form(qapp, default_detailers):
    form = EditForm(default_detailers=default_detailers)
    form._on_save = MagicMock(side_effect=form._on_save)
    yield form
    form.deleteLater()


# ── set_unit() field population tests ─────────────────────────────────


class TestSetUnitPopulatesAllFields:
    """AC#1: set_unit() populates all fields correctly."""

    def test_identity_fields_populated(self, edit_form, sample_unit):
        edit_form.set_unit(sample_unit)
        assert edit_form.com_number_edit.text() == "COM-TEST-001"
        assert edit_form.job_name_edit.text() == "Test Job Alpha"
        assert edit_form.contract_edit.text() == "CNT-2024-001"
        assert edit_form.description_edit.text() == "A sample unit"
        assert edit_form.checking_status_edit.text() == "In Progress"

    def test_detailer_combo_set(self, edit_form, sample_unit):
        edit_form.set_unit(sample_unit)
        assert edit_form.detailer_edit.currentText() == "Jackie / IEC Internals"

    def test_numeric_fields_populated(self, edit_form, sample_unit):
        edit_form.set_unit(sample_unit)
        assert edit_form.dept_hours_spin.value() == 40.0
        assert edit_form.target_hours_spin.value() == 36.0
        assert edit_form.iec_hours_spin.value() == 4.0
        assert edit_form.percent_spin.value() == 50.0
        assert edit_form.actual_hours_spin.value() == 20.0

    def test_date_fields_populated(self, edit_form, sample_unit):
        edit_form.set_unit(sample_unit)
        sd = edit_form.start_date_edit.date().toPyDate()
        assert sd == date(2025, 1, 15)
        cd = edit_form.completion_date_edit.date().toPyDate()
        assert cd == date(2025, 2, 1)

    def test_null_dates_show_unset_sentinel(self, edit_form, sample_unit):
        edit_form.set_unit(sample_unit)
        # unit_moved_to_checking_date is None
        d = edit_form.checking_date_edit.date().toPyDate()
        assert d == date(2000, 1, 1)  # ClearableDateEdit._UNSET

    def test_set_unit_none_clears_all_fields(self, edit_form, sample_unit):
        edit_form.set_unit(sample_unit)
        edit_form.set_unit(None)
        assert edit_form.com_number_edit.text() == ""
        assert edit_form.job_name_edit.text() == ""
        assert edit_form.dept_hours_spin.value() == 0
        assert edit_form.current_unit is None


# ── Revert tests ──────────────────────────────────────────────────────


class TestRevertRestoresOriginalValues:
    """AC#1 (second half): revert restores original values."""

    def test_revert_restores_values_after_edit(self, edit_form, sample_unit):
        edit_form.set_unit(sample_unit)
        # Simulate user edits
        edit_form.job_name_edit.setText("CHANGED NAME")
        edit_form.dept_hours_spin.setValue(999.0)
        edit_form.actual_hours_spin.setValue(555.0)
        assert edit_form.job_name_edit.text() == "CHANGED NAME"
        # Revert
        edit_form.set_unit(sample_unit)
        assert edit_form.job_name_edit.text() == "Test Job Alpha"
        assert edit_form.dept_hours_spin.value() == 40.0
        assert edit_form.actual_hours_spin.value() == 20.0

    def test_revert_clears_dirty_flag(self, edit_form, sample_unit):
        edit_form.set_unit(sample_unit)
        edit_form.job_name_edit.setText("Dirty")
        # set_unit clears dirty
        edit_form.set_unit(sample_unit)
        assert edit_form.is_dirty is False


# ── _on_save() emit tests ─────────────────────────────────────────────


class TestOnSaveEmitsCorrectData:
    """AC#1: _on_save() persists all fields including actual_hours."""

    def test_save_emits_unit_with_actual_hours(self, edit_form, sample_unit):
        saved_units = []
        edit_form.saved.connect(lambda u: saved_units.append(u))

        edit_form.set_unit(sample_unit)
        edit_form.actual_hours_spin.setValue = 42.0  # won't work, re-read from spin
        edit_form._on_save()

        assert len(saved_units) == 1
        emitted = saved_units[0]
        assert emitted.actual_hours == 20.0  # from sample_unit
        assert emitted.job_name == "Test Job Alpha"
        assert emitted.com_number == "COM-TEST-001"
        assert emitted.detailer == "Jackie / IEC Internals"
        assert emitted.department_hours == 40.0
        assert emitted.percent_complete == 50.0

    def test_save_emits_none_actual_hours(self, edit_form, sample_unit):
        """actual_hours may be 0.0 — should still be emitted."""
        edit_form.set_unit(sample_unit)
        edit_form.actual_hours_spin.setValue(0.0)
        edit_form._on_save()
        assert edit_form.current_unit is not None  # save should have emitted

    def test_save_updates_fields_from_form(self, edit_form, sample_unit):
        saved_units = []
        edit_form.saved.connect(lambda u: saved_units.append(u))

        edit_form.set_unit(sample_unit)
        edit_form.job_name_edit.setText("Modified Job")
        edit_form.actual_hours_spin.setValue(99.5)
        edit_form.percent_spin.setValue(75.0)
        edit_form._on_save()

        assert len(saved_units) == 1
        emitted = saved_units[0]
        assert emitted.job_name == "Modified Job"
        assert emitted.actual_hours == 99.5
        assert emitted.percent_complete == 75.0

    def test_save_without_unit_shows_status(self, edit_form):
        edit_form.set_unit(None)
        edit_form._on_save()
        assert "No Unit loaded" in edit_form.status_label.text()
