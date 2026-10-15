"""The edit form and inline bar only show "✓ Saved" after the background save succeeds."""

from __future__ import annotations

import pytest

from data.models import Unit
from gui.edit_form import EditForm
from gui.inline_edit_bar import InlineEditBar

DETAILERS = ["— Unassigned —", "Cancelled", "Jackie H"]


def _unit(com: str = "12345") -> Unit:
    return Unit(
        com_number=com,
        job_name="Job",
        contract_number="C1",
        description="Desc",
        detailer="Jackie H",
        checking_status="",
        department_hours=40.0,
        target_department_hours=40.0,
        iec_internal_hours=0.0,
        percent_complete=10.0,
        actual_hours=0.0,
    )


@pytest.fixture
def form(qtbot):
    w = EditForm(DETAILERS)
    qtbot.addWidget(w)
    w.set_unit(_unit())
    return w


@pytest.fixture
def bar(qtbot):
    w = InlineEditBar(DETAILERS)
    qtbot.addWidget(w)
    w.set_unit(_unit())
    return w


def test_edit_form_shows_saving_until_result(form):
    form._on_save()
    assert "Saving" in form.status_label.text()
    assert "✓ Saved" not in form.status_label.text()

    form.show_save_result("12345", True)
    assert "✓ Saved" in form.status_label.text()
    assert not form.is_dirty


def test_edit_form_failure_keeps_edits_dirty(form):
    form._on_save()
    form.show_save_result("12345", False)
    assert "failed" in form.status_label.text()
    assert form.is_dirty


def test_edit_form_ignores_results_for_other_units(form):
    form._on_save()
    form.show_save_result("99999", False)
    assert "Saving" in form.status_label.text()
    assert not form.is_dirty


def test_inline_bar_shows_saving_until_result(bar):
    bar._on_save()
    assert "Saving" in bar.status_label.text()
    assert "✓ Saved" not in bar.status_label.text()
    bar.show_save_result("12345", True)
    assert "✓ Saved" in bar.status_label.text()


def test_inline_bar_failure_marks_dirty(bar):
    bar._on_save()
    bar.show_save_result("12345", False)
    assert "failed" in bar.status_label.text()
    assert bar._dirty
