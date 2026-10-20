# tests/test_checklist_filter.py
"""Tests for gui/checklist_filter.py — the Excel-style filter dropdown."""

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from PyQt5.QtCore import Qt

from gui.checklist_filter import ChecklistFilterButton, ChecklistPopup, FilterOption

YEARS = [
    FilterOption("2025", "2025", [FilterOption("2025-03", "March"), FilterOption("2025-07", "July")]),
    FilterOption("2026", "2026", [FilterOption("2026-01", "January")]),
]
NAMES = [FilterOption("Jane", "Jane"), FilterOption("Tom", "Tom"), FilterOption("Lee", "Lee")]


def _popup(qtbot, options, selected):
    accepted = []
    popup = ChecklistPopup(options, set(selected), accepted.append)
    qtbot.addWidget(popup)
    return popup, accepted


def _item(popup, label):
    return popup.tree.findItems(label, Qt.MatchExactly | Qt.MatchRecursive)[0]


def test_whole_year_selection_checks_its_months(qtbot):
    popup, _ = _popup(qtbot, YEARS, {"2025"})
    assert _item(popup, "2025").checkState(0) == Qt.Checked
    assert _item(popup, "July").checkState(0) == Qt.Checked
    assert popup.checked_keys() == {"2025"}


def test_some_months_give_a_partial_year(qtbot):
    popup, _ = _popup(qtbot, YEARS, {"2025-07"})
    assert _item(popup, "2025").checkState(0) == Qt.PartiallyChecked
    assert popup.checked_keys() == {"2025-07"}


def test_everything_checked_means_no_filter(qtbot):
    popup, _ = _popup(qtbot, NAMES, set())
    popup._set_visible_checks(Qt.Checked)
    assert popup.checked_keys() == set()


def test_search_limits_select_all_to_matches(qtbot):
    popup, accepted = _popup(qtbot, NAMES, set())
    popup.search_edit.setText("ja")
    assert _item(popup, "Tom").isHidden()
    popup.select_all_btn.click()
    popup.accept()
    assert accepted == [{"Jane"}]


def test_search_finds_months(qtbot):
    popup, _ = _popup(qtbot, YEARS, set())
    popup.search_edit.setText("jul")
    assert not _item(popup, "2025").isHidden()
    assert not _item(popup, "July").isHidden()
    assert _item(popup, "March").isHidden()
    assert _item(popup, "2026").isHidden()


def test_button_text_and_signal(qtbot):
    button = ChecklistFilterButton("Year")
    qtbot.addWidget(button)
    button.set_options(YEARS)
    assert button.text().startswith("Year: All")
    with qtbot.waitSignal(button.selection_changed):
        button._on_popup_accepted({"2025-07"})
    assert button.text().startswith("Year: July 2025")
    assert button.font().bold()
    button.set_selected({"2025", "2026"})
    assert button.text().startswith("Year: 2 selected")


def test_set_selected_is_silent_by_default(qtbot):
    button = ChecklistFilterButton("Detailer")
    qtbot.addWidget(button)
    with qtbot.assertNotEmitted(button.selection_changed):
        button.set_selected({"Jane"})
