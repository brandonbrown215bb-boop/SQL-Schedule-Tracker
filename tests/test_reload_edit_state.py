# tests/test_reload_edit_state.py
"""Reloads must not wipe unsaved edits or bypass optimistic locking."""

from dataclasses import replace
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from data.models import Unit
from gui.list_panel import ListPanel
from gui.main_window import MainWindow


def _unit(com: str, updated_at: str = "2026-10-15 08:00:00.000") -> Unit:
    return Unit(
        com_number=com,
        job_name=f"Job {com}",
        contract_number=f"CN-{com}",
        description="O)2 8X8X13",
        detailer="Carl M",
        checking_status="",
        notes="original",
        department_hours=40.0,
        detailing_due_date=date.today() + timedelta(days=20),
        updated_at=updated_at,
    )


def _reloaded(units: list[Unit]) -> list[Unit]:
    """Fresh copies as another user's save + reload would produce."""
    return [replace(u, updated_at="2026-10-15 09:30:00.000") for u in units]


@pytest.fixture
def panel(qapp):
    units = [_unit("1001"), _unit("1002"), _unit("1003")]
    widget = ListPanel(units)
    widget.set_show_inline_edit(True)
    assert widget._select_com("1002")
    return widget


def test_reload_keeps_dirty_inline_edits(panel):
    bar = panel._inline_edit_bar
    bar.notes_edit.setText("half-typed note")
    assert bar.is_dirty

    emitted = []
    panel.unit_selected.connect(emitted.append)
    panel.refresh(_reloaded(panel._model.all_units))

    assert bar.is_dirty
    assert bar.notes_edit.text() == "half-typed note"
    # Still holds the unit it was opened from, so the save hits the lock check.
    assert bar._unit.updated_at == "2026-10-15 08:00:00.000"
    assert panel._get_selected_com() == "1002"
    assert emitted == []


def test_reload_refreshes_clean_inline_bar(panel):
    bar = panel._inline_edit_bar
    assert not bar.is_dirty

    panel.refresh(_reloaded(panel._model.all_units))

    assert bar._unit.com_number == "1002"
    assert bar._unit.updated_at == "2026-10-15 09:30:00.000"


def test_sort_rebuild_keeps_dirty_inline_edits(panel):
    bar = panel._inline_edit_bar
    bar.notes_edit.setText("draft")
    panel._on_header_clicked(0)
    assert bar.is_dirty
    assert bar.notes_edit.text() == "draft"


def _fake_window(current: Unit, dirty: bool) -> MagicMock:
    win = MagicMock()
    win.units = [current]
    win.current_unit = current
    win._form_dirty = dirty
    win.edit_form.current_unit = current
    win._svc.detect_changed_due_dates.return_value = []
    win._pending_reload_count = 0
    win._search_edit.text.return_value = ""
    win.list_panel._inline_edit_bar.isVisible.return_value = False
    return win


def test_reload_while_form_dirty_keeps_original_updated_at(qapp):
    old = _unit("2001")
    win = _fake_window(old, dirty=True)
    new = _reloaded([old])

    MainWindow._on_load_finished(win, new)

    assert win.edit_form.current_unit is old
    assert win.current_unit is old
    win.edit_form.set_unit.assert_not_called()
    level = win._notify.call_args_list[0].args[1]
    assert level == "warning"


def test_reload_while_form_clean_takes_new_unit(qapp):
    old = _unit("2001")
    win = _fake_window(old, dirty=False)
    new = _reloaded([old])

    MainWindow._on_load_finished(win, new)

    assert win.edit_form.current_unit is new[0]
    win.edit_form.set_unit.assert_called_once_with(new[0])
