# tests/test_no_scroll_filter.py
"""Tests for NoScrollEventFilter.

Verifies:
1. QComboBox wheel event ignored when closed.
2. QDoubleSpinBox wheel event ignored and value unchanged.
3. QDateEdit / ClearableDateEdit wheel event ignored and value unchanged.
4. QDoubleSpinBox button symbols set to NoButtons (hidden stepper arrows).
5. QDoubleSpinBox suppresses Up and Down arrow key stepping (manual entry only).
6. Integration with EditForm and InlineEditBar widgets.
"""

from datetime import date

import pytest
from PyQt5.QtCore import QDate, QPoint, QPointF, Qt
from PyQt5.QtGui import QKeyEvent, QWheelEvent
from PyQt5.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.edit_form import ClearableDateEdit, EditForm
from gui.inline_edit_bar import InlineEditBar
from gui.no_scroll_filter import NoScrollEventFilter, install_no_scroll_filter


def _create_wheel_event(delta: int = 120) -> QWheelEvent:
    """Helper to create a standard QWheelEvent."""
    return QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.NoScrollPhase,
        False,
    )


def test_combobox_wheel_ignored(qtbot):
    combo = QComboBox()
    combo.addItems(["Alpha", "Beta", "Gamma"])
    combo.setCurrentIndex(0)

    install_no_scroll_filter(combo)

    event = _create_wheel_event(-120)
    QApplication.sendEvent(combo, event)

    assert combo.currentIndex() == 0, "ComboBox index should not change on wheel scroll when closed"


def test_spinbox_wheel_ignored(qtbot):
    spin = QDoubleSpinBox()
    spin.setValue(10.0)

    install_no_scroll_filter(spin)

    event = _create_wheel_event(120)
    QApplication.sendEvent(spin, event)

    assert spin.value() == 10.0, "SpinBox value should not change on wheel scroll"


def test_spinbox_no_buttons_set(qtbot):
    spin = QDoubleSpinBox()
    assert spin.buttonSymbols() != QAbstractSpinBox.NoButtons

    install_no_scroll_filter(spin)

    assert spin.buttonSymbols() == QAbstractSpinBox.NoButtons, "SpinBox stepper buttons should be set to NoButtons"


def test_spinbox_arrow_keys_suppressed(qtbot):
    spin = QDoubleSpinBox()
    spin.setValue(5.0)

    install_no_scroll_filter(spin)

    # Send Up arrow key
    key_up = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Up, Qt.NoModifier)
    QApplication.sendEvent(spin, key_up)
    assert spin.value() == 5.0, "Up arrow key should not step SpinBox value"

    # Send Down arrow key
    key_down = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Down, Qt.NoModifier)
    QApplication.sendEvent(spin, key_down)
    assert spin.value() == 5.0, "Down arrow key should not step SpinBox value"


def test_date_edit_wheel_ignored(qtbot):
    date_edit = ClearableDateEdit()
    initial_date = QDate(2026, 7, 22)
    date_edit.setDate(initial_date)

    install_no_scroll_filter(date_edit)

    event = _create_wheel_event(120)
    QApplication.sendEvent(date_edit, event)

    assert date_edit.date() == initial_date, "DateEdit date should not change on wheel scroll"


def test_edit_form_no_scroll_integration(qtbot):
    detailers = ["Alice", "Bob"]
    form = EditForm(default_detailers=detailers)
    qtbot.addWidget(form)

    # Check button symbols on numeric fields
    assert form.dept_hours_spin.buttonSymbols() == QAbstractSpinBox.NoButtons
    assert form.target_hours_spin.buttonSymbols() == QAbstractSpinBox.NoButtons
    assert form.iec_hours_spin.buttonSymbols() == QAbstractSpinBox.NoButtons
    assert form.percent_spin.buttonSymbols() == QAbstractSpinBox.NoButtons
    assert form.actual_hours_spin.buttonSymbols() == QAbstractSpinBox.NoButtons

    form.dept_hours_spin.setValue(40.0)

    event = _create_wheel_event(120)
    QApplication.sendEvent(form.dept_hours_spin, event)
    assert form.dept_hours_spin.value() == 40.0, "EditForm spinbox value should remain 40.0"

    key_up = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Up, Qt.NoModifier)
    QApplication.sendEvent(form.dept_hours_spin, key_up)
    assert form.dept_hours_spin.value() == 40.0, "EditForm spinbox value should not increment on Up arrow"


def test_inline_edit_bar_no_scroll_integration(qtbot):
    detailers = ["Alice", "Bob"]
    bar = InlineEditBar(default_detailers=detailers)
    qtbot.addWidget(bar)

    assert bar.pct_spin.buttonSymbols() == QAbstractSpinBox.NoButtons
    assert bar.target_hours_spin.buttonSymbols() == QAbstractSpinBox.NoButtons
    assert bar.iec_hours_spin.buttonSymbols() == QAbstractSpinBox.NoButtons

    bar.pct_spin.setValue(75.0)

    event = _create_wheel_event(120)
    QApplication.sendEvent(bar.pct_spin, event)
    assert bar.pct_spin.value() == 75.0, "InlineEditBar spinbox value should remain 75.0"
