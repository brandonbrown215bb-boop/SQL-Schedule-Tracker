"""
gui/sync_status.py — Reusable widget for displaying Excel sync queue progress.

Shows a label like "3 updates remaining" alongside a QProgressBar that advances
as the background worker drains the pending-sync queue. Designed to be embedded
in both the status bar (as a compact badge) and the automation bar (as a wider
inline widget).
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QSizePolicy, QWidget


class SyncStatusWidget(QWidget):
    """A horizontal label + progress bar pair for showing sync queue progress.

    The widget is hidden by default and shown by the MainWindow while a sync
    batch is being processed.  ``set_progress()`` accepts the current remaining
    count and the total (processed + remaining) so the bar can be drawn in
    determinate mode.

    Accessibility: the progress bar's accessible name is updated on every
    ``set_progress()`` call so screen readers announce the current state.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("sync_status_widget")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._label = QLabel("")
        self._label.setObjectName("sync_status_label")
        self._label.setMinimumWidth(140)
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setObjectName("sync_status_bar")
        self._bar.setMinimum(0)
        self._bar.setMaximum(100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)
        self._bar.setFormat("%v / %m")
        self._bar.setMinimumWidth(160)
        # Compact, fits inline in the automation bar
        self._bar.setFixedHeight(14)
        layout.addWidget(self._bar, 1)

        self._last_remaining = 0
        self._last_total = 0
        self.setVisible(False)
        self.setAccessibleName("Sync queue status")

    def set_progress(self, remaining: int | str, total: int) -> None:
        """Refresh the label and progress bar.

        Args:
            remaining: number of units still in the queue (including the
                in-flight worker, if any) or a status message string.
            total: number of units in the current batch (processed + remaining).
                If ``total <= 0`` the bar is reset to 0/0.
        """
        self.setVisible(True)
        try:
            rem_val = int(remaining)
            is_str_msg = False
        except (ValueError, TypeError):
            rem_val = 0
            is_str_msg = True

        if is_str_msg:
            self._label.setText(str(remaining))
            self._bar.setRange(0, 0)
            self._bar.setValue(0)
            self._bar.setFormat("…")
            self.setAccessibleName(str(remaining))
            return

        remaining = max(0, rem_val)
        total = max(0, int(total))
        self._last_remaining = remaining
        self._last_total = total

        if remaining == 0:
            self._label.setText("✓ Synced")
            self._bar.setRange(0, 1)
            self._bar.setValue(1)
            self._bar.setFormat("Done")
            self.setAccessibleName("All updates synced")
            return

        if total <= 0:
            # Nothing to track — show indeterminate-style placeholder
            self._bar.setRange(0, 1)
            self._bar.setValue(0)
            self._bar.setFormat("…")
            self._label.setText(f"{remaining} update{'s' if remaining != 1 else ''} remaining")
            self.setAccessibleName(
                f"Sync in progress: {remaining} update{'s' if remaining != 1 else ''} remaining"
            )
            return

        processed = max(0, total - remaining)
        self._bar.setRange(0, total)
        self._bar.setValue(processed)
        # Custom format: percentage + remaining
        pct = round((processed / total) * 100) if total else 0
        self._bar.setFormat(f"{pct}%  ({processed}/{total})")
        self._label.setText(f"{remaining} update{'s' if remaining != 1 else ''} remaining")
        self.setAccessibleName(
            f"Sync in progress: {remaining} of {total} update{'s' if total != 1 else ''} remaining"
        )

    def reset(self) -> None:
        """Reset internal counters (call when a new batch begins)."""
        self._last_remaining = 0
        self._last_total = 0
        self._bar.setRange(0, 1)
        self._bar.setValue(0)
        self._bar.setFormat("…")
        self._label.setText("")
        self.setVisible(False)

    def remaining(self) -> int:
        """Return the last ``remaining`` value passed to ``set_progress()``."""
        return self._last_remaining

    def total(self) -> int:
        """Return the last ``total`` value passed to ``set_progress()``."""
        return self._last_total
