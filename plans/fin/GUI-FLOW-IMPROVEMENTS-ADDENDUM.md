# GUI Code Audit and Implementation Plan (Sprint 4 & Gaps Addendum)

This document catalogs a comprehensive review of the active codebase (`gui/` package + `main.py`), audits the progress made against the original `/plans/begin/GUI-FLOW-IMPROVEMENTS.md` plan, identifies critical architectural/UX gaps, and outlines a concrete road map to implement the remaining Sprint 4 items alongside newly discovered improvements.

---

## Executive Summary & Codebase Audit

A comprehensive review of the active codebase reveals that **Sprint 1, 2, and 3 are already fully implemented** (correcting the out-of-date `/plans/fin/GUI-FLOW-PROGRESS-2026-06-23.md` progress report). 

### Completed Features (Sprints 1-3)
1. **P1 (Top-Level QToolBar)**: Global data operations (SSRS pull, CSV import, Refresh, Export) are cleanly decoupled into the top-level toolbar. Sync status has been moved to the status bar, freeing vertical space in the right panel. History requested is now a button inside the edit form.
2. **P2 (Collapsible Timeline Panel)**: Fully implemented with an arrow toggle and config persistence.
3. **P4 (Global Search Bar)**: Positioned in the toolbar, debounced to 300ms, and redirects multi-matches to the List panel search.
4. **P6 (Keyboard Shortcuts)**: `Ctrl+1/2/3` are mapped to Calendar, List, and Alerts views.
5. **P8 (Batch Mode Awareness)**: Yellow banner displays count of selected units and disables the right panel.
6. **P10 (Alert Badge)**: Displays count of red alerts on the Alerts toggle button.
7. **P12 (Dirty Title Indicator)**: Prepends `*` to the title when the Edit Form is dirty.
8. **P13 (Inline Edit Bar Repositioning)**: Repositions the Inline Edit Bar above the table when a row is selected (Option B).
9. **P14 (Theme Button Icons)**: Replaced emojis with standard Unicode sun/moon fallbacks.
10. **P15 (Splitter Tuning)**: Splitter default ratio is tuned to 1:1, and min sizes are set.
11. **P16 (View Title Labels)**: Sub-headers are present above the view stack.
12. **P17 (Blame Label)**: Removed hardcoded slate color (Option B), making the label inherit default window text color.
13. **P18 (Calendar Event Selection Feedback)**: Draws a border around the selected unit's cell in the calendar widget.
14. **P19 (Right Panel Collapse)**: Toggle button added at the top-right of the edit form with config persistence.

---

## Critical Gaps & Visual Inconsistencies Discovered

During our code audit, we identified several critical UX, data integrity, and visual styling issues that are **not** fully addressed in the current code:

### ⚠️ UX & Data Integrity Gaps
1. **Severe Data Loss Risk in Inline Edit Bar**:
   - The `InlineEditBar` tracks its own dirty state (`self._dirty`), but it does not notify the main window.
   - `MainWindow._confirm_discard()` only checks `self._form_dirty` (which is mapped only to the right `EditForm`).
   - If a user makes inline changes and closes the application or switches to another view (like Calendar), the changes are **discarded silently** without warning or prompting the user.
2. **Synchronous/Blocking I/O in CSV Import, SSRS Pull, and Export**:
   - CSV import preview calculation, Excel export, and SSRS pulls currently execute directly on the main GUI thread.
   - When a pull or export is initiated, the application freezes entirely. The OS will mark it as "Not Responding" for multi-minute SSRS syncs.
   - The static `LoadingOverlay` is shown, but its spinner cannot animate because the GUI event loop is frozen.

### 🎨 Visual & Theme Compliance Issues
1. **Theme Toggle Overwrites Alert Badge Styles**:
   - `apply_theme()` dynamically styles all `QPushButton` widgets using the `_BTN_DEFAULT` template.
   - If a user toggles the theme, `apply_theme` wipes out the custom red styling on the Alerts button (`color: #dc2626; font-weight: bold;`) until the next reload.
   - Furthermore, the color `#dc2626` is hardcoded. In dark mode, this red lacks contrast on a `#1e293b` background. It should use the theme token `text_error` (`#f87171` in dark mode).
2. **Unstyled Global Containers**:
   - The theme engine in `gui/theme.py` completely ignores `QMainWindow`, `QMenuBar`, `QStatusBar`, `QSplitter`, and `QProgressBar`.
   - In dark mode, this results in jarring visual inconsistencies where the menu bar, status bar, splitter handles, and progress bar are drawn using default Windows light-gray gradients.
3. **Muted Blame Label (P17 Option A)**:
   - The blame label currently uses normal text color. It should be styled with `text_secondary` to display as muted metadata, separate from the primary data.

---

## Action Plan for Sprint 4 & Core Improvements

### 1. Theme Engine Updates
- **File:** `gui/theme.py`
- **Change:**
  - Register `QProgressBar` in `_THEME_HANDLERS` using theme tokens (`accent` for chunk, `bg_tertiary` for background).
  - Update `apply_theme` to find the `blame_label` child (using `widget.findChild(QWidget, "blame_label")`) and style it with `text_secondary` color (Option A).
  - Add stylesheet support for global UI containers:
    - `QMainWindow` (base styling)
    - `QMenuBar` & `QMenu` (dark-mode friendly navigation bars)
    - `QStatusBar` (polished status indicators)
    - `QSplitter::handle` (subtle separators matching border colors)

### 2. UX & Data Integrity Fixes
- **File:** `gui/main_window.py`
- **Change:**
  - **Background Worker Threads (P5)**:
    - Implement `PullSSRSWorker`, `CSVImportWorker`, and `ExcelExportWorker` inheriting from `QThread`.
    - Connect actions (SSRS pull, CSV import, Excel export) to these threads.
    - Wire success/error handlers to show responsive QMessageBox warnings and trigger data reloads.
    - Re-show the `LoadingOverlay` during operations (which will now spin smoothly).
  - **Unified Edit State (P20)**:
    - Check *both* `self.edit_form.is_dirty` and `self.list_panel._inline_edit_bar.is_dirty` inside `_confirm_discard()`.
    - Wire a unified title-change listener so either surface dirtying updates the `*` window title indicator.
  - **Alert Badge Theme Compliance**:
    - Update `_update_alert_badge()` to use the current theme's `text_error` color token instead of hardcoded `#dc2626`.
    - Call `_update_alert_badge()` at the end of `_apply_theme_by_name()` to ensure badge styles are re-applied and not lost during theme toggles.

### 3. Toast Notification System
- **File:** `gui/notification_panel.py` [NEW]
  - Create `NotificationPanel` class (P9).
  - Toast overlay anchored at the bottom-center of the MainWindow.
  - Support `INFO`, `SUCCESS`, `WARNING`, and `ERROR` types with respective left-border colors.
  - Auto-dismiss with animations and stacking behavior.
  - Support queuing notifications when `LoadingOverlay` is visible (P21).
- **File:** `gui/main_window.py`
  - Replace `status_bar.showMessage()` calls with `self._notify()` to delegate notification management to the new overlay (retaining status bar for persistent status).

---

## Verification Plan

### Automated Tests
- Run existing test suites to confirm no regressions are introduced:
  ```powershell
  .\test.bat
  ```
- Write unit tests for new worker threads (`test_workers.py`) verifying database consistency and error propagation.
- Write unit tests for `NotificationPanel` (`test_notification_panel.py`) verifying queueing and Z-order.

### Manual Verification
- Verify theme toggles (light/dark) re-apply Alert Badge colors and style the menu bar, status bar, splitter handles, and progress bar cleanly.
- Edit values in the Inline Edit Bar, and verify that the window title updates with `*` and warns before closing the application or selecting another unit.
- Initiate a pull SSRS operation, verify that the UI remains responsive (movable, resizable) and that the loading overlay spinner continues to rotate.
