"""
gui/loading_overlay.py — Semi-transparent loading spinner overlay.

Appears over the central widget while I/O is in progress.
Disappears when loading finishes or errors.

Usage (in MainWindow):
    self.loading_overlay = LoadingOverlay(self.centralWidget())
    self.loading_overlay.show_with_message("Loading units...")
    # ... async load ...
    self.loading_overlay.hide()

Uses QTimer-based spinner animation — no threading needed.
"""

from __future__ import annotations

import logging
import time as _time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


class LoadingOverlay(QWidget):
    """Semi-transparent overlay with a spinning indicator and message."""

    SPINNER_RADIUS = 16
    SPINNER_WIDTH = 4
    SPINNER_SEGMENTS = 8  # number of arc positions
    _MIN_VISIBLE_MS = 200  # minimum display time to avoid flicker

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setVisible(False)

        # Center layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # Message label
        self._label = QLabel("Loading...")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("""
            QLabel {
                color: #3b82f6;
                font-size: 14px;
                font-weight: 600;
                background: transparent;
                padding: 4px 12px;
            }
        """)
        layout.addWidget(self._label)

        # Spinner animation state
        self._angle: float = 0.0  # current rotation in degrees
        self._spinner_timer: QTimer | None = None
        self._show_timestamp: float = 0.0

    def show_with_message(self, message: str = "Loading...") -> None:
        """Show the overlay and start the spinner animation."""
        self._label.setText(message)
        parent = self.parent()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self._show_timestamp = _time.monotonic()

        # Start spinner animation (30fps)
        if self._spinner_timer is None:
            self._spinner_timer = QTimer(self)
            self._spinner_timer.setInterval(33)  # ~30fps
            self._spinner_timer.timeout.connect(self._advance_spinner)
        self._angle = 0.0
        self._spinner_timer.start()

    def hide(self) -> None:
        """Hide the overlay, respecting minimum visible time."""
        elapsed_ms = (_time.monotonic() - self._show_timestamp) * 1000
        if elapsed_ms < self._MIN_VISIBLE_MS:
            # Delay hide via timer so the overlay is visible long enough
            QTimer.singleShot(int(self._MIN_VISIBLE_MS - elapsed_ms), self._do_hide)
        else:
            self._do_hide()

    def _do_hide(self) -> None:
        """Actually hide the overlay and stop the spinner."""
        if self._spinner_timer and self._spinner_timer.isActive():
            self._spinner_timer.stop()
        super().hide()

    def _advance_spinner(self) -> None:
        """Advance the spinner by one frame."""
        self._angle = (self._angle + 30) % 360  # 30 per frame = 360 in ~0.33s
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        try:
            if not self.isVisible():
                return

            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Dark opaque backdrop (avoids WA_TranslucentBackground segfaults on Linux)
            painter.fillRect(self.rect(), QColor(30, 30, 40, 220))

            # Draw spinner
            center = self.rect().center()
            cx, cy = center.x(), center.y() - 20  # slightly above label

            for i in range(self.SPINNER_SEGMENTS):
                segment_angle = self._angle + (360.0 / self.SPINNER_SEGMENTS) * i
                alpha = int(255 * (i / self.SPINNER_SEGMENTS))  # fade towards end
                painter.setPen(QPen(QColor(59, 130, 246, alpha), self.SPINNER_WIDTH))
                painter.setBrush(Qt.NoBrush)

                # Draw an arc for this segment
                start_angle = int(segment_angle * 16)  # Qt uses 1/16th degrees
                span_angle = int((360.0 / self.SPINNER_SEGMENTS) * 16)
                painter.drawArc(
                    cx - self.SPINNER_RADIUS,
                    cy - self.SPINNER_RADIUS,
                    self.SPINNER_RADIUS * 2,
                    self.SPINNER_RADIUS * 2,
                    start_angle,
                    span_angle,
                )

            painter.end()
        except Exception:
            logger.exception("LoadingOverlay paint error")  # Log instead of silent pass

    def resizeEvent(self, event) -> None:
        """Re-cover the parent when resized."""
        super().resizeEvent(event)
        parent = self.parent()
        if parent is not None:
            self.setGeometry(parent.rect())
