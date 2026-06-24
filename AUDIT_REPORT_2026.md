# SQL-Schedule-Tracker Audit Report (2026)

This document compiles the findings of the 2026 codebase audit for the SQL-Schedule-Tracker application. It covers logical/functional bugs, graphical and UX style errors, and data integrity or synchronization pitfalls.

---

## 1. Logical and Functional Bugs

### Issue 1.1: Capacity Red Check Skipped when Due Today
- **Severity**: High
- **File Path**: `data/models.py` (Approx. lines 168–186)
- **Description**: The capacity-based red check is skipped when `working_days` is 0. This occurs when a unit's detailing due date is today or on a non-working day. Because `working_days > 0` evaluates to `False`, the method bypasses capacity checks. Consequently, incomplete units due today are incorrectly marked as gray or yellow instead of red.
- **Recommended Concrete Fix**: Change the check to return `"red"` immediately if `working_days == 0` and there are still remaining department hours to complete:
  ```python
  if working_days <= 0:
      if remaining_hours > 0:
          return "red"
  ```

### Issue 1.2: Connection Leak in get_by_com
- **Severity**: Medium
- **File Path**: `services/unit_service.py` (Approx. lines 71–84, 174–181)
- **Description**: `UnitService.get_by_com()` calls `_get_conn()`, which opens a new raw `sqlite3.connect()` connection but never closes it. This leads to leaked file handles, particularly when fetching single units during conflict checks.
- **Recommended Concrete Fix**: Replace the raw connection instantiator with the thread-local database connection manager `get_db(self._db_path)` or explicitly close the connection in a `finally` block.

### Issue 1.3: remaining_hours Out-of-Sync on Manual Saves
- **Severity**: High
- **File Path**: `data/writer.py` (Approx. lines 90–146)
- **Description**: The SQL `UPDATE` statement inside `save_unit()` does not include or update the `remaining_hours` column. While `remaining_hours` is computed during CSV imports, manual updates to `percent_complete` or `department_hours` via the GUI do not recalculate or persist the new `remaining_hours` in the database, causing stale data in subsequent Excel exports.
- **Recommended Concrete Fix**: Recalculate `remaining_hours = department_hours * (1.0 - percent_complete)` in `save_unit()` and include the `remaining_hours` field in the SQL update query parameters.

### Issue 1.4: Identicals Rule Persistent Data Loss
- **Severity**: High
- **File Path**: `data/loader.py` (Approx. lines 59–95)
- **Description**: The identicals rule zeroes out `target_department_hours` in-memory for secondary identical units. If a user edits and saves a secondary identical unit, this `0.0` value is permanently saved to the database. If due dates or contracts shift later and this unit becomes primary, it is skipped in `_apply_identicals()`, meaning it permanently retains the `0.0` target hours instead of restoring the original value.
- **Recommended Concrete Fix**: Restore or compute the original `target_department_hours` dynamically when a unit is designated as the primary identical during the loader phase, or avoid persisting the in-memory zeroed-out target hours to the database.

### Issue 1.5: Sync/Cache Data Wiping on Transient OS Errors
- **Severity**: High
- **File Path**: `sync/revision_store.py` (lines 111–115) and `sync/shared_cache.py` (lines 159–168)
- **Description**: The internal `_read_all()` methods catch general `OSError` exceptions (such as sharing violations on Windows network drives) and handle them by returning an empty dictionary `{}`. Upon writing back during a commit, the empty cache overwrites the entire JSON file, deleting all other units' revision histories or cached sync states.
- **Recommended Concrete Fix**: Do not catch general `OSError` or implement a safe retry mechanism. Propagate the error so that the operation is aborted instead of destructively overwriting the cache.

### Issue 1.6: Blank Preview Overwrites DB Values with NULL
- **Severity**: High
- **File Path**: `automation/import_preview.py` (Approx. lines 135–137)
- **Description**: The import preview generator skips comparison when `new_val` is `None` (corresponding to blank fields in the CSV), reporting "no changes". However, during actual import execution, these blank values are imported as `None` / `NULL`, silently overwriting and deleting existing database values.
- **Recommended Concrete Fix**: Modify the diff preview logic to explicitly check if a key is present but `None` in the incoming data, and compare it against the current database value to report the upcoming deletion/overwrite.

### Issue 1.7: validate_input Decorator Ignores Positional Arguments
- **Severity**: Medium
- **File Path**: `services/validation.py` (Approx. lines 260–299)
- **Description**: The `@validate_input` decorator loops over `field_rules.items()` and looks for them in `kwargs`. If decorated methods are invoked using positional arguments (e.g. `set_hours(5.0)`), they bypass validation entirely.
- **Recommended Concrete Fix**: Use `inspect.Signature.bind()` to bind the incoming `*args` and `**kwargs` to the function parameters before executing the validation loop.

### Issue 1.8: Missing Date Validation in UNIT_FIELD_RULES
- **Severity**: Medium
- **File Path**: `services/validation.py` (Approx. lines 74–154)
- **Description**: `UNIT_FIELD_RULES` contains no validation rules for date fields (e.g., `unit_detailing_start_date`, `detailing_due_date`). This allows invalid types (such as raw strings) to bypass validation and subsequently crash the writer during the `isoformat()` conversion.
- **Recommended Concrete Fix**: Add explicit `FieldRule` specifications for all date fields to validate that they are either instances of `date` or `None`.

---

## 2. Graphical and UX Errors

### Issue 2.1: Silent Thread Save Discard in Batch Edit
- **Severity**: High
- **File Path**: `gui/main_window.py` (Approx. lines 744–764) & `gui/batch_edit_dialog.py` (Approx. lines 119–147)
- **Description**: When executing batch edits, `BatchEditDialog` loops over units and emits `unit_saved` signals. `MainWindow._start_save_worker()` processes the first unit by launching a thread worker. For subsequent units, `_active_save_worker_running()` evaluates to `True`, prompting the code to log a warning and return immediately. This discards all saves after the first unit.
- **Recommended Concrete Fix**: Implement a FIFO queue (`self._save_queue: list[Unit]`) for save workers in `MainWindow`. When a save worker finishes, trigger the next unit in the queue.

### Issue 2.2: Invalid Field Stylesheet Override Clears Custom Theme
- **Severity**: Medium
- **File Path**: `gui/edit_form.py` (line 27 & lines 343–346)
- **Description**: `EditForm._validate_fields()` resets styles by setting input field stylesheets to `_VALID_STYLE = ""`. This erases the stylesheet applied by the global `apply_theme()` function, causing the input fields to revert to default OS colors and break the Dark Theme.
- **Recommended Concrete Fix**: Re-apply the standard themed input stylesheet on validation success, or use custom Qt properties (e.g. `invalid="true"`) to apply red borders without clearing the base styles.

### Issue 2.3: Contrast/Readability Violations for Invalid Fields in Dark Theme
- **Severity**: High
- **File Path**: `gui/edit_form.py` (line 26)
- **Description**: The invalid field style is hardcoded as `border: 2px solid red; background-color: #fff0f0;`. In Dark Theme, the text color remains white, causing white text on a light pink background, which violates WCAG contrast guidelines.
- **Recommended Concrete Fix**: Explicitly define a dark text color (e.g., `color: #1e293b;`) in `_INVALID_STYLE`, or make the invalid style color theme-aware.

### Issue 2.4: Contrast/Readability Violations in Conflict Dialog
- **Severity**: High
- **File Path**: `gui/conflict_dialog.py` (lines 119–120)
- **Description**: Differing cells are highlighted with a light yellow background (`#fef9c3`) without setting a text foreground color. In Dark Theme, this results in unreadable white text on a light yellow background.
- **Recommended Concrete Fix**: Set a dark foreground color for the highlighted cells:
  ```python
  item_local.setForeground(QBrush(QColor("#1e293b")))
  item_remote.setForeground(QBrush(QColor("#1e293b")))
  ```

### Issue 2.5: Contrast/Readability Violations in Import Preview Dialog
- **Severity**: High
- **File Path**: `gui/import_preview_dialog.py` (lines 85, 95, 122)
- **Description**: Custom rows are colored with light backgrounds (green, yellow, red pastel) but their labels retain default white text in Dark Theme. Additionally, the dialog fails to invoke `apply_theme()`, bypassing the themed styles.
- **Recommended Concrete Fix**: Call `apply_theme(self, theme_name)` in the constructor and ensure that labels overlaying the background colors have their text color set to dark (e.g., `#1e293b`).

### Issue 2.6: TimelineWidget Painting Breaks Dark Theme
- **Severity**: High
- **File Path**: `gui/timeline_panel.py` (lines 152, 223, 227, 236–237, 243, 257, 279)
- **Description**: The custom `TimelineWidget` paint event uses hardcoded light colors (such as `#fcfcff` and `#edf0f8`) and dark text. When Dark Theme is enabled, this widget remains a high-glare white box, violating style consistency.
- **Recommended Concrete Fix**: Retrieve drawing colors dynamically from the active theme tokens:
  ```python
  tokens = THEMES[self._theme_name]
  bg_color = QColor(tokens["bg_secondary"])
  text_color = QColor(tokens["text_primary"])
  ```

### Issue 2.7: Lack of Visual Checked State for View Toggle Buttons
- **Severity**: Medium
- **File Path**: `gui/theme.py` (line 234) & `gui/main_window.py` (lines 411–426)
- **Description**: The checkable view toggle buttons (Calendar, List, Alerts) share the same visual style when checked and unchecked, providing no visual indication of the active panel.
- **Recommended Concrete Fix**: Add a `:checked` pseudo-class to the button stylesheets in `gui/theme.py` using active selection colors.

### Issue 2.8: Dead UI Code in Sync Status Widget
- **Severity**: Medium
- **File Path**: `gui/main_window.py` (lines 303–305) & `gui/sync_status.py`
- **Description**: The status bar's `SyncStatusWidget` is initialized but `set_progress()` is never called, leaving the progress bar permanently invisible.
- **Recommended Concrete Fix**: Wire the background worker thread saves to update this progress widget, displaying the progress bar during saves.

### Issue 2.9: Broken Close ETA Tracking
- **Severity**: Medium
- **File Path**: `gui/main_window.py` (lines 242–244, 1541–1543)
- **Description**: `self._sync_unit_durations` is never populated, so `_avg_unit_seconds()` always returns `0.0`, resulting in a static `Estimated time remaining: …` (dots) in the close dialog.
- **Recommended Concrete Fix**: Record save worker start times and append the elapsed seconds to `self._sync_unit_durations` in `_on_save_finished()`.

### Issue 2.10: Audit Dialog Populating & Sorting Race
- **Severity**: Medium
- **File Path**: `gui/audit_dialog.py` (line 100 & lines 139–141)
- **Description**: `self.table.setSortingEnabled(True)` is enabled before loading the database rows. This triggers the sorting algorithm on every single `setItem()` call, causing lag and potential row shuffling during load.
- **Recommended Concrete Fix**: Disable sorting during population and re-enable it afterward:
  ```python
  self.table.setSortingEnabled(False)
  # load data
  self.table.setSortingEnabled(True)
  ```

### Issue 2.11: Stale Search Match Selection
- **Severity**: Low
- **File Path**: `gui/main_window.py` (lines 360–396)
- **Description**: Clearing the global search field returns early but fails to clear `self._search_single_match`. Pressing Enter on a blank search box selects the stale matched unit.
- **Recommended Concrete Fix**: Clear `self._search_single_match = None` in `_on_global_search()` if the search query is empty.

### Issue 2.12: Misleading Save Warning on Local Validation Failure
- **Severity**: Low
- **File Path**: `gui/main_window.py` (lines 789–795)
- **Description**: When a save fails due to a local validation check (like date constraints), the error dialog suggests checking the network connection, which is misleading.
- **Recommended Concrete Fix**: Check if the error is a `ValidationError` and display a message focused on data input errors instead of network connectivity issues.

### Issue 2.13: Inline Edit Bar Save Button Color Violation
- **Severity**: Low
- **File Path**: `gui/inline_edit_bar.py` (lines 95–99)
- **Description**: The Save button in the inline bar lacks an `objectName`. In `theme.py`, save buttons are only colored green if their name contains `"save"`. Thus, it is rendered in gray.
- **Recommended Concrete Fix**: Set the object name to `"inline_save_btn"` in the constructor of `InlineEditBar`.

### Issue 2.14: Missing Selection Synchronization in CalendarPanel
- **Severity**: Medium
- **File Path**: `gui/main_window.py` (lines 725–740) & `gui/calendar_panel.py` (lines 270–280)
- **Description**: Selection changes in the list panel or global search are not propagated to the `CalendarPanel`, leaving the calendar desynchronized.
- **Recommended Concrete Fix**: In `MainWindow.on_unit_selected()`, invoke `self.calendar_panel.set_highlighted_unit(unit.com_number if unit else None)`.

### Issue 2.15: Missing Selection Synchronization in AlertPanel
- **Severity**: Medium
- **File Path**: `gui/main_window.py` (lines 725–740) & `gui/alert_panel.py`
- **Description**: Similar to the calendar, the selected unit is not highlighted in the `AlertPanel`'s alerts list.
- **Recommended Concrete Fix**: Implement a `set_selected_unit(self, unit)` method on `AlertPanel` and call it from `MainWindow.on_unit_selected()`.

### Issue 2.16: Onboarding Mentions Non-Existent Context Menus
- **Severity**: Low
- **File Path**: `gui/onboarding.py` (line 87)
- **Description**: Onboarding text states that "Right-click context menus available" on the List View, but no such menus are implemented.
- **Recommended Concrete Fix**: Remove the misleading text or implement context menus in `gui/list_panel.py`.

---

## 3. Data Integrity and Synchronization Pitfalls

### Issue 3.1: Sync System Complete Bypass
- **Severity**: High
- **File Path**: `gui/main_window.py`, `services/unit_service.py`
- **Description**: The multi-user file-based locking manager (`LockManager`) and revision tracking store (`RevisionStore`) are fully implemented but never invoked during the unit editing or saving pipeline. Units are saved directly via `UnitService.save()`, rendering the sync/conflict system inactive.
- **Recommended Concrete Fix**: Call `SyncService.acquire_lock()` when editing/selecting a unit and `SyncService.commit_revision()` inside the save worker pipeline.

### Issue 3.2: SQLite WAL Mode on Shared Drive
- **Severity**: High
- **File Path**: `data/db.py` (line 34), `automation/import_csv.py` (line 164)
- **Description**: SQLite's write-ahead logging (WAL) mode is initialized by default. However, WAL mode uses shared-memory files (`.shm`) which require `mmap` support. Network filesystems (SMB/NFS) do not support `mmap`, leading to operational errors or DB corruption.
- **Recommended Concrete Fix**: Check if the database path resides on a network volume, and disable WAL mode (falling back to rollback journal modes like `DELETE`) if it is on a network drive.

### Issue 3.3: Transaction Integrity Failure in DDL Migrations
- **Severity**: High
- **File Path**: `services/migration_registry.py` (lines 101–119)
- **Description**: Migrations are run via `conn.executescript()`. In SQLite, `executescript()` automatically commits previous commands and runs statements individually. If a script fails midway, the database is left in a partially migrated, corrupted state, as `rollback()` has no effect on already committed DDL statements.
- **Recommended Concrete Fix**: Split the migration script by semicolon and run each statement inside an explicit transaction context using `conn.execute()`.

### Issue 3.4: Fingerprint Caching Stale Value Bug
- **Severity**: Medium
- **File Path**: `data/loader.py` (lines 15, 27–56)
- **Description**: `unit_fingerprint()` caches calculated hashes in a module-level dictionary `_fingerprint_cache` keyed by `com_number`. There is no mechanism to invalidate these cache entries when a unit is modified, returning stale fingerprint hashes.
- **Recommended Concrete Fix**: Remove the cache entirely since calculation is lightweight, or invalidate the cache entry for the unit on save.

### Issue 3.5: False Audit Logs from SQLite Type Affinity
- **Severity**: Medium
- **File Path**: `data/db.py` (lines 183–193)
- **Description**: SQLite's dynamic affinity converts floating point values like `0.0` or `40.0` into integers (`0` or `40`) to save space. When read back, Python compares `str(0) != str(0.0)`, writing duplicate/false change entries to `_audit_log`.
- **Recommended Concrete Fix**: Convert and normalize values numerically (e.g. comparing floats) before performing string differences.

### Issue 3.6: New Unit Audit Log Blind Spot
- **Severity**: Medium
- **File Path**: `data/db.py` (lines 172–173)
- **Description**: New unit insertions are completely omitted from the audit trail because `old_row is None` causes `log_field_changes` to return early.
- **Recommended Concrete Fix**: Log new unit creations in the audit trail with `old_value = NULL` and `new_value` populated with the initial insert data.

### Issue 3.7: Unchecked OS Errors in Lock Manager and Session Registry
- **Severity**: Medium
- **File Path**: `sync/lock_manager.py` (lines 123–128) & `sync/session_registry.py` (lines 133–143)
- **Description**: Lock removals and session directory iterations lack error handling, allowing permission or disk errors to crash the application's heartbeat timers.
- **Recommended Concrete Fix**: Wrap `unlink()` and `iterdir()` operations in standard `try-except OSError` blocks and log warning messages instead of crashing.

### Issue 3.8: Optimistic Locking Bypass on Missing updated_at
- **Severity**: Medium
- **File Path**: `data/writer.py` (lines 81–86)
- **Description**: Optimistic locking checks are bypassed if `unit.updated_at` is empty or falsy, allowing users to save over modified records without concurrency checks.
- **Recommended Concrete Fix**: Raise an error if `updated_at` is empty or ensure it is always initialized when loading units.
