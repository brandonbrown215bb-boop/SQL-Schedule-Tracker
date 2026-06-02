"""
gui/close_progress_dialog.py — Modal dialog shown while Excel syncs drain on close.

This dialog is non-cancelable: users must wait for syncs to finish before the
app can close. It displays a heading, an "N updates remaining" subtext, a
determinate QProgressBar, and a footer with an estimated time remaining
(derived from a rolling average of past per-unit write times supplied by
the caller).

The dialog exposes a ``set_state()`` slot and an ``is_idle()`` predicate so
the caller can drive updates from a QTimer and detect when the queue has
fully drained, at which point it can call ``accept()`` to unblock the
application's ``closeEvent``.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


def _format_seconds(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds < 0 or seconds != seconds:  # NaN guard
        return "—"
    if seconds < 1.0:
        return "<1s"
    if seconds < 60:
        return f"{int(round(seconds))}s"
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs}s"


class CloseProgressDialog(QDialog):
    """Modal "Saving updates…" dialog with a live progress bar."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("close_progress_dialog")
        self.setWindowTitle("Saving updates…")
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowCloseButtonHint
        )
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        outer = QVBoxLayout(self)
        outer.setSpacing(10)
        outer.setContentsMargins(20, 20, 20, 20)

        self._heading = QLabel("Saving updates to Excel…")
        self._heading.setObjectName("close_progress_heading")
        heading_font = QFont()
        heading_font.setBold(True)
        heading_font.setPointSize(12)
        self._heading.setFont(heading_font)
        self._heading.setAlignment(Qt.AlignCenter)
        outer.addWidget(self._heading)

        self._remaining_label = QLabel("0 updates remaining")
        self._remaining_label.setObjectName("close_progress_remaining")
        self._remaining_label.setAlignment(Qt.AlignCenter)
        outer.addWidget(self._remaining_label)

        self._bar = QProgressBar()
        self._bar.setObjectName("close_progress_bar")
        self._bar.setRange(0, 1)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setFormat("%v / %m")
        self._bar.setMinimumHeight(20)
        outer.addWidget(self._bar)

        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 0, 0, 0)
        self._eta_label = QLabel("Estimated time remaining: …")
        self._eta_label.setObjectName("close_progress_eta")
        self._eta_label.setAlignment(Qt.AlignCenter)
        footer_row.addWidget(self._eta_label, 1)
        outer.addLayout(footer_row)

        self._last_remaining = 0
        self._last_total = 0
        self._last_avg_seconds = 0.0

    def set_state(self, remaining: int, total: int, avg_seconds: float) -> None:
        """Refresh the dialog with the latest queue state."""
        remaining = max(0, int(remaining))
        total = max(0, int(total))
        avg_seconds = max(0.0, float(avg_seconds))
        self._last_remaining = remaining
        self._last_total = total
        self._last_avg_seconds = avg_seconds

        self._remaining_label.setText(
            f"{remaining} update{'s' if remaining != 1 else ''} remaining"
        )

        if remaining == 0:
            self._bar.setRange(0, 1)
            self._bar.setValue(1)
            self._bar.setFormat("Done")
            self._eta_label.setText("All updates saved — closing…")
            return

        if total <= 0:
            self._bar.setRange(0, 1)
            self._bar.setValue(0)
            self._bar.setFormat("…")
            self._eta_label.setText("Estimated time remaining: …")
            return

        processed = max(0, total - remaining)
        self._bar.setRange(0, total)
        self._bar.setValue(processed)
        pct = int(round((processed / total) * 100))
        self._bar.setFormat(f"{pct}%  ({processed}/{total})")

        if avg_seconds > 0:
            eta = remaining * avg_seconds
        else:
            self._eta_label.setText("Estimated time remaining: …")
            return
        self._eta_label.setText(
            f"Estimated time remaining: ~{_format_seconds(eta)}"
        )

    def is_idle(self) -> bool:
        """Return True when the queue has fully drained."""
        return self._last_remaining <= 0

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Disallow user-initiated close; only programmatic accept() closes us."""
        event.ignore()
