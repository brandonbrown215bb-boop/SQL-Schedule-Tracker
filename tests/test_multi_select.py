"""Multi-row selection in the list: Ctrl/Shift-click, sorting and reloads keep it intact."""

from __future__ import annotations

from datetime import date

import pytest
from PyQt5.QtCore import Qt

from data.models import Unit
from gui.list_panel import ListPanel


def _unit(com: str, job: str, due: date) -> Unit:
    return Unit(
        com_number=com,
        job_name=job,
        contract_number="C1",
        description="Desc",
        detailer="Jackie H",
        checking_status="",
        department_hours=40.0,
        target_department_hours=40.0,
        iec_internal_hours=0.0,
        percent_complete=10.0,
        actual_hours=0.0,
        detailing_due_date=due,
    )


UNITS = [
    _unit("11111", "Delta", date(2026, 11, 1)),
    _unit("22222", "Alpha", date(2026, 11, 4)),
    _unit("33333", "Charlie", date(2026, 11, 2)),
    _unit("44444", "Bravo", date(2026, 11, 3)),
]


@pytest.fixture
def panel(qtbot):
    p = ListPanel(list(UNITS), default_detailers=["— Unassigned —", "Cancelled", "Jackie H"])
    qtbot.addWidget(p)
    p.show()
    qtbot.waitExposed(p)
    return p


def _click_row(qtbot, panel, com: str, modifier=Qt.NoModifier):
    row = panel._row_for_com(com)
    rect = panel.table.visualItemRect(panel.table.item(row, 0))
    qtbot.mouseClick(panel.table.viewport(), Qt.LeftButton, modifier, rect.center())


def _selected(panel) -> set[str]:
    return {u.com_number for u in panel._get_selected_units()}


def test_ctrl_click_builds_selection_in_any_sort_order(qtbot, panel):
    for _ in range(2):  # ascending and descending
        _click_row(qtbot, panel, "33333")
        _click_row(qtbot, panel, "11111", Qt.ControlModifier)
        _click_row(qtbot, panel, "44444", Qt.ControlModifier)
        assert _selected(panel) == {"11111", "33333", "44444"}
        job_col = panel._model.visible_columns.index("job_name")
        panel._on_header_clicked(job_col)


def test_current_unit_is_last_clicked(qtbot, panel):
    _click_row(qtbot, panel, "33333")
    _click_row(qtbot, panel, "22222", Qt.ControlModifier)
    assert panel._get_selected_unit().com_number == "22222"


def test_sorting_keeps_whole_selection(qtbot, panel):
    _click_row(qtbot, panel, "11111")
    _click_row(qtbot, panel, "22222", Qt.ControlModifier)
    _click_row(qtbot, panel, "44444", Qt.ControlModifier)

    job_col = panel._model.visible_columns.index("job_name")
    panel._on_header_clicked(job_col)
    assert _selected(panel) == {"11111", "22222", "44444"}
    assert panel._get_selected_unit().com_number == "44444"
    assert panel._selection_label.isVisibleTo(panel)
    assert "3 units selected" in panel._selection_label.text()


def test_reload_keeps_selection_of_remaining_units(qtbot, panel):
    _click_row(qtbot, panel, "11111")
    _click_row(qtbot, panel, "33333", Qt.ControlModifier)
    # Reload with fresh objects, one of the selected units gone
    panel.refresh([_unit(u.com_number, u.job_name, u.detailing_due_date) for u in UNITS if u.com_number != "11111"])
    assert _selected(panel) == {"33333"}


def test_plain_click_collapses_to_one_row(qtbot, panel):
    _click_row(qtbot, panel, "11111")
    _click_row(qtbot, panel, "22222", Qt.ControlModifier)
    _click_row(qtbot, panel, "33333")
    assert _selected(panel) == {"33333"}
    assert not panel._selection_label.isVisibleTo(panel)
