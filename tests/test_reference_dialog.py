# tests/test_reference_dialog.py
"""Tests for gui/reference_dialog.py — ReferenceDialog."""

import pytest

from gui.reference_dialog import ReferenceDialog


@pytest.fixture
def dialog(qapp):
    """Create a ReferenceDialog instance."""
    dlg = ReferenceDialog(
        parent=None,
        theme_name="light",
        cvd_mode="none",
        high_contrast=False,
    )
    return dlg


class TestReferenceDialog:
    def test_creation(self, dialog):
        assert dialog is not None
        assert dialog.windowTitle() == "Legend & Reference Guide"
        assert dialog.tabs.count() == 3

    def test_tabs_content(self, dialog):
        # Verify the three tabs exist with their names
        assert dialog.tabs.tabText(0) == "🎨 Visual Legend"
        assert dialog.tabs.tabText(1) == "📖 Glossary & Terms"
        assert dialog.tabs.tabText(2) == "⌨ Keyboard Shortcuts"

        # Verify tables are populated
        assert dialog.status_table.rowCount() == 6
        assert dialog.alert_table.rowCount() == 3
        assert dialog.timeline_table.rowCount() == 6
        assert dialog.glossary_table.rowCount() == 6
        assert dialog.shortcuts_table.rowCount() == 9

    def test_theme_update(self, dialog):
        # Switch to dark theme with protanopia CVD mode and high contrast
        dialog.set_theme(theme_name="dark", cvd_mode="protanopia", high_contrast=True)
        assert dialog._theme_name == "dark"
        assert dialog._cvd_mode == "protanopia"
        assert dialog._high_contrast is True

        # Check that rows are populated and styled
        # Green status (complete) is the first row (index 0)
        green_symbol_item = dialog.status_table.item(0, 0)
        assert green_symbol_item is not None
        assert green_symbol_item.text() == "✓"

        # In protanopia dark mode, green is mapped to amber/yellow in CVD overrides:
        # CVD_OVERRIDES["protanopia"]["dark"]["green"] = "#fbbf24"
        from gui.theme import status_style
        hex_color, _, _ = status_style("dark", "green", "protanopia")
        assert hex_color == "#fbbf24"
        assert green_symbol_item.foreground().color().name() == "#fbbf24"
