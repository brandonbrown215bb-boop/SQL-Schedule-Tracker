"""
tests/test_close_progress_dialog.py — Unit tests for
gui.close_progress_dialog.CloseProgressDialog.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from PyQt5.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)
except Exception:
    pytest.skip("PyQt5 not available", allow_module_level=True)

from gui.close_progress_dialog import CloseProgressDialog, _format_seconds


class TestFormatSeconds:
    def test_zero(self):
        assert _format_seconds(0) == "<1s"
    def test_subsecond(self):
        assert _format_seconds(0.5) == "<1s"
    def test_seconds(self):
        assert _format_seconds(5) == "5s"
    def test_minutes(self):
        assert _format_seconds(75) == "1m 15s"
    def test_negative(self):
        assert _format_seconds(-3) == "—"
    def test_nan(self):
        assert _format_seconds(float("nan")) == "—"


class TestDialogBasics:
    def test_starts_idle(self, qtbot):
        dlg = CloseProgressDialog()
        qtbot.addWidget(dlg)
        assert dlg.is_idle() is True
        assert "Saving" in dlg.windowTitle()

    def test_close_event_ignored(self, qtbot):
        dlg = CloseProgressDialog()
        qtbot.addWidget(dlg)
        dlg.show()
        dlg.close()
        assert dlg.isVisible()


class TestSetState:
    def test_in_progress(self, qtbot):
        dlg = CloseProgressDialog()
        qtbot.addWidget(dlg)
        dlg.set_state(remaining=3, total=5, avg_seconds=1.5)
        assert dlg.is_idle() is False
        assert "3 update" in dlg._remaining_label.text()
        assert dlg._bar.maximum() == 5
        assert dlg._bar.value() == 2

    def test_eta_calc(self, qtbot):
        dlg = CloseProgressDialog()
        qtbot.addWidget(dlg)
        dlg.set_state(remaining=4, total=10, avg_seconds=5.0)
        assert "20s" in dlg._eta_label.text()

    def test_idle_done(self, qtbot):
        dlg = CloseProgressDialog()
        qtbot.addWidget(dlg)
        dlg.set_state(remaining=0, total=5, avg_seconds=1.0)
        assert dlg.is_idle() is True
        assert dlg._bar.value() == 1

    def test_zero_total_placeholder(self, qtbot):
        dlg = CloseProgressDialog()
        qtbot.addWidget(dlg)
        dlg.set_state(remaining=2, total=0, avg_seconds=0.0)
        assert dlg.is_idle() is False
        assert dlg._bar.value() == 0

    def test_clamps_negative(self, qtbot):
        dlg = CloseProgressDialog()
        qtbot.addWidget(dlg)
        dlg.set_state(remaining=-3, total=-5, avg_seconds=-1.0)
        assert dlg.is_idle() is True

    def test_singular(self, qtbot):
        dlg = CloseProgressDialog()
        qtbot.addWidget(dlg)
        dlg.set_state(remaining=1, total=2, avg_seconds=2.0)
        text = dlg._remaining_label.text()
        assert "1 update " in text

    def test_plural(self, qtbot):
        dlg = CloseProgressDialog()
        qtbot.addWidget(dlg)
        dlg.set_state(remaining=7, total=10, avg_seconds=2.0)
        assert "7 updates" in dlg._remaining_label.text()

    def test_zero_avg_eta_omitted(self, qtbot):
        dlg = CloseProgressDialog()
        qtbot.addWidget(dlg)
        dlg.set_state(remaining=3, total=5, avg_seconds=0.0)
        eta_text = dlg._eta_label.text()
        assert "…" in eta_text or "—" in eta_text

    def test_progress_percent(self, qtbot):
        dlg = CloseProgressDialog()
        qtbot.addWidget(dlg)
        dlg.set_state(remaining=2, total=4, avg_seconds=1.0)
        assert "50%" in dlg._bar.text()
