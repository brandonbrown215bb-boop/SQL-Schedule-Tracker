# tests/test_inline_edit_bar.py
"""Tests for gui/inline_edit_bar.py — InlineEditBar widget."""

from datetime import date

import pytest

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
        checking_status="",
        department_hours=40.0,
        target_department_hours=40.0,
        iec_internal_hours=0.0,
        percent_complete=50.0,
        actual_hours=20.0,
        notes="Some notes",
        status_color="yellow",
        detailing_due_date=date(2025, 7, 15),
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
        assert bar.notes_edit.text() == "Some notes"
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
    def test_field_change_marks_dirty(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        assert bar.is_dirty is False
        bar.pct_spin.setValue(75.0)
        assert bar.is_dirty is True

    def test_notes_change_marks_dirty(self, bar, sample_unit):
        bar.set_unit(sample_unit)
        bar.notes_edit.setText("Changed")
        assert bar.is_dirty is True


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
        bar._on_save()
        emitted_unit = received[0]
        assert emitted_unit.com_number == "14201"
        assert emitted_unit.job_name == "Test Job"
        assert emitted_unit.percent_complete == 75.0

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
        bar.notes_edit.setText("Changed")
        bar._on_revert()
        assert bar.pct_spin.value() == 50.0
        assert bar.notes_edit.text() == "Some notes"
        assert bar.is_dirty is False


class TestInlineEditBarDate:
    def test_save_preserves_due_date(self, bar, sample_unit):
        received = []
        bar.unit_saved.connect(lambda u: received.append(u))
        bar.set_unit(sample_unit)
        bar._on_save()
        assert received[0].detailing_due_date == date(2025, 7, 15)
