"""
gui/onboarding.py — First-launch walkthrough overlay.

Shows a step-by-step highlight of the main UI areas with 1-sentence
explanations. Skippable. Replayable via Help menu.

Usage (in MainWindow.__init__):
    from gui.onboarding import should_show_onboarding, show_onboarding
    if should_show_onboarding(config):
        QTimer.singleShot(500, lambda: show_onboarding(self, self.config))

Usage (in Help menu):
    action = menu.addAction("Show Walkthrough")
    action.triggered.connect(lambda: show_onboarding(self, self.config))
"""

from __future__ import annotations

from typing import NamedTuple

from PyQt5.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# ─── Walkthrough Steps ───────────────────────────────────────────────

class WalkthroughStep(NamedTuple):
    widget_name: str        # objectName of the widget to highlight
    title: str              # short heading
    description: str        # 1-sentence explanation
    position: str = "bottom"  # callout position: top, bottom, left, right


ONBOARDING_STEPS: list[WalkthroughStep] = [
    # ── 1. Calendar & List ───────────────────────────────────────────
    WalkthroughStep(
        widget_name="calendar_panel",
        title="Calendar & List & Alerts",
        description=(
            "Three views for browsing units: Calendar (dates with dots), "
            "List (sortable table with filters), and Alerts (per-detailer "
            "urgency dashboard). Switch via the toggle buttons above."
        ),
        position="bottom",
    ),
    # ── 2. View Toggle ───────────────────────────────────────────────
    WalkthroughStep(
        widget_name="view_stack",
        title="View Toggle Buttons",
        description=(
            "Toggle between Calendar, List, and Alerts views. "
            "Your active view is saved automatically between sessions. "
            "The list view includes COM search, detailer/status/date "
            "filters, and a toggle to show/hide stale units."
        ),
        position="top",
    ),
    # ── 3. Calendar view ─────────────────────────────────────────────
    WalkthroughStep(
        widget_name="calendar_view_btn",
        title="Calendar View",
        description=(
            "The Calendar view shows colored dots on dates with units due. "
            "Click a date to see its units listed below the calendar. "
            "Date-cell dots are color-coded by status (green=done, red=overdue, "
            "yellow=in-progress, purple=ready-for-checking, orange=nearly-done). "
            "Stale units (past due >30 days) are hidden by default."
        ),
        position="top",
    ),
    # ── 4. List view ─────────────────────────────────────────────────
    WalkthroughStep(
        widget_name="list_view_btn",
        title="List View",
        description=(
            "Sortable table of all units with multi-column filtering: "
            "status, detailer, date presets (overdue/today/next 7-30 days/month), "
            "custom date range, COM search, and alert-level filter. "
            "Column widths are resizable. Right-click context menus available. "
            "Press Ctrl+F to jump to the COM search box."
        ),
        position="top",
    ),
    # ── 5. Alerts view ───────────────────────────────────────────────
    WalkthroughStep(
        widget_name="alerts_view_btn",
        title="Alerts View",
        description=(
            "Per-detailer alert dashboard grouping units by urgency: "
            "Overdue (red), Urgent (≤7 days, orange), Approaching (≤14 days, yellow), "
            "On Track (blue/green). Each detailer row shows their assigned units "
            "sorted by alert level, with checking-surge detection and capacity warnings. "
            "Units can be recategorized via tag-based novelty detection."
        ),
        position="top",
    ),
    # ── 6. Timeline panel ────────────────────────────────────────────
    WalkthroughStep(
        widget_name="timeline_panel",
        title="Unit Timeline",
        description=(
            "Horizontal milestone bar chart for the selected unit. "
            "Shows Detailing Start, Moved to Checking, Detailing Complete, "
            "Dept Due (prev), and Detailing Due dates. The bar's fill color "
            "reflects the unit's computed status: green=100%, orange=95-99%, "
            "purple=90-94%, yellow=1-89%, gray=0%, red=overdue/behind-schedule. "
            "Capacity-based logic factors in remaining hours vs. available working days."
        ),
        position="left",
    ),
    # ── 7. Edit form ─────────────────────────────────────────────────
    WalkthroughStep(
        widget_name="edit_form",
        title="Edit Form",
        description=(
            "Modify any field of the selected unit: COM number (read-only), "
            "job name, contract, description, detailer, checking status, notes, "
            "department/target/IEC hours, % complete, actual hours, and 6 date fields. "
            "Press Ctrl+S or click Save to write changes to SQLite. "
            "Saves run in the background; the form stays editable while saving. "
            "Dirty tracking shows unsaved changes. Auto-computed target hours "
            "for primary identical units; non-primary values are read-only."
        ),
        position="left",
    ),
    # ── 8. Theme & Accessibility ──────────────────────────────────────
    WalkthroughStep(
        widget_name="theme_btn",
        title="Theme & Accessibility",
        description=(
            "Toggle between light and dark themes (Ctrl+T). "
            "The adjacent ♿ button opens accessibility settings: "
            "color-blind vision (CVD) modes (protanopia/deuteranopia/tritanopia) "
            "and high-contrast mode. Preference is saved automatically."
        ),
        position="bottom",
    ),
    # ── 9. Automation bar: Import CSV ─────────────────────────────────
    WalkthroughStep(
        widget_name="pull_csv_btn",
        title="Import CSV",
        description=(
            "Import a CSV report from SSRS into the SQLite database. "
            "Opens a file picker; new rows are upserted by COM number. "
            "After import the view automatically refreshes to show the latest data."
        ),
        position="top",
    ),
    # ── 10. Automation bar: Pull SSRS ─────────────────────────────────
    WalkthroughStep(
        widget_name="pull_ssrs_btn",
        title="Pull SSRS (Online Import)",
        description=(
            "Fetch fresh data directly from an SSRS ReportServer endpoint "
            "configured in config.yaml. Supports configurable lookback/lookahead "
            "date ranges. Inserts and updates rows in SQLite, then auto-refreshes."
        ),
        position="top",
    ),
    # ── 11. Automation bar: Refresh ───────────────────────────────────
    WalkthroughStep(
        widget_name="refresh_btn",
        title="Refresh from SQLite",
        description=(
            "Reload all unit data from the SQLite database. "
            "Has a 3-second cooldown to prevent rapid re-triggers. "
            "Press F5 as a keyboard shortcut. Also refreshes automatically "
            "when the database file changes externally (file watcher)."
        ),
        position="top",
    ),
    # ── 12. Automation bar: Export Excel ──────────────────────────────
    WalkthroughStep(
        widget_name="export_btn",
        title="Export to Excel",
        description=(
            "Export the SQLite database contents to the 'Current List' sheet "
            "of an Excel workbook (.xlsm/.xlsx). Reconciles with the shared "
            "workbook used by the detailing team."
        ),
        position="top",
    ),
    # ── 13. Status bar ────────────────────────────────────────────────
    WalkthroughStep(
        widget_name="status_bar",
        title="Status Bar",
        description=(
            "Shows loading progress, save confirmations, unit count, "
            "and sync status messages. The app auto-reloads when the "
            "SQLite database changes externally. If multi-user sync is "
            "enabled, a presence indicator here shows who else is online; "
            "click it for session details."
        ),
        position="top",
    ),
    # ── 14. Help & Reports menus ──────────────────────────────────────
    WalkthroughStep(
        widget_name="menuBar",
        title="Reports & Help Menus",
        description=(
            "The Reports menu opens a Scheduling Dashboard with segmented "
            "bar charts (exportable as PNG) showing status distribution by "
            "detailer, filtered by date range. The Help menu lets you "
            "replay this walkthrough and view the About dialog."
        ),
        position="bottom",
    ),
    # ── 15. Keyboard shortcuts ────────────────────────────────────────
    WalkthroughStep(
        widget_name="left_panel",
        title="Keyboard Shortcuts",
        description=(
            "Ctrl+S = Save current unit, Ctrl+T = Toggle theme, "
            "F5 = Refresh data, Ctrl+F = Focus COM search, "
            "Escape = Clear selection. The list view also supports "
            "arrow-key navigation and context menus."
        ),
        position="bottom",
    ),
]


# ─── Onboarding Overlay ──────────────────────────────────────────────

class OnboardingOverlay(QWidget):
    """Semi-transparent overlay that highlights one widget at a time.

    Covers the entire parent window. Paints a dark mask with a
    transparent "hole" around the target widget, plus a callout bubble.
    """

    def __init__(self, parent: QWidget, steps: list[WalkthroughStep],
                 on_complete=None, on_skip=None):
        super().__init__(parent)
        self.steps = steps
        self.current_step = 0
        self.on_complete = on_complete
        self.on_skip = on_skip

        # Make this widget cover the entire parent
        self.setGeometry(0, 0, parent.width(), parent.height())
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Build the callout UI
        self._target_widget: QWidget | None = None
        self._highlight_rect = QRect()
        self._build_callout()
        # NOTE: _update_highlight() is deferred to showEvent() because
        # QWidget::mapTo() segfaults when called before the widget is shown.

    def _build_callout(self):
        """Create the callout bubble."""
        self.callout = QFrame(self)
        self.callout.setStyleSheet("""
            QFrame {
                background: #1e293b;
                border: 1px solid #475569;
                border-radius: 8px;
            }
        """)
        self.callout.setFixedWidth(320)

        layout = QVBoxLayout(self.callout)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 10, 12, 10)

        # Step indicator (dots)
        self.step_indicator = QLabel()
        self.step_indicator.setAlignment(Qt.AlignCenter)
        self.step_indicator.setStyleSheet("color: #64748b; font-size: 10px;")
        layout.addWidget(self.step_indicator)

        # Title
        self.title_label = QLabel()
        title_font = self.title_label.font()
        title_font.setPointSize(11)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet("color: #f1f5f9;")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        # Description
        self.desc_label = QLabel()
        self.desc_label.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        # Navigation buttons
        nav = QHBoxLayout()
        nav.setSpacing(6)

        self.back_btn = QPushButton("← Back")
        self.back_btn.setStyleSheet(self._btn_secondary_style())
        self.back_btn.clicked.connect(self._go_back)
        nav.addWidget(self.back_btn)

        nav.addStretch()

        self.skip_btn = QPushButton("Skip")
        self.skip_btn.setStyleSheet(self._btn_secondary_style())
        self.skip_btn.clicked.connect(self._skip)
        nav.addWidget(self.skip_btn)

        self.next_btn = QPushButton("Next →")
        self.next_btn.setStyleSheet(self._btn_primary_style())
        self.next_btn.clicked.connect(self._go_next)
        nav.addWidget(self.next_btn)

        layout.addLayout(nav)

        # CSS-based shadow (avoids QGraphicsDropShadowEffect segfaults on Linux)
        self.callout.setStyleSheet("""
            QFrame {
                background: #1e293b;
                border: 1px solid #475569;
                border-radius: 8px;
                margin: 2px;
            }
        """)

    @staticmethod
    def _btn_primary_style() -> str:
        return """
            QPushButton {
                background: #3b82f6; color: white; border: none;
                border-radius: 6px; padding: 5px 14px; font-weight: 500;
            }
            QPushButton:hover { background: #2563eb; }
        """

    @staticmethod
    def _btn_secondary_style() -> str:
        return """
            QPushButton {
                background: transparent; color: #94a3b8; border: 1px solid #475569;
                border-radius: 6px; padding: 5px 12px;
            }
            QPushButton:hover { background: #334155; color: #e2e8f0; }
        """

    def _update_highlight(self):
        """Update the target highlight, callout content, and button state."""
        step = self.steps[self.current_step]

        # Update text
        self.title_label.setText(step.title)
        self.desc_label.setText(step.description)

        # Update step indicator dots
        dots = []
        for i, _ in enumerate(self.steps):
            dots.append("●" if i == self.current_step else "○")
        self.step_indicator.setText("  ".join(dots))

        # Update button state
        self.back_btn.setVisible(self.current_step > 0)
        if self.current_step == len(self.steps) - 1:
            self.next_btn.setText("Done ✓")
        else:
            self.next_btn.setText("Next →")

        # Find target widget by objectName
        target = self.parent().findChild(QWidget, step.widget_name)
        self._target_widget = target

        if target and target.isVisible():
            # Map target geometry to overlay coordinates.
            # mapTo() is safe here because showEvent has already fired.
            tl = self._map_widget_to_overlay(target, QPoint(0, 0))
            br = self._map_widget_to_overlay(
                target, QPoint(target.width(), target.height()))
            self._highlight_rect = QRect(tl, br)

            # Position the callout relative to the target
            self._position_callout(self._highlight_rect, step.position)
        else:
            # Widget not found or hidden (e.g., wrong view) — center the callout
            self._highlight_rect = QRect()
            self._position_centered()

        self.update()  # trigger repaint

    @staticmethod
    def _map_widget_to_overlay(widget, point: QPoint) -> QPoint:
        """Map *point* from *widget*'s local coords to the overlay's coords.

        Uses QWidget.mapTo() which correctly accounts for layout margins,
        spacing, and DPI scaling. Safe to call after showEvent (the overlay
        must be visible/realized).
        """
        # Walk up to the top-level window, then map from widget to window
        # The overlay is a direct child of the window, same as the widget's
        # ancestor chain, so mapTo(window) gives us overlay-relative coords.
        window = widget
        while window.parentWidget() is not None:
            window = window.parentWidget()
        return widget.mapTo(window, point)

    def _position_callout(self, target_rect: QRect, position: str):
        """Position the callout bubble relative to the target widget."""
        padding = 12
        cw, ch = 320, self.callout.sizeHint().height()

        if position == "bottom":
            x = target_rect.center().x() - cw // 2
            y = target_rect.bottom() + padding
        elif position == "top":
            x = target_rect.center().x() - cw // 2
            y = target_rect.top() - ch - padding
        elif position == "right":
            x = target_rect.right() + padding
            y = target_rect.center().y() - ch // 2
        elif position == "left":
            x = target_rect.left() - cw - padding
            y = target_rect.center().y() - ch // 2
        else:
            x = target_rect.center().x() - cw // 2
            y = target_rect.bottom() + padding

        # Clamp to overlay bounds
        x = max(8, min(x, self.width() - cw - 8))
        y = max(8, min(y, self.height() - ch - 8))

        self.callout.setGeometry(x, y, cw, ch)

    def _position_centered(self):
        """Center the callout in the overlay (fallback when target not found)."""
        cw, ch = 320, self.callout.sizeHint().height()
        x = (self.width() - cw) // 2
        y = (self.height() - ch) // 2
        self.callout.setGeometry(x, y, cw, ch)

    def paintEvent(self, event):
        """Paint the dim overlay with a transparent hole around the target."""
        if not self._target_widget or self._highlight_rect.isEmpty():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Full-screen dark mask
        mask = QPainterPath()
        mask.addRect(QRectF(self.rect()))

        # Transparent hole around the target
        hole = QPainterPath()
        padding = 6
        r = QRectF(self._highlight_rect.adjusted(-padding, -padding, padding, padding))
        hole.addRoundedRect(r, 8, 8)

        # Subtract hole from mask
        final = mask.subtracted(hole)

        painter.fillPath(final, QBrush(QColor(0, 0, 0, 140)))

        # Highlight border around target
        painter.setPen(QPen(QColor(96, 165, 250), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(r, 8, 8)

    def _go_next(self):
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            self._update_highlight()
        else:
            self._finish()

    def _go_back(self):
        if self.current_step > 0:
            self.current_step -= 1
            self._update_highlight()

    def _skip(self):
        self._finish()

    def _finish(self):
        """Dismiss the overlay and invoke callbacks."""
        self.hide()
        self.deleteLater()
        if self.on_complete:
            self.on_complete()

    def showEvent(self, event):
        """Defer initial highlight until the widget is fully realized."""
        super().showEvent(event)
        # Use a timer so the widget hierarchy is fully established before mapTo()
        QTimer.singleShot(0, self._update_highlight)

    def resizeEvent(self, event):
        """Re-center when parent resizes."""
        super().resizeEvent(event)
        self.setGeometry(self.parent().rect())
        # Guard: only update highlight after the initial show has completed.
        # During the first show(), resizeEvent fires before mapTo() is safe.
        if self._target_widget is not None or self._highlight_rect.isValid():
            self._update_highlight()


# ─── Public API ──────────────────────────────────────────────────────

def should_show_onboarding(config: dict) -> bool:
    """Check if the walkthrough should be shown."""
    return not config.get("ui", {}).get("onboarding_completed", False)


def show_onboarding(parent: QWidget, config: dict | None = None) -> None:
    """Show the onboarding walkthrough overlay."""
    def on_complete():
        if config is not None:
            config.setdefault("ui", {})["onboarding_completed"] = True

    overlay = OnboardingOverlay(parent, ONBOARDING_STEPS, on_complete=on_complete)
    overlay.show()
    overlay.raise_()
