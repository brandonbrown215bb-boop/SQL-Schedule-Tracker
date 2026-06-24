# gui/inline_edit_bar.py
"""InlineEditBar — compact editing bar for quick edits in the list panel.

Appears between the filter group and the table when a row is selected
(repositioned from below the table on selection).
Shows the most commonly edited fields: detailer, due date, % complete, notes.
Emits unit_saved(Unit) on save, which routes through the existing SaveWorker pipeline.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from data.models import Unit
from gui.edit_form import ClearableDateEdit


class InlineEditBar(QWidget):
    """Compact horizontal editing bar for quick unit edits.

    Fields: COM (read-only), Detailer, Due Date, % Complete, Notes.
    Save/Revert buttons. Enter in any field triggers save.
    Escape reverts if dirty.

    Signals:
        unit_saved(Unit): Emitted when user saves. Routes through MainWindow.on_save_unit().
    """

    unit_saved = pyqtSignal(object)  # Unit
    dirty_changed = pyqtSignal(bool)

    def __init__(self, default_detailers: list[str], parent=None):
        super().__init__(parent)
        self._unit: Unit | None = None
        self._dirty = False
        self._loading = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # COM (read-only)
        layout.addWidget(QLabel("COM:"))
        self.com_label = QLabel("")
        self.com_label.setMinimumWidth(60)
        self.com_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.com_label)

        layout.addWidget(QLabel("|"))

        # Detailer
        layout.addWidget(QLabel("Detailer:"))
        self.detailer_combo = QComboBox()
        self.detailer_combo.addItems(default_detailers)
        self.detailer_combo.setMinimumWidth(120)
        self.detailer_combo.currentIndexChanged.connect(self._on_field_changed)
        layout.addWidget(self.detailer_combo)

        # Due Date
        layout.addWidget(QLabel("Due:"))
        self.due_date_edit = ClearableDateEdit()
        self.due_date_edit.setMinimumWidth(100)
        self.due_date_edit.setCalendarPopup(True)
        self.due_date_edit.dateChanged.connect(self._on_field_changed)
        layout.addWidget(self.due_date_edit)

        # % Complete
        layout.addWidget(QLabel("%:"))
        self.pct_spin = QDoubleSpinBox()
        self.pct_spin.setRange(0.0, 100.0)
        self.pct_spin.setSuffix("%")
        self.pct_spin.setDecimals(1)
        self.pct_spin.setMinimumWidth(60)
        self.pct_spin.valueChanged.connect(self._on_field_changed)
        layout.addWidget(self.pct_spin)

        # Notes
        layout.addWidget(QLabel("Notes:"))
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Quick notes...")
        self.notes_edit.setMinimumWidth(120)
        self.notes_edit.textChanged.connect(self._on_field_changed)
        self.notes_edit.returnPressed.connect(self._on_save)
        layout.addWidget(self.notes_edit, stretch=1)

        # Save button
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("inline_save_btn")
        self.save_btn.setMinimumWidth(50)
        self.save_btn.clicked.connect(self._on_save)
        layout.addWidget(self.save_btn)

        # Revert button
        self.revert_btn = QPushButton("Revert")
        self.revert_btn.setMinimumWidth(50)
        self.revert_btn.clicked.connect(self._on_revert)
        layout.addWidget(self.revert_btn)

        self.setVisible(False)

    # ── Public API ───────────────────────────────────────────────────

    def set_unit(self, unit: Unit | None) -> None:
        """Populate bar from unit, or clear/hide if None.

        If the bar is dirty and a different unit is selected, the caller
        should prompt for discard before calling this method.
        """
        if self._dirty and unit is not None and self._unit is not None and unit.com_number != self._unit.com_number:
            # Don't overwrite dirty state — caller must confirm
            return

        self._unit = unit
        self._loading = True
        try:
            if unit is None:
                self._clear_fields()
                self.setVisible(False)
                return

            self.com_label.setText(unit.com_number)
            self._set_combo_text(self.detailer_combo, unit.detailer or "")
            if unit.detailing_due_date:
                from PyQt5.QtCore import QDate

                self.due_date_edit.setDate(
                    QDate(
                        unit.detailing_due_date.year,
                        unit.detailing_due_date.month,
                        unit.detailing_due_date.day,
                    )
                )
            else:
                self.due_date_edit.setDate(QDate())
            self.pct_spin.setValue(unit.percent_complete)
            self.notes_edit.setText(unit.notes or "")
            self.setVisible(True)
        finally:
            self._loading = False
            was_dirty = self._dirty
            self._dirty = False
            if was_dirty:
                self.dirty_changed.emit(False)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    # ── Events ───────────────────────────────────────────────────────

    def _on_field_changed(self) -> None:
        if not self._loading:
            if not self._dirty:
                self._dirty = True
                self.dirty_changed.emit(True)

    def _on_save(self) -> None:
        if self._unit is None:
            return
        from PyQt5.QtCore import QDate

        unit = Unit(
            com_number=self._unit.com_number,
            job_name=self._unit.job_name,
            contract_number=self._unit.contract_number,
            description=self._unit.description,
            detailer=self.detailer_combo.currentText(),
            checking_status=self._unit.checking_status,
            dr_checks=self._unit.dr_checks,
            dvl_checks=self._unit.dvl_checks,
            department_hours=self._unit.department_hours,
            target_department_hours=self._unit.target_department_hours,
            iec_internal_hours=self._unit.iec_internal_hours,
            percent_complete=self.pct_spin.value(),
            actual_hours=self._unit.actual_hours,
            notes=self.notes_edit.text(),
            status_color=self._unit.status_color,
        )
        # Preserve date fields from original unit
        unit.detailing_due_date = (
            self.due_date_edit.date().toPyDate()
            if self.due_date_edit.date().isValid() and self.due_date_edit.date() > QDate(2000, 1, 1)
            else None
        )
        unit.unit_detailing_start_date = self._unit.unit_detailing_start_date
        unit.unit_moved_to_checking_date = self._unit.unit_moved_to_checking_date
        unit.unit_detailing_completion_date = self._unit.unit_detailing_completion_date
        unit.build_date = self._unit.build_date
        unit.dept_due_date_previous = self._unit.dept_due_date_previous
        unit.updated_at = self._unit.updated_at

        was_dirty = self._dirty
        self._dirty = False
        if was_dirty:
            self.dirty_changed.emit(False)
        self.unit_saved.emit(unit)

    def _on_revert(self) -> None:
        if self._unit is not None:
            self.set_unit(self._unit)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            if self._dirty:
                self._on_revert()
            return
        super().keyPressEvent(event)

    # ── Helpers ──────────────────────────────────────────────────────

    def _clear_fields(self) -> None:
        self.com_label.setText("")
        self.detailer_combo.setCurrentIndex(0)
        self.pct_spin.setValue(0.0)
        self.notes_edit.setText("")
        was_dirty = self._dirty
        self._dirty = False
        if was_dirty:
            self.dirty_changed.emit(False)

    @staticmethod
    def _set_combo_text(combo: QComboBox, text: str) -> None:
        idx = combo.findText(text)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentText(text)
