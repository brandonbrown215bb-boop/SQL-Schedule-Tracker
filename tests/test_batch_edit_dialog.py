# tests/test_batch_edit_dialog.py
"""Tests for gui/batch_edit_dialog.py — BatchEditDialog."""

from datetime import date

import pytest

from data.models import Unit
from gui.batch_edit_dialog import BatchEditDialog


@pytest.fixture
def sample_units():
    """Create a list of units for batch editing."""
    return [
        Unit(
            com_number="14201",
            job_name="Job A",
            contract_number="CN-001",
            description="Desc A",
            detailer="Carl M",
            checking_status="",
            department_hours=40.0,
            target_department_hours=40.0,
            iec_internal_hours=0.0,
            percent_complete=50.0,
            actual_hours=20.0,
            status_color="yellow",
            detailing_due_date=date(2025, 7, 15),
        ),
        Unit(
            com_number="14202",
            job_name="Job B",
            contract_number="CN-002",
            description="Desc B",
            detailer="Jackie H",
            checking_status="",
            department_hours=60.0,
            target_department_hours=60.0,
            iec_internal_hours=0.0,
            percent_complete=30.0,
            actual_hours=18.0,
            status_color="gray",
            detailing_due_date=date(2025, 8, 1),
        ),
        Unit(
            com_number="14203",
            job_name="Job C",
            contract_number="CN-003",
            description="Desc C",
            detailer="Tommy N",
            checking_status="",
            department_hours=80.0,
            target_department_hours=80.0,
            iec_internal_hours=0.0,
            percent_complete=75.0,
            actual_hours=60.0,
            status_color="purple",
            detailing_due_date=date(2025, 9, 1),
        ),
    ]


@pytest.fixture
def dialog(qapp, sample_units):
    """Create a BatchEditDialog with sample units."""
    dlg = BatchEditDialog(
        sample_units,
        default_detailers=["— Unassigned —", "Carl M", "Jackie H", "Tommy N", "Brandon B"],
    )
    return dlg


class TestBatchEditDialogCreation:
    def test_dialog_creates(self, dialog):
        assert dialog is not None
        assert "3 units" in dialog.windowTitle()

    def test_progress_bar_hidden_initially(self, dialog):
        assert dialog.progress_bar.isVisible() is False


class TestBatchEditDialogApply:
    def test_no_changes_emits_nothing(self, dialog):
        received = []
        dialog.unit_saved.connect(lambda u: received.append(u))
        dialog._apply()
        assert len(received) == 0

    def test_detailer_change_emits_for_all(self, dialog, sample_units):
        received = []
        dialog.unit_saved.connect(lambda u: received.append(u))
        dialog.detailer_check.setChecked(True)
        dialog.detailer_combo.setCurrentText("Brandon B")
        dialog._apply()
        assert len(received) == 3
        for unit in received:
            assert unit.detailer == "Brandon B"

    def test_percent_change_emits_for_all(self, dialog, sample_units):
        received = []
        dialog.unit_saved.connect(lambda u: received.append(u))
        dialog.pct_check.setChecked(True)
        dialog.pct_spin.setValue(90.0)
        dialog._apply()
        assert len(received) == 3
        for unit in received:
            assert unit.percent_complete == 90.0

    def test_status_change_emits_for_all(self, dialog, sample_units):
        received = []
        dialog.unit_saved.connect(lambda u: received.append(u))
        dialog.status_check.setChecked(True)
        dialog.status_combo.setCurrentText("green")
        dialog._apply()
        assert len(received) == 3
        for unit in received:
            assert unit.status_color == "green"

    def test_multiple_field_changes(self, dialog, sample_units):
        received = []
        dialog.unit_saved.connect(lambda u: received.append(u))
        dialog.detailer_check.setChecked(True)
        dialog.detailer_combo.setCurrentText("Brandon B")
        dialog.pct_check.setChecked(True)
        dialog.pct_spin.setValue(100.0)
        dialog._apply()
        assert len(received) == 3
        for unit in received:
            assert unit.detailer == "Brandon B"
            assert unit.percent_complete == 100.0

    def test_get_updated_units(self, dialog, sample_units):
        dialog.detailer_check.setChecked(True)
        dialog.detailer_combo.setCurrentText("Brandon B")
        dialog._apply()
        updated = dialog.get_updated_units()
        assert len(updated) == 3
