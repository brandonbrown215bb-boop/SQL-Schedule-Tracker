# GUI Flow Improvement Plan

*Generated: 2026-06-16*  
*Last reviewed: 2026-06-23 (codebase audit) — corrections applied per review*

> This document catalogs interface-flow issues discovered during a comprehensive review of the application's GUI layer (`gui/` package + `main.py` orchestration). Each item includes a description of the problem, the affected files, and a concrete implementation guide for when the work is picked up.

---

## Pre-Implementation: Signal Ownership Model

> **Read this before implementing P3, P7, P8, P9, P12, or P13.**

This plan adds up to 6 new signals across 5 widgets, all converging on MainWindow. Without a clear ownership model, this becomes a debugging nightmare — signal cycles, double-fires, and ordering dependencies.

**Rules:**

1. **MainWindow owns shared state.** Active detailer filter, batch mode, and dirty state live in MainWindow. Panels *read* shared state on view switch. Panels *push* changes only when the user explicitly acts (not on internal state changes).

2. **One signal per concept.** `detailer_changed(str)` means the same thing whether it comes from ListPanel, CalendarPanel, or AlertPanel. Don't create `list_detailer_changed` and `calendar_detailer_changed` — that defeats the purpose.

3. **No signal chains.** If Panel A emits and Panel B relays, you have a chain. Instead, Panel A emits → MainWindow receives → MainWindow calls Panel B's `set_*()` method directly.

4. **Guard against re-entrancy.** Every signal handler that pushes state to other panels must check `if self._active_detailer != detailer:` before propagating. Without this, changing the detailer in ListPanel → updates MainWindow → pushes to AlertPanel → AlertPanel emits → updates MainWindow → infinite loop.

5. **Disconnect on view switch.** When `_switch_view()` changes the stacked widget index, signals from the now-hidden panel must not fire. Use `blockSignals(True)` on the hidden panel's filter widgets during the switch, or check `self.view_stack.currentIndex()` in handlers.

---

## Table of Contents

1. [Top-Level QToolBar for Global Operations](#p1-top-level-qtoolbar-for-global-operations)
2. [Collapsible Timeline Panel](#p2-collapsible-timeline-panel)
3. [Calendar View with Filters](#p3-calendar-view-with-filters)
4. [Persistent Global Search Bar](#p4-persistent-global-search-bar)
5. [Progress Dialogs for Long Operations](#p5-progress-dialogs-for-long-operations)
6. [Keyboard Shortcuts for View Switching](#p6-keyboard-shortcuts-for-view-switching)
7. [Cross-View Detailer Filter Persistence](#p7-cross-view-detailer-filter-persistence)
8. [Batch Mode Awareness in Right Panel](#p8-batch-mode-awareness-in-right-panel)
9. [Dedicated Notification Area](#p9-dedicated-notification-area)
10. [Alert Badge on View Toggle Buttons](#p10-alert-badge-on-view-toggle-buttons)
11. [Move History Button to Right Panel](#p11-move-history-button-to-right-panel)
12. [Unsaved Changes Indicator in Window Title](#p12-unsaved-changes-indicator-in-window-title)
13. [Inline Edit Bar Repositioning](#p13-inline-edit-bar-repositioning)
14. [Theme Button Icon Rendering](#p14-theme-button-icon-rendering)
15. [Splitter Default Size Tuning](#p15-splitter-default-size-tuning)
16. [View Title Labels](#p16-view-title-labels)
17. [Blame Label Theme Compliance](#p17-blame-label-theme-compliance)
18. [Calendar Event Selection Feedback](#p18-calendar-event-selection-feedback)
19. [Right Panel Collapse Toggle](#p19-right-panel-collapse-toggle)
20. [Unified Edit State Model](#p20-unified-edit-state-model)
21. [LoadingOverlay + NotificationPanel Coexistence](#p21-loadingoverlay--notificationpanel-coexistence)

---

## P1: Top-Level QToolBar for Global Operations

### Problem

The automation bar (Import CSV, Pull SSRS, Refresh, Export, History) lives inside the right panel at the bottom, sandwiched between the edit form and sync status widget. These are **global data operations**, not right-panel-specific actions. Their placement means:
- They consume valuable vertical space in the right panel that could be used by the edit form.
- "History" is a per-unit action grouped with database-wide operations — misleading.
- The right panel's layout becomes bottom-heavy with up to 5+ buttons in cramped rows.

### Implementation Guide

1. **Create a QToolBar in MainWindow._init_central_layout()**:
   - Instantiate `QToolBar()` with object name `"global_toolbar"`.
   - Set `setMovable(False)` to prevent user reordering.
   - Set icon size to 24x24 for readability.
   - **Note:** `QToolBar` + `QAction` has different sizing behavior than `QHBoxLayout` + `QPushButton`. Test on both themes — actions may appear smaller or differently spaced than the current buttons. Adjust `setIconSize()` and `setToolButtonStyle()` as needed.

2. **Move button creation from _build_automation_bar() to the new toolbar**:
   - Create: `Import CSV`, `Pull SSRS`, `Refresh`, `Export Excel` as `QAction` objects.
   - Connect each action to the existing handler methods (`_pull_csv`, `_pull_ssrs`, `_refresh_data`, `_export_excel`).
   - Add a separator between import/export operations and navigation.

3. **Remove the automation bar from _init_right_panel()**:
   - In `_init_right_panel()`, delete the `auto_bar = self._build_automation_bar()` call and its addition to the layout.
   - Delete or comment out `_build_automation_bar()` method entirely (verify no other callers).

4. **Move History action to right panel (was P11)**:
   - In `gui/edit_form.py`, in the `button_row` (where Save and Revert are), add a third button: `📋 History`.
   - Connect to a new signal `history_requested(Unit)` emitted by the edit form.
   - In MainWindow, connect `edit_form.history_requested` to `self._open_audit`.
   - `_open_audit()` already reads `self.current_unit.com_number`, so it will work for the current unit regardless of which button triggered it.

5. **Relocate sync status widget**:
   - The sync status widget is currently in the right panel. With the automation bar removed, move it to the status bar as a permanent widget (right-aligned). This frees the right panel entirely for content.

6. **Remove empty space**:
   - The right panel layout no longer needs the outer `QVBoxLayout(outer)` wrapping; simplify the right panel layout to just Timeline + EditForm.

### Files to Modify

- `gui/main_window.py` — `_init_central_layout()`, `_init_right_panel()`, `_build_automation_bar()`, `_build_help_menu()` (may need reorder)
- `gui/edit_form.py` — add History button inside the form, emit `history_requested` signal

---

## P2: Collapsible Timeline Panel

### Problem

The TimelinePanel has a fixed minimum height of 220px (dynamically grows to fit milestones). This compresses the EditForm — the primary action surface — especially on smaller screens (1366×768). The user may want to reclaim vertical space for the edit form.

### Implementation Guide

1. **Add collapse toggle to TimelinePanel**:
   - In `gui/timeline_panel.py`, change the header layout from a QLabel to a QWidget with a QHBoxLayout.
   - Add a `QToolButton` toggle arrow (▶/▼ style) on the left side of the header.
   - Store collapsed state as `self._collapsed: bool`.

2. **Implement collapse/expand logic**:
   - When collapsed: hide the `TimelineWidget` (the custom paint widget). Set a fixed small height on the panel (e.g. `setFixedHeight(header_height + 8)`).
   - When expanded: show the timeline widget, restore dynamic height via `setMinimumHeight(...)` / `setMaximumHeight(...)`.
   - Toggle the arrow icon between ▶ (collapsed, points right) and ▼ (expanded, points down).

3. **Persist collapse state in config**:
   - Emit a signal `collapse_changed(bool)` that MainWindow connects to, which saves to `self._services.config["ui"]["timeline_collapsed"]`.
   - On MainWindow init, read the saved state and apply it before the timeline is first painted.
   - **Default state on first launch: expanded.** New users should see the timeline immediately so they understand what it is.

4. **Smooth transition (follow-up, not sprint scope)**:
   - Use a `QPropertyAnimation` on `maximumHeight` for a smooth collapse/expand animation (200ms ease-in-out).
   - Ship the instant collapse/expand first. Add animation in a follow-up if there's time.

### Files to Modify

- `gui/timeline_panel.py` — header, collapse toggle, `set_unit()` conditional height
- `gui/main_window.py` — save/restore collapse state, connect signal

---

## P3: Calendar View with Filters

### Problem

CalendarPanel has no filtering capability — it displays dots for all non-stale units. With 500+ units, every date cell is a dense cluster of 5+ dots with a "99+" badge. The user cannot narrow the calendar to a specific detailer, status, or date range without switching to List view.

### Implementation Guide

1. **Add compact filter bar above the calendar**:
   - Insert a `QHBoxLayout` between the header ("Calendar" + "Today" button) and the `EventCalendarWidget`.
   - Add a `QComboBox` for "Detailer:" (populated from unit list).
   - Add a `QComboBox` for "Status:" using the same `STATUS_LABELS` keys.
   - Keep them compact with `setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)`.

2. **Wire filters to calendar dots**:
   - Store filter state as `self._filter_detailer: str = "All"` and `self._filter_status: str = "All"`.
   - On filter change, call `self.calendar.set_events(filtered_units)` where `filtered_units` applies the selected filter(s) to `self.units`.
   - Re-populate the event list for the currently selected date.

3. **Preserve filter state**:
   - Save calendar filter state to config similar to list panel filters.

4. **Layout note**: The calendar already has a header row with "Today" button. Adding a filter bar above the calendar widget means the left panel gets taller. On 1366×768, this could push the calendar grid below the fold. Integrate filters into the existing header row (same row as "Today" button) rather than adding a new row, or make the filter bar collapsible.

### Files to Modify

- `gui/calendar_panel.py` — filter bar UI, filter application
- `gui/main_window.py` — state preservation across view switches

---

## P4: Persistent Global Search Bar

### Problem

`Ctrl+F` only works in List view and focuses the list panel's search field. In Calendar or Alerts view, there is no search capability at all. Users must switch to List view to find a unit by COM number, job name, or contract number.

### Implementation Guide

1. **Add search field to the new top-level QToolBar** (see P1):
   - Insert a `QLineEdit` widget into the toolbar using `toolbar.addWidget(...)`.
   - Set placeholder text: "Search COM #, job name, or contract…".
   - Set a fixed width of ~250px.
   - Enable clear button: `setClearButtonEnabled(True)`.
   - **Fallback:** If P1 is not yet implemented, place the search bar in the left panel above the view stack (below the view toggle buttons). P4 should not block on P1.

2. **Implement global search logic in MainWindow**:
   - On every keystroke (debounced at 300ms), filter `self.units` by the query string.
   - Match against: `com_number.lower()`, `job_name.lower()`, `contract_number.lower()`.
   - If exactly one unit matches: auto-select it on Enter key press. **Do not auto-select while the user is still typing** — this would be disruptive if the user is refining a query. Require Enter to confirm.
   - If multiple match: switch to List view and apply the search filter to the list panel's search field.
   - **Warning:** If a background refresh fires while the user is typing, the search results and the data model can desync. Re-run the search query after every data refresh.

3. **Keyboard shortcut**:
   - Keep `Ctrl+F` bound to the existing handler, but change the handler to focus the toolbar search field instead of the list panel search.
   - Add `Ctrl+Shift+F` to focus the List panel search (advanced search with all filters visible).

4. **Clear search on Escape**:
   - When the search field has focus and Escape is pressed, clear the field and restore the previous view.

### Files to Modify

- `gui/main_window.py` — toolbar search bar, `keyPressEvent` update, search logic
- `gui/list_panel.py` — optionally accept external search text injection

---

## P5: Progress Dialogs for Long Operations

### Problem

SSRS pull, CSV import, and Excel export show only a status bar message. The `LoadingOverlay` exists but is only used for initial data load. Multi-minute operations (especially SSRS pulls) give the user no indication of progress, and the UI remains seemingly unresponsive.

### Implementation Guide

1. **Ship WaitCursor-first approach** (MVP):
   - Set `setCursor(Qt.WaitCursor)` on the MainWindow and re-show the `LoadingOverlay` during the operation.
   - This is the minimum viable fix. Ship this first, add threading in a follow-up if there's time.

2. **Threaded approach** (follow-up, not sprint scope):
   - Create a reusable `_run_with_progress(description: str, fn: callable)` helper.
   - Show a `QProgressDialog` with `setWindowTitle(description)`, `setLabelText("Processing...")`, `setMinimumDuration(1500)` (only show if operation takes >1.5s).
   - Use `setRange(0, 0)` for indeterminate progress (marquee style) since these operations don't report step counts.
   - **Threading complexity warning:** The current codebase is entirely synchronous. Adding background threads means:
     - Thread safety for the SQLite connection (currently per-thread, but services aren't thread-safe)
     - Progress reporting from worker thread to GUI thread (requires signals)
     - Cancellation support (what happens if the user clicks Cancel mid-import?)
     - Error propagation from worker thread to GUI thread (use `pyqtSignal` to marshal errors back)
   - Do not attempt threading in the same sprint as P5's MVP. Ship WaitCursor first.

3. **Wrap specific operations**:
   - **SSRS pull** (`_pull_ssrs`): wrap the `import_service.from_ssrs(...)` call.
   - **CSV import** (`_pull_csv`): wrap the `import_service.from_csv(...)` call after the preview dialog is approved.
   - **Excel export** (`_export_excel`): wrap the `export_service.to_excel(...)` call.

4. **Error handling**:
   - If the background thread raises, catch and show the error via the existing `QMessageBox.warning` pattern from the main thread using `pyqtSignal`.

### Files to Modify

- `gui/main_window.py` — `_run_with_progress()`, `_pull_ssrs()`, `_pull_csv()`, `_export_excel()`
- `gui/loading_overlay.py` — optionally add a text label to show current operation name

---

## P6: Keyboard Shortcuts for View Switching

### Problem

Switching between Calendar, List, and Alerts views requires a mouse click on the toggle buttons. Power users working through 100+ units per session will benefit from keyboard shortcuts for rapid context switching.

### Implementation Guide

1. **Register shortcuts in MainWindow.keyPressEvent()**:
   - `Ctrl+1` → switch to Calendar view (index 0).
   - `Ctrl+2` → switch to List view (index 1).
   - `Ctrl+3` → switch to Alerts view (index 2).
   - **Conflict warning:** KDE Plasma uses `Ctrl+1-9` for virtual desktop switching by default. Test on the target environment (KDE Plasma on Manjaro). If there's a conflict, use `Ctrl+Alt+1/2/3` instead, or document how to disable the Plasma shortcut.

2. **Add to existing keyPressEvent**:
   - Add three new `if` branches after the existing shortcuts:
     ```python
     if a0.key() == Qt.Key_1 and a0.modifiers() & Qt.ControlModifier:
         self._switch_view("calendar")
         return
     if a0.key() == Qt.Key_2 and a0.modifiers() & Qt.ControlModifier:
         self._switch_view("list")
         return
     if a0.key() == Qt.Key_3 and a0.modifiers() & Qt.ControlModifier:
         self._switch_view("alerts")
         return
     ```
   - **Audit existing shortcuts first:** `Ctrl+T` is used for theme toggle, `Ctrl+F` for list search. Verify no conflicts before adding.

3. **Add visual cues**:
   - Update the view toggle button tooltips to show the shortcuts:
     - "📅 Calendar (Ctrl+1)"
     - "📋 List (Ctrl+2)"
     - "🔔 Alerts (Ctrl+3)"

4. **Document in help menu**:
   - Add a "Keyboard Shortcuts" option to the Help menu that shows a dialog listing all shortcuts.

### Files to Modify

- `gui/main_window.py` — `keyPressEvent()`, `_init_left_panel()` button tooltips, help menu
- `gui/list_panel.py` — verify no shortcut conflicts

---

## P7: Cross-View Detailer Filter Persistence

> **Depends on P3.** P3 must be implemented first so CalendarPanel has a `set_detailer()` method to receive propagated filters.

### Problem

When filtering by a specific detailer in Alerts view, switching to Calendar or List view loses that detailer filter. The user must re-select the detailer each time they switch views, breaking workflow continuity.

### Implementation Guide

1. **Store active detailer in MainWindow**:
   - Add `self._active_detailer: str = "All"` to `MainWindow.__init__()`.
   - Add `self._active_status: str = "All"` for status filter persistence.

2. **Unified filter change propagation**:
   - Create a method `_on_global_detailer_changed(detailer: str)` in MainWindow.
   - Have each panel emit a `detailer_changed` signal when its local detailer filter changes.
   - Connect all panels to propagate: when the user changes detailer in any view, update `self._active_detailer` and push to all panels that support detailer filtering.
   - **Opt-in per view:** Not every view should automatically receive the filter. The user might want to see all units in the Calendar while filtering the List to one detailer. Add a "link filters" toggle (small chain-link icon button near the view toggle) that enables/disables cross-view propagation. Default: disabled.

3. **⚠️ AlertPanel needs a `detailer_changed` signal (currently missing):**
   - **Codebase finding:** The current `AlertPanel` (line 168 of `gui/alert_panel.py`) defines only `unit_selected = pyqtSignal(object)` — **no `detailer_changed` signal exists**.
   - **Fix:** Add `detailer_changed = pyqtSignal(str)` to `AlertPanel`.
   - **Wire:** Emit `self.detailer_changed.emit(new_detailer)` from both:
     - `AlertPanel._on_detailer_changed()` — when user picks a new detailer from the combo.
     - `AlertPanel.set_detailer(name)` — when the detailer is set programmatically via cross-view propagation.
     - Guard `set_detailer()` against re-entrancy: only emit if the value actually changed.

4. **Apply on view switch**:
   - In `_switch_view(view_name)`, after setting the view stack index, call:
     - Calendar: `self.calendar_panel.set_detailer(self._active_detailer)` (only if P3 is implemented and "link filters" is enabled)
     - List: if detailer combo exists, set its value to `self._active_detailer`
     - Alerts: `self.alert_panel.set_detailer(self._active_detailer)`

5. **Partial filter carry-over**:
   - Status filter is List-specific (paint dot colors). Don't force status across views.
   - Date range filter is List-specific. Don't carry over to Calendar/Alerts.

### Files to Modify

- `gui/alert_panel.py` — **add `detailer_changed = pyqtSignal(str)`**, emit from `_on_detailer_changed()` and `set_detailer()`
- `gui/main_window.py` — `_active_detailer`, `_on_global_detailer_changed()`, `_switch_view()` apply logic
- `gui/calendar_panel.py` — add `set_detailer()` and `detailer_changed` signal (if P3 implemented)
- `gui/list_panel.py` — emit `detailer_changed` when its combo changes

---

## P8: Batch Mode Awareness in Right Panel

### Problem

When the user selects 2+ rows in List view, a batch edit bar appears below the table in the left panel. The right panel continues to show the Timeline and EditForm for the *last single-selected* unit. There is no visual indication on the right side that batch mode is active, which is confusing.

### Implementation Guide

1. **Create a batch mode notification in the right panel**:
   - Add a `QFrame` or `QLabel` at the top of the right panel (above the timeline) with object name `"batch_banner"`.
   - Style: yellow/amber background, bold text: "📦 Batch Mode — N units selected".
   - Hidden by default.

2. **Connect batch state from list panel to right panel**:
   - In `ListPanel._update_batch_bar()`, emit a new signal `batch_mode_changed(int)` where the int is the count of selected units (0 means no batch).
   - In MainWindow, connect this signal to a handler that shows/hides the batch banner in the right panel.

3. **Dim/hide right panel content**:
   - When batch mode is active, either:
     - **Option A**: Set the TimelinePanel and EditForm to `setEnabled(False)` (grayed out but visible).
     - **Option B**: Replace the right panel content with a "Batch editing N units" placeholder widget.
   - Prefer Option A as it's simpler and lets the user still see the last selected unit's data.

4. **Dismiss inline edit bar on multi-select**:
   - When the user transitions from single-select to multi-select, the inline edit bar should be hidden and any in-progress inline edits discarded. The batch bar replaces it as the editing surface.
   - When the user transitions from multi-select back to single-select, the inline edit bar reappears for the newly selected row.

5. **Batch mode exit**:
   - When the user clears selection (batch count drops to 0), re-enable the right panel content.

### Files to Modify

- `gui/list_panel.py` — add `batch_mode_changed` signal, emit from `_update_batch_bar()`
- `gui/main_window.py` — connect signal, show/hide batch banner, disable/enable right panel
- `gui/edit_form.py` — no changes needed (handled externally)
- `gui/timeline_panel.py` — no changes needed (handled externally)

---

## P9: Dedicated Notification Area

### Problem

All messages compete for the single-line QStatusBar: loading messages, save confirmations (3s), errors, presence info, auto-refresh countdown. Messages of different importance (transient info vs persistent alerts) use the same channel, and overlapping timers cause jarring text flickering.

### Implementation Guide

1. **Create a notification overlay widget**:
   - In `gui/`, create `notification_panel.py` with a `NotificationPanel(QWidget)` class.
   - It should be a toast-like overlay anchored to the bottom-center of the MainWindow.
   - Support multiple notification types: `INFO`, `SUCCESS`, `WARNING`, `ERROR`.
   - Each notification auto-dismisses after a configurable timeout (default 4s for INFO, 8s for ERROR).
   - Style with colored left border (green for SUCCESS, red for ERROR, yellow for WARNING).
   - **Stacking behavior:** If multiple notifications fire in quick succession, stack them vertically (newest at bottom). Maximum 3 visible at a time — older ones auto-dismiss to make room. Each notification slides in from the bottom and fades out on dismiss.

2. **Integrate into MainWindow**:
   - In `_init_central_layout()`, overlay the `NotificationPanel` on top of the `main_splitter`.
   - Replace direct `self.status_bar.showMessage(...)` calls with `self._notify(message, type=..., timeout=...)` in the 10+ locations where status bar messages are set.

3. **Reserve status bar for persistent state**:
   - Keep only: loaded unit count, sync status, presence indicator.
   - Show these as permanent widgets on the status bar.

4. **Migration**:
   - Replace all `self.status_bar.showMessage("...", ...)` calls (search for ~27 occurrences) with `self._notify()` calls.
   - Each replacement maps the message duration to the appropriate notification type:
     - "✓ Saved..." → SUCCESS, 3s
     - "Save failed..." → ERROR, 8s
     - "Loading..." → INFO, auto-dismiss once finished
     - "Auto-refresh: 5min" → INFO, 3s

5. **Coexistence with LoadingOverlay**: The `LoadingOverlay` (used for initial data load) and `NotificationPanel` are both overlay widgets. Define a Z-order: `LoadingOverlay` is always on top (it blocks interaction), `NotificationPanel` is below it. Notifications that fire while the `LoadingOverlay` is visible should be queued and displayed after the overlay is dismissed.

### Files to Modify

- `gui/notification_panel.py` — NEW file
- `gui/main_window.py` — 25+ status bar message replacements, integrate overlay
- `gui/__init__.py` — export NotificationPanel

---

## P10: Alert Badge on View Toggle Buttons

### Problem

The Alert view contains actionable information (overdue units, capacity warnings, checking surge detection) but users must click the "🔔 Alerts" button to discover there are issues. There's no hint that alerts are waiting.

### Implementation Guide

1. **Compute alert counts per panel**:
   - In `MainWindow`, after data load, compute:
     - `self._alert_critical_count`: count of units with `calculated_status_color == "red"`.
     - `self._alert_checking_surge_count`: count of units in checking surge.
   - Store these counts.

2. **Update the Alerts button text**:
   - In `_init_left_panel()`, initially set the Alerts button text to `"🔔 Alerts"`.
   - After load, if `_alert_critical_count > 0`, update to `f"🔔 Alerts ({_alert_critical_count})"`.
   - Style the button differently when count > 0: red text or bold font.

3. **Update counts on every data refresh**:
   - In `_on_load_finished()`, after setting `self.units`, recalculate counts and update the button.
   - In `_on_save_finished()`, similar recalculation (a unit may have been marked complete).

4. **Extend to Calendar and List counts (optional)**:
   - Show overdue count on Calendar button.
   - Show total loaded count on List button.
   - Avoid making buttons too wide — keep badges short.

5. **Theme compliance**: Badge styling (red text or bold font when count > 0) must work in both light and dark themes. Use `palette().color(QPalette.Highlight)` or `palette().color(QPalette.Text)` — never hardcode a color value.

### Files to Modify

- `gui/main_window.py` — `_init_left_panel()`, `_on_load_finished()`, `_on_save_finished()`, badge update helper

---

## P11: Move History Button

> **Merged into P1.** The History button is now part of P1's implementation guide (step 4). This item is tracked as part of P1 and should not be estimated or scheduled separately.

---

## P12: Unsaved Changes Indicator in Window Title

### Problem

Dirty state is tracked internally (`_form_dirty`, `_inline_edit_bar.is_dirty`) but not visible in the window title. When multiple windows might be open, or when the user alt-tabs away and returns, there's no immediate visual cue that unsaved work exists.

### Implementation Guide

1. **Update window title on dirty state change**:
   - In `MainWindow._on_dirty_changed(dirty: bool)` (already connected from EditForm), update the window title:
     ```python
     def _on_dirty_changed(self, dirty: bool) -> None:
         self._form_dirty = dirty
         base_title = "Unit Tracker"
         if dirty:
             self.setWindowTitle(f"* {base_title}")
         else:
             self.setWindowTitle(base_title)
     ```

2. **Handle inline edit bar dirty state**:
   - The InlineEditBar doesn't dirty the MainWindow's form dirty flag. Add a new signal `inline_dirty_changed(bool)` from ListPanel.
   - In MainWindow, connect it and combine with `_form_dirty` to determine if ANY unsaved changes exist.

3. **Clear indicator on save**:
   - After a successful save (`_on_save_finished()`), set title back to base (already happens via `_on_dirty_changed(False)` emitted by EditForm).

4. **Set base title on app load**:
   - In `__init__()`, call `self.setWindowTitle("Unit Tracker")` — already done.

5. **⚠️ Known Limitation (Sprint 1 → Sprint 4 gap):**
   - P12 is implemented in Sprint 1, **but** the inline edit bar and edit form have separate save paths and separate dirty flags. With this Sprint 1 implementation, the window title will correctly show `*` when inline bar changes exist, **but the correct save path may be ambiguous** — only `UnitService.save()` via whichever surface triggered the save will fire.
   - If the user makes changes in *both* the inline bar and the edit form before saving, only the save path of the last-triggered surface fires. The other side's changes are silently lost.
   - **This gap is resolved by P20 (Unified Edit State Model, Sprint 4).** Do not attempt to fix it here — just ship the visual indicator. Document that the inline+form interaction caveat is a known limitation until P20 lands.

### Files to Modify

- `gui/main_window.py` — `_on_dirty_changed()`, connect inline dirty signal, `_on_save_finished()` title reset
- `gui/list_panel.py` — emit `inline_dirty_changed` signal from `_inline_edit_bar`

---

## P13: Inline Edit Bar Repositioning

### Problem

The InlineEditBar appears *below* the QTableWidget when a row is selected. If the table has hundreds of rows and the user selects a row near the bottom, the inline bar may be below the visible viewport — the user has to scroll down to see it. This defeats the purpose of "inline" editing.

### Implementation Guide

1. **Current layout** (codebase verified):
   ```
   VBoxLayout:
     [Filter Group]
     [QTableWidget]  (stretch=1)
     [InlineEditBar]  (fixed height)      ← line 577 of gui/list_panel.py
     [Batch Bar]      (hidden until multi-select)
     [Status Label]
     [Blame Label]
   ```

   > **Note:** The InlineEditBar's own docstring says "Appears between the filter group and the table" but this is inaccurate — it's below the table. The layout diagram above is the correct one. When implementing this P13, also fix the docstring in `gui/inline_edit_bar.py` line 5.

2. **Option A: Pin to reference row**:
   - Instead of adding InlineEditBar to the main layout, add it as a **sticky widget** inside the table's viewport.
   - Use `self.table.setViewportMargins(0, 0, 0, inline_bar_height)` and position the bar absolutely at the bottom of the viewport.

3. **Option B: Slide from top of table**:
   - When a row is selected, insert the InlineEditBar between the filter group and the table (reorder layout).
   - This requires removing it from position 2 and inserting at position 1:
     ```python
     layout.removeWidget(self._inline_edit_bar)
     layout.insertWidget(1, self._inline_edit_bar)  # After filter group
     ```

4. **Option C: Keep below but auto-scroll**:
   - When a row is selected, if the inline bar is not visible (`isVisible()` + check viewport), auto-scroll the table down by `inline_bar_height + 10` pixels.
   - This is the simplest fix but least user-friendly.

5. **Recommendation**: Implement Option B (reorder layout on selection) — it's clean and keeps the bar always visible at the top of the data area.
   - **Relayout flash warning:** Removing and re-inserting a widget from a `QVBoxLayout` at runtime causes a visible relayout flash. Test on the target hardware to ensure it's acceptable.
   - **Deselect behavior:** When the selection is cleared, move the bar back to its original position (below the table). This means the layout reorders twice per selection cycle (bottom → top on select, top → bottom on deselect). If this proves jarring, keep the bar at the top permanently once the first selection is made.
   - **Also update the docstring** of `gui/inline_edit_bar.py` to say "Appears below the table" instead of "between filter group and table".

### Files to Modify

- `gui/list_panel.py` — `_build_ui()` layout reordering, `_on_selection_changed()` to ensure bar is visible
- `gui/inline_edit_bar.py` — fix docstring line 5 to match actual layout

---

## P14: Theme Button Icon Rendering

### Problem

The theme toggle button uses emoji characters `☀` (light mode) and `🌙` (dark mode). Emoji rendering varies significantly across OS platforms and may appear as tofu boxes (□) on some Linux configurations without color emoji fonts installed.

### Implementation Guide

1. **Replace emoji with SVG icons**:
   - Create two SVG icon files in a new `resources/` directory:
     - `resources/sun.svg` — 16×16 sun icon for dark mode indicator
     - `resources/moon.svg` — 16×16 moon icon for light mode indicator
   - Use simple, reliably-rendered paths (no emoji).

   **Sun SVG**:
   ```svg
   <svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
     <circle cx="8" cy="8" r="3" fill="#currentColor"/>
     <line x1="8" y1="1" x2="8" y2="3" stroke="#currentColor" stroke-width="1.5"/>
     <line x1="8" y1="13" x2="8" y2="15" stroke="#currentColor" stroke-width="1.5"/>
     <line x1="1" y1="8" x2="3" y2="8" stroke="#currentColor" stroke-width="1.5"/>
     <line x1="13" y1="8" x2="15" y2="8" stroke="#currentColor" stroke-width="1.5"/>
   </svg>
   ```
   **Moon SVG**:
   ```svg
   <svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg">
     <path d="M13 8.5A5.5 5.5 0 0 1 7.5 3a5.5 5.5 0 0 0 5.5 5.5z" fill="#currentColor"/>
   </svg>
   ```

2. **Use QIcon.fromTheme or QPixmap**:
   ```python
   from PyQt5.QtGui import QIcon, QPixmap
   from PyQt5.QtSvg import QSvgRenderer
   # Or use QPixmap.load() with PNG fallback
   self.theme_btn.setIcon(QIcon("resources/sun.svg"))
   ```

3. **Update _apply_theme_by_name**:
   - Replace `self.theme_btn.setText("☀" if ...)` with `self.theme_btn.setIcon(...)`.

4. **Cross-platform fallback**:
   - If `QSvgRenderer` is too heavy, embed simple Unicode characters that are reliably rendered across platforms, such as `\u2600` (☀), `\u263E` (☾).
   - **Preferred fallback:** Use `QIcon.fromTheme("weather-clear")` / `QIcon.fromTheme("weather-clear-night")` — these exist on most Linux DEs (including KDE Plasma) and don't require shipping SVG files. Fall back to SVG only if the theme icon is not available.

### Files to Modify

- `gui/main_window.py` — `_init_left_panel()`, `_apply_theme_by_name()`
- `resources/sun.svg` — NEW file
- `resources/moon.svg` — NEW file

---

## P15: Splitter Default Size Tuning

### Problem

The default splitter ratio is 1:2 (left panel:right panel). The left panel contains the data views (Calendar/List/Alerts) which are the primary browsing surface. The right panel contains the Timeline (secondary) and EditForm (primary action). The current ratio gives too much space to the right panel, which has poor space utilization: the Timeline is capped at ~220px, and the EditForm scrolls anyway.

### Implementation Guide

1. **Change default splitter ratio**:
   - In `_init_splitter_sizes()`, change from `[self.width() // 3, 2 * self.width() // 3]` to `[self.width() // 2, self.width() // 2]` (50/50).
   - Or try `[3 * self.width() // 5, 2 * self.width() // 5]` (60/40 favoring left panel).

2. **Set minimum sizes**:
   - Left panel minimum: 300px (ensures table columns don't compress too tightly).
   - Right panel minimum: 350px (enough for form fields without horizontal scrolling).
   ```python
   left_widget.setMinimumWidth(300)
   right_widget.setMinimumWidth(350)
   ```

3. **Consider a three-column layout**:
   - If the user works primarily in List view, the right panel is less needed (inline edit bar handles quick edits). Consider adding a toggle to collapse the right panel entirely:
     - Add a "▶|" button at the splitter handle to collapse/expand the right panel.
     - This can be a small QPushButton overlaid on the splitter.

4. **Preserve existing user preference**:
   - If the user has manually resized the splitter, save to config and restore on next launch (already implemented via `_save_ui_config()`).

### Files to Modify

- `gui/main_window.py` — `_init_splitter_sizes()`, `_init_left_panel()`/`_init_right_panel()` minimum sizes, right panel collapse toggle

---

## P16: View Title Labels

### Problem

The left panel has no title or label indicating which view is active. A new user may not immediately understand what "Calendar", "List", or "Alerts" shows. The view buttons at the top are the only indicators, and the checked button state can be subtle.

### Implementation Guide

1. **Add a bold title label above the view stack**:
   - In `_init_left_panel()`, after the toggle layout and before the view stack, add a QLabel:
     ```python
     self.view_title = QLabel("<b>📅 Calendar View</b>")
     self.view_title.setObjectName("view_title")
     self.view_title.setStyleSheet("font-size: 14px; padding: 4px 0;")
     left_container.addWidget(self.view_title)
     ```

2. **Update title on view switch**:
   - In `_switch_view(view_name)`, after setting the view stack index and button states, update the title:
     ```python
     titles = {
         "calendar": "📅 Calendar View — Upcoming due dates at a glance",
         "list": "📋 List View — Filtered sortable table of all units",
         "alerts": "🔔 Alerts View — Per-detailer alert dashboard",
     }
     self.view_title.setText(f"<b>{titles.get(view_name, '')}</b>")
     ```

3. **Style for subtlety**:
   - Use a muted color (e.g., `color: palette(mid)`) so the title doesn't compete with content.
   - Make it small but readable (10-11px is enough).

4. **Space-saving option**: To save vertical space in the left panel, hide the title label by default and show it only when the user hovers over the view toggle button area. Alternatively, make it a user preference (`ui.show_view_titles`) that defaults to off.

### Files to Modify

- `gui/main_window.py` — `_init_left_panel()` add label, `_switch_view()` update text

---

## P17: Blame Label Theme Compliance

> **Quick win — belongs in Sprint 1, not Sprint 3. This is a one-line fix.**

### Problem

The "Last edited by..." label in `gui/list_panel.py` uses a hardcoded `#64748b` (slate-500) color via inline stylesheet. This color is readable in light mode but may have insufficient contrast in dark mode or high-contrast mode.

### Implementation Guide

1. **⚠️ Theme system uses type-based dispatch, not name-based CSS rules:**
   - **Codebase finding:** `gui/theme.py` applies stylesheet rules via a **type-based handler registry** (`_THEME_HANDLERS` dict, line 474). `QLabel` is **not in the handler registry**, so a name-based CSS rule like `#blame_label { color: palette(mid); }` in `apply_theme()` would **never be applied**.
   - The recommended approach below uses `findChild()` in `apply_theme()` to set the label's color explicitly, following the same pattern already used for `"left_panel"` and `"right_panel"` (lines 528-531 of `gui/theme.py`).

2. **Option A (Preferred): Explicit color via `findChild` in `apply_theme()`**:
   - In `gui/theme.py`, inside `apply_theme()`, add a block after the existing panel-color blocks:
     ```python
     blame_label = widget.findChild(QWidget, "blame_label")
     if blame_label is not None:
         blame_label.setStyleSheet(f"color: {tokens['text_secondary']}; font-size: 11px; padding-left: 4px;")
     ```
   - Then in `gui/list_panel.py` line 591, replace the hardcoded stylesheet with:
     ```python
     self.blame_label.setStyleSheet("font-size: 11px; padding-left: 4px;")  # color set by theme
     ```
   - This keeps the color theme-aware while letting the theme system handle it centrally.

3. **Option B (Simpler, if theme.py changes feel risky)**:
   - Simply remove the `color:` from the inline stylesheet in `gui/list_panel.py`:
     ```python
     self.blame_label.setStyleSheet("font-size: 11px; padding-left: 4px;")
     ```
   - The label inherits `QPalette.WindowText` from its parent, which changes with the theme.
   - **Trade-off:** This loses the muted/secondary text distinction — the blame label will be the same color as normal text instead of slightly grayed.

4. **Set the object name**:
   - The blame label already has `setObjectName("blame_label")` which is good.

### Files to Modify

- `gui/list_panel.py` — remove hardcoded `color: #64748b` from blame_label stylesheet
- `gui/theme.py` — add `findChild(QWidget, "blame_label")` block in `apply_theme()` (Option A) or do nothing (Option B)

---

## P18: Calendar Event Selection Feedback

### Problem

When the user clicks a unit in the CalendarPanel's event list, the unit is selected and the right panel updates. However, there is no visual feedback on the calendar cell itself confirming which unit was selected. The calendar dot colors remain the same, and the date cell highlight is the standard QCalendarWidget selection (blue background). This makes it hard to track which unit is being examined.

### Implementation Guide

1. **Track selected unit's due date**:
   - Store `self._selected_com_number: str | None` in CalendarPanel.
   - When a unit is selected (via event list click), set `_selected_com_number` to the unit's COM number.
   - Call `self.calendar.updateCells()` to trigger a repaint.

2. **Highlight the selected unit's date cell**:
   - In `EventCalendarWidget.paintCell()`, check if any unit on this date matches the selected COM number.
   - If so, draw a thicker border around the cell (2px solid blue or accent color).
   - Example:
     ```python
     if self._highlighted_com:
         for unit in units:
             if unit.com_number == self._highlighted_com:
                 painter.setPen(QPen(QColor(50, 90, 190), 2))
                 painter.drawRect(rect.adjusted(2, 2, -2, -2))
                 break
     ```

3. **Add `set_highlighted_unit(com_number: str | None)` method**:
   - On EventCalendarWidget and CalendarPanel.
   - Called from the event list click handler (`_on_event_clicked`).
   - When `None`, clear the highlight.

4. **Clear highlight on date change**:
   - When the user clicks a new date in the calendar, clear the selected COM highlight.

5. **Theme compliance**: The highlight border color must come from the theme, not be hardcoded. Use `palette().color(QPalette.Highlight)` instead of a fixed blue. This ensures visibility in dark mode, light mode, and high-contrast themes.

6. **Multi-select note**: If multiple units on the same date are selected (via Ctrl+click in the event list), highlight all of them. Draw the border only once per cell regardless of how many selected units share the date.

### Files to Modify

- `gui/calendar_panel.py` — `_selected_com_number`, `_on_event_clicked()`, highlight passing
- `gui/calendar_panel.py` — `EventCalendarWidget.paintCell()` highlight logic, `set_highlighted_unit()`

---

## P19: Right Panel Collapse Toggle

### Problem

When the user works primarily in List view, the right panel (Timeline + EditForm) consumes screen space that could be used for the table. The inline edit bar handles quick edits without needing the right panel. There's no way to collapse the right panel.

### Implementation Guide

1. **Add a collapse toggle button**:
   - Place a small `QPushButton` (◀/▶) at the splitter handle position or at the top of the right panel.
   - When collapsed: hide the right panel, give all space to the left panel. Show a thin ▶ button at the right edge to expand.
   - When expanded: restore the previous splitter sizes.

2. **Persist state in config**:
   - Save `ui.right_panel_collapsed` and `ui.right_panel_sizes` to config.
   - On launch, restore the collapsed/expanded state.

3. **Interaction with P2**: If the timeline is collapsed and the right panel is also collapsed, the user has effectively hidden all right-panel content. This is fine — they can expand either independently.

### Files to Modify

- `gui/main_window.py` — collapse toggle button, splitter state management, config persistence

---

## P20: Unified Edit State Model

### Problem

The inline edit bar and the edit form have separate save paths and separate dirty flags. Changes in one don't reflect in the other. The window title shows `*` but only one save path fires. This is confusing and can lead to data loss.

### Implementation Guide

1. **Create a shared edit state object**:
   - Define an `EditState` class that tracks: `is_dirty`, `source` (inline or form), `pending_unit` (the Unit with unsaved changes).
   - Both the inline edit bar and the edit form read from and write to this shared object.

2. **Single save path**:
   - When either surface triggers a save, the shared `EditState` is consulted. If dirty, the save goes through `UnitService.save()` regardless of which surface initiated it.
   - After save, both surfaces are re-populated from the saved unit.

3. **Dirty tracking unification**:
   - Both surfaces connect to the same `EditState.mark_dirty()` method.
   - The window title indicator (P12) reads from `EditState.is_dirty` instead of tracking form-only dirty state.

### Files to Modify

- `gui/edit_form.py` — connect to shared EditState
- `gui/inline_edit_bar.py` — connect to shared EditState
- `gui/list_panel.py` — emit dirty changes from inline bar to shared state
- `gui/main_window.py` — create and own the EditState, wire save path

---

## P21: LoadingOverlay + NotificationPanel Coexistence

### Problem

Both `LoadingOverlay` and `NotificationPanel` are overlay widgets in the main window. Without explicit Z-order management, they can overlap incorrectly — notifications appearing behind the loading overlay, or the overlay dismissing and leaving orphaned notifications.

### Implementation Guide

1. **Define Z-order**:
   - `LoadingOverlay` is always on top (it blocks interaction).
   - `NotificationPanel` is below it.

2. **Queue notifications during loading**:
   - If a notification fires while `LoadingOverlay` is visible, store it in a queue.
   - When `LoadingOverlay` is dismissed, flush the queue to `NotificationPanel`.

3. **Implementation**:
   - Add a `queue_notification(message, type, timeout)` method to `NotificationPanel`.
   - In `MainWindow`, check `self._loading_overlay.isVisible()` before calling `self._notify()`. If visible, queue instead.

### Files to Modify

- `gui/notification_panel.py` — add queue support
- `gui/main_window.py` — check overlay state before notifying
- `gui/loading_overlay.py` — emit signal on dismiss to flush queue

---

## Implementation Priority Matrix

| Priority | Item | Effort | Impact | Dependencies |
|----------|------|--------|--------|-------------|
| P1 | Top-Level QToolBar (+ History button) | Medium | High | None |
| P2 | Collapsible Timeline | Low | Medium | None |
| P3 | Calendar Filters | Medium | High | None |
| P4 | Global Search Bar | Low | Medium | P1 (toolbar, with fallback) |
| P5 | Progress Dialogs | Medium | Medium | None |
| P6 | Keyboard Shortcuts | Low | Medium | None |
| P7 | Cross-View Filters | Medium | High | P3 (calendar filters) |
| P8 | Batch Mode Awareness | Low | Medium | None |
| P9 | Notification Area | High | Medium | None |
| P10 | Alert Badge | Low | Medium | None |
| P11 | ~~Move History Button~~ | — | — | Merged into P1 |
| P12 | Dirty Title Indicator | Low | Low | None |
| P13 | Inline Edit Bar Position | Low | Low | None |
| P14 | Theme Button Icons | Low | Low | None |
| P15 | Splitter Tuning | Low | Low | None |
| P16 | View Title Labels | Low | Low | None |
| P17 | Blame Label Theme | Low | Low | None |
| P18 | Calendar Selection Feedback | Low | Low | None |
| P19 | Right Panel Collapse Toggle | Low | Medium | None |
| P20 | Unified Edit State Model | Medium | Medium | P8, P12 |
| P21 | LoadingOverlay + NotificationPanel Coexistence | Low | Medium | P9 |

### Recommended Sprint Plan

**Sprint 1 — Core UX improvements (High Impact, Low-Med Effort)**:
- P6: Keyboard shortcuts (Ctrl+1/2/3)
- P10: Alert badge on view buttons
- P17: Blame label theme compliance (one-liner, quick win — use Option A or B)
- P12: Dirty title indicator (see Known Limitation note in P12 step 5)
- P15: Splitter default size tuning
- P16: View title labels

**Sprint 2 — Navigation & search (High Impact, Medium Effort)**:
- P1: Top-level toolbar (decouples global operations from right panel)
- P4: Global search bar
- P3: Calendar with filters (must complete before P7)
- P7: Cross-view detailer persistence (depends on P3; **requires adding `detailer_changed` signal to AlertPanel** — see P7 step 3)

**Sprint 3 — Visual polish & space optimization**:
- P2: Collapsible timeline
- P8: Batch mode awareness
- P13: Inline edit bar repositioning **+ fix docstring**
- P14: Theme button icons
- P18: Calendar selection feedback
- P19: Right panel collapse toggle

**Sprint 4 — UX depth**:
- P5: Progress dialogs (WaitCursor MVP first, threading follow-up)
- P9: Notification area ⚠️ **Stretch goal** — highest effort item in the plan, may need descoping if time is tight
- P21: LoadingOverlay + NotificationPanel coexistence (small, pairs with P9)
- P20: Unified Edit State Model ⚠️ **Depends on P8 and P12** being done. If P8 slips, P20's dependency chain breaks. Consider swapping P20 into Sprint 3 if P8 is delayed.