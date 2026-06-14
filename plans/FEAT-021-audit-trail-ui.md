# FEAT-021: Audit Trail & Change History Browser

**Status**: Draft  
**Priority**: High  
**Effort**: M (9 days)  
**Depends on**: ARCH-001, ARCH-002  
**Implements**: MOC-A (Change Audit Trail)  

---

## Problem Statement

The application has no change history tracking:

- **Who changed what?** — Unknown. No user attribution for edits.
- **When was it changed?** — Only `updated_at` timestamp, no history.
- **What was the previous value?** — Lost forever on save.
- **Can I revert?** — No undo/redo, no point-in-time recovery.
- **Conflict resolution** — User sees "modified by another user" but has no context of what changed or when.

---

## Proposed Solution

An audit log system that records every field-level change with user attribution, plus a UI for browsing, filtering, and reverting changes.

### Audit Schema

```sql
-- SQLite audit log table
CREATE TABLE IF NOT EXISTS _audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    com_number  TEXT NOT NULL,                    -- FK to units.com_number
    field       TEXT NOT NULL,                    -- field name (e.g., "percent_complete")
    old_value   TEXT,                              -- previous value (serialized)
    new_value   TEXT,                              -- new value (serialized)
    changed_by  TEXT NOT NULL DEFAULT '',          -- username@machine or API key
    changed_at  TEXT NOT NULL DEFAULT (datetime('now')),
    change_type TEXT NOT NULL DEFAULT 'edit',      -- 'edit' | 'import' | 'revert' | 'api'
    revision    INTEGER NOT NULL DEFAULT 0,        -- revision number at time of change
    metadata    TEXT                               -- JSON blob: source, client IP, etc.
);

CREATE INDEX idx_audit_com ON _audit_log(com_number);
CREATE INDEX idx_audit_time ON _audit_log(changed_at);
CREATE INDEX idx_audit_user ON _audit_log(changed_by);
CREATE INDEX idx_audit_type ON _audit_log(change_type);
```

### AuditService

```python
# services/audit_service.py

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from data.db import get_db
from data.models import Unit

logger = logging.getLogger(__name__)


@dataclass
class AuditEntry:
    id: int
    com_number: str
    field: str
    old_value: str | None
    new_value: str | None
    changed_by: str
    changed_at: str
    change_type: str
    revision: int
    metadata: dict | None = None


# Fields whose changes are NOT audited (noise reduction)
_SKIP_FIELDS = {
    "updated_at", "excel_row", "fingerprint", "base_revision",
    "working_days", "_milestones_cache", "due_date_changed",
    "is_non_primary_identical", "previous_detailing_due_date",
}


class AuditService:
    """Records and queries audit log entries."""
    
    def __init__(self, db_path: str, owner_id: str | None = None):
        self._db_path = db_path
        self._owner_id = owner_id or "unknown"
    
    def record_change(
        self,
        unit: Unit,
        old_unit: Unit | None,
        change_type: str = "edit",
        metadata: dict | None = None,
    ) -> None:
        """Record all field-level changes between old_unit and unit.
        
        If old_unit is None, records every editable field as "set" (initial state).
        """
        conn = get_db(self._db_path)
        cursor = conn.cursor()
        
        old_values = self._unit_to_dict(old_unit) if old_unit else {}
        new_values = self._unit_to_dict(unit)
        
        for field, new_val in new_values.items():
            if field in _SKIP_FIELDS:
                continue
            old_val = old_values.get(field)
            
            # Serialize dates and complex types
            old_str = self._serialize(old_val)
            new_str = self._serialize(new_val)
            
            if old_str == new_str and old_unit is not None:
                continue  # no change
            
            cursor.execute(
                """INSERT INTO _audit_log 
                   (com_number, field, old_value, new_value, changed_by, 
                    change_type, revision, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    unit.com_number,
                    field,
                    old_str,
                    new_str,
                    self._owner_id,
                    change_type,
                    unit.base_revision,
                    json.dumps(metadata) if metadata else None,
                )
            )
        
        conn.commit()
        if old_unit:
            logger.debug(
                f"Audited changes for {unit.com_number} by {self._owner_id}"
            )
    
    def get_history(
        self,
        com_number: str | None = None,
        changed_by: str | None = None,
        field: str | None = None,
        change_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Query audit log with filters."""
        conn = get_db(self._db_path)
        cursor = conn.cursor()
        
        where = []
        params = []
        
        if com_number:
            where.append("com_number = ?")
            params.append(com_number)
        if changed_by:
            where.append("changed_by = ?")
            params.append(changed_by)
        if field:
            where.append("field = ?")
            params.append(field)
        if change_type:
            where.append("change_type = ?")
            params.append(change_type)
        if date_from:
            where.append("changed_at >= ?")
            params.append(date_from)
        if date_to:
            where.append("changed_at <= ?")
            params.append(date_to)
        
        where_clause = " AND ".join(where) if where else "1=1"
        
        cursor.execute(
            f"SELECT * FROM _audit_log WHERE {where_clause} "
            f"ORDER BY changed_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset]
        )
        
        return [AuditEntry(**dict(row)) for row in cursor.fetchall()]
    
    def get_unit_history(self, com_number: str) -> list[AuditEntry]:
        """Get full change history for a single unit."""
        return self.get_history(com_number=com_number, limit=1000)
    
    def get_changes_by_user(self, user: str, limit: int = 100) -> list[AuditEntry]:
        """Get all changes made by a specific user."""
        return self.get_history(changed_by=user, limit=limit)
    
    def revert_change(self, entry_id: int) -> Unit | None:
        """Revert a single field change by audit entry ID.
        
        Returns the updated Unit, or None if the entry doesn't exist.
        This only reverts ONE field — not the entire unit state.
        """
        conn = get_db(self._db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM _audit_log WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        entry = AuditEntry(**dict(row))
        
        # Revert: set field back to old_value
        if entry.old_value is None:
            sql = f"UPDATE units SET {entry.field} = NULL WHERE com_number = ?"
            cursor.execute(sql, (entry.com_number,))
        else:
            sql = f"UPDATE units SET {entry.field} = ? WHERE com_number = ?"
            cursor.execute(sql, (entry.old_value, entry.com_number))
        
        conn.commit()
        logger.info(f"Reverted {entry.com_number}.{entry.field} to {entry.old_value}")
        
        # Reload and return the updated unit
        from data.loader import load_units
        units = load_units(self._db_path)
        for u in units:
            if u.com_number == entry.com_number:
                return u
        return None
    
    @staticmethod
    def _unit_to_dict(unit: Unit | None) -> dict[str, Any]:
        if unit is None:
            return {}
        return {
            "job_name": unit.job_name,
            "contract_number": unit.contract_number,
            "description": unit.description,
            "detailer": unit.detailer,
            "checking_status": unit.checking_status,
            "notes": unit.notes,
            "department_hours": unit.department_hours,
            "target_department_hours": unit.target_department_hours,
            "iec_internal_hours": unit.iec_internal_hours,
            "percent_complete": unit.percent_complete,
            "actual_hours": unit.actual_hours,
            "unit_detailing_start_date": 
                unit.unit_detailing_start_date.isoformat() if unit.unit_detailing_start_date else None,
            "unit_moved_to_checking_date":
                unit.unit_moved_to_checking_date.isoformat() if unit.unit_moved_to_checking_date else None,
            "unit_detailing_completion_date":
                unit.unit_detailing_completion_date.isoformat() if unit.unit_detailing_completion_date else None,
            "detailing_due_date":
                unit.detailing_due_date.isoformat() if unit.detailing_due_date else None,
            "dept_due_date_previous":
                unit.dept_due_date_previous.isoformat() if unit.dept_due_date_previous else None,
            "build_date":
                unit.build_date.isoformat() if unit.build_date else None,
        }
    
    @staticmethod
    def _serialize(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, float):
            return f"{value:.4f}"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)
```

### Audit Dialog UI

```python
# gui/audit_dialog.py

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QMessageBox,
)

from data.models import Unit
from services.audit_service import AuditService


class AuditDialog(QDialog):
    """Browse, filter, and revert change history."""
    
    def __init__(self, audit_service: AuditService, com_number: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._audit = audit_service
        self._com_number = com_number
        
        self.setWindowTitle(f"Change History{f' — COM {com_number}' if com_number else ''}")
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)
        
        layout = QVBoxLayout(self)
        
        # ── Filter bar ──
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Field:"))
        self.field_combo = QComboBox()
        self.field_combo.addItem("All Fields", "")
        for field in [
            "job_name", "contract_number", "description", "detailer",
            "department_hours", "percent_complete", "actual_hours",
            "detailing_due_date", "notes",
        ]:
            self.field_combo.addItem(field.replace("_", " ").title(), field)
        filter_layout.addWidget(self.field_combo)
        
        filter_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("All Types", "")
        self.type_combo.addItem("Edit", "edit")
        self.type_combo.addItem("Import", "import")
        self.type_combo.addItem("API", "api")
        self.type_combo.addItem("Revert", "revert")
        filter_layout.addWidget(self.type_combo)
        
        filter_layout.addStretch()
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._load_data)
        filter_layout.addWidget(self.refresh_btn)
        
        layout.addLayout(filter_layout)
        
        # ── History table ──
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Time", "COM #", "Field", "Old Value", "New Value",
            "Changed By", "Type"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)
        
        # ── Action buttons ──
        action_layout = QHBoxLayout()
        
        self.revert_btn = QPushButton("↩ Revert Selected Change")
        self.revert_btn.setToolTip("Revert the selected field to its previous value")
        self.revert_btn.clicked.connect(self._revert_selected)
        action_layout.addWidget(self.revert_btn)
        
        self.detail_btn = QPushButton("View Details")
        self.detail_btn.clicked.connect(self._show_detail)
        action_layout.addWidget(self.detail_btn)
        
        action_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        action_layout.addWidget(close_btn)
        
        layout.addLayout(action_layout)
        
        # Load data
        self._load_data()
    
    def _load_data(self) -> None:
        """Load audit entries with current filters."""
        field = self.field_combo.currentData() or None
        change_type = self.type_combo.currentData() or None
        
        entries = self._audit.get_history(
            com_number=self._com_number,
            field=field,
            change_type=change_type,
            limit=1000,
        )
        
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self.table.setItem(row, 0, QTableWidgetItem(entry.changed_at))
            self.table.setItem(row, 1, QTableWidgetItem(entry.com_number))
            self.table.setItem(row, 2, QTableWidgetItem(entry.field))
            self.table.setItem(row, 3, QTableWidgetItem(entry.old_value or "—"))
            self.table.setItem(row, 4, QTableWidgetItem(entry.new_value or "—"))
            self.table.setItem(row, 5, QTableWidgetItem(entry.changed_by))
            self.table.setItem(row, 6, QTableWidgetItem(entry.change_type))
            
            # Store entry ID for revert
            item = self.table.item(row, 0)
            if item:
                item.setData(Qt.UserRole, entry.id)
    
    def _revert_selected(self) -> None:
        """Revert the currently selected audit entry."""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Revert", "Please select a change to revert.")
            return
        
        entry_id = self.table.item(row, 0).data(Qt.UserRole)
        field = self.table.item(row, 2).text()
        old_val = self.table.item(row, 3).text()
        com = self.table.item(row, 1).text()
        
        reply = QMessageBox.question(
            self,
            "Confirm Revert",
            f"Revert {com}.{field} to '{old_val}'?\n\n"
            f"This will undo this specific field change.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        
        try:
            unit = self._audit.revert_change(entry_id)
            if unit:
                QMessageBox.information(
                    self, "Reverted", f"Successfully reverted {com}.{field}"
                )
                self._load_data()
            else:
                QMessageBox.warning(self, "Error", "Could not revert change.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Revert failed: {e}")
    
    def _show_detail(self) -> None:
        """Show a detail popup for the selected entry."""
        row = self.table.currentRow()
        if row < 0:
            return
        details = "\n".join(
            f"{self.table.horizontalHeaderItem(c).text()}: {self.table.item(row, c).text()}"
            for c in range(self.table.columnCount())
        )
        QMessageBox.information(self, "Change Details", details)
```

### Integration Points

```python
# 1. In UnitService.save() — record audit before save
def save(self, unit: Unit, version_stamp: str) -> Unit:
    old_unit = self.get_by_com(unit.com_number)
    result = super().save(unit, version_stamp)
    self._audit.record_change(unit, old_unit, change_type="edit")
    return result

# 2. In MainWindow — add audit button to right panel
def _init_right_panel(self) -> None:
    ...
    audit_btn = QPushButton("📋 History")
    audit_btn.clicked.connect(self._open_audit)
    auto_bar.addWidget(audit_btn)

def _open_audit(self) -> None:
    dlg = AuditDialog(
        self._audit_service,
        com_number=self.current_unit.com_number if self.current_unit else None,
        parent=self,
    )
    dlg.exec_()
```

---

## Implementation Phases

### Phase 1: Audit Table + Write Path (2 days)
1. Add `_audit_log` table to database schema
2. Implement `AuditService.record_change()` method
3. Integrate with `UnitService.save()` to record changes on every save
4. **Tests**: Verify audit entries created on save, verify field-level diffing, verify `_SKIP_FIELDS` exclusion

### Phase 2: Query API (2 days)
1. Implement `AuditService.get_history()` with all filter parameters
2. Implement `AuditService.get_unit_history()` and `get_changes_by_user()`
3. Implement `AuditService.revert_change()` with reverse update
4. **Tests**: Test filtering, pagination, revert correctness

### Phase 3: Audit Dialog UI (3 days)
1. Implement `AuditDialog` with filter bar, sortable table, action buttons
2. Add navigation: double-click COM to jump to unit in main view
3. Style with current theme (dark/light)
4. Wire into MainWindow right panel and Help menu
5. **Tests**: UI smoke tests, verify filter/sort/revert flows

### Phase 4: Revert + Blame (2 days)
1. Add "Show changes by user" view in Help menu
2. Add blame overlay on list panel (show last editor per field)
3. Add import event recording (CSV/SSRS imports create audit entries with change_type="import")
4. **Tests**: Test blame computation, import audit recording

---

## Success Criteria

1. Every save operation records field-level changes to `_audit_log`
2. Audit dialog loads and filters 10,000+ entries without lag
3. Revert correctly restores a single field to its previous value
4. Import operations are recorded with `change_type="import"` and source metadata
5. Blame view shows last editor for each unit

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Audit table grows unbounded | Medium | Add retention policy (90 days); archive to separate file |
| Revert of complex fields breaks | Low | Revert only works on scalar fields; dates are stored as ISO strings |
| Performance impact on every save | Low | Single INSERT per changed field; sub-millisecond |
| Old audit data after revert | Low | Revert creates a NEW audit entry (not deletion) |

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Table + Write | 2 |
| Phase 2: Query API | 2 |
| Phase 3: Audit Dialog UI | 3 |
| Phase 4: Revert + Blame | 2 |
| **Total** | **9** |