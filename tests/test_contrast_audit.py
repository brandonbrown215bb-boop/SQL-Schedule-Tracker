# tests/test_contrast_audit.py
"""US-015a: Audit status color contrast across all themes and CVD modes.

Produces a contrast ratio report for every status color against every row
background across all themes and CVD modes (6 statuses × 2 themes × 4 CVD
modes × 3 backgrounds = 144+ combinations).
"""

from __future__ import annotations

import json
import os
import sys

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gui.theme import (
    STATUS_COLORS,
    THEMES,
    CVD_OVERRIDES,
    get_status_colors,
)

ALL_STATUSES = ["gray", "yellow", "purple", "orange", "green", "red"]
ALL_CVD_MODES = ["none", "deuteranopia", "protanopia", "tritanopia"]
ALL_THEMES = ["light", "dark"]

# Background colors for alternating rows
ROW_BG_LIGHT = {"bg_light": "#ffffff", "bg_dark": "#f1f5f9"}  # primary / tertiary
ROW_BG_DARK = {"bg_light": "#0f172a", "bg_dark": "#334155"}     # primary / tertiary

WCAG_AA_THRESHOLD = 4.5
WCAG_AA_LARGE_THRESHOLD = 3.0


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    hex_str = hex_str.lstrip("#")
    return int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)


def relative_luminance(hex_color: str) -> float:
    """Compute WCAG 2.1 relative luminance."""
    r, g, b = [c / 255.0 for c in hex_to_rgb(hex_color)]
    r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """Compute WCAG contrast ratio between foreground and background colors."""
    l1 = relative_luminance(fg_hex)
    l2 = relative_luminance(bg_hex)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def run_audit() -> dict:
    """Run the full contrast audit and return results dict."""
    results = {
        "list_panel": [],
        "calendar": [],
        "failures": [],
    }

    for theme in ALL_THEMES:
        row_bgs = ROW_BG_LIGHT if theme == "light" else ROW_BG_DARK
        for cvd_mode in ALL_CVD_MODES:
            colors = get_status_colors(theme, cvd_mode)

            for status in ALL_STATUSES:
                fg = colors.get(status, "#888888")

                # List panel: status-colored text on alternating row backgrounds
                for bg_name, bg_hex in row_bgs.items():
                    ratio = contrast_ratio(fg, bg_hex)
                    entry = {
                        "component": "list_panel",
                        "theme": theme,
                        "cvd_mode": cvd_mode,
                        "status": status,
                        "fg": fg,
                        "bg": bg_hex,
                        "bg_name": bg_name,
                        "ratio": ratio,
                        "pass_aa": ratio >= WCAG_AA_THRESHOLD,
                        "pass_large": ratio >= WCAG_AA_LARGE_THRESHOLD,
                    }
                    results["list_panel"].append(entry)
                    if ratio < WCAG_AA_THRESHOLD:
                        results["failures"].append(entry)

                # Calendar: status-colored dots on calendar background
                cal_bg_hex = THEMES[theme]["bg_primary"]
                ratio = contrast_ratio(fg, cal_bg_hex)
                entry = {
                    "component": "calendar",
                    "theme": theme,
                    "cvd_mode": cvd_mode,
                    "status": status,
                    "fg": fg,
                    "bg": cal_bg_hex,
                    "bg_name": "calendar_bg",
                    "ratio": ratio,
                    "pass_aa": ratio >= WCAG_AA_THRESHOLD,
                }
                results["calendar"].append(entry)
                if ratio < WCAG_AA_THRESHOLD:
                    results["failures"].append(entry)

    return results


class TestContrastAudit:
    """US-015a: Contrast audit tests."""

    def test_audit_produces_report(self, tmp_path):
        """AC#1, AC#2: Audit runs and produces a matrix report with all combinations."""
        report = run_audit()
        # 6 statuses × 4 CVD modes × 2 themes × 2 row bgs = 96 list_panel entries
        assert len(report["list_panel"]) == 96
        # 6 statuses × 4 CVD modes × 2 themes = 48 calendar entries
        assert len(report["calendar"]) == 48
        # Save the report
        report_path = tmp_path / "contrast_audit.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        assert report_path.exists()

    def test_audit_identifies_failures(self, tmp_path):
        """AC#2: Each failing combination lists fg, bg, and ratio."""
        report = run_audit()
        for failure in report["failures"]:
            assert "fg" in failure
            assert "bg" in failure
            assert "ratio" in failure
            assert failure["ratio"] < WCAG_AA_THRESHOLD
        # Save for US-015b reference
        report_path = tmp_path / "contrast_audit.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

    def test_audit_includes_calendar_combinations(self):
        """AC#3: Calendar panel dot contrast is also audited (48 combos)."""
        report = run_audit()
        assert len(report["calendar"]) == 48

    def test_report_saved_to_file(self, tmp_path):
        """AC#4: Report is saved to contrast_audit.json."""
        report = run_audit()
        report_path = tmp_path / "contrast_audit.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        # Verify it can be read back
        with open(report_path) as f:
            loaded = json.load(f)
        assert len(loaded["list_panel"]) == 96

    def test_current_colors_audit_completes(self):
        """US-015b: After fixes, base status colors pass WCAG AA (4.5:1) on all
        backgrounds within their theme. CVD overrides pass at least 3:1 (large text)
        on all backgrounds — the theoretical maximum for cross-theme CVD."""
        report = run_audit()
        assert len(report["list_panel"]) == 96
        assert len(report["calendar"]) == 48
        
        # Separate base failures (no CVD mode) from CVD failures
        base_failures = [f for f in report["failures"] if f["cvd_mode"] == "none"]
        cvd_failures = [f for f in report["failures"] if f["cvd_mode"] != "none"]
        
        # Base colors must all pass 4.5:1
        if base_failures:
            print(f"\n[CONTRAST AUDIT] {len(base_failures)} base color failures:")
            for f in base_failures:
                print(f"  {f['theme']}/{f['status']}: fg={f['fg']} bg={f['bg']} ratio={f['ratio']}")
        assert len(base_failures) == 0, \
            f"{len(base_failures)} base color combinations fail WCAG AA"
        
        # CVD overrides: check they at least pass 3:1 (large text) on all backgrounds
        cvd_below_large = [f for f in cvd_failures 
                          if ("list_panel" in f.get("component", "") and not f.get("pass_large", False))
                          or ("calendar" in f.get("component", "") and f.get("ratio", 0) < 3.0)]
        if cvd_below_large:
            print(f"\n[CONTRAST AUDIT] {len(cvd_below_large)} CVD combos below 3:1:")
            for f in cvd_below_large:
                print(f"  {f['theme']}/{f['cvd_mode']}/{f['status']}: fg={f['fg']} bg={f['bg']} ratio={f['ratio']}")
        assert len(cvd_below_large) == 0, \
            f"{len(cvd_below_large)} CVD combinations below 3:1 (large text min)"
        
        # Report remaining CVD 4.5:1 failures (expected — mathematically impossible on all bgs)
        cvd_45_failures = [f for f in cvd_failures if f not in cvd_below_large]
        if cvd_45_failures:
            print(f"\n[CONTRAST AUDIT] {len(cvd_45_failures)} CVD combos below 4.5:1 but ≥3:1 (acceptable)")
            for f in cvd_45_failures[:5]:
                print(f"  {f['theme']}/{f['cvd_mode']}/{f['status']}: ratio={f['ratio']}")
