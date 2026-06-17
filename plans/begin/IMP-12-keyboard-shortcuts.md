# IMP-12: Keyboard Shortcuts

**Status**: NOT STARTED  
**Priority**: Medium  
**Effort**: Small  

## Objective

Add keyboard shortcuts for common actions: Ctrl+S (save), Ctrl+F (focus search), F5 (refresh), Escape (deselect), Delete (clear date).

## Background

The `MainWindow.keyPressEvent()` already handles some shortcuts:
- `Ctrl+S` — save (already implemented)
- `Ctrl+T` — toggle theme (already implemented)
- `F5` — refresh (already implemented)
- `Ctrl+F` — focus search (already implemented)
- `Escape` — deselect (already implemented)

What's missing: visual feedback in menus/tooltips, Delete key clearing dates in the edit form, and accessibility (screen reader announcements).

## Remaining Work

### 1. Delete key for date fields

The `ClearableDateEdit` class already handles Delete/Backspace to clear to the "unset" sentinel. This is done. Ensure the tooltip on each date field mentions "Press Delete to clear."

### 2. Tooltip documentation

Add keyboard shortcut hints to tooltips:
- Save button: "Save Changes (Ctrl+S)"
- Refresh button: "Reload data (F5)"
- Search field: "Search (Ctrl+F)"
- Theme button: "Toggle dark/light theme (Ctrl+T)"

### 3. Menu accelerator hints

The Help and Reports menus should show keyboard shortcuts in their text:
- "Scheduling Dashboard" (no shortcut)
- "Show Walkthrough" (no shortcut)

### 4. Accessibility

Add `setToolTip` descriptions that mention keyboard equivalents for all buttons.

## Testing

1. Press each shortcut and verify the correct action fires
2. Verify tooltips mention keyboard shortcuts
3. Verify Delete key works in date fields (already tested)

## Files to Modify

1. `gui/main_window.py` — Add tooltip strings with shortcut hints
2. `gui/edit_form.py` — Ensure ClearableDateEdit tooltips mention Delete key
3. `gui/list_panel.py` — Search field tooltip mentions Ctrl+F