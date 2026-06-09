# MOC-A: Change Audit Trail

**Status**: PROPOSED
**Priority**: High
**Effort**: Medium
**MOC Principle**: Every change is recorded — what changed, when, and by whom

## Problem

When a user edits a unit (due date, detailer, status, hours), the change goes straight to SQLite. The `updated_at` timestamp records *when*, but there is no record of *what* changed or *who* changed it. When something goes wrong — a due date gets pushed, a detailer gets reassigned accidentally, hours are overwritten — there is no way to:

- See the history of a specific unit
- Understand what changed in the last sync/import
- Recover from an unwanted change
- Answer "who moved this unit's due date?"

This is the most fundamental gap in the current change management approach.

## Proposed Implementation

### Phase 1 — Change Log Table

Add a `change_log` SQLite table:

```sql
CREATE TABLE change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    com_number TEXT NOT NULL,
    field_changed TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT DEFAULT (datetime('now')),
    changed_by TEXT DEFAULT 'local',  -- username or session ID
    source TEXT DEFAULT 'manual',      -- 'manual', 'import', 'batch', 'sync'
    FOREIGN KEY (com_number) REFERENCES units(com_number)
);
CREATE INDEX idx_change_log_com ON change_log(com_number);
CREATE INDEX idx_change_log_time ON change_log(changed_at);
```

Write a trigger in `data/writer.py` → `save_unit()` that diffs the old Unit (from DB) vs new Unit (from form) and inserts one row per changed field into `change_log`.

### Phase 2 — Change History Dialog

Add a "History" button to the edit form (or right-click → "View Change History" in the list panel):

```
┌─────────────────────────────────────────────────┐
│ Change History — COM 20091                       │
├──────────┬────────────┬──────────┬──────────────┤
│ Field    │ Old Value  │ New Value│ When         │
├──────────┼────────────┼──────────┼──────────────┤
│ Due Date │ 2026-06-15 │ 2026-07-01│ 6/9 14:32  │
│ Detailer │ John Doe   │ Jane Smith│ 6/9 14:30  │
│ % Comp   │ 50%        │ 75%       │ 6/8 09:15  │
├──────────┴────────────┴──────────┴──────────────┤
│ [Revert Selected]            [Close]            │
└─────────────────────────────────────────────────┘
```

### Phase 3 — Change Summary on Import

After CSV/SSRS import, show a summary dialog of all changes detected:

- "3 units had due dates changed"
- "12 units were newly assigned to detailers"
- "5 units had completion percentages updated"

This uses the same `change_log` data — just aggregated by import session.

## Files to Modify/Create

1. `data/db.py` — Add `change_log` table schema + migration
2. `data/writer.py` — Diff old vs new unit on save, insert change_log rows
3. `gui/change_history_dialog.py` — New file, per-unit history viewer
4. `gui/edit_form.py` — "History" button
5. `gui/list_panel.py` — Right-click → "View Change History" context menu action
6. `automation/import_csv.py` — Tag change_log rows with source='import'
7. `gui/main_window.py` — Post-import change summary dialog

## Edge Cases

- **Bulk/batch operations**: Each unit gets its own change_log rows, all with the same `changed_at` and `source='batch'`
- **No actual change**: If the user clicks Save but nothing changed, no change_log entries
- **Import overwriting manual edit**: The `change_log` captures both — shows that the import overwrote a manual entry (field-level audit)
- **Revert**: Phase 2's "Revert Selected" button would apply the old_value back to the unit and save it (with its own change_log entry noting the revert)

## Pros

- **Complete change history** for every unit — answers "what happened" questions
- **"Who changed what"** accountability via `changed_by` field
- **Integration with existing sync** — the `source` field distinguishes manual edits from imports from multi-user sync
- **Revert capability** — one-click undo of specific field changes
- **Import transparency** — after pulling from SSRS, you can see exactly what the import changed
- **Low storage cost** — text table with indexed lookups, small footprint even with thousands of changes
- **Non-breaking** — additive schema change with migration

## Cons

- **Performance on save** — diff check + change_log inserts add overhead per save (mitigated: only when values actually change)
- **Storage growth** — active shops could generate hundreds of change_log rows per day (mitigated: auto-cleanup of entries older than N days, configurable)
- **Revert complexity** — reverting a due date doesn't automatically re-check dependent calculations (capacity warnings, stale status) — the recalculation happens on next load/save, not instantly
- **No approval gate** — this is informational only; it records changes but doesn't prevent them
- **Multi-user attribution** — `changed_by` defaults to 'local'; requires session registry integration to attribute to actual users

## Dependencies

- `sync/session_registry.py` for user attribution (optional — can default to 'local')
- IMP-13 (Batch Operations) — batch edits should use `source='batch'` in change_log
