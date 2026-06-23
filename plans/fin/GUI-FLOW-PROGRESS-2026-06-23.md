# GUI Flow Improvements — Implementation Progress Report

**Date:** 2026-06-23  
**Status:** Sprint 1 Complete, Sprints 2–4 Not Started  

## Summary

Implementation of the GUI Flow Improvement Plan has begun. **Sprint 1** (Core UX improvements) is fully implemented. Work on Sprints 2–4 remains.

---

## Sprint 1 — Core UX Improvements ✅ COMPLETE

### P6: Keyboard Shortcuts for View Switching
- **Files changed:** `gui/main_window.py`
- **What was done:** Added `Ctrl+1` → Calendar, `Ctrl+2` → List, `Ctrl+3` → Alerts to `keyPressEvent()`.
- **UI cues:** View button labels updated to show shortcuts: `"📅 Calendar (Ctrl+1)"`, `"📋 List (Ctrl+2)"`, `"🔔 Alerts (Ctrl+3)"`.
- **Tooltips:** Updated on toggle buttons to reflect shortcuts.

### P10: Alert Badge on View Toggle Buttons
- **Files changed:** `gui/main_window.py`
- **What was done:** Added `_update_alert_badge()` method that counts units with `calculated_status_color == "red"` (excluding stale). When count > 0, the Alerts button shows bold red text with the count: `"🔔 Alerts (5) (Ctrl+3)"`.
- **Called from:** `_on_load_finished()` after every data refresh.
- **Note:** Uses hardcoded `#dc2626` red for the badge. Plan recommends theme-aware colors — this is a known limitation for a follow-up.

### P12: Unsaved Changes Indicator in Window Title
- **Files changed:** `gui/main_window.py`
- **What was done:** Extended `_on_dirty_changed()` to prepend `"* "` to the window title when dirty state is `True`. Clears when save completes.
- **Known limitation:** The inline edit bar and edit form have separate save paths. Only the edit form's dirty flag is tracked here. See P20 (Sprint 4) for the unified fix.

### P15: Splitter Default Size Tuning
- **Files changed:** `gui/main_window.py`
- **What was done:** Changed default splitter ratio from 1:2 (33%/67%) to 1:1 (50%/50%). Set minimum panel widths: left panel = 300px, right panel = 350px.
- **Preservation:** User-saved splitter sizes (via config) are still honored.

### P16: View Title Labels
- **Files changed:** `gui/main_window.py`
- **What was done:** Added `view_title` QLabel above the view stack in the left panel. Updates on view switch with descriptive text:
  - Calendar: "📅 Calendar View — Upcoming due dates at a glance"
  - List: "📋 List View — Filtered sortable table of all units"
  - Alerts: "🔔 Alerts View — Per-detailer alert dashboard"

### P17: Blame Label Theme Compliance
- **Files changed:** `gui/list_panel.py`
- **What was done:** Removed hardcoded `color: #64748b` from blame_label stylesheet. Used **Option B** (simplest fix) — the label now inherits `QPalette.WindowText` from its parent, which changes with the theme.
- **Trade-off:** The blame label no longer has muted/secondary text styling, it matches normal text color. Option A (theme.py `findChild` approach) can be applied later for better visual distinction.

---

## Sprint 2 — Navigation & Search 🔴 NOT STARTED

### P1: Top-Level QToolBar
- **Status:** Not implemented
- **Effort:** Medium
- **Depends on:** None
- **Action needed:** Move Import CSV, Pull SSRS, Refresh, Export Excel to a `QToolBar` at the top of the main window. Move History button to edit_form as per plan (P11 merged into P1). Relocate sync status widget to status bar.

### P4: Global Search Bar
- **Status:** Not implemented
- **Effort:** Low
- **Depends on:** P1 (QToolBar, with fallback to left panel)
- **Action needed:** Add `QLineEdit` search field to toolbar with 300ms debounced search across `com_number`, `job_name`, `contract_number`. Auto-switch to List view on multi-match.

---

## Sprint 3 — Visual Polish & Space Optimization 🔴 NOT STARTED

### P2: Collapsible Timeline Panel
- **Status:** Not implemented
- **Effort:** Low
- **Action needed:** Add collapse toggle (▶/▼) to TimelinePanel header. Persist state in config.

### P8: Batch Mode Awareness in Right Panel
- **Status:** Not implemented
- **Effort:** Low
- **Action needed:** Add batch banner to right panel, connect `batch_mode_changed` signal from ListPanel. Disable right panel content when batch active.

### P13: Inline Edit Bar Repositioning
- **Status:** Not implemented
- **Effort:** Low
- **Action needed:** Reorder layout on selection to move InlineEditBar above the table (Option B from plan). Also fix docstring in `gui/inline_edit_bar.py` line 5 which incorrectly says "Appears between the filter group and the table" — it's actually below the table.

### P14: Theme Button Icon Rendering
- **Status:** Not implemented
- **Effort:** Low
- **Action needed:** Replace emoji ☀/🌙 with SVG icons or `QIcon.fromTheme()` calls. Create `resources/sun.svg` and `resources/moon.svg`.

### P18: Calendar Event Selection Feedback
- **Status:** Not implemented
- **Effort:** Low
- **Action needed:** Track selected unit in CalendarPanel, draw highlight border in `paintCell()`. Use `palette().color(QPalette.Highlight)` for theme compliance.

### P19: Right Panel Collapse Toggle
- **Status:** Not implemented
- **Effort:** Low
- **Action needed:** Add collapse toggle button (◀/▶) at splitter position. Persist state in config.

---

## Sprint 4 — UX Depth 🔴 NOT STARTED

### P5: Progress Dialogs for Long Operations
- **Status:** Not implemented
- **Effort:** Medium
- **Action needed:** Ship WaitCursor-first approach (MVP) for SSRS pull, CSV import, Excel export. Add threading with `_run_with_progress()` helper as follow-up.

### P9: Dedicated Notification Area
- **Status:** Not implemented
- **Effort:** High
- **Action needed:** Create `gui/notification_panel.py` with toast-like overlay. Replace 25+ `status_bar.showMessage()` calls with `_notify()`. Support INFO/SUCCESS/WARNING/ERROR types. Reserve status bar for persistent state only.
- **⚠️ This is the highest-effort item in the entire plan.** May need descoping.

### P20: Unified Edit State Model
- **Status:** Not implemented
- **Effort:** Medium
- **Depends on:** P8, P12
- **Action needed:** Create `EditState` class shared by inline edit bar and edit form. Single save path. Unifies dirty tracking.
- **⛓️ Dependency chain:** P8 + P12 must be done first. If P8 slips, P20's dependency chain breaks. Consider swapping P20 into Sprint 3 if P8 is delayed.

### P21: LoadingOverlay + NotificationPanel Coexistence
- **Status:** Not implemented
- **Effort:** Low
- **Depends on:** P9
- **Action needed:** Define Z-order (LoadingOverlay on top). Queue notifications during loading, flush on overlay dismiss.

---

## Files Modified (Sprint 1)

| File | Changes |
|------|---------|
| `gui/main_window.py` | P6 (shortcuts), P10 (alert badge), P12 (dirty title), P15 (splitter), P16 (view title) |
| `gui/list_panel.py` | P17 (blame label color removed) |

---

## Tests

**No tests were modified or created in Sprint 1.** All changes are UI-layer (MainWindow orchestration, cosmetic). The existing test suite should continue to pass. To verify:

```bash
cd c:\Users\jbrow263\Downloads\Code Projects\SQL-Schedule-App\SQL-Schedule-Tracker
python -m pytest tests/ -v -k "not qtest"  # Skip tests requiring Qt display
```

---

## Questions & Blockers

1. **P4 Search vs P1 Toolbar:** P4 (global search) depends on P1 (toolbar) for optimal placement, but has a fallback. Should we implement P4 before P1 using the left-panel fallback?

2. **P13 Docstring:** `gui/inline_edit_bar.py` line 5 docstring says "Appears between the filter group and the table" but it's actually below the table. Should we fix this in Sprint 3 as planned, or address it earlier since it's a documentation drift issue?

3. **Platform test:** The plan warns about KDE Plasma `Ctrl+1-9` conflict. The target environment is Windows 11 per SYSTEM INFORMATION, so this is not a concern for this deployment.

4. **P5 Threading complexity:** The WaitCursor-first approach is safe to implement without threading analysis. The full threading approach needs careful review of SQLite thread safety in the service layer.

---

*Report generated by Cline during implementation of GUI-FLOW-IMPROVEMENTS.md*