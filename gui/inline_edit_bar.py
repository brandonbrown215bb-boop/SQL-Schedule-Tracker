# gui/inline_edit_bar.py
"""InlineEditBar — compact editing bar for quick edits in the list panel.

Appears at the bottom of the screen when a row is selected.
Shows 16 scheduling fields in a clean 2-row layout with validation,
notes editing, and theme awareness.
"""

from __future__ import annotations

from datetime import date

from PyQt5.QtCore import QDate, QEvent, QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from data.models import Unit
from gui.edit_form import ClearableDateEdit, _get_invalid_style
from gui.no_scroll_filter import install_no_scroll_filter
from services.validation import validate_unit


class EnterKeySaveFilter(QObject):
    """Filter that catches Enter/Return key presses to trigger save in InlineEditBar."""

    def __init__(self, save_callback, parent=None):
        super().__init__(parent)
        self.save_callback = save_callback

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.save_callback()
                return True
        return super().eventFilter(obj, event)


class InlineEditBar(QWidget):
    """Compact 2-row editing bar for quick unit edits.

    Fields:
      Row 1: COM (read-only), Detailer, % Complete, Checking Status, DR Checks, DVL Checks, Notes (popover), Status Label, Save/Revert buttons.
      Row 2: Start Date, Checking Date, Completion Date, Detailing Due Date, Target Dept. Hours, IEC Hours, Actual Hours to Detail, Hour Variance, Remaining Demand, Hours Checking.

    Signals:
        unit_saved(Unit): Emitted when user saves. Routes through MainWindow.on_save_unit().
        dirty_changed(bool): Emitted when edit state changes.
    """

    unit_saved = pyqtSignal(object)  # Unit
    dirty_changed = pyqtSignal(bool)

    def __init__(self, default_detailers: list[str], parent=None):
        super().__init__(parent)
        self._unit: Unit | None = None
        self._notes: str = ""
        self._dirty = False
        self._loading = False
        self._theme_name = "light"

        self._enter_filter = EnterKeySaveFilter(self._on_save, self)

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
        self.detailer_combo.installEventFilter(self._enter_filter)
        row1_layout.addWidget(self.detailer_combo)

        # % Complete
        row1_layout.addWidget(QLabel("% Complete:"))
        self.pct_spin = QDoubleSpinBox()
        self.pct_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.pct_spin.setRange(0.0, 100.0)
        self.pct_spin.setSuffix("%")
        self.pct_spin.setDecimals(1)
        self.pct_spin.setMinimumWidth(65)
        self.pct_spin.valueChanged.connect(self._on_field_changed)
        self.pct_spin.valueChanged.connect(self._on_pct_changed)
        self.pct_spin.installEventFilter(self._enter_filter)
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

        # Notes inline text edit (stretches to fill remaining space)
        row1_layout.addWidget(QLabel("Notes:"))
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Notes...")
        self.notes_edit.textChanged.connect(self._on_field_changed)
        self.notes_edit.returnPressed.connect(self._on_save)
        row1_layout.addWidget(self.notes_edit, 1)

        # Status feedback label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        row1_layout.addWidget(self.status_label)

        # Save button
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("inline_save_btn")
        self.save_btn.setMinimumWidth(50)
        self.save_btn.setToolTip("Save unit changes (Enter)")
        self.save_btn.clicked.connect(self._on_save)
        row1_layout.addWidget(self.save_btn)

        # Revert button
        self.revert_btn = QPushButton("Revert")
        self.revert_btn.setMinimumWidth(50)
        self.revert_btn.setToolTip("Discard changes (Esc)")
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
        self.start_date_edit.installEventFilter(self._enter_filter)
        row2_layout.addWidget(self.start_date_edit)

        # Moved to Checking Date
        row2_layout.addWidget(QLabel("Checking Date:"))
        self.checking_date_edit = ClearableDateEdit()
        self.checking_date_edit.setMinimumWidth(90)
        self.checking_date_edit.dateChanged.connect(self._on_field_changed)
        self.checking_date_edit.installEventFilter(self._enter_filter)
        row2_layout.addWidget(self.checking_date_edit)

        # Detailing Completion Date
        row2_layout.addWidget(QLabel("Completion Date:"))
        self.completion_date_edit = ClearableDateEdit()
        self.completion_date_edit.setMinimumWidth(90)
        self.completion_date_edit.dateChanged.connect(self._on_field_changed)
        self.completion_date_edit.installEventFilter(self._enter_filter)
        row2_layout.addWidget(self.completion_date_edit)

        # Detailing Due Date
        row2_layout.addWidget(QLabel("Due Date:"))
        self.due_date_edit = ClearableDateEdit()
        self.due_date_edit.setMinimumWidth(90)
        self.due_date_edit.setToolTip("Detailing Due Date")
        self.due_date_edit.dateChanged.connect(self._on_field_changed)
        self.due_date_edit.installEventFilter(self._enter_filter)
        row2_layout.addWidget(self.due_date_edit)

        row2_layout.addWidget(QLabel("|"))

        # Target Dept. Hours
        row2_layout.addWidget(QLabel("Target Hours:"))
        self.target_hours_spin = QDoubleSpinBox()
        self.target_hours_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.target_hours_spin.setRange(0.0, 99999.0)
        self.target_hours_spin.setDecimals(2)
        self.target_hours_spin.setMinimumWidth(70)
        self.target_hours_spin.setToolTip("Target Hours (Auto-calculated from Dept Hours - IEC Hours, or manually editable)")
        self.target_hours_spin.valueChanged.connect(self._on_field_changed)
        self.target_hours_spin.installEventFilter(self._enter_filter)
        row2_layout.addWidget(self.target_hours_spin)

        # IEC Hours
        row2_layout.addWidget(QLabel("IEC Hours:"))
        self.iec_hours_spin = QDoubleSpinBox()
        self.iec_hours_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.iec_hours_spin.setRange(0.0, 99999.0)
        self.iec_hours_spin.setDecimals(2)
        self.iec_hours_spin.setMinimumWidth(70)
        self.iec_hours_spin.valueChanged.connect(self._on_field_changed)
        self.iec_hours_spin.valueChanged.connect(self._on_iec_changed)
        self.iec_hours_spin.installEventFilter(self._enter_filter)
        row2_layout.addWidget(self.iec_hours_spin)

        # Actual Hours to Detail
        row2_layout.addWidget(QLabel("Actual Hours:"))
        self.actual_hours_to_detail_spin = QDoubleSpinBox()
        self.actual_hours_to_detail_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.actual_hours_to_detail_spin.setRange(0.0, 99999.0)
        self.actual_hours_to_detail_spin.setDecimals(2)
        self.actual_hours_to_detail_spin.setMinimumWidth(70)
        self.actual_hours_to_detail_spin.valueChanged.connect(self._on_field_changed)
        self.actual_hours_to_detail_spin.valueChanged.connect(self._on_actual_detail_changed)
        self.actual_hours_to_detail_spin.installEventFilter(self._enter_filter)
        row2_layout.addWidget(self.actual_hours_to_detail_spin)

        # Hour Variance
        row2_layout.addWidget(QLabel("Variance:"))
        self.hour_variance_spin = QDoubleSpinBox()
        self.hour_variance_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.hour_variance_spin.setRange(-99999.0, 99999.0)
        self.hour_variance_spin.setDecimals(2)
        self.hour_variance_spin.setMinimumWidth(70)
        self.hour_variance_spin.valueChanged.connect(self._on_field_changed)
        self.hour_variance_spin.installEventFilter(self._enter_filter)
        row2_layout.addWidget(self.hour_variance_spin)

        # Remaining Demand
        row2_layout.addWidget(QLabel("Remaining Demand:"))
        self.remaining_demand_spin = QDoubleSpinBox()
        self.remaining_demand_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.remaining_demand_spin.setRange(0.0, 99999.0)
        self.remaining_demand_spin.setDecimals(2)
        self.remaining_demand_spin.setMinimumWidth(70)
        self.remaining_demand_spin.valueChanged.connect(self._on_field_changed)
        self.remaining_demand_spin.installEventFilter(self._enter_filter)
        row2_layout.addWidget(self.remaining_demand_spin)

        # Hours Checking
        row2_layout.addWidget(QLabel("Hours Checking:"))
        self.hours_checking_spin = QDoubleSpinBox()
        self.hours_checking_spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.hours_checking_spin.setRange(0.0, 99999.0)
        self.hours_checking_spin.setDecimals(2)
        self.hours_checking_spin.setMinimumWidth(70)
        self.hours_checking_spin.valueChanged.connect(self._on_field_changed)
        self.hours_checking_spin.installEventFilter(self._enter_filter)
        row2_layout.addWidget(self.hours_checking_spin)

        main_layout.addWidget(row1_widget)
        main_layout.addWidget(row2_widget)

        install_no_scroll_filter(self)
        self.setVisible(False)

    # ── Public API ───────────────────────────────────────────────────

    def set_theme(self, theme_name: str, cvd_mode: str = "none") -> None:
        """Update theme name for error styling."""
        self._theme_name = theme_name
        self.update()

    def set_unit(self, unit: Unit | None) -> None:
        """Populate bar from unit, or clear/hide if None."""
        if self._dirty and unit is not None and self._unit is not None and unit.com_number != self._unit.com_number:
            # Don't overwrite dirty state — caller must confirm
            return

        self._unit = unit
        self._loading = True
        self.status_label.setText("")
        try:
            if unit is None:
                self._clear_fields()
                self.setVisible(False)
                return

            self.notes_edit.setText(unit.notes or "")

            self.com_label.setText(unit.com_number)
            self._set_combo_text(self.detailer_combo, unit.detailer or "")
            self.pct_spin.setValue(unit.percent_complete)
            self.checking_status_edit.setText(unit.checking_status or "")
            self.dr_checks_edit.setText(unit.dr_checks or "")
            self.dvl_checks_edit.setText(unit.dvl_checks or "")

            self._set_date(self.start_date_edit, unit.unit_detailing_start_date)
            self._set_date(self.checking_date_edit, unit.unit_moved_to_checking_date)
            self._set_date(self.completion_date_edit, unit.unit_detailing_completion_date)
            self._set_date(self.due_date_edit, unit.detailing_due_date)

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
            if self.detailer_combo.currentText().strip() == "Cancelled":
                self.target_hours_spin.setValue(0.0)
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

    def _validate_fields(self, unit: Unit) -> list[str]:
        """Validate unit fields and set visual error indicators."""
        errors: list[str] = []

        # Reset widget styles
        for widget in (
            self.pct_spin,
            self.target_hours_spin,
            self.actual_hours_to_detail_spin,
            self.due_date_edit,
            self.start_date_edit,
            self.checking_date_edit,
            self.completion_date_edit,
        ):
            widget.setStyleSheet("")
            widget.setProperty("invalid", False)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

        valid, validation_errors = validate_unit(unit)
        if not valid:
            invalid_style = _get_invalid_style(self._theme_name)
            for err in validation_errors:
                field = err.split(":")[0] if ":" in err else ""
                if field == "percent_complete":
                    self.pct_spin.setStyleSheet(invalid_style)
                    self.pct_spin.setToolTip(err)
                elif field == "target_department_hours":
                    self.target_hours_spin.setStyleSheet(invalid_style)
                    self.target_hours_spin.setToolTip(err)
                elif field == "actual_hours_to_detail_unit":
                    self.actual_hours_to_detail_spin.setStyleSheet(invalid_style)
                    self.actual_hours_to_detail_spin.setToolTip(err)
            errors.extend(validation_errors)

        # Date order validation (warnings)
        dates = [
            ("Detailing Start", unit.unit_detailing_start_date),
            ("Moved to Checking", unit.unit_moved_to_checking_date),
            ("Detailing Complete", unit.unit_detailing_completion_date),
        ]
        set_dates = [(name, d) for name, d in dates if d is not None]
        if len(set_dates) >= 2:
            for i in range(len(set_dates) - 1):
                name_a, date_a = set_dates[i]
                name_b, date_b = set_dates[i + 1]
                if date_a > date_b:
                    errors.append(f"Date order warning: {name_a} is after {name_b}")

        return errors

    def _on_save(self) -> None:
        if self._unit is None:
            return

        detailer_txt = self.detailer_combo.currentText().strip()
        detailer = "" if self.detailer_combo.currentIndex() == 0 else detailer_txt

        unit = Unit(
            com_number=self._unit.com_number,
            job_name=self._unit.job_name,
            contract_number=self._unit.contract_number,
            description=self._unit.description,
            detailer=detailer,
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
            notes=self.notes_edit.text(),
            status_color=self._unit.status_color,
        )

        unit.unit_detailing_start_date = self._get_date(self.start_date_edit)
        unit.unit_moved_to_checking_date = self._get_date(self.checking_date_edit)
        unit.unit_detailing_completion_date = self._get_date(self.completion_date_edit)
        unit.detailing_due_date = self._get_date(self.due_date_edit)

        # Preserve metadata from original unit
        unit.build_date = self._unit.build_date
        unit.dept_due_date_previous = self._unit.dept_due_date_previous
        unit.updated_at = self._unit.updated_at
        unit.excel_row = self._unit.excel_row
        unit.fingerprint = self._unit.fingerprint
        unit.base_revision = self._unit.base_revision
        unit.working_days = self._unit.working_days

        errors = self._validate_fields(unit)
        if errors:
            self.status_label.setText('<span style="color: red;">⚠ ' + "; ".join(errors) + "</span>")
            hard_errors = [e for e in errors if not e.startswith("Date order warning")]
            if hard_errors:
                return

        was_dirty = self._dirty
        self._dirty = False
        if was_dirty:
            self.dirty_changed.emit(False)

        self.status_label.setText('<span style="color: green;">✓ Saved</span>')
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
        self.notes_edit.setText("")
        self.com_label.setText("")
        self.detailer_combo.setCurrentIndex(0)
        self.pct_spin.setValue(0.0)
        self.checking_status_edit.setText("")
        self.dr_checks_edit.setText("")
        self.dvl_checks_edit.setText("")
        self._set_date(self.start_date_edit, None)
        self._set_date(self.checking_date_edit, None)
        self._set_date(self.completion_date_edit, None)
        self._set_date(self.due_date_edit, None)
        self.target_hours_spin.setValue(0.0)
        self.iec_hours_spin.setValue(0.0)
        self.actual_hours_to_detail_spin.setValue(0.0)
        self.hour_variance_spin.setValue(0.0)
        self.remaining_demand_spin.setValue(0.0)
        self.hours_checking_spin.setValue(0.0)
        self.status_label.setText("")

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
