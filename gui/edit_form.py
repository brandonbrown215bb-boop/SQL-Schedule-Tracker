from datetime import date

from PyQt5.QtCore import QDate, Qt, pyqtSignal
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,  # Added QComboBox
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from data.models import Unit


class ClearableDateEdit(QDateEdit):
    """QDateEdit that clears to the 'unset' sentinel on Delete/Backspace."""

    _UNSET = QDate(2000, 1, 1)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setCalendarPopup(True)
        self.setSpecialValueText(" — ")
        self.setDate(self._UNSET)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.setDate(self._UNSET)
            event.accept()
            return
        super().keyPressEvent(event)


class EditForm(QWidget):
    """Form for editing a Unit's properties."""

    saved = pyqtSignal(Unit) # Re-added
    dirty_changed = pyqtSignal(bool)

    def __init__(self, default_detailers: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("edit_form")

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<b>Edit Unit</b>"))

        # Scroll area so the form doesn't overflow on small screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        form_container = QWidget()
        self.form = QFormLayout(form_container)
        scroll.setWidget(form_container)
        layout.addWidget(scroll)

        # --- Identity fields ---
        identity_label = QLabel("<b>Identity Fields</b>")
        self.form.addRow(identity_label)
        self.form.addRow(self._create_h_line())

        self.com_number_edit = QLineEdit()
        self.com_number_edit.setReadOnly(True)  # COM number is the key, don't edit

        self.form.addRow(QLabel("COM Number:"), self.com_number_edit)

        self.job_name_edit = QLineEdit()
        self.form.addRow(QLabel("Job Name:"), self.job_name_edit)

        self.contract_edit = QLineEdit()
        self.form.addRow(QLabel("Contract #:"), self.contract_edit)
        self.description_edit = QLineEdit()
        self.form.addRow(QLabel("Description:"), self.description_edit)

        self.detailer_edit = QComboBox() # Changed to QComboBox
        self.detailer_edit.addItems(default_detailers)
        self.form.addRow(QLabel("Detailer:"), self.detailer_edit)

        self.checking_status_edit = QLineEdit()
        self.form.addRow(QLabel("Checking Status:"), self.checking_status_edit)

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Notes...")
        self.notes_edit.setMinimumHeight(60)
        self.notes_edit.setMaximumHeight(120)
        self.form.addRow(QLabel("Notes:"), self.notes_edit)

        # --- Numeric fields ---
        numeric_label = QLabel("<b>Numeric Fields</b>")
        self.form.addRow(numeric_label)
        self.form.addRow(self._create_h_line())

        self.dept_hours_spin = QDoubleSpinBox()
        self.dept_hours_spin.setFocusPolicy(Qt.ClickFocus)
        self.dept_hours_spin.setMaximum(99999.0)
        self.dept_hours_spin.setDecimals(2)
        self.dept_hours_spin.setSingleStep(0.25)
        self.form.addRow(QLabel("Dept Hours:"), self.dept_hours_spin)

        self.target_hours_spin = QDoubleSpinBox()
        self.target_hours_spin.setFocusPolicy(Qt.ClickFocus)
        self.target_hours_spin.setMaximum(99999.0)
        self.target_hours_spin.setDecimals(2)
        self.target_hours_spin.setSingleStep(0.25)
        self.target_hours_spin.setReadOnly(True)
        self.target_hours_spin.setToolTip("Auto-calculated: Dept Hours − IEC Internal Hours")
        self.form.addRow(QLabel("Target Hours:"), self.target_hours_spin)

        self.iec_hours_spin = QDoubleSpinBox()
        self.iec_hours_spin.setFocusPolicy(Qt.ClickFocus)
        self.iec_hours_spin.setMaximum(99999.0)
        self.iec_hours_spin.setDecimals(2)
        self.iec_hours_spin.setSingleStep(0.25)
        self.form.addRow(QLabel("IEC Internal Hours:"), self.iec_hours_spin)

        self.percent_spin = QDoubleSpinBox()
        self.percent_spin.setFocusPolicy(Qt.ClickFocus)
        self.percent_spin.setMaximum(100.0)
        self.percent_spin.setDecimals(1)
        self.percent_spin.setSuffix("%")
        self.form.addRow(QLabel("% Complete:"), self.percent_spin)

        self.actual_hours_spin = QDoubleSpinBox()
        self.actual_hours_spin.setFocusPolicy(Qt.ClickFocus)
        self.actual_hours_spin.setMaximum(99999.0)
        self.actual_hours_spin.setDecimals(2)
        self.actual_hours_spin.setSingleStep(0.25)
        self.form.addRow(QLabel("Actual Hours:"), self.actual_hours_spin)

        # --- Date fields ---
        date_label = QLabel("<b>Date Fields</b>")
        self.form.addRow(date_label)
        self.form.addRow(self._create_h_line())

        self.start_date_edit = ClearableDateEdit()
        self.form.addRow(QLabel("Detailing Start:"), self.start_date_edit)

        self.checking_date_edit = ClearableDateEdit()
        self.form.addRow(QLabel("Moved to Checking:"), self.checking_date_edit)

        self.completion_date_edit = ClearableDateEdit()
        self.form.addRow(QLabel("Detailing Complete:"), self.completion_date_edit)

        self.due_prev_date_edit = ClearableDateEdit()
        self.form.addRow(QLabel("Dept Due (prev):"), self.due_prev_date_edit)

        self.due_date_edit = ClearableDateEdit()
        self.form.addRow(QLabel("Detailing Due:"), self.due_date_edit)

        self.build_date_edit = ClearableDateEdit()
        self.form.addRow(QLabel("Build Date:"), self.build_date_edit)

        # ── Dirty tracking ──
        self.current_unit: Unit | None = None
        self._dirty = False
        self._loading = False
        _fields = (
            self.job_name_edit, self.contract_edit, self.description_edit,
            self.detailer_edit,
            self.checking_status_edit,
            self.notes_edit,
            self.dept_hours_spin,
            self.iec_hours_spin, self.percent_spin, self.actual_hours_spin,
            self.start_date_edit, self.checking_date_edit,
            self.completion_date_edit, self.due_prev_date_edit,
            self.due_date_edit, self.build_date_edit,
        )
        for f in _fields:
            if isinstance(f, QLineEdit):
                f.textChanged.connect(self._mark_dirty)
            elif isinstance(f, QComboBox):
                f.currentIndexChanged.connect(self._mark_dirty)
            elif isinstance(f, QTextEdit):
                f.textChanged.connect(self._mark_dirty)
            elif isinstance(f, (QDateEdit, QDoubleSpinBox)):
                if isinstance(f, QDateEdit):
                    f.dateChanged.connect(self._mark_dirty)
                if isinstance(f, QDoubleSpinBox):
                    f.valueChanged.connect(self._mark_dirty)

        # --- Auto-calculate Target Hours = Dept Hours - IEC Hours ---
        self.dept_hours_spin.valueChanged.connect(self._update_target_hours)
        self.iec_hours_spin.valueChanged.connect(self._update_target_hours)

        # --- Buttons ---
        button_row = QHBoxLayout()

        save_btn = QPushButton("💾 Save Changes")
        save_btn.setObjectName("save_btn")
        save_btn.clicked.connect(self._on_save)
        button_row.addWidget(save_btn)

        revert_btn = QPushButton("↩ Revert")
        revert_btn.setObjectName("revert_btn")
        revert_btn.clicked.connect(lambda: self.set_unit(self.current_unit))
        button_row.addWidget(revert_btn)

        layout.addLayout(button_row)

        # Empty label for status messages
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

    def _create_h_line(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def set_unit(self, unit: Unit | None):
        """Populate form from a Unit object."""
        self._loading = True
        self._dirty = False
        self.dirty_changed.emit(False)
        # Block signals during population to prevent dirty-tracking fires
        _signal_blocks = []
        _fields = (
            self.job_name_edit, self.contract_edit, self.description_edit,
            self.detailer_edit, self.checking_status_edit,
            self.notes_edit,
            self.dept_hours_spin,
            self.iec_hours_spin, self.percent_spin, self.actual_hours_spin,
            self.start_date_edit, self.checking_date_edit,
            self.completion_date_edit, self.due_prev_date_edit,
            self.due_date_edit, self.build_date_edit,
        )
        for f in _fields:
            f.blockSignals(True)
            _signal_blocks.append(f)
        try:
            if unit is None:
                self.com_number_edit.setText("")
                self.job_name_edit.setText("")
                self.contract_edit.setText("")
                self.description_edit.setText("")
                # self.detailer_edit.setText("") # REMOVED: Replaced with QComboBox
                self.detailer_edit.setCurrentIndex(0)
                self.checking_status_edit.setText("")
                self.notes_edit.setPlainText("")
                self.dept_hours_spin.setValue(0)
                self.target_hours_spin.setValue(0)
                self.iec_hours_spin.setValue(0)
                self.percent_spin.setValue(0)
                self.actual_hours_spin.setValue(0)
                self._set_date(self.start_date_edit, None)
                self._set_date(self.checking_date_edit, None)
                self._set_date(self.completion_date_edit, None)
                self._set_date(self.due_prev_date_edit, None)
                self._set_date(self.due_date_edit, None)
                self._set_date(self.build_date_edit, None)
                self.current_unit = None
                return

            self.current_unit = unit
            self.status_label.setText("")

            self.com_number_edit.setText(unit.com_number)
            self.job_name_edit.setText(unit.job_name)
            self.contract_edit.setText(unit.contract_number)
            self.description_edit.setText(unit.description)
            if unit.detailer and self.detailer_edit.findText(unit.detailer) >= 0:
                self.detailer_edit.setCurrentText(unit.detailer)
            else:
                self.detailer_edit.setCurrentIndex(0)
            self.checking_status_edit.setText(unit.checking_status)
            self.notes_edit.setPlainText(unit.notes)


            self.dept_hours_spin.setValue(unit.department_hours)
            self.target_hours_spin.setValue(unit.target_department_hours)
            self.iec_hours_spin.setValue(unit.iec_internal_hours)
            self.percent_spin.setValue(unit.percent_complete)
            self.actual_hours_spin.setValue(unit.actual_hours)

            self._set_date(self.start_date_edit, unit.unit_detailing_start_date)
            self._set_date(self.checking_date_edit, unit.unit_moved_to_checking_date)
            self._set_date(self.completion_date_edit, unit.unit_detailing_completion_date)
            self._set_date(self.due_prev_date_edit, unit.dept_due_date_previous)
            self._set_date(self.due_date_edit, unit.detailing_due_date)
            self._set_date(self.build_date_edit, unit.build_date)
        finally:
            for f in _signal_blocks:
                f.blockSignals(False)
            self._loading = False

    def _on_save(self):
        """Collect form data into a Unit and emit."""
        if self.current_unit is None:
            self.status_label.setText("No Unit loaded")
            return

        # Validate required fields
        com_number = self.com_number_edit.text().strip()
        if not com_number:
            self.status_label.setText('<span style="color: red;">COM Number cannot be empty</span>')
            return

        # Preserve fields from the original unit that aren't in the form
        orig = self.current_unit
        detailer_txt = self.detailer_edit.currentText().strip()
        detailer = "" if self.detailer_edit.currentIndex() == 0 else detailer_txt
        updated = Unit(
            com_number=com_number,
            job_name=self.job_name_edit.text(),
            contract_number=self.contract_edit.text(),
            description=self.description_edit.text(),
            detailer=detailer,
            checking_status=self.checking_status_edit.text(),
            notes=self.notes_edit.toPlainText(),
            department_hours=self.dept_hours_spin.value(),
            target_department_hours=self.target_hours_spin.value(),
            iec_internal_hours=self.iec_hours_spin.value(),
            percent_complete=self.percent_spin.value(),
            actual_hours=self.actual_hours_spin.value(),
            working_days=orig.working_days if orig else None,
            status_color=orig.status_color if orig else "gray",
            unit_detailing_start_date=self._get_date(self.start_date_edit),
            unit_moved_to_checking_date=self._get_date(self.checking_date_edit),
            unit_detailing_completion_date=self._get_date(self.completion_date_edit),
            dept_due_date_previous=self._get_date(self.due_prev_date_edit),
            detailing_due_date=self._get_date(self.due_date_edit),
            build_date=self._get_date(self.build_date_edit),
            updated_at=orig.updated_at,
            excel_row=orig.excel_row,
            fingerprint=orig.fingerprint,
            base_revision=orig.base_revision,
        )

        self.saved.emit(updated)
        self.status_label.setText("<span style='color: green;'>✓ Saved</span>")
        self._dirty = False
        self.dirty_changed.emit(False)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def _mark_dirty(self) -> None:
        if self._loading or self._dirty:
            return
        self._dirty = True
        self.dirty_changed.emit(True)

    def _update_target_hours(self) -> None:
        """Auto-calculate target hours = dept hours - IEC hours.

        For non-primary identicals the target must stay at 0 regardless
        of what is typed into Dept Hours or IEC Internal Hours.
        """
        if self.current_unit and self.current_unit.is_non_primary_identical:
            self.target_hours_spin.setValue(0.0)
            return
        dept = self.dept_hours_spin.value()
        iec = self.iec_hours_spin.value()
        self.target_hours_spin.setValue(max(0.0, dept - iec))

    def _set_date(self, widget: QDateEdit, d: date | None):
        if d is not None:
            widget.setDate(QDate(d.year, d.month, d.day))
        else:
            widget.setDate(QDate(2000, 1, 1))  # "unset" sentinel

    def _get_date(self, widget: QDateEdit) -> date | None:
        d = widget.date().toPyDate()
        if d.year == 2000 and d.month == 1 and d.day == 1:
            return None
        return d
