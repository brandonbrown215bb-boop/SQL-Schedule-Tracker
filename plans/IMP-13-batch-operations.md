# IMP-13: Batch Operations

**Status**: NOT STARTED  
**Priority**: Low  
**Effort**: Large  

## Objective

Add multi-select support to the list panel for batch operations: reassign detailer, update status, shift due dates.

## Problem Statement

Users currently must edit units one at a time. For bulk operations (e.g., reassigning 20 units from "John" to "Jane" or shifting all due dates for a group by +7 days), this is time-consuming and error-prone.

## Proposed Scope

### Phase 1 — Multi-select in list panel

- Change `QTableWidget` selection mode from `SingleSelection` to `ExtendedSelection`
- Add a context menu or toolbar button: "Batch Edit…"
- Show a selection count in the status label: "Showing 50 of 200 units (12 selected)"

### Phase 2 — Batch edit dialog

Create a `BatchEditDialog` (new `gui/batch_edit_dialog.py`) with:

- **Detailer**: QComboBox with all detailers + "— No change —"
- **Due date offset**: QSpinBox for "Shift due dates by N days" (positive=future, negative=past)
- **Status color**: QComboBox with "— No change —" + all status colors
- **Notes append**: QTextEdit to append text to existing notes
- **Department hours**: QDoubleSpinBox with "— No change —" option
- **Apply button**: Applies changes to all selected units

### Phase 3 — Save

Iterate over selected units, apply changes, and call `save_unit()` for each. Show progress in status bar:

```
Saving batch: 5/12 complete...
```

### Phase 4 — Undo (stretch)

Since batch operations affect many units, a simple "revert to last saved" per unit (see IMP-15) is important. This could be an "Undo batch" button that reloads the affected units from the DB.

## UI Sketch

```
┌─────────────────────────────────────┐
│ Batch Edit — 12 units selected     │
│─────────────────────────────────────│
│ Detailer: [— No change — ▾]        │
│ Shift due dates by: [0] days       │
│ Status: [— No change — ▾]          │
│ Append to notes: [________________] │
│ Dept Hours: [— No change — ▾]      │
│                                     │
│     [Cancel]    [Apply]            │
└─────────────────────────────────────┘
```

## Edge Cases

- **Mixed selection**: Some units may have different current detailers — always use "— No change —" as default
- **Due date shift could push past build date**: Log a warning but still apply
- **Partial failure**: If some units fail to save (optimistic lock conflict), show which ones failed and continue with the rest
- **Progress indication**: Use `QProgressDialog` or status bar updates for long-running batches (50+ units)

## Files to Create/Modify

1. `gui/list_panel.py` — Change selection mode to ExtendedSelection
2. `gui/list_panel.py` — Add "Batch Edit…" button or context menu
3. `gui/list_panel.py` — Update status label with selection count
4. `gui/batch_edit_dialog.py` — New file, batch edit dialog
5. `gui/main_window.py` — Wire batch edit signal (selected units → dialog → save loop)

## Dependencies

- IMP-15 (undo/redo) would be a good companion — consider implementing before or alongside batch ops

## Testing

1. Select multiple units via Ctrl+click / Shift+click
2. Open batch dialog, change detailer, apply
3. Verify all selected units now have the new detailer
4. Verify save count matches selection count
5. Error handling: one unit fails, others succeed