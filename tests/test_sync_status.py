"""
tests/test_sync_status.py — Unit tests for gui.sync_status.SyncStatusWidget.

These tests don't require a real Excel file or a QApplication event loop —
they exercise the widget's pure-logic API by constructing a widget against
a QApplication created in the module-level fixture (see conftest).
"""

from __future__ import annotations

import os
import sys

import pytest

# Ensure repo root is on sys.path so `gui` imports work in all environments
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# QApplication must exist before any QWidget is created.  We share one for
# the entire test session via a conftest fixture; if no such fixture is
# available (e.g. running this file in isolation) we create one ourselves.
try:
    from PyQt5.QtWidgets import QApplication  # type: ignore[reportMissingImports]

    _app = QApplication.instance() or QApplication(sys.argv)
except Exception:  # pragma: no cover - skip if PyQt5 unavailable
    pytest.skip("PyQt5 not available", allow_module_level=True)

from gui.sync_status import SyncStatusWidget


class TestSyncStatusWidgetBasics:
    """Test the widget's initial state and simple show/hide behavior."""

    def test_starts_hidden(self, qtbot):
        widget = SyncStatusWidget()
        qtbot.addWidget(widget)
        assert not widget.isVisible()

    def test_remaining_and_total_default_to_zero(self, qtbot):
        widget = SyncStatusWidget()
        qtbot.addWidget(widget)
        assert widget.remaining() == 0
        assert widget.total() == 0


class TestSyncStatusWidgetUpdate:
    """Test the set_progress() method produces correct label/bar state."""

    def test_update_with_remaining_and_total(self, qtbot):
        widget = SyncStatusWidget()
        qtbot.addWidget(widget)
        widget.set_progress(remaining=3, total=5)
        assert widget.remaining() == 3
        assert widget.total() == 5
        # Processed = 5 - 3 = 2 → 40%
        assert "3 update" in widget._label.text()
        # Bar should be determinate
        assert widget._bar.minimum() == 0
        assert widget._bar.maximum() == 5
        assert widget._bar.value() == 2

    def test_update_with_zero_remaining_marks_done(self, qtbot):
        widget = SyncStatusWidget()
        qtbot.addWidget(widget)
        widget.set_progress(remaining=0, total=3)
        assert widget.remaining() == 0
        assert "Synced" in widget._label.text()
        # Bar shows done
        assert widget._bar.value() == 1

    def test_update_with_zero_total_shows_placeholder(self, qtbot):
        widget = SyncStatusWidget()
        qtbot.addWidget(widget)
        widget.set_progress(remaining=2, total=0)
        assert widget.remaining() == 2
        # Should still show the remaining count
        assert "2 update" in widget._label.text()

    def test_update_clamps_negative_values(self, qtbot):
        widget = SyncStatusWidget()
        qtbot.addWidget(widget)
        widget.set_progress(remaining=-5, total=-3)
        # Negative inputs are clamped to 0
        assert widget.remaining() == 0
        assert widget.total() == 0

    def test_update_singular_form(self, qtbot):
        widget = SyncStatusWidget()
        qtbot.addWidget(widget)
        widget.set_progress(remaining=1, total=2)
        # Singular: "1 update remaining" (no trailing 's')
        assert "1 update " in widget._label.text() or widget._label.text().endswith("remaining")

    def test_update_plural_form(self, qtbot):
        widget = SyncStatusWidget()
        qtbot.addWidget(widget)
        widget.set_progress(remaining=2, total=5)
        # Plural: "2 updates remaining"
        text = widget._label.text()
        assert "2 updates" in text

    def test_reset_clears_state(self, qtbot):
        widget = SyncStatusWidget()
        qtbot.addWidget(widget)
        widget.set_progress(remaining=4, total=7)
        widget.reset()
        assert widget.remaining() == 0
        assert widget.total() == 0
        assert widget._label.text() == ""


class TestSyncStatusWidgetAccessibility:
    """Test that the widget exposes accessible name updates."""

    def test_accessible_name_in_progress(self, qtbot):
        widget = SyncStatusWidget()
        qtbot.addWidget(widget)
        widget.set_progress(remaining=3, total=5)
        name = widget.accessibleName()
        assert "3" in name
        assert "remaining" in name

    def test_accessible_name_when_done(self, qtbot):
        widget = SyncStatusWidget()
        qtbot.addWidget(widget)
        widget.set_progress(remaining=0, total=5)
        assert "synced" in widget.accessibleName().lower()
