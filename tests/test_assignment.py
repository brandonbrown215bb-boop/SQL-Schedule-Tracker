"""Right-click "Assign to", Mark as Cancelled confirmation, and batch save reporting."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QMessageBox

from data.models import Unit
from gui.list_panel import ListPanel
from gui.main_window import MainWindow
from services.assignment import assign_detailer, mark_cancelled

TODAY = date(2026, 10, 15)
DETAILERS = ["— Unassigned —", "Cancelled", "Jackie H", "Tommy N"]


def _unit(com: str = "12345", detailer: str = "", start: date | None = None, notes: str = "") -> Unit:
    return Unit(
        com_number=com,
        job_name="Job",
        contract_number="C1",
        description="Desc",
        detailer=detailer,
        checking_status="",
        notes=notes,
        department_hours=40.0,
        target_department_hours=40.0,
        iec_internal_hours=0.0,
        percent_complete=0.0,
        actual_hours=0.0,
        unit_detailing_start_date=start,
    )


# ── Assignment rules ──────────────────────────────────────────────────


def test_assign_unassigned_sets_start_date_without_note():
    original = _unit(detailer="— Unassigned —")
    updated = assign_detailer(original, "Jackie H", TODAY)
    assert updated.detailer == "Jackie H"
    assert updated.unit_detailing_start_date == TODAY
    assert updated.notes == ""
    # The live unit is untouched until the save succeeds
    assert original.detailer == "— Unassigned —"
    assert original.unit_detailing_start_date is None


def test_reassign_resets_start_date_and_appends_note():
    original = _unit(detailer="Jackie H", start=date(2026, 9, 1), notes="Waiting on drawings")
    updated = assign_detailer(original, "Tommy N", TODAY)
    assert updated.detailer == "Tommy N"
    assert updated.unit_detailing_start_date == TODAY
    assert updated.notes == "Waiting on drawings\n10/15/2026: reassigned from Jackie H to Tommy N"
    assert original.notes == "Waiting on drawings"


def test_unassign_clears_start_date_and_notes_it():
    updated = assign_detailer(_unit(detailer="Jackie H", start=date(2026, 9, 1)), "— Unassigned —", TODAY)
    assert updated.detailer == ""
    assert updated.unit_detailing_start_date is None
    assert updated.notes == "10/15/2026: unassigned from Jackie H"


def test_same_detailer_is_a_no_op():
    assert assign_detailer(_unit(detailer="Jackie H"), "Jackie H", TODAY) is None
    assert assign_detailer(_unit(detailer=""), "— Unassigned —", TODAY) is None


def test_mark_cancelled_returns_copy():
    original = _unit(detailer="Jackie H")
    updated = mark_cancelled(original)
    assert (updated.detailer, updated.target_department_hours) == ("Cancelled", 0.0)
    assert original.detailer == "Jackie H"
    assert mark_cancelled(updated) is None


# ── List panel actions ────────────────────────────────────────────────


@pytest.fixture
def panel(qtbot):
    p = ListPanel([], default_detailers=DETAILERS)
    qtbot.addWidget(p)
    return p


def test_assign_units_emits_one_batch(panel):
    units = [_unit("11111", ""), _unit("22222", "Jackie H"), _unit("33333", "Tommy N")]
    received = []
    panel.units_saved.connect(received.append)
    panel._assign_units(units, "Tommy N")
    assert len(received) == 1
    assert [u.com_number for u in received[0]] == ["11111", "22222"]  # 33333 unchanged
    assert all(u.detailer == "Tommy N" for u in received[0])
    assert units[0].detailer == ""  # originals untouched


@pytest.mark.parametrize("answer, expected_batches", [(QMessageBox.No, 0), (QMessageBox.Yes, 1)])
def test_cancel_asks_first(panel, monkeypatch, answer, expected_batches):
    asked = []

    def fake_question(*args, **kwargs):
        asked.append(args[2])
        return answer

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    received = []
    panel.units_saved.connect(received.append)
    units = [_unit("11111", "Jackie H"), _unit("22222", "Cancelled")]
    panel._cancel_units(units)

    assert len(asked) == 1
    assert "11111" in asked[0] and "22222" not in asked[0]  # already-cancelled units skipped
    assert len(received) == expected_batches
    assert units[0].detailer == "Jackie H"  # live unit untouched either way


# ── Batch summary ─────────────────────────────────────────────────────


def _batch_stub(errors, saved):
    calls = SimpleNamespace(notify=[], reloads=0)
    stub = SimpleNamespace(
        _batch_errors=errors,
        _batch_saved=saved,
        _save_queue=[],
        _active_save_worker_running=lambda: False,
        _notify=lambda msg, kind: calls.notify.append((msg, kind)),
        _load_data_async=lambda: setattr(calls, "reloads", calls.reloads + 1),
    )
    return stub, calls


def test_batch_success_gives_one_toast():
    stub, calls = _batch_stub([], 3)
    MainWindow._finish_batch_if_done(stub)
    assert calls.notify == [("Saved 3 units", "success")]
    assert stub._batch_errors is None


def test_batch_failures_give_one_summary(monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: shown.append(a[2])))
    stub, calls = _batch_stub([("11111", "changed by another user"), ("22222", "database is locked")], 5)
    MainWindow._finish_batch_if_done(stub)
    assert len(shown) == 1
    assert "Saved 5 of 7" in shown[0]
    assert "COM 11111: changed by another user" in shown[0]
    assert calls.reloads == 1
    assert stub._batch_errors is None


def test_batch_not_finished_while_queue_has_units():
    stub, calls = _batch_stub([], 1)
    stub._save_queue = [object()]
    MainWindow._finish_batch_if_done(stub)
    assert calls.notify == []
    assert stub._batch_errors == []
