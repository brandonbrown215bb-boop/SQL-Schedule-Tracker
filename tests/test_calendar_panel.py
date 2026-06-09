# tests/test_calendar_panel.py
"""Tests for CalendarPanel and EventCalendarWidget — US-006b AC#2.

Verifies that multi-unit dates appear in the event list,
and selecting a date emits the correct unit_selected signal.
"""

from __future__ import annotations

from datetime import date

import pytest
from PyQt5.QtCore import QDate, Qt

from data.models import Unit
from gui.calendar_panel import CalendarPanel

# ── Fixtures ──────────────────────────────────────────────────────────


def _make_unit(com_number: str, job_name: str, due_date: date, status: str = "yellow") -> Unit:
    return Unit(
        com_number=com_number,
        job_name=job_name,
        contract_number=f"CNT-{com_number}",
        description="Test unit",
        detailer="Test Detailer",
        checking_status="",
        status_color=status,
        department_hours=10.0,
        percent_complete=50.0,
        working_days=[0, 1, 2, 3],
        detailing_due_date=due_date,
        build_date=None,
    )


@pytest.fixture
def units_with_shared_due_date():
    """Two units with the same detailing due date."""
    d = date(2099, 7, 15)
    return [
        _make_unit("COM-100", "Alpha Job", d, "yellow"),
        _make_unit("COM-200", "Beta Job", d, "green"),
    ]


@pytest.fixture
def units_with_different_dates():
    """Units on different dates."""
    return [
        _make_unit("COM-100", "Alpha Job", date(2099, 7, 10), "yellow"),
        _make_unit("COM-200", "Beta Job", date(2099, 7, 15), "green"),
        _make_unit("COM-300", "Gamma Job", date(2099, 7, 20), "red"),
    ]


@pytest.fixture
def calendar_panel(units_with_different_dates, qapp):
    panel = CalendarPanel(units=units_with_different_dates)
    yield panel
    panel.deleteLater()


# ── Event list tests ──────────────────────────────────────────────────


class TestMultiUnitDatesAppearInEventList:
    """AC#2: Multi-unit dates appear in the event list."""

    def test_date_with_multiple_units_shows_all(self, units_with_shared_due_date, qapp):
        panel = CalendarPanel(units=units_with_shared_due_date)
        # Simulate clicking the date (units use 2099-07-15)
        qdate = QDate(2099, 7, 15)
        panel._on_date_clicked(qdate)
        assert panel.event_list.count() == 2

    def test_date_with_single_unit_shows_one(self, calendar_panel):
        qdate = QDate(2099, 7, 10)
        calendar_panel._on_date_clicked(qdate)
        assert calendar_panel.event_list.count() == 1

    def test_event_list_shows_com_number_and_job_name(self, units_with_shared_due_date, qapp):
        panel = CalendarPanel(units=units_with_shared_due_date)
        qdate = QDate(2099, 7, 15)
        panel._on_date_clicked(qdate)
        text_0 = panel.event_list.item(0).text()
        text_1 = panel.event_list.item(1).text()
        items_text = {text_0, text_1}
        assert any("COM-100" in t for t in items_text)
        assert any("COM-200" in t for t in items_text)


# ── Signal emission tests ─────────────────────────────────────────────


class TestDateSelectionEmitsCorrectSignal:
    """AC#2: Selecting a date emits the correct unit_selected signal."""

    def test_clicking_event_item_emits_unit(self, calendar_panel):
        qdate = QDate(2099, 7, 10)
        calendar_panel._on_date_clicked(qdate)
        received = []
        calendar_panel.unit_selected.connect(lambda u: received.append(u))
        item = calendar_panel.event_list.item(0)
        calendar_panel._on_event_clicked(item)
        assert len(received) == 1
        assert received[0].com_number == "COM-100"

    def test_units_stored_on_event_items(self, calendar_panel):
        qdate = QDate(2099, 7, 15)
        calendar_panel._on_date_clicked(qdate)
        item = calendar_panel.event_list.item(0)
        unit = item.data(Qt.UserRole)
        assert unit is not None
        assert unit.com_number == "COM-200"
