# tests/test_notification_panel.py
"""Tests for gui/notification_panel.py — NotificationPanel and ToastWidget."""

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QMainWindow

from gui.loading_overlay import LoadingOverlay
from gui.notification_panel import NotificationPanel, ToastWidget


class DummyMainWindow(QMainWindow):
    """Dummy MainWindow containing a loading overlay and notification panel."""

    def __init__(self):
        super().__init__()
        self.central = QWidget(self)
        self.setCentralWidget(self.central)
        self.loading_overlay = LoadingOverlay(self.central)
        self.notification_panel = NotificationPanel(self)


@pytest.fixture
def main_win(qapp):
    win = DummyMainWindow()
    win.show()
    return win


class TestToastWidget:
    def test_toast_widget_creation(self, qapp):
        toast = ToastWidget("Hello info", "info", "light", "none")
        assert toast.text_label.text() == "Hello info"
        assert toast.icon_label.text() == "ℹ️"
        toast.timer.stop()  # Clean up timer
        toast.deleteLater()

    def test_toast_widget_colors_by_level(self, qapp):
        toast_success = ToastWidget("Success", "success", "dark", "none")
        assert toast_success.icon_label.text() == "✅"
        toast_success.timer.stop()  # Clean up timer
        toast_success.deleteLater()

        toast_error = ToastWidget("Error", "error", "light", "none")
        assert toast_error.icon_label.text() == "❌"
        toast_error.timer.stop()  # Clean up timer
        toast_error.deleteLater()


class TestNotificationPanel:
    def test_panel_creation(self, main_win):
        panel = main_win.notification_panel
        assert panel is not None
        assert panel.layout.count() == 0

    def test_show_notification(self, main_win):
        panel = main_win.notification_panel
        panel.show_notification("Info Message", "info")

        assert len(panel._toasts) == 1
        toast = panel._toasts[0]
        assert toast.text_label.text() == "Info Message"
        toast.timer.stop()  # Clean up timer

    def test_dismiss_toast_via_close_button(self, main_win, qtbot):
        panel = main_win.notification_panel
        panel.show_notification("Message to close", "info")
        assert len(panel._toasts) == 1
        toast = panel._toasts[0]

        # Simulate close button click
        qtbot.mouseClick(toast.close_btn, Qt.LeftButton)

        # Wait for the fade-out/deletion to complete (anim is 250ms)
        qtbot.wait(400)
        assert len(panel._toasts) == 0

    def test_stacking_limit(self, main_win):
        panel = main_win.notification_panel
        for i in range(5):
            panel.show_notification(f"Message {i}", "info")

        # Verify stacking list is capped at 3
        assert len(panel._toasts) == 3

        # Clean up all active toast timers
        for toast in panel._toasts:
            toast.timer.stop()

    def test_queuing_when_loading_overlay_active(self, main_win):
        panel = main_win.notification_panel
        main_win.loading_overlay.show_with_message("Loading database...")

        # Add notification while loading overlay is visible
        panel.show_notification("Queued Message", "info")

        assert len(panel._toasts) == 0
        assert len(panel._queue) == 1
        assert panel._queue[0] == ("Queued Message", "info")

        # Hide loading overlay synchronously (bypassing the 200ms timer)
        main_win.loading_overlay._do_hide()
        panel.flush_queue()

        # Toast should now be visible
        assert len(panel._queue) == 0
        assert len(panel._toasts) == 1
        assert panel._toasts[0].text_label.text() == "Queued Message"

        # Clean up active toast timers
        for toast in panel._toasts:
            toast.timer.stop()
