# gui/no_scroll_filter.py
"""NoScrollEventFilter — disables mouse wheel scrolling and arrow-key stepping on edit controls.

Prevents accidental value changes when scrolling through forms or pressing arrow keys in spinner boxes.
Allows mouse wheel scrolling inside expanded drop-down pick-lists when open.
Hides up/down stepper buttons on numeric spin boxes for clean, manual-entry fields.
"""

from __future__ import annotations

from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDateEdit,
    QWidget,
)


class NoScrollEventFilter(QObject):
    """Event filter that blocks mouse wheel value changes on edit controls and suppresses

    Up/Down arrow keys on spin boxes, allowing wheel events to propagate to parent scroll areas.
    """

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # Check if the target is an edit control
        if isinstance(obj, (QComboBox, QAbstractSpinBox, QDateEdit)):
            # Suppress Up and Down arrow key stepping on spin boxes
            if isinstance(obj, QAbstractSpinBox) and event.type() == QEvent.KeyPress:
                if event.key() in (Qt.Key_Up, Qt.Key_Down):
                    event.accept()
                    return True

            # Intercept Mouse Wheel events
            if event.type() == QEvent.Wheel:
                # If it's a QComboBox with an open/visible drop-down menu, allow popup scrolling
                if isinstance(obj, QComboBox):
                    view = obj.view()
                    if view and view.isVisible():
                        return super().eventFilter(obj, event)

                # Ignore wheel event so it propagates up to parent containers (e.g., QScrollArea)
                event.ignore()
                return True

        return super().eventFilter(obj, event)


_global_no_scroll_filter: NoScrollEventFilter | None = None


def install_no_scroll_filter(target: QObject | None = None) -> NoScrollEventFilter:
    """Install the NoScrollEventFilter on a specific widget, container, or globally on QApplication.

    If target is None, installs globally on QApplication.instance().
    Returns the installed NoScrollEventFilter instance.
    """
    global _global_no_scroll_filter
    if _global_no_scroll_filter is None:
        _global_no_scroll_filter = NoScrollEventFilter()

    app = QApplication.instance()
    if app is not None:
        app.installEventFilter(_global_no_scroll_filter)

    if target is not None and target != app:
        target.installEventFilter(_global_no_scroll_filter)
        if isinstance(target, QAbstractSpinBox):
            target.setButtonSymbols(QAbstractSpinBox.NoButtons)
        if isinstance(target, QWidget):
            for child in target.findChildren((QComboBox, QAbstractSpinBox, QDateEdit)):
                child.installEventFilter(_global_no_scroll_filter)
                if isinstance(child, QAbstractSpinBox):
                    child.setButtonSymbols(QAbstractSpinBox.NoButtons)

    return _global_no_scroll_filter
