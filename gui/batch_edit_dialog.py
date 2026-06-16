# gui/batch_edit_dialog.py
"""BatchEditDialog — apply field changes to multiple units at once.

Shows checkboxes for each field (detailer, due date, % complete, status).
When the user checks a field and clicks OK, that field's value is applied
to all selected units. Units are saved individually through the standard
UnitService.save() path (with validation + pre-save hooks).
"""

from __future__ import annotations

from PyQt5.QtCore import QDate, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
)

from data.models import Unit
from gui.edit_form import ClearableDateEdit


class BatchEditDialog(QDialog):
    """Dialog for applying common field values to multiple units.

    Signals:
        unit_saved(Unit): Emitted for each unit that was changed and saved.
    """

    unit_saved = pyqtSignal(object)  # Unit

    def __init__(
        self,
        units: list[Unit],
        default_detailers: list[str],
        tag_repo=None,
        parent=None,
    ):
        super().__init__(parent)
        self._units = units
        self._tag_repo = tag_repo
        self._updated_units: list[Unit] = []

        self.setWindowTitle(f"Batch Edit — {len(units)} units")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(f"<b>Editing {len(units)} units</b>")
        header.setWordWrap(True)
        layout.addWidget(header)

        # Fields to edit
        form = QFormLayout()

        # Detailer
        self.detailer_check = QCheckBox("Change detailer")
        self.detailer_combo = QComboBox()
        self.detailer_combo.setEnabled(False)
        self.detailer_combo.addItems(default_detailers)
        self.detailer_check.toggled.connect(self.detailer_combo.setEnabled)
        form.addRow(self.detailer_check, self.detailer_combo)

        # Due date
        self.due_date_check = QCheckBox("Change due date")
        self.due_date_edit = ClearableDateEdit()
        self.due_date_edit.setEnabled(False)
        self.due_date_edit.setCalendarPopup(True)
        self.due_date_edit.setDate(QDate.currentDate().addDays(14))
        self.due_date_check.toggled.connect(self.due_date_edit.setEnabled)
        form.addRow(self.due_date_check, self.due_date_edit)

        # Percent complete
        self.pct_check = QCheckBox("Change % complete")
        self.pct_spin = QDoubleSpinBox()
        self.pct_spin.setEnabled(False)
        self.pct_spin.setRange(0.0, 100.0)
        self.pct_spin.setSuffix("%")
        self.pct_spin.setDecimals(1)
        self.pct_spin.setValue(50.0)
        self.pct_check.toggled.connect(self.pct_spin.setEnabled)
        form.addRow(self.pct_check, self.pct_spin)

        # Status
        self.status_check = QCheckBox("Set status")
        self.status_combo = QComboBox()
        self.status_combo.setEnabled(False)
        self.status_combo.addItems(["", "gray", "yellow", "purple", "orange", "green", "red"])
        self.status_check.toggled.connect(self.status_combo.setEnabled)
        form.addRow(self.status_check, self.status_combo)

        layout.addLayout(form)

        # Progress bar (shown during save)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Warning for large batches
        if len(units) > 50:
            warning = QLabel(f"⚠️ Applying to {len(units)} units. This may take a moment.")
            warning.setStyleSheet("color: #f59e0b;")
            layout.addWidget(warning)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply(self) -> None:
        """Apply selected field changes to all units and save."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(self._units))

        for i, unit in enumerate(self._units):
            changed = False

            if self.detailer_check.isChecked():
                unit.detailer = self.detailer_combo.currentText()
                changed = True
            if self.due_date_check.isChecked():
                qdate = self.due_date_edit.date()
                unit.detailing_due_date = qdate.toPyDate()
                changed = True
            if self.pct_check.isChecked():
                unit.percent_complete = self.pct_spin.value()
                changed = True
            if self.status_check.isChecked() and self.status_combo.currentText():
                unit.status_color = self.status_combo.currentText()
                changed = True

            if changed:
                self._updated_units.append(unit)
                self.unit_saved.emit(unit)

            self.progress_bar.setValue(i + 1)

        self.accept()

    def get_updated_units(self) -> list[Unit]:
        return self._updated_units
