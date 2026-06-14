# IMP-017: Bulk Operations

**Status**: Draft  
**Priority**: Medium  
**Effort**: M (5 days)  
**Depends on**: ARCH-002  

---

## Problem Statement

No multi-select or batch editing capabilities exist:

| Operation | Current Behavior | Impact |
|-----------|-----------------|--------|
| Assign detailer to multiple units | Must edit each unit individually | 5+ minutes for 20-unit reassignment |
| Change due dates on a group | Manual per-unit | Error-prone, slow |
| Export filtered results | Only "all or nothing" Excel export | Can't export a focused subset |
| Clear notes on stale units | Manual per-unit | Tedious cleanup |

---

## Solution

Multi-select in the list panel with a batch edit dialog.

### Multi-Select in List Panel

```python
# gui/list_panel.py — additions

from PyQt5.QtCore import Qt


class ListPanel(QWidget):
    # Add to existing class
    
    def _enable_multi_select(self):
        """Enable multi-selection with checkboxes or Ctrl/Shift+click."""
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        
        # Ctrl+A — select all
        select_all_action = QAction("Select All", self)
        select_all_action.setShortcut(QKeySequence.SelectAll)
        select_all_action.triggered.connect(self._select_all)
        self.addAction(select_all_action)
        
        # Context menu for batch operations
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_batch_menu)
    
    def _select_all(self):
        self.table.selectAll()
    
    def get_selected_units(self) -> list[Unit]:
        """Return list of currently selected Unit objects."""
        selected = []
        for item in self.table.selectedItems():
            unit = item.data(Qt.UserRole)
            if unit and unit not in selected:
                selected.append(unit)
        return selected
    
    def _show_batch_menu(self, pos):
        """Show context menu with batch operations when multiple items selected."""
        selected = self.get_selected_units()
        if len(selected) < 2:
            return  # Show default single-item context menu
        
        menu = QMenu(self)
        menu.addAction(f"📝 Batch Edit ({len(selected)} units)", self._open_batch_dialog)
        menu.addAction("📋 Assign Detailer...", self._batch_assign_detailer)
        menu.addAction("📅 Set Due Date...", self._batch_set_due_date)
        menu.addAction("📤 Export Selected...", self._batch_export)
        menu.exec_(self.table.viewport().mapToGlobal(pos))
    
    def _open_batch_dialog(self):
        """Open batch edit dialog for selected units."""
        selected = self.get_selected_units()
        if not selected:
            return
        dlg = BatchEditDialog(selected, self._tag_repo, parent=self)
        if dlg.exec_():
            # Save changed units
            for unit in dlg.get_updated_units():
                self.parent().on_save_unit(unit)
```

### Batch Edit Dialog

```python
# gui/batch_edit_dialog.py

from PyQt5.QtCore import Qt, QDate
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QVBoxLayout, QWidget,
)


class BatchEditDialog(QDialog):
    """Dialog for applying common field values to multiple units."""
    
    def __init__(self, units: list[Unit], tag_repo=None, parent=None):
        super().__init__(parent)
        self._units = units
        self._tag_repo = tag_repo
        self._updated_units: list[Unit] = []
        
        self.setWindowTitle(f"Batch Edit — {len(units)} units")
        self.setMinimumWidth(450)
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
        self.detailer_combo.addItems(["-- Unassigned --", "Brandon B", "Jackie H", "Carl M", "David K", "Tommy N"])
        self.detailer_check.toggled.connect(self.detailer_combo.setEnabled)
        form.addRow(self.detailer_check, self.detailer_combo)
        
        # Due date
        self.due_date_check = QCheckBox("Change due date")
        self.due_date_edit = QDateEdit()
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
        self.pct_spin.setValue(50.0)
        self.pct_check.toggled.connect(self.pct_spin.setEnabled)
        form.addRow(self.pct_check, self.pct_spin)
        
        # Status
        self.status_check = QCheckBox("Set status color")
        self.status_combo = QComboBox()
        self.status_combo.setEnabled(False)
        self.status_combo.addItems(["", "gray", "yellow", "purple", "orange", "green", "red"])
        self.status_check.toggled.connect(self.status_combo.setEnabled)
        form.addRow(self.status_check, self.status_combo)
        
        layout.addLayout(form)
        
        # Progress bar (for multi-unit save)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Count warning
        if len(units) > 50:
            self.count_warning = QLabel(
                f"⚠️ Applying to {len(units)} units. This may take a moment."
            )
            self.count_warning.setStyleSheet("color: #f59e0b;")
            layout.addWidget(self.count_warning)
    
    def _apply(self):
        """Apply selected field changes to all units."""
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
            
            self.progress_bar.setValue(i + 1)
        
        self.accept()
    
    def get_updated_units(self) -> list[Unit]:
        return self._updated_units
```

### Integration

```python
# In MainWindow, add batch save handler
def on_batch_save(self, units: list[Unit]):
    """Save multiple units with progress tracking."""
    self._sync_status_session_total = len(units)
    self._sync_status_session_initial = len(units)
    self._sync_unit_durations = []
    
    for unit in units:
        self._start_save_worker(unit)
```

---

## Implementation Phases

### Phase 1: Multi-Select + Context Menu (3 days)
1. Enable `ExtendedSelection` mode in list panel table
2. Add Ctrl+A select all
3. Add context menu with batch operations
4. Implement `get_selected_units()`
5. **Tests**: Verify multi-select, select all, context menu visibility

### Phase 2: Batch Edit Dialog + Save (2 days)
1. Implement `BatchEditDialog` with field checkboxes
2. Wire save path through MainWindow with progress bar
3. Add batch export to CSV
4. **Tests**: Verify field changes applied to all selected units, verify progress bar

---

## Success Criteria

1. Multi-select works with Ctrl+click, Shift+click, Ctrl+A
2. Batch edit dialog changes apply to all selected units
3. Batch save shows progress bar
4. Batch export produces CSV with only selected units
5. No performance degradation with 500+ selected units

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Multi-Select + Menu | 3 |
| Phase 2: Batch Dialog + Save | 2 |
| **Total** | **5** |