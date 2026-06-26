# gui/inline_edit_bar.py
"""InlineEditBar — compact editing bar for quick edits in the list panel.

Appears at the bottom of the screen when a row is selected.
Shows 15 scheduling fields in a clean 2-row layout.
Emits unit_saved(Unit) on save, which routes through the existing SaveWorker pipeline.
"""

from __future__ import annotations

from datetime import date
from PyQt5.QtCore import QDate, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from data.models import Unit
from gui.edit_form import ClearableDateEdit


class InlineEditBar(QWidget):
    """Compact 2-row editing bar for quick unit edits.

    Fields:
      Row 1: COM (read-only), Detailer, % Complete, Checking Status, DR Checks, DVL Checks, Save/Revert buttons.
      Row 2: Start Date, Checking Date, Completion Date, Target Dept. Hours, IEC Hours, Actual Hours to Detail, Hour Variance, Remaining Demand, Hours Checking.

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

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        # ─── Row 1: Identity & Status ────────────────────────────────
        row1_widget = QWidget()
        row1_layout = QHBoxLayout(row1_widget)
        row1_layout.setContentsMargins(0, 0, 0, 0)
        row1_layout.setSpacing(6)

        # COM (read-only)
        row1_layout.addWidget(QLabel("COM:"))
        self.com_label = QLabel("")
        self.com_label.setMinimumWidth(60)
        self.com_label.setStyleSheet("font-weight: bold;")
        row1_layout.addWidget(self.com_label)

        row1_layout.addWidget(QLabel("|"))

        # Detailer
        row1_layout.addWidget(QLabel("Detailer:"))
        self.detailer_combo = QComboBox()
        self.detailer_combo.addItems(default_detailers)
        self.detailer_combo.setMinimumWidth(110)
        self.detailer_combo.currentIndexChanged.connect(self._on_field_changed)
        row1_layout.addWidget(self.detailer_combo)

        # % Complete
        row1_layout.addWidget(QLabel("% Complete:"))
        self.pct_spin = QDoubleSpinBox()
        self.pct_spin.setRange(0.0, 100.0)
        self.pct_spin.setSuffix("%")
        self.pct_spin.setDecimals(1)
        self.pct_spin.setMinimumWidth(65)
        self.pct_spin.valueChanged.connect(self._on_field_changed)
        self.pct_spin.valueChanged.connect(self._on_pct_changed)
        row1_layout.addWidget(self.pct_spin)

        # Checking Status
        row1_layout.addWidget(QLabel("Checking Status:"))
        self.checking_status_edit = QLineEdit()
        self.checking_status_edit.setMinimumWidth(100)
        self.checking_status_edit.textChanged.connect(self._on_field_changed)
        self.checking_status_edit.returnPressed.connect(self._on_save)
        row1_layout.addWidget(self.checking_status_edit)

        # DR Checks
        row1_layout.addWidget(QLabel("DR Check:"))
        self.dr_checks_edit = QLineEdit()
        self.dr_checks_edit.setMinimumWidth(80)
        self.dr_checks_edit.textChanged.connect(self._on_field_changed)
        self.dr_checks_edit.returnPressed.connect(self._on_save)
        row1_layout.addWidget(self.dr_checks_edit)

        # DVL Checks
        row1_layout.addWidget(QLabel("DVL Check:"))
        self.dvl_checks_edit = QLineEdit()
        self.dvl_checks_edit.setMinimumWidth(80)
        self.dvl_checks_edit.textChanged.connect(self._on_field_changed)
        self.dvl_checks_edit.returnPressed.connect(self._on_save)
        row1_layout.addWidget(self.dvl_checks_edit)

        row1_layout.addStretch(1)

        # Save button
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("inline_save_btn")
        self.save_btn.setMinimumWidth(50)
        self.save_btn.clicked.connect(self._on_save)
        row1_layout.addWidget(self.save_btn)

        # Revert button
        self.revert_btn = QPushButton("Revert")
        self.revert_btn.setMinimumWidth(50)
        self.revert_btn.clicked.connect(self._on_revert)
        row1_layout.addWidget(self.revert_btn)

        # ─── Row 2: Dates & Hours ────────────────────────────────────
        row2_widget = QWidget()
        row2_layout = QHBoxLayout(row2_widget)
        row2_layout.setContentsMargins(0, 0, 0, 0)
        row2_layout.setSpacing(6)

        # Detailing Start Date
        row2_layout.addWidget(QLabel("Start Date:"))
        self.start_date_edit = ClearableDateEdit()
        self.start_date_edit.setMinimumWidth(90)
        self.start_date_edit.dateChanged.connect(self._on_field_changed)
        row2_layout.addWidget(self.start_date_edit)

        # Moved to Checking Date
        row2_layout.addWidget(QLabel("Checking Date:"))
        self.checking_date_edit = ClearableDateEdit()
        self.checking_date_edit.setMinimumWidth(90)
        self.checking_date_edit.dateChanged.connect(self._on_field_changed)
        row2_layout.addWidget(self.checking_date_edit)

        # Detailing Completion Date
        row2_layout.addWidget(QLabel("Completion Date:"))
        self.completion_date_edit = ClearableDateEdit()
        self.completion_date_edit.setMinimumWidth(90)
        self.completion_date_edit.dateChanged.connect(self._on_field_changed)
        row2_layout.addWidget(self.completion_date_edit)

        row2_layout.addWidget(QLabel("|"))

        # Target Dept. Hours
        row2_layout.addWidget(QLabel("Target Dept. Hours:"))
        self.target_hours_spin = QDoubleSpinBox()
        self.target_hours_spin.setRange(0.0, 99999.0)
        self.target_hours_spin.setDecimals(2)
        self.target_hours_spin.setMinimumWidth(70)
        self.target_hours_spin.valueChanged.connect(self._on_field_changed)
        row2_layout.addWidget(self.target_hours_spin)

        # IEC Hours
        row2_layout.addWidget(QLabel("IEC Hours:"))
        self.iec_hours_spin = QDoubleSpinBox()
        self.iec_hours_spin.setRange(0.0, 99999.0)
        self.iec_hours_spin.setDecimals(2)
        self.iec_hours_spin.setMinimumWidth(70)
        self.iec_hours_spin.valueChanged.connect(self._on_field_changed)
        self.iec_hours_spin.valueChanged.connect(self._on_iec_changed)
        row2_layout.addWidget(self.iec_hours_spin)

        # Actual Hours to Detail
        row2_layout.addWidget(QLabel("Actual Hours to Detail:"))
        self.actual_hours_to_detail_spin = QDoubleSpinBox()
        self.actual_hours_to_detail_spin.setRange(0.0, 99999.0)
        self.actual_hours_to_detail_spin.setDecimals(2)
        self.actual_hours_to_detail_spin.setMinimumWidth(70)
        self.actual_hours_to_detail_spin.valueChanged.connect(self._on_field_changed)
        self.actual_hours_to_detail_spin.valueChanged.connect(self._on_actual_detail_changed)
        row2_layout.addWidget(self.actual_hours_to_detail_spin)

        # Hour Variance
        row2_layout.addWidget(QLabel("Hour Variance:"))
        self.hour_variance_spin = QDoubleSpinBox()
        self.hour_variance_spin.setRange(-99999.0, 99999.0)
        self.hour_variance_spin.setDecimals(2)
        self.hour_variance_spin.setMinimumWidth(70)
        self.hour_variance_spin.valueChanged.connect(self._on_field_changed)
        row2_layout.addWidget(self.hour_variance_spin)

        # Remaining Demand
        row2_layout.addWidget(QLabel("Remaining Demand:"))
        self.remaining_demand_spin = QDoubleSpinBox()
        self.remaining_demand_spin.setRange(0.0, 99999.0)
        self.remaining_demand_spin.setDecimals(2)
        self.remaining_demand_spin.setMinimumWidth(70)
        self.remaining_demand_spin.valueChanged.connect(self._on_field_changed)
        row2_layout.addWidget(self.remaining_demand_spin)

        # Hours Checking
        row2_layout.addWidget(QLabel("Hours Checking:"))
        self.hours_checking_spin = QDoubleSpinBox()
        self.hours_checking_spin.setRange(0.0, 99999.0)
        self.hours_checking_spin.setDecimals(2)
        self.hours_checking_spin.setMinimumWidth(70)
        self.hours_checking_spin.valueChanged.connect(self._on_field_changed)
        row2_layout.addWidget(self.hours_checking_spin)

        main_layout.addWidget(row1_widget)
        main_layout.addWidget(row2_widget)

        self.setVisible(False)

    # ── Public API ───────────────────────────────────────────────────

    def set_unit(self, unit: Unit | None) -> None:
        """Populate bar from unit, or clear/hide if None."""
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
            self.pct_spin.setValue(unit.percent_complete)
            self.checking_status_edit.setText(unit.checking_status or "")
            self.dr_checks_edit.setText(unit.dr_checks or "")
            self.dvl_checks_edit.setText(unit.dvl_checks or "")

            self._set_date(self.start_date_edit, unit.unit_detailing_start_date)
            self._set_date(self.checking_date_edit, unit.unit_moved_to_checking_date)
            self._set_date(self.completion_date_edit, unit.unit_detailing_completion_date)

            self.target_hours_spin.setValue(unit.target_department_hours)
            self.iec_hours_spin.setValue(unit.iec_internal_hours)
            self.actual_hours_to_detail_spin.setValue(unit.actual_hours_to_detail_unit)
            self.hour_variance_spin.setValue(unit.hour_variance)
            self.remaining_demand_spin.setValue(unit.remaining_demand)
            self.hours_checking_spin.setValue(unit.hours_checking)

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

    def _on_iec_changed(self) -> None:
        if self._loading or self._unit is None:
            return
        if self._unit.is_non_primary_identical:
            self.target_hours_spin.setValue(0.0)
            return
        dept = self._unit.department_hours or 0.0
        iec = self.iec_hours_spin.value()
        self.target_hours_spin.setValue(max(0.0, dept - iec))

    def _on_actual_detail_changed(self) -> None:
        if self._loading or self._unit is None:
            return
        dept = self._unit.department_hours or 0.0
        actual = self.actual_hours_to_detail_spin.value()
        self.hour_variance_spin.setValue(dept - actual)

    def _on_pct_changed(self) -> None:
        if self._loading or self._unit is None:
            return
        dept = self._unit.department_hours or 0.0
        pct = self.pct_spin.value()
        self.remaining_demand_spin.setValue(dept * (1.0 - pct / 100.0))

    def _on_save(self) -> None:
        if self._unit is None:
            return

        # Prepare updated Unit object
        unit = Unit(
            com_number=self._unit.com_number,
            job_name=self._unit.job_name,
            contract_number=self._unit.contract_number,
            description=self._unit.description,
            detailer=self.detailer_combo.currentText(),
            checking_status=self.checking_status_edit.text(),
            dr_checks=self.dr_checks_edit.text(),
            dvl_checks=self.dvl_checks_edit.text(),
            department_hours=self._unit.department_hours,
            target_department_hours=self.target_hours_spin.value(),
            iec_internal_hours=self.iec_hours_spin.value(),
            percent_complete=self.pct_spin.value(),
            actual_hours=self._unit.actual_hours,
            actual_hours_to_detail_unit=self.actual_hours_to_detail_spin.value(),
            hour_variance=self.hour_variance_spin.value(),
            remaining_demand=self.remaining_demand_spin.value(),
            hours_checking=self.hours_checking_spin.value(),
            notes=self._unit.notes,
            status_color=self._unit.status_color,
        )

        unit.unit_detailing_start_date = self._get_date(self.start_date_edit)
        unit.unit_moved_to_checking_date = self._get_date(self.checking_date_edit)
        unit.unit_detailing_completion_date = self._get_date(self.completion_date_edit)

        # Preserve dates and metadata from original unit
        unit.detailing_due_date = self._unit.detailing_due_date
        unit.build_date = self._unit.build_date
        unit.dept_due_date_previous = self._unit.dept_due_date_previous
        unit.updated_at = self._unit.updated_at
        unit.excel_row = self._unit.excel_row
        unit.fingerprint = self._unit.fingerprint
        unit.base_revision = self._unit.base_revision
        unit.working_days = self._unit.working_days

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
        self.checking_status_edit.setText("")
        self.dr_checks_edit.setText("")
        self.dvl_checks_edit.setText("")
        self._set_date(self.start_date_edit, None)
        self._set_date(self.checking_date_edit, None)
        self._set_date(self.completion_date_edit, None)
        self.target_hours_spin.setValue(0.0)
        self.iec_hours_spin.setValue(0.0)
        self.actual_hours_to_detail_spin.setValue(0.0)
        self.hour_variance_spin.setValue(0.0)
        self.remaining_demand_spin.setValue(0.0)
        self.hours_checking_spin.setValue(0.0)

        was_dirty = self._dirty
        self._dirty = False
        if was_dirty:
            self.dirty_changed.emit(False)

    def _set_date(self, widget: ClearableDateEdit, d: date | None) -> None:
        if d is not None:
            widget.setDate(QDate(d.year, d.month, d.day))
        else:
            widget.setDate(QDate(2000, 1, 1))

    def _get_date(self, widget: ClearableDateEdit) -> date | None:
        d = widget.date().toPyDate()
        if d.year == 2000 and d.month == 1 and d.day == 1:
            return None
        return d

    @staticmethod
    def _set_combo_text(combo: QComboBox, text: str) -> None:
        idx = combo.findText(text)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentText(text)
