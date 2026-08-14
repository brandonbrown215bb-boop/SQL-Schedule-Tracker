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
    "unassigned": "#6f6f6f",
    "gray": "#6f6f6f",  # darkened for WCAG AA 4.5:1 on bg_tertiary
    "yellow": "#92600a",
    "purple": "#7e3fb0",
    "orange": "#b24e00",  # darkened for WCAG AA 4.5:1 on bg_primary
    "green": "#1a7a4a",
    "red": "#c0392b",
}

EXPECTED_DARK = {
    "unassigned": "#9faec3",
    "gray": "#9faec3",  # lightened for WCAG AA 4.5:1 on bg_tertiary
    "yellow": "#facc15",
    "purple": "#d69aff",  # lightened for WCAG AA 4.5:1 on bg_tertiary
    "orange": "#fb923c",
    "green": "#4ade80",
    "red": "#ff9999",  # lightened for WCAG AA 4.5:1 on bg_tertiary
}

ALL_STATUSES = ["unassigned", "gray", "yellow", "purple", "orange", "green", "red"]


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
        assert label == "Not Started"

    def test_unassigned_light(self):
        hex_color, icon, label = status_style("light", "unassigned")
        assert hex_color == "#6f6f6f"
        assert icon == "⚠"
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


class TestStyleAlertsBtn:
    """Tests for style_alerts_btn dynamic button styling."""

    def test_style_alerts_btn_light_with_alerts(self, qapp):
        from PyQt5.QtWidgets import QPushButton

        from gui.theme import style_alerts_btn

        btn = QPushButton()
        style_alerts_btn(btn, theme_name="light", has_alerts=True, high_contrast=False)
        stylesheet = btn.styleSheet()
        assert "color: #dc2626" in stylesheet
        assert "font-weight: bold" in stylesheet
        assert "background: #f1f5f9" in stylesheet

    def test_style_alerts_btn_light_no_alerts(self, qapp):
        from PyQt5.QtWidgets import QPushButton

        from gui.theme import style_alerts_btn

        btn = QPushButton()
        style_alerts_btn(btn, theme_name="light", has_alerts=False, high_contrast=False)
        stylesheet = btn.styleSheet()
        assert "color: #1e293b" in stylesheet
        assert "font-weight: 500" in stylesheet
        assert "background: #f1f5f9" in stylesheet

    def test_style_alerts_btn_dark_with_alerts(self, qapp):
        from PyQt5.QtWidgets import QPushButton

        from gui.theme import style_alerts_btn

        btn = QPushButton()
        style_alerts_btn(btn, theme_name="dark", has_alerts=True, high_contrast=False)
        stylesheet = btn.styleSheet()
        assert "color: #f87171" in stylesheet
        assert "font-weight: bold" in stylesheet
        assert "background: #334155" in stylesheet

    def test_style_alerts_btn_dark_no_alerts(self, qapp):
        from PyQt5.QtWidgets import QPushButton

        from gui.theme import style_alerts_btn

        btn = QPushButton()
        style_alerts_btn(btn, theme_name="dark", has_alerts=False, high_contrast=False)
        stylesheet = btn.styleSheet()
        assert "color: #f1f5f9" in stylesheet
        assert "font-weight: 500" in stylesheet
        assert "background: #334155" in stylesheet


class TestGetDeptHoursColor:
    """Tests for get_dept_hours_color — dynamic conditional formatting."""

    def test_min_max_identical(self):
        from PyQt5.QtGui import QColor

        from gui.theme import get_dept_hours_color

        # When min_val == max_val, it should return the low hours color (c1)
        bg, fg = get_dept_hours_color("light", 50.0, 100.0, 100.0, cvd_mode="none")
        # For light theme normal, c1 is #e2f0d9 (226, 240, 217)
        assert bg == QColor("#e2f0d9")
        # Brightness is high, so foreground should be dark (#0f172a)
        assert fg == QColor("#0f172a")

    def test_interpolation_bounds(self):
        from PyQt5.QtGui import QColor

        from gui.theme import get_dept_hours_color

        # Min value
        bg_min, _ = get_dept_hours_color("light", 10.0, 10.0, 100.0, cvd_mode="none")
        assert bg_min == QColor("#e2f0d9")

        # Max value
        bg_max, _ = get_dept_hours_color("light", 100.0, 10.0, 100.0, cvd_mode="none")
        assert bg_max == QColor("#c73838")

    def test_interpolation_midpoint(self):
        from PyQt5.QtGui import QColor

        from gui.theme import get_dept_hours_color

        # Midpoint value (55.0 is exactly halfway between 10.0 and 100.0)
        bg_mid, _ = get_dept_hours_color("light", 55.0, 10.0, 100.0, cvd_mode="none")
        # Mid point for light theme normal is #ffeb9c
        assert bg_mid == QColor("#ffeb9c")

    def test_clamping_out_of_bounds(self):
        from PyQt5.QtGui import QColor

        from gui.theme import get_dept_hours_color

        # Below min
        bg_low, _ = get_dept_hours_color("light", 5.0, 10.0, 100.0, cvd_mode="none")
        assert bg_low == QColor("#e2f0d9")

        # Above max
        bg_high, _ = get_dept_hours_color("light", 150.0, 10.0, 100.0, cvd_mode="none")
        assert bg_high == QColor("#c73838")

    def test_cvd_overrides_light(self):
        from PyQt5.QtGui import QColor

        from gui.theme import get_dept_hours_color

        # Deuteranopia min color in light mode: #e0f2f1 (Teal)
        bg, _ = get_dept_hours_color("light", 10.0, 10.0, 100.0, cvd_mode="deuteranopia")
        assert bg == QColor("#e0f2f1")

        # Protanopia min color in light mode: #e3f2fd (Blue)
        bg, _ = get_dept_hours_color("light", 10.0, 10.0, 100.0, cvd_mode="protanopia")
        assert bg == QColor("#e3f2fd")

        # Tritanopia max color in light mode: #880e4f (Dark Raspberry)
        bg, _ = get_dept_hours_color("light", 100.0, 10.0, 100.0, cvd_mode="tritanopia")
        assert bg == QColor("#880e4f")

    def test_cvd_overrides_dark(self):
        from PyQt5.QtGui import QColor

        from gui.theme import get_dept_hours_color

        # Deuteranopia min color in dark mode: #004d40
        bg, _ = get_dept_hours_color("dark", 10.0, 10.0, 100.0, cvd_mode="deuteranopia")
        assert bg == QColor("#004d40")

        # Protanopia max color in dark mode: #7f2d12
        bg, _ = get_dept_hours_color("dark", 100.0, 10.0, 100.0, cvd_mode="protanopia")
        assert bg == QColor("#7f2d12")

    def test_foreground_contrast(self):
        from PyQt5.QtGui import QColor

        from gui.theme import get_dept_hours_color

        # Verify dark background results in white text
        # Dark theme normal c3 is #7f1d1d (Ruby Red) which is dark -> text should be white
        _, fg_dark = get_dept_hours_color("dark", 100.0, 10.0, 100.0, cvd_mode="none")
        assert fg_dark == QColor("#ffffff")

        # Light theme normal c1 is #e2f0d9 (Soft Green) which is light -> text should be dark slate
        _, fg_light = get_dept_hours_color("light", 10.0, 10.0, 100.0, cvd_mode="none")
        assert fg_light == QColor("#0f172a")


class TestApplyThemePopupStyling:
    """Tests that apply_theme sets global QApplication styles for popup dialogs (QMessageBox, QDialog)."""

    def test_apply_theme_dark_sets_app_popup_styles(self, qapp):
        from PyQt5.QtWidgets import QWidget

        from gui.theme import apply_theme

        w = QWidget()
        apply_theme(w, "dark")

        app_ss = qapp.styleSheet()
        assert "QMessageBox" in app_ss
        assert "QDialog" in app_ss
        assert "background-color: #0f172a" in app_ss
        assert "color: #f1f5f9" in app_ss

    def test_apply_theme_light_sets_app_popup_styles(self, qapp):
        from PyQt5.QtWidgets import QWidget

        from gui.theme import apply_theme

        w = QWidget()
        apply_theme(w, "light")

        app_ss = qapp.styleSheet()
        assert "QMessageBox" in app_ss
        assert "background-color: #ffffff" in app_ss
        assert "color: #1e293b" in app_ss


class TestMainWindowThemeInit:
    """Tests that MainWindow._init_theme propagates theme to all panels (including AlertPanel)."""

    def test_dark_mode_init_propagates_to_alert_panel(self, qapp, tmp_path, db_path):
        from gui.main_window import MainWindow, ServiceRegistry

        config = {
            "sqlite_path": str(db_path),
            "ui": {
                "theme": "dark",
                "colorblind_mode": "none",
            },
        }
        config_path = tmp_path / "config.yaml"
        services = ServiceRegistry(config, str(config_path), str(db_path))

        win = MainWindow(services)
        assert win.alert_panel._theme_name == "dark"
        assert win.calendar_panel._theme_name == "dark"
        assert win.list_panel._theme_name == "dark"



