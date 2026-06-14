# IMP-14: Inline Editing in List View

**Status**: NOT STARTED
**Priority**: Medium
**Effort**: Medium

## Objective

Allow editing of unit data directly from the list view without requiring the user to switch focus to the right-panel edit form. A compact inline editing bar appears when a row is selected, providing quick access to the most commonly edited fields.

## Background

Currently, editing a unit requires:
1. Click a row in the list view (or calendar)
2. The edit form populates in the right panel
3. User edits fields in the form
4. User clicks Save

This works but creates a context switch — the user's eyes and mouse have to travel across the screen. For quick edits (changing a due date, updating % complete, reassigning a detailer), an inline bar would be faster.

The existing `EditForm` widget handles all the complexity: dirty tracking, date sentinel values, target hours auto-calculation, optimistic locking, conflict detection. The inline bar should reuse this infrastructure, not duplicate it.

## Approach: Row Editor Bar

When a row is selected in the list view, a compact horizontal editing bar appears between the filter group and the table. It shows the selected unit's key editable fields. User edits, presses Enter or clicks Save, and the same `SaveWorker` pipeline fires.

**Why not cell-level delegates:** `QTableWidget` + cell delegates is clunky for dates (popup inside a cell), hard to validate, and would require rebuilding the save pipeline. The bar approach reuses `EditForm`'s logic and keeps the list view as a fast scanner.

## UI Layout

```
┌─ Filters ─────────────────────────────────────────────────────┐
│ Status: [All ▾]  Detailer: [All ▾]  Alert: [All ▾]  [✓ Stale]│
│ Date: [All ▾]  Due from: [__/__/____] to: [__/__/____]  ...  │
│ [Clear Filters]                              [Columns...]     │
├─ Edit Bar (visible when row selected) ────────────────────────┤
│ COM: 12345  │ Detailer: [Jackie H ▾] │ Due: [__/__/____] │  │
│ %: [___] │ Status: [gray ▾] │ Notes: [________] │ [💾] [↩] │
├─ Table ───────────────────────────────────────────────────────┤
│ COM    │ Due Date   │ Job Name      │ Detailer  │ Status │...│
│ 12345  │ 06/15/2026 │ Some Job Name │ Jackie H  │ ●      │   │
│ ...                                                            │
└────────────────────────────────────────────────────────────────┘
```

## Edit Bar Fields

The bar shows a subset of editable fields — the ones most likely to be changed in a quick-edit scenario:

| Field | Widget | Notes |
|---|---|---|
| COM Number | `QLabel` (read-only) | Identity, not editable |
| Detailer | `QComboBox` | Same dropdown as `EditForm`, populated from `config.default_detailers` |
| Detailing Due Date | `ClearableDateEdit` | Reuse existing class; Delete key clears to unset |
| % Complete | `QDoubleSpinBox` | 0–100, same as `EditForm` |
| Status | `QComboBox` | Manual status override: gray, yellow, purple, orange, green, red |
| Notes | `QLineEdit` | Single-line (not QTextEdit — keeps bar compact) |
| Save | `QPushButton` "💾 Save" | Triggers save |
| Revert | `QPushButton` "↩ Revert" | Resets bar to current unit state |

**Not in the bar** (available only in the right-panel `EditForm`):
- Job Name, Contract #, Description, Checking Status
- Dept Hours, IEC Hours, Target Hours, Actual Hours
- Start Date, Checking Date, Completion Date, Prev Due Date, Build Date

These are "identity" or "rarely changed" fields. The bar focuses on the operational fields: who, when, how far, what status.

## Behavior

### Selection
- Single-click a row → populate the bar from that unit
- Bar appears only when a unit is selected; hidden when selection is cleared
- If the user clicks a different row while the bar is dirty, show a discard warning (same pattern as `EditForm.dirty_changed`)

### Editing
- Any field change marks the bar as dirty
- Dirty state is tracked (same `_dirty` / `_loading` pattern as `EditForm`)
- Pressing Enter in any field triggers save
- Tab order follows the field left-to-right

### Save
- On save, collect bar data into a `Unit` object (preserving all non-bar fields from the original unit)
- Emit a `unit_saved(Unit)` signal from `ListPanel`
- `MainWindow` connects to this signal and routes through the existing `on_save_unit()` → `SaveWorker` → `writer.save_unit()` pipeline
- On success: bar shows brief "✓ Saved" feedback, table refreshes (already happens via `_on_save_finished`)
- On conflict: show the existing conflict dialog

### Revert
- Resets all bar fields to the current unit's values
- Clears dirty state

### Keyboard
- `Enter` in any field → save
- `Escape` → revert (if dirty) or clear selection (if clean)
- `Tab` → next field (standard)

## Architecture

### New widget: `InlineEditBar`

A `QWidget` subclass, owned by `ListPanel`. Lives between the filter group and the table in the layout.

```
InlineEditBar (QWidget)
  ├── QLabel (COM, read-only)
  ├── QComboBox (Detailer)
  ├── ClearableDateEdit (Due Date)
  ├── QDoubleSpinBox (% Complete)
  ├── QComboBox (Status)
  ├── QLineEdit (Notes)
  ├── QPushButton (Save)
  └── QPushButton (Revert)
```

**Signal:**
- `unit_saved(Unit)` — emitted when user clicks Save or presses Enter

**Public API:**
- `set_unit(unit: Unit | None)` — populate bar from unit, or clear/hide if None
- `is_dirty` property

### Changes to `ListPanel`

1. Add `InlineEditBar` between filter group and table in `_build_ui()`
2. Connect `unit_selected` signal → `InlineEditBar.set_unit()`
3. Connect `InlineEditBar.unit_saved` → new `ListPanel` signal `unit_saved`
4. Hide bar when no selection; show when row selected
5. Handle dirty-on-selection-change warning

### Changes to `MainWindow`

1. Connect `list_panel.unit_saved` → `MainWindow.on_save_unit()` (same slot the `EditForm.saved` signal uses)
2. No other changes — the save pipeline is already signal-driven

### Save data flow

```
InlineEditBar.set_unit(unit)          ← ListPanel emits unit_selected
InlineEditBar user edits fields
InlineEditBar._on_save()
  → constructs Unit (bar fields + preserved original fields)
  → emit unit_saved(unit)
    → ListPanel.unit_saved.emit(unit)
      → MainWindow.on_save_unit(unit)
        → SaveWorker → writer.save_unit() → SQLite
          → _on_save_finished()
            → _commit_unit_to_memory()
            → list_panel.refresh()  ← table updates
```

## Files to Modify

1. `gui/list_panel.py` — Add `InlineEditBar` widget, wire into layout and signals
2. `gui/main_window.py` — Connect `list_panel.unit_saved` to `on_save_unit()`

## Testing

1. Select a row → bar populates with that unit's data
2. Edit a field → bar becomes dirty
3. Click Save → unit saves, table refreshes, bar shows "✓ Saved"
4. Edit a field → click Revert → fields reset to original values
5. Edit a field → click different row → discard warning appears
6. Save with optimistic lock conflict → conflict dialog appears
7. Bar hidden when no row selected
8. Bar hidden when selection cleared
9. Enter key in any field triggers save
10. Escape key reverts dirty bar

## Open Questions

1. **Should the bar be collapsible?** Power users who never use inline edit might want it hidden. A toggle button or "pin" could work. Defer to v2 if requested.
2. **Should edits sync to the right-panel EditForm?** If the user opens the edit form after editing inline, the form should show the updated values. This already works via `_commit_unit_to_memory()` — the form repopulates from `self.current_unit` on selection change.
3. **Multi-select batch edit?** Out of scope. The bar edits one unit at a time. Batch operations are a separate feature (IMP-13).
