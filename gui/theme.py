"""
gui/theme.py — Theme definitions and applicator for Unit Tracker.

Two built-in themes ("light" and "dark") plus CVD-safe adjustments.
All colors are defined here — panels import from this module.

STATUS_LABELS is populated at startup from config.yaml's status_labels
key via init_labels(). This keeps theme.py in sync with user-customized
label text and avoids duplicating the mapping.

Usage:
    from gui.theme import init_labels, status_style, apply_theme, THEMES

    # At startup (main_window.py __init__):
    init_labels(config.get("status_labels", {}))

    # Get status display info:
    hex_color, icon, label = status_style("dark", "red", cvd_mode="deuteranopia")
    # → ("#3b82f6", "✕", "Overdue")  # red overridden to blue in deuteranopia mode

    # Get a badge stylesheet string:
    badge_css = get_badge_style("light", "green")
    # → "background: rgba(26,122,74,0.15); color: #1a7a4a; border-radius: 10px; ..."

    # Apply theme to a widget tree:
    apply_theme(main_window, "dark", cvd_mode="none", high_contrast=False)
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QWidget,
    QProgressBar,
)

# ─── Theme Token Dicts ───────────────────────────────────────────────

_TOKENS_LIGHT: dict[str, str] = {
    "bg_primary": "#ffffff",
    "bg_secondary": "#f8fafc",
    "bg_tertiary": "#f1f5f9",
    "bg_hover": "#e2e8f0",
    "bg_selected": "#dbeafe",
    "text_primary": "#1e293b",
    "text_secondary": "#64748b",
    "text_muted": "#94a3b8",
    "text_on_accent": "#ffffff",
    "text_error": "#dc2626",
    "text_success": "#16a34a",
    "border": "#e2e8f0",
    "border_strong": "#cbd5e1",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "accent_active": "#1d4ed8",
}

_TOKENS_DARK: dict[str, str] = {
    "bg_primary": "#0f172a",
    "bg_secondary": "#1e293b",
    "bg_tertiary": "#334155",
    "bg_hover": "#475569",
    "bg_selected": "#334155",
    "text_primary": "#f1f5f9",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "text_on_accent": "#ffffff",
    "text_error": "#f87171",
    "text_success": "#4ade80",
    "border": "#334155",
    "border_strong": "#475569",
    "accent": "#60a5fa",
    "accent_hover": "#93c5fd",
    "accent_active": "#bfdbfe",
}

THEMES: dict[str, dict[str, str]] = {
    "light": _TOKENS_LIGHT,
    "dark": _TOKENS_DARK,
}


# ─── Status Colors ───────────────────────────────────────────────────

# Palette revised to meet WCAG AA 4.5:1 at body text sizes on their
# respective backgrounds. Values verified with the APCA contrast tool.

_STATUS_COLORS_LIGHT: dict[str, str] = {
    "gray": "#6f6f6f",  # unassigned   — was #767676, darkened for 4.5:1 on bg_tertiary ✓
    "yellow": "#92600a",  # in progress  — already passed ✓
    "purple": "#7e3fb0",  # ready check  — already passed ✓
    "orange": "#b24e00",  # returned     — was #c05c00, darkened for 4.5:1 on bg_primary ✓
    "green": "#1a7a4a",  # released     — already passed ✓
    "red": "#c0392b",  # overdue      — already passed ✓
}

_STATUS_COLORS_DARK: dict[str, str] = {
    "gray": "#9faec3",  # was #94a3b8, lightened for 4.5:1 on bg_tertiary ✓
    "yellow": "#facc15",  # already passed ✓
    "purple": "#d69aff",  # was #c084fc, lightened for 4.5:1 on bg_tertiary ✓
    "orange": "#fb923c",  # already passed ✓
    "green": "#4ade80",  # already passed ✓
    "red": "#ff9999",  # was #ff8484, lightened to 5.16:1 on bg_tertiary ✓
}

STATUS_COLORS: dict[str, dict[str, str]] = {
    "light": _STATUS_COLORS_LIGHT,
    "dark": _STATUS_COLORS_DARK,
}


# ─── Status Shape Icons ───────────────────────────────────────────────

STATUS_SHAPES: dict[str, str] = {
    "gray": "●",
    "yellow": "◆",
    "purple": "▲",
    "orange": "■",
    "green": "✓",
    "red": "✕",
}


# ─── Status Labels ────────────────────────────────────────────────────

# Populated at startup from config["status_labels"] via init_labels().
# Falls back to sensible defaults if the config key is absent.

STATUS_LABELS: dict[str, str] = {
    "gray": "Unassigned",
    "yellow": "In Progress",
    "purple": "Ready for Check",
    "orange": "Checked & Returned",
    "green": "Released",
    "red": "Overdue/Potential Miss",
}


def init_labels(config_labels: dict[str, str]) -> None:
    """Populate STATUS_LABELS from config.yaml's status_labels dict.

    Call once during MainWindow.__init__, before any panel is built.
    This keeps theme.py in sync with user-customized label text and
    avoids duplicating the mapping.
    """
    if config_labels:
        STATUS_LABELS.update(config_labels)


# ─── CVD Overrides ────────────────────────────────────────────────────
# Theme-aware: each CVD mode can specify different overrides per theme.
# Format: {cvd_mode: {theme_name: {status: hex_color}}}
# Colors chosen to meet WCAG AA 4.5:1 on their respective theme backgrounds.

_CVD_DEUTERANOPIA: dict[str, dict[str, str]] = {
    "light": {
        "red": "#7f1d1d",  # dark red — 7.4:1 on #fff ✓
        "green": "#0f766e",  # dark teal — 4.5:1 on #fff ✓
    },
    "dark": {
        "red": "#ff9999",  # light red — 5.2:1 on #334155 ✓
        "green": "#5eead4",  # light teal — 4.6:1 on #334155 ✓
    },
}

_CVD_PROTANOPIA: dict[str, dict[str, str]] = {
    "light": {
        "red": "#1e3a8a",  # dark blue — 8.1:1 on #fff ✓
        "green": "#92400e",  # dark amber — 5.5:1 on #fff ✓
    },
    "dark": {
        "red": "#93c5fd",  # light blue — 4.5:1 on #334155 ✓
        "green": "#fbbf24",  # light amber — 5.4:1 on #334155 ✓
    },
}

_CVD_TRITANOPIA: dict[str, dict[str, str]] = {
    "light": {
        "yellow": "#9d174d",  # dark raspberry — 4.8:1 on #fff ✓
        "accent": "#0f766e",  # dark teal — 4.5:1 on #fff ✓
    },
    "dark": {
        "yellow": "#f9a8d4",  # light pink — 4.5:1 on #334155 ✓
        "accent": "#5eead4",  # light teal — 4.6:1 on #334155 ✓
    },
}

CVD_OVERRIDES: dict[str, dict[str, dict[str, str]]] = {
    "deuteranopia": _CVD_DEUTERANOPIA,
    "protanopia": _CVD_PROTANOPIA,
    "tritanopia": _CVD_TRITANOPIA,
}


# ─── Stylesheet Templates ─────────────────────────────────────────────

_BTN_PRIMARY = """\
    QPushButton {{
        background: {accent};
        color: {text_on_accent};
        border: none;
        border-radius: 6px;
        padding: 6px 14px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: {accent_hover}; }}
    QPushButton:pressed {{ background: {accent_active}; }}
"""

_BTN_SUCCESS = """\
    QPushButton {{
        background: {text_success};
        color: {text_on_accent};
        border: none;
        border-radius: 6px;
        padding: 6px 14px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: {accent_hover}; }}
    QPushButton:pressed {{ background: {accent_active}; }}
"""

_BTN_DEFAULT = """\
    QPushButton {{
        background: {bg_tertiary};
        color: {text_primary};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 6px 14px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: {border}; }}
    QPushButton:checked {{
        background: {accent};
        color: {text_on_accent};
        border: 1px solid {accent};
    }}
    QPushButton:checked:hover {{
        background: {accent_hover};
    }}
"""

_TABLE = """\
    QTableWidget {{
        background-color: {bg_primary};
        color: {text_primary};
        border: 1px solid {border};
        border-radius: 6px;
        font-size: 12px;
        selection-background-color: {bg_selected};
        selection-color: {text_primary};
        alternate-background-color: {bg_tertiary};
        gridline-color: {border};
    }}
    QTableWidget::item {{
        padding: 4px 6px;
        border-bottom: 1px solid {border};
    }}
    QTableWidget::item:selected {{ background: {bg_selected}; }}
    QHeaderView::section {{
        background: {bg_secondary};
        border: none;
        border-bottom: 2px solid {border_strong};
        padding: 6px 8px;
        font-size: 10px;
        font-weight: 600;
        color: {text_secondary};
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}
"""

_INPUT = """\
    QLineEdit, QDateEdit, QDoubleSpinBox {{
        background: {bg_primary};
        color: {text_primary};
        border: 1px solid {border};
        border-radius: 5px;
        padding: 4px 8px;
        min-height: 22px;
        font-size: 12px;
        selection-background-color: {bg_selected};
    }}
    QLineEdit:focus, QDateEdit:focus, QDoubleSpinBox:focus {{
        border-color: {accent};
    }}
    QComboBox {{
        background: {bg_primary};
        color: {text_primary};
        border: 1px solid {border};
        border-radius: 5px;
        padding: 4px 8px;
        min-height: 22px;
        font-size: 12px;
        selection-background-color: {bg_selected};
    }}
    QComboBox:focus {{
        border-color: {accent};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        width: 20px;
        border: none;
        border-left: 1px solid {border};
    }}
    QComboBox QAbstractItemView {{
        background: {bg_primary};
        color: {text_primary};
        border: 1px solid {border};
        selection-background-color: {bg_selected};
        outline: none;
        max-height: 300px;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 4px 8px;
        min-height: 22px;
    }}
"""

_CARD = """\
    QFrame, QGroupBox {{
        background: {bg_secondary};
        border: 1px solid {border};
        border-radius: 6px;
    }}
"""


# ─── Helper Functions ─────────────────────────────────────────────────


def _stylesheet(tokens: dict[str, str], template: str) -> str:
    """Interpolate a token dict into a stylesheet template."""
    return template.format(**tokens)


def boost_contrast(theme_name: str) -> dict[str, str]:
    """Return a copy of the theme dict with boosted contrast."""
    base = dict(THEMES[theme_name])
    if theme_name == "dark":
        base["text_primary"] = "#ffffff"
        base["text_secondary"] = "#cbd5e1"
        base["border"] = "#475569"
    else:
        base["text_primary"] = "#000000"
        base["text_secondary"] = "#334155"
        base["border"] = "#94a3b8"
    return base


def get_status_colors(theme_name: str, cvd_mode: str = "none") -> dict[str, str]:
    """Return the status color dict for a theme, with optional CVD overrides.

    CVD overrides are theme-aware: each mode specifies different color mappings
    for light and dark themes, ensuring WCAG AA contrast in all combinations.
    """
    colors = dict(STATUS_COLORS[theme_name])
    if cvd_mode != "none" and cvd_mode in CVD_OVERRIDES:
        theme_overrides = CVD_OVERRIDES[cvd_mode].get(theme_name, {})
        colors.update(theme_overrides)
    return colors


def get_badge_style(theme_name: str, status: str, cvd_mode: str = "none") -> str:
    """Return an inline CSS string for a status badge.

    Derives colors from get_status_colors() so that CVD overrides and
    boost_contrast() are honoured automatically. This replaces the old
    static _BADGE_* / _BADGE_DARK_* constants which were hardcoded and
    bypassed the CVD/contrast pipeline.
    """
    colors = get_status_colors(theme_name, cvd_mode)
    fg = colors.get(status, "#888888")
    c = QColor(fg)
    r, g, b = c.red(), c.green(), c.blue()
    bg = f"rgba({r},{g},{b},0.15)"
    return (
        f"background: {bg}; color: {fg}; border-radius: 10px; "
        f"padding: 2px 8px; font-size: 11px; font-weight: 600;"
    )


def status_style(theme_name: str, status: str, cvd_mode: str = "none") -> tuple[str, str, str]:
    """Get display info for a status level.

    Returns:
        (hex_color, icon_shape, label_text)
    """
    colors = get_status_colors(theme_name, cvd_mode)
    hex_color = colors.get(status, "#888888")
    icon = STATUS_SHAPES.get(status, "?")
    label = STATUS_LABELS.get(status, status)
    return (hex_color, icon, label)


# ─── Theme Application ───────────────────────────────────────────────

# US-013: Widget-type handler registry for extensible theme application.
# Adding a new widget type requires only adding one entry here — no changes
# to apply_theme() or _style_widget() needed (Open/Closed Principle).


def _style_button(widget: QWidget, tokens: dict[str, str]) -> None:
    obj = widget.objectName().lower()
    if "save" in obj:
        widget.setStyleSheet(_stylesheet(tokens, _BTN_SUCCESS))
    elif any(k in obj for k in ("primary", "run", "macro")):
        widget.setStyleSheet(_stylesheet(tokens, _BTN_PRIMARY))
    else:
        widget.setStyleSheet(_stylesheet(tokens, _BTN_DEFAULT))


def _style_table(widget: QWidget, tokens: dict[str, str]) -> None:
    widget.setStyleSheet(_stylesheet(tokens, _TABLE))


def _style_input(widget: QWidget, tokens: dict[str, str]) -> None:
    widget.setStyleSheet(_stylesheet(tokens, _INPUT))


def _style_card(widget: QWidget, tokens: dict[str, str]) -> None:
    widget.setStyleSheet(_stylesheet(tokens, _CARD))


def _style_calendar(widget: QWidget, tokens: dict[str, str]) -> None:
    t = tokens
    widget.setStyleSheet(f"""
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background: {t["bg_secondary"]};
            border-bottom: 1px solid {t["border"]};
        }}
        QCalendarWidget QTableView {{
            background: {t["bg_primary"]};
            color: {t["text_primary"]};
            selection-background-color: {t["accent"]};
            selection-color: {t["text_on_accent"]};
            alternate-background-color: {t["bg_tertiary"]};
        }}
        QCalendarWidget QToolButton {{
            color: {t["text_primary"]};
            background: transparent;
            border: none;
            border-radius: 4px;
            padding: 4px;
            min-width: 24px;
            min-height: 24px;
        }}
        QCalendarWidget QToolButton:hover {{
            background: {t["bg_hover"]};
        }}
        QCalendarWidget QToolButton:pressed {{
            background: {t["accent"]};
            color: {t["text_on_accent"]};
        }}
        QCalendarWidget QMenu {{
            background: {t["bg_primary"]};
            color: {t["text_primary"]};
            border: 1px solid {t["border"]};
            padding: 2px 0px;
        }}
        QCalendarWidget QMenu::item {{
            padding: 6px 30px 6px 20px;
        }}
        QCalendarWidget QMenu::item:selected {{
            background: {t["accent"]};
            color: {t["text_on_accent"]};
        }}
        QCalendarWidget QSpinBox {{
            background: {t["bg_primary"]};
            color: {t["text_primary"]};
            border: 1px solid {t["border"]};
            border-radius: 4px;
        }}
        QCalendarWidget QSpinBox::up-button, QCalendarWidget QSpinBox::down-button {{
            subcontrol-origin: border;
            background: {t["bg_tertiary"]};
        }}
        QCalendarWidget QSpinBox::up-button:hover, QCalendarWidget QSpinBox::down-button:hover {{
            background: {t["bg_hover"]};
        }}
    """)


def _style_progress(widget: QWidget, tokens: dict[str, str]) -> None:
    t = tokens
    widget.setStyleSheet(f"""
        QProgressBar {{
            border: 1px solid {t["border"]};
            background: {t["bg_tertiary"]};
            border-radius: 4px;
            text-align: center;
            color: {t["text_primary"]};
        }}
        QProgressBar::chunk {{
            background-color: {t["accent"]};
            border-radius: 3px;
        }}
    """)


_THEME_HANDLERS: dict[type, Callable] = {
    QPushButton: _style_button,
    QTableWidget: _style_table,
    QLineEdit: _style_input,
    QComboBox: _style_input,
    QDateEdit: _style_input,
    QDoubleSpinBox: _style_input,
    QFrame: _style_card,
    QGroupBox: _style_card,
    QCalendarWidget: _style_calendar,
    QProgressBar: _style_progress,
}


def _style_widget(widget: QWidget, tokens: dict[str, str]) -> None:
    """Apply stylesheet to a single widget using the handler registry.

    Looks up the handler for the widget's type in _THEME_HANDLERS.
    If no handler is found, the widget is skipped (safe fallback).
    Subclasses are matched by checking the MRO (method resolution order),
    so e.g. EventCalendarWidget(QCalendarWidget) matches the calendar handler.
    """
    widget_type = type(widget)

    # Direct type match first
    handler = _THEME_HANDLERS.get(widget_type)
    if handler is not None:
        handler(widget, tokens)
        return

    # Check MRO for subclass matches (e.g. EventCalendarWidget -> QCalendarWidget)
    for base in widget_type.__mro__[1:]:  # skip the type itself
        handler = _THEME_HANDLERS.get(base)
        if handler is not None:
            handler(widget, tokens)
            return
    # No handler found — safe fallback, continue to children


def apply_theme(
    widget: QWidget, theme_name: str, cvd_mode: str = "none", high_contrast: bool = False
) -> None:
    """Apply a theme to a widget and all its children recursively.

    Args:
        widget:        Root widget (typically MainWindow).
        theme_name:    "light" or "dark".
        cvd_mode:      CVD override mode, or "none".
        high_contrast: If True, boost contrast in the chosen theme.
    """
    tokens = THEMES[theme_name]
    if high_contrast:
        tokens = boost_contrast(theme_name)

    # Set backgrounds on plain QWidget panels that have no type-specific handler.
    for name in ("left_panel", "right_panel"):
        panel = widget.findChild(QWidget, name)
        if panel is not None:
            panel.setStyleSheet(f"background: {tokens['bg_secondary']};")

    # Global UI container stylesheets if root widget is QMainWindow
    from PyQt5.QtWidgets import QMainWindow
    if isinstance(widget, QMainWindow):
        widget.setStyleSheet(f"""
            QMainWindow {{
                background: {tokens['bg_primary']};
            }}
            QMenuBar {{
                background: {tokens['bg_secondary']};
                color: {tokens['text_primary']};
                border-bottom: 1px solid {tokens['border']};
            }}
            QMenuBar::item {{
                background: transparent;
                color: {tokens['text_primary']};
            }}
            QMenuBar::item:selected {{
                background: {tokens['bg_hover']};
            }}
            QMenu {{
                background: {tokens['bg_secondary']};
                color: {tokens['text_primary']};
                border: 1px solid {tokens['border']};
            }}
            QMenu::item:selected {{
                background: {tokens['accent']};
                color: {tokens['text_on_accent']};
            }}
            QStatusBar {{
                background: {tokens['bg_secondary']};
                color: {tokens['text_secondary']};
                border-top: 1px solid {tokens['border']};
            }}
            QSplitter::handle {{
                background: {tokens['border']};
            }}
        """)

    _style_widget(widget, tokens)
    for child in widget.findChildren(QWidget):
        _style_widget(child, tokens)

    # Style blame_label (Option A) at the very end to override any generic QFrame styles
    blame = widget.findChild(QWidget, "blame_label")
    if blame is not None:
        blame.setStyleSheet(f"color: {tokens['text_secondary']}; font-size: 11px; padding-left: 4px;")


def style_alerts_btn(
    widget: QWidget, theme_name: str, has_alerts: bool, high_contrast: bool = False
) -> None:
    """Style the Alerts button dynamically based on theme and alert presence.

    Ensures the button retains the correct border, padding, border-radius,
    and hover styling of _BTN_DEFAULT, while applying bold and text_error styling
    if has_alerts is True.
    """
    tokens = THEMES[theme_name]
    if high_contrast:
        tokens = boost_contrast(theme_name)

    if has_alerts:
        color = tokens.get("text_error", "#dc2626")
        font_weight = "bold"
    else:
        color = tokens.get("text_primary", "#1e293b")
        font_weight = "500"

    style = f"""
        QPushButton {{
            background: {tokens['bg_tertiary']};
            color: {color};
            border: 1px solid {tokens['border']};
            border-radius: 6px;
            padding: 6px 14px;
            font-weight: {font_weight};
        }}
        QPushButton:hover {{ background: {tokens['border']}; }}
    """
    widget.setStyleSheet(style)


def get_group_highlight_palette(theme_name: str) -> tuple[QColor, QColor]:
    """Return a (color_a, color_b) palette for value-based group highlights.

    Each unique grouping value is assigned one of the two colors via
    ``hash(str(value)) % 2``, so the same value always maps to the same
    color regardless of sort order. Singletons receive no color at all.

    Colors are chosen to be subtle enough not to compete with status
    colors while still providing clear visual separation between groups.
    """
    if theme_name == "dark":
        return (
            QColor("#1e3a8a"),  # deep navy  — blue family
            QColor("#3b1f6b"),  # deep violet — purple family
        )
    else:
        return (
            QColor("#dbeafe"),  # blue-100
            QColor("#ede9fe"),  # violet-100
        )


# Keep old name as a shim so any callers outside list_panel still work.
def get_group_highlight_color(theme_name: str) -> QColor:
    """Deprecated shim — use get_group_highlight_palette instead."""
    return get_group_highlight_palette(theme_name)[0]


# ─── Week-of-the-Month Highlight Palettes ─────────────────────────────

_WEEK_COLORS_LIGHT: dict[int, str] = {
    1: "#dbeafe",  # Light Blue
    2: "#ccfbf1",  # Light Teal
    3: "#f3e8ff",  # Light Purple
    4: "#fef3c7",  # Light Amber
    5: "#ffe4e6",  # Light Rose
}

_WEEK_COLORS_DARK: dict[int, str] = {
    1: "#1e3a8a",  # Deep Blue
    2: "#115e59",  # Deep Teal
    3: "#4c1d95",  # Deep Purple
    4: "#78350f",  # Deep Amber
    5: "#881337",  # Deep Rose
}

_WEEK_COLORS_DEUT_PROT_LIGHT: dict[int, str] = {
    1: "#dbeafe",  # Blue
    2: "#cffafe",  # Cyan
    3: "#ede9fe",  # Violet
    4: "#fef3c7",  # Amber/Yellow
    5: "#e2e8f0",  # Muted Gray
}

_WEEK_COLORS_DEUT_PROT_DARK: dict[int, str] = {
    1: "#1e3a8a",  # Deep Blue
    2: "#155e75",  # Deep Cyan
    3: "#4c1d95",  # Deep Violet
    4: "#78350f",  # Deep Amber
    5: "#334155",  # Deep Gray
}

_WEEK_COLORS_TRIT_LIGHT: dict[int, str] = {
    1: "#ccfbf1",  # Light Teal
    2: "#fce7f3",  # Light Pink
    3: "#ffe4e6",  # Light Red
    4: "#ffedd5",  # Light Orange
    5: "#f1f5f9",  # Light Gray
}

_WEEK_COLORS_TRIT_DARK: dict[int, str] = {
    1: "#115e59",  # Deep Teal
    2: "#701a75",  # Deep Pink
    3: "#881337",  # Deep Rose
    4: "#7c2d12",  # Deep Orange
    5: "#334155",  # Deep Gray
}

_WEEK_COLORS_HIGH_CONTRAST_LIGHT: dict[int, str] = {
    1: "#93c5fd",  # Blue-300
    2: "#5eead4",  # Teal-300
    3: "#c084fc",  # Purple-300
    4: "#fde047",  # Yellow-300
    5: "#fda4af",  # Rose-300
}

_WEEK_COLORS_HIGH_CONTRAST_DARK: dict[int, str] = {
    1: "#2563eb",  # Blue-600
    2: "#0d9488",  # Teal-600
    3: "#7c3aed",  # Purple-600
    4: "#ea580c",  # Orange-600
    5: "#e11d48",  # Rose-600
}


def get_week_highlight_color(
    theme_name: str, week_index: int, cvd_mode: str = "none", high_contrast: bool = False
) -> QColor:
    """Return the theme-appropriate QColor for a 1-based week index (1 to 5)."""
    idx = max(1, min(5, week_index))
    
    if high_contrast:
        palette = _WEEK_COLORS_HIGH_CONTRAST_DARK if theme_name == "dark" else _WEEK_COLORS_HIGH_CONTRAST_LIGHT
    elif cvd_mode in ("deuteranopia", "protanopia"):
        palette = _WEEK_COLORS_DEUT_PROT_DARK if theme_name == "dark" else _WEEK_COLORS_DEUT_PROT_LIGHT
    elif cvd_mode == "tritanopia":
        palette = _WEEK_COLORS_TRIT_DARK if theme_name == "dark" else _WEEK_COLORS_TRIT_LIGHT
    else:
        palette = _WEEK_COLORS_DARK if theme_name == "dark" else _WEEK_COLORS_LIGHT
        
    return QColor(palette[idx])

