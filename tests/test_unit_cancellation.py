# tests/test_unit_cancellation.py
"""Tests for production unit cancellation feature."""

from datetime import date, timedelta

from PyQt5.QtCore import QDate

from data.models import Unit
from gui.alert_panel import AlertPanel
from gui.batch_edit_dialog import BatchEditDialog
from gui.calendar_panel import EventCalendarWidget
from gui.list_panel import UnitListModel
from services.pre_save_hooks import target_hours_hook


def test_unit_is_cancelled_property():
    u1 = Unit(com_number="101", job_name="Job 1", contract_number="C1", description="D1", detailer="Cancelled", checking_status="")
    u2 = Unit(com_number="102", job_name="Job 2", contract_number="C2", description="D2", detailer="Jackie H", checking_status="")

    assert u1.is_cancelled is True
    assert u2.is_cancelled is False


def test_cancelled_unit_is_not_stale():
    past_due = date.today() - timedelta(days=60)
    u_cancelled = Unit(
        com_number="101",
        job_name="Job 1",
        contract_number="C1",
        description="D1",
        detailer="Cancelled",
        checking_status="",
        detailing_due_date=past_due,
    )
    u_active = Unit(
        com_number="102",
        job_name="Job 2",
        contract_number="C2",
        description="D2",
        detailer="Jackie H",
        checking_status="",
        detailing_due_date=past_due,
    )

    assert u_cancelled.is_stale is False
    assert u_active.is_stale is True


def test_target_hours_hook_zeros_cancelled_unit_target():
    unit = Unit(
        com_number="101",
        job_name="Job 1",
        contract_number="C1",
        description="D1",
        detailer="Cancelled",
        checking_status="",
        department_hours=40.0,
        target_department_hours=40.0,
        iec_internal_hours=5.0,
    )

    target_hours_hook(unit, {})
    assert unit.target_department_hours == 0.0
    assert unit.department_hours == 40.0  # Preserved as historical data


def test_restoring_detailer_recalculates_target_hours():
    unit = Unit(
        com_number="101",
        job_name="Job 1",
        contract_number="C1",
        description="D1",
        detailer="Jackie H",
        checking_status="",
        department_hours=40.0,
        target_department_hours=0.0,
        iec_internal_hours=5.0,
    )

    target_hours_hook(unit, {})
    assert unit.target_department_hours == 35.0


def test_alert_panel_excludes_cancelled_units(qtbot):
    u1 = Unit(com_number="101", job_name="Job 1", contract_number="C1", description="D1", detailer="Jackie H", checking_status="", detailing_due_date=date.today() - timedelta(days=2))
    u_cancelled = Unit(com_number="102", job_name="Job 2", contract_number="C2", description="D2", detailer="Cancelled", checking_status="", detailing_due_date=date.today() - timedelta(days=2))

    panel = AlertPanel([u1, u_cancelled])
    panel.show()
    qtbot.addWidget(panel)

    panel.refresh()
    # Alert list should only contain u1
    assert len(panel._filtered_units) == 1
    assert panel._filtered_units[0].com_number == "101"


def test_list_model_cancelled_filtering():
    u1 = Unit(com_number="101", job_name="Job 1", contract_number="C1", description="D1", detailer="Jackie H", checking_status="")
    u_cancelled = Unit(com_number="102", job_name="Job 2", contract_number="C2", description="D2", detailer="Cancelled", checking_status="")

    model = UnitListModel([u1, u_cancelled])

    # Default (show_cancelled = False): cancelled excluded
    model.apply_filters(show_cancelled=False)
    assert len(model.filtered_units) == 1
    assert model.filtered_units[0].com_number == "101"

    # With show_cancelled = True: cancelled included
    model.apply_filters(show_cancelled=True)
    assert len(model.filtered_units) == 2

    # With detailer filter = "Cancelled": cancelled included even if show_cancelled=False
    model.apply_filters(detailer="Cancelled", show_cancelled=False)
    assert len(model.filtered_units) == 1
    assert model.filtered_units[0].com_number == "102"


def test_calendar_widget_cancelled_filtering():
    today = date.today()
    u1 = Unit(com_number="101", job_name="Job 1", contract_number="C1", description="D1", detailer="Jackie H", checking_status="", detailing_due_date=today)
    u_cancelled = Unit(com_number="102", job_name="Job 2", contract_number="C2", description="D2", detailer="Cancelled", checking_status="", detailing_due_date=today)

    cal = EventCalendarWidget()

    # Default (show_cancelled = False)
    cal.set_show_cancelled(False)
    cal.set_events([u1, u_cancelled])
    qtoday = QDate(today.year, today.month, today.day)
    assert len(cal.events_by_date[qtoday]) == 1
    assert cal.events_by_date[qtoday][0].com_number == "101"

    # Show cancelled = True
    cal.set_show_cancelled(True)
    cal.set_events([u1, u_cancelled])
    assert len(cal.events_by_date[qtoday]) == 2


def test_batch_edit_dialog_cancel_units(qtbot):
    u1 = Unit(com_number="101", job_name="Job 1", contract_number="C1", description="D1", detailer="Jackie H", checking_status="", department_hours=20.0, target_department_hours=20.0)
    u2 = Unit(com_number="102", job_name="Job 2", contract_number="C2", description="D2", detailer="Tommy N", checking_status="", department_hours=30.0, target_department_hours=30.0)

    dlg = BatchEditDialog([u1, u2], ["— Unassigned —", "Cancelled", "Jackie H", "Tommy N"])
    qtbot.addWidget(dlg)

    # Check detailer and select Cancelled
    dlg.detailer_check.setChecked(True)
    idx = dlg.detailer_combo.findText("Cancelled")
    assert idx >= 0
    dlg.detailer_combo.setCurrentIndex(idx)

    dlg._apply()

    assert u1.detailer == "Cancelled"
    assert u1.target_department_hours == 0.0
    assert u2.detailer == "Cancelled"
    assert u2.target_department_hours == 0.0
