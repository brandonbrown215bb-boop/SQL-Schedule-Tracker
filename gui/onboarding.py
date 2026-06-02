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

from typing import NamedTuple, Optional

from PyQt5.QtCore import Qt, QTimer, QRect, QRectF, QPoint
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QBrush, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QApplication, QFrame,
)


# ─── Walkthrough Steps ───────────────────────────────────────────────

class WalkthroughStep(NamedTuple):
    widget_name: str        # objectName of the widget to highlight
    title: str              # short heading
    description: str        # 1-sentence explanation
    position: str = "bottom"  # callout position: top, bottom, left, right


ONBOARDING_STEPS: list[WalkthroughStep] = [
    WalkthroughStep(
        widget_name="calendar_panel",
        title="Calendar & List",
        description="Browse units by date (calendar) or see everything sorted by due date (list). Toggle between them with the buttons above.",
        position="bottom",
    ),
    WalkthroughStep(
        widget_name="view_stack",
        title="View Toggle",
        description="Switch between Calendar view and List view. Your preference is saved automatically.",
        position="top",
    ),
    WalkthroughStep(
        widget_name="timeline_panel",
        title="Unit Timeline",
        description="See the selected unit's milestone dates, progress, and status at a glance.",
        position="left",
    ),
    WalkthroughStep(
        widget_name="edit_form",
        title="Edit Form",
        description="Modify any field of the selected unit. Press Ctrl+S or click Save to write changes to SQLite.",
        position="left",
    ),
    WalkthroughStep(
        widget_name="pull_csv_btn",
        title="Import & Refresh",
        description="Import fresh data from a CSV file, or refresh the view from the SQLite database.",
        position="top",
    ),
    WalkthroughStep(
        widget_name="status_bar",
        title="Status Bar",
        description="Messages, sync status, and unit count appear here. The app auto-reloads when the Excel file changes.",
        position="top",
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


def show_onboarding(parent: QWidget, config: dict = None) -> None:
    """Show the onboarding walkthrough overlay."""
    def on_complete():
        if config is not None:
            config.setdefault("ui", {})["onboarding_completed"] = True

    overlay = OnboardingOverlay(parent, ONBOARDING_STEPS, on_complete=on_complete)
    overlay.show()
    overlay.raise_()