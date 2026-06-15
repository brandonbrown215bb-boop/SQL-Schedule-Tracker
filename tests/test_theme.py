# tests/test_theme.py
"""Tests for Theme status color mapping — US-006b AC#3.

Verifies that each status (green, yellow, red, gray, purple, orange)
maps to the correct color hex code in both light and dark themes.
"""

from __future__ import annotations

import pytest

from gui.theme import get_status_colors, status_style

# ── Expected color values from theme.py ──────────────────────────────

EXPECTED_LIGHT = {
    "gray": "#6f6f6f",  # darkened for WCAG AA 4.5:1 on bg_tertiary
    "yellow": "#92600a",
    "purple": "#7e3fb0",
    "orange": "#b24e00",  # darkened for WCAG AA 4.5:1 on bg_primary
    "green": "#1a7a4a",
    "red": "#c0392b",
}

EXPECTED_DARK = {
    "gray": "#9faec3",  # lightened for WCAG AA 4.5:1 on bg_tertiary
    "yellow": "#facc15",
    "purple": "#d69aff",  # lightened for WCAG AA 4.5:1 on bg_tertiary
    "orange": "#fb923c",
    "green": "#4ade80",
    "red": "#ff9999",  # lightened for WCAG AA 4.5:1 on bg_tertiary
}

ALL_STATUSES = ["gray", "yellow", "purple", "orange", "green", "red"]


class TestStatusColorsLight:
    """AC#3: Each status maps to correct hex in light theme."""

    @pytest.mark.parametrize("status,expected", EXPECTED_LIGHT.items())
    def test_light_status_color(self, status, expected):
        colors = get_status_colors("light")
        assert colors[status] == expected, (
            f"Light {status}: got {colors[status]}, expected {expected}"
        )


class TestStatusColorsDark:
    """AC#3: Each status maps to correct hex in dark theme."""

    @pytest.mark.parametrize("status,expected", EXPECTED_DARK.items())
    def test_dark_status_color(self, status, expected):
        colors = get_status_colors("dark")
        assert colors[status] == expected, (
            f"Dark {status}: got {colors[status]}, expected {expected}"
        )


class TestStatusStyleReturnsCorrectTuple:
    """status_style returns (hex_color, icon_shape, label_text)."""

    def test_green_light(self):
        hex_color, icon, label = status_style("light", "green")
        assert hex_color == "#1a7a4a"
        assert icon == "✓"
        assert label == "Released"

    def test_red_dark(self):
        hex_color, icon, label = status_style("dark", "red")
        assert hex_color == "#ff9999"
        assert icon == "✕"
        assert label == "Overdue/Potential Miss"

    def test_gray_light(self):
        hex_color, icon, label = status_style("light", "gray")
        assert hex_color == "#6f6f6f"
        assert icon == "●"
        assert label == "Unassigned"

    def test_all_statuses_return_three_tuple(self):
        for theme in ("light", "dark"):
            for status in ALL_STATUSES:
                result = status_style(theme, status)
                assert len(result) == 3, f"{theme}/{status}: expected 3-tuple, got {result}"
                hex_color, icon, label = result
                assert isinstance(hex_color, str) and hex_color.startswith("#")
                assert isinstance(icon, str) and len(icon) > 0
                assert isinstance(label, str) and len(label) > 0


class TestCVDOverrides:
    """CVD mode overrides — theme-aware (different colors per theme)."""

    def test_deuteranopia_light_overrides(self):
        colors = get_status_colors("light", cvd_mode="deuteranopia")
        assert colors["red"] == "#7f1d1d"
        assert colors["green"] == "#0f766e"

    def test_deuteranopia_dark_overrides(self):
        colors = get_status_colors("dark", cvd_mode="deuteranopia")
        assert colors["red"] == "#ff9999"
        assert colors["green"] == "#5eead4"

    def test_protanopia_light_overrides(self):
        colors = get_status_colors("light", cvd_mode="protanopia")
        assert colors["red"] == "#1e3a8a"
        assert colors["green"] == "#92400e"

    def test_protanopia_dark_overrides(self):
        colors = get_status_colors("dark", cvd_mode="protanopia")
        assert colors["red"] == "#93c5fd"
        assert colors["green"] == "#fbbf24"

    def test_tritanopia_light_overrides(self):
        colors = get_status_colors("light", cvd_mode="tritanopia")
        assert colors["yellow"] == "#9d174d"

    def test_tritanopia_dark_overrides(self):
        colors = get_status_colors("dark", cvd_mode="tritanopia")
        assert colors["yellow"] == "#f9a8d4"

    def test_no_cvd_mode_preserves_defaults(self):
        colors = get_status_colors("light", cvd_mode="none")
        assert colors == EXPECTED_LIGHT
