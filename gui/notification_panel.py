# gui/notification_panel.py
"""NotificationPanel — Toast notification system for transient UI feedback.

Anchored at the bottom-center of the MainWindow. Supports INFO, SUCCESS, WARNING,
and ERROR levels with custom themed styling, slide/fade animations, stacking behavior
(max 3 toasts), and queuing while the LoadingOverlay is active.
"""

from __future__ import annotations

import logging

from PyQt5.QtCore import QPropertyAnimation, Qt, QTimer
from PyQt5.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.theme import THEMES, get_status_colors

logger = logging.getLogger(__name__)


class ToastWidget(QFrame):
    """Individual animated toast frame representing a single notification."""

    def __init__(self, message: str, level: str, theme_name: str, cvd_mode: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ToastWidget")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        symbols = {
            "info": "ℹ️",  # noqa: RUF001
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
        }
        symbol = symbols.get(level.lower(), "ℹ️")  # noqa: RUF001

        self.icon_label = QLabel(symbol)
        self.icon_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.icon_label)

        self.text_label = QLabel(message)
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("background: transparent;")
        layout.addWidget(self.text_label, 1)

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: palette(mid);
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                color: palette(text);
            }
        """)
        self.close_btn.clicked.connect(self.dismiss)
        layout.addWidget(self.close_btn)

        # Style resolution
        tokens = THEMES.get(theme_name, THEMES["light"])
        border_colors = {
            "info": tokens.get("accent", "#3b82f6"),
            "success": tokens.get("text_success", "#16a34a"),
            "warning": get_status_colors(theme_name, cvd_mode).get("yellow", "#eab308"),
            "error": tokens.get("text_error", "#dc2626"),
        }
        border_color = border_colors.get(level.lower(), tokens.get("accent", "#3b82f6"))

        bg = tokens.get("bg_secondary", "#f8fafc")
        border = tokens.get("border", "#e2e8f0")
        text_color = tokens.get("text_primary", "#1e293b")

        self.setStyleSheet(f"""
            #ToastWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-left: 4px solid {border_color};
                border-radius: 6px;
            }}
            QLabel {{
                color: {text_color};
                font-size: 12px;
            }}
        """)

        # Opacity and animation setup
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(250)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.dismiss)
        self.timer.start(4000)

    def dismiss(self):
        self.timer.stop()
        self.fade_anim.stop()

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(250)
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.finished.connect(self._on_fade_out_finished)
        self.fade_anim.start()

    def _on_fade_out_finished(self):
        self.hide()
        parent = self.parent()
        if parent and hasattr(parent, "remove_toast"):
            parent.remove_toast(self)
        self.deleteLater()


class NotificationPanel(QWidget):
    """Floating container for toast alerts. Captures toast geometry and positioning."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(6)

        self._queue: list[tuple[str, str]] = []
        self._toasts: list[ToastWidget] = []
        self._theme_name = "light"
        self._cvd_mode = "none"

        if parent:
            parent.installEventFilter(self)
            self.update_position()

    def eventFilter(self, obj, event) -> bool:
        if obj == self.parent() and event.type() == event.Resize:
            self.update_position()
        return super().eventFilter(obj, event)

    def update_position(self):
        parent = self.parent()
        if parent:
            width = 450
            height = 300
            x = (parent.width() - width) // 2
            y = parent.height() - height - 40
            self.setGeometry(x, y, width, height)

    def set_theme(self, theme_name: str, cvd_mode: str = "none") -> None:
        self._theme_name = theme_name
        self._cvd_mode = cvd_mode

    def show_notification(self, message: str, level: str = "info") -> None:
        main_win = self.window()
        if hasattr(main_win, "loading_overlay") and main_win.loading_overlay is not None and main_win.loading_overlay.isVisible():
            self.queue_notification(message, level)
            return

        toast = ToastWidget(message, level, self._theme_name, self._cvd_mode, self)
        toast.setAttribute(Qt.WA_TransparentForMouseEvents, False)

        self.layout.addWidget(toast)
        self._toasts.append(toast)

        if len(self._toasts) > 3:
            oldest = self._toasts.pop(0)
            oldest.dismiss()

    def queue_notification(self, message: str, level: str = "info") -> None:
        self._queue.append((message, level))

    def flush_queue(self) -> None:
        while self._queue:
            message, level = self._queue.pop(0)
            self.show_notification(message, level)

    def remove_toast(self, toast: ToastWidget) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
