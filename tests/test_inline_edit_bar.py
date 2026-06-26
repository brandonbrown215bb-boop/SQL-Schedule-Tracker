# tests/test_inline_edit_bar.py
"""Tests for gui/inline_edit_bar.py — InlineEditBar widget."""

from datetime import date
import pytest
from PyQt5.QtCore import QDate
from data.models import Unit
from gui.inline_edit_bar import InlineEditBar


@pytest.fixture
def bar(qapp):
    """Create an InlineEditBar with default detailers."""
    widget = InlineEditBar(default_detailers=["— Unassigned —", "Carl M", "Jackie H"])
    return widget


@pytest.fixture
def sample_unit():
    return Unit(
        com_number="14201",
        job_name="Test Job",
        contract_number="CN-001",
        description="Test",
        detailer="Carl M",
        checking_status="In Progress",
        dr_checks="Pending",
        dvl_checks="N/A",
        department_hours=40.0,
        target_department_hours=40.0,
        iec_internal_hours=0.0,
        percent_complete=50.0,
        actual_hours=20.0,
        actual_hours_to_detail_unit=15.0,
        hour_variance=25.0,
        remaining_demand=20.0,
        hours_checking=2.5,
        notes="Some notes",
        status_color="yellow",
        detailing_due_date=date(2025, 7, 15),
        unit_detailing_start_date=date(2025, 7, 1),
        unit_moved_to_checking_date=date(2025, 7, 10),
        unit_detailing_completion_date=date(2025, 7, 12),
    )


class TestInlineEditBarCreation:
    def test_bar_creates_without_error(self, bar):
        assert bar is not None
        assert bar.isVisible() is False

    def test_bar_has_dirty_property(self, bar):
        assert bar.is_dirty is False


class TestInlineEditBarSetUnit:
    def test_set_unit_populates_fields(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        assert bar.com_label.text() == "14201"
        assert bar.pct_spin.value() == 50.0
        assert bar.checking_status_edit.text() == "In Progress"
        assert bar.dr_checks_edit.text() == "Pending"
        assert bar.dvl_checks_edit.text() == "N/A"
        assert bar.target_hours_spin.value() == 40.0
        assert bar.iec_hours_spin.value() == 0.0
        assert bar.actual_hours_to_detail_spin.value() == 15.0
        assert bar.hour_variance_spin.value() == 25.0
        assert bar.remaining_demand_spin.value() == 20.0
        assert bar.hours_checking_spin.value() == 2.5
        assert bar.start_date_edit.date() == QDate(2025, 7, 1)
        assert bar.checking_date_edit.date() == QDate(2025, 7, 10)
        assert bar.completion_date_edit.date() == QDate(2025, 7, 12)
        assert bar.isVisible() is True

    def test_set_unit_none_hides_bar(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        assert bar.isVisible() is True
        bar.set_unit(None)
        assert bar.isVisible() is False

    def test_set_unit_resets_dirty(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        bar.pct_spin.setValue(75.0)
        assert bar.is_dirty is True
        bar.set_unit(sample_unit)
        assert bar.is_dirty is False


class TestInlineEditBarDirty:
    def test_pct_change_marks_dirty(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        assert bar.is_dirty is False
        bar.pct_spin.setValue(75.0)
        assert bar.is_dirty is True

    def test_checking_status_change_marks_dirty(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        bar.checking_status_edit.setText("Done")
        assert bar.is_dirty is True

    def test_dirty_changed_signal_on_edit(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        emitted = []
        bar.dirty_changed.connect(lambda val: emitted.append(val))
        bar.pct_spin.setValue(75.0)
        assert len(emitted) == 1
        assert emitted[0] is True

    def test_dirty_changed_signal_on_save(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        bar.pct_spin.setValue(75.0)
        emitted = []
        bar.dirty_changed.connect(lambda val: emitted.append(val))
        bar._on_save()
        assert len(emitted) == 1
        assert emitted[0] is False

    def test_dirty_changed_signal_on_revert(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        bar.pct_spin.setValue(75.0)
        emitted = []
        bar.dirty_changed.connect(lambda val: emitted.append(val))
        bar._on_revert()
        assert len(emitted) == 1
        assert emitted[0] is False


class TestInlineEditBarSave:
    def test_save_emits_signal(self, bar, sample_unit):
        received = []
        bar.unit_saved.connect(lambda u: received.append(u))
        bar.set_unit(sample_unit)
        bar.pct_spin.setValue(75.0)
        bar._on_save()
        assert len(received) == 1

    def test_save_preserves_original_fields(self, bar, sample_unit):
        received = []
        bar.unit_saved.connect(lambda u: received.append(u))
        bar.set_unit(sample_unit)
        bar.pct_spin.setValue(75.0)
        bar.checking_status_edit.setText("Reviewed")
        bar._on_save()
        emitted_unit = received[0]
        assert emitted_unit.com_number == "14201"
        assert emitted_unit.job_name == "Test Job"
        assert emitted_unit.percent_complete == 75.0
        assert emitted_unit.checking_status == "Reviewed"

    def test_save_clears_dirty(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        bar.pct_spin.setValue(75.0)
        assert bar.is_dirty is True
        bar._on_save()
        assert bar.is_dirty is False

    def test_save_no_unit_does_nothing(self, bar):
        bar._on_save()  # should not raise


class TestInlineEditBarRevert:
    def test_revert_resets_fields(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        bar.pct_spin.setValue(75.0)
        bar.checking_status_edit.setText("Changed")
        bar._on_revert()
        assert bar.pct_spin.value() == 50.0
        assert bar.checking_status_edit.text() == "In Progress"
        assert bar.is_dirty is False


class TestInlineEditBarDate:
    def test_save_preserves_dates(self, bar, sample_unit):
        received = []
        bar.unit_saved.connect(lambda u: received.append(u))
        bar.set_unit(sample_unit)
        bar._on_save()
        assert received[0].detailing_due_date == date(2025, 7, 15)
        assert received[0].unit_detailing_start_date == date(2025, 7, 1)
        assert received[0].unit_moved_to_checking_date == date(2025, 7, 10)
        assert received[0].unit_detailing_completion_date == date(2025, 7, 12)


class TestInlineEditBarAutoCalculations:
    def test_pct_change_updates_remaining_demand(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        # dept hours = 40.0. At 50%, remaining = 20.0
        bar.pct_spin.setValue(25.0)  # remaining demand should become 30.0
        assert bar.remaining_demand_spin.value() == 30.0

    def test_iec_change_updates_target_hours(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        # dept hours = 40.0.
        bar.iec_hours_spin.setValue(10.0)  # target hours should become 30.0
        assert bar.target_hours_spin.value() == 30.0

    def test_actual_detail_change_updates_variance(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        # dept hours = 40.0.
        bar.actual_hours_to_detail_spin.setValue(18.5)  # variance should become 21.5
        assert bar.hour_variance_spin.value() == 21.5
