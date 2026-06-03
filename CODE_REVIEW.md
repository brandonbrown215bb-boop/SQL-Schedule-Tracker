# Comprehensive Code Review

Review date: 2026-06-03

Scope: full repository review of the PyQt5/SQLite schedule viewer, including `main.py`,
`data/`, `gui/`, `automation/`, `sync/`, and tests.

## Verification Run

Commands run:

```bash
python -m compileall main.py data gui sync automation tests
QT_QPA_PLATFORM=offscreen pytest
ruff check .
mypy .
```

Results:

- Compile check: passed.
- Pytest without Qt offscreen: aborted during collection because Qt could not initialize a display backend.
- Pytest with `QT_QPA_PLATFORM=offscreen`: 177 passed, 10 failed.
- Ruff: failed with 140 lint findings.
- Mypy: failed with 126 type-check findings.

## Findings

### Critical: GUI save writes one object but refreshes the UI with a different, stale object

References:

- `gui/edit_form.py:286-308`
- `gui/main_window.py:398-405`
- `gui/main_window.py:539-554`

`EditForm._on_save()` constructs an edited `Unit` and emits it. `MainWindow._start_save_worker()` passes that edited object to `SaveWorker`, so the database write can succeed. But `_on_save_finished()` ignores the worker's saved unit and instead reads `self.current_unit`, which still points to the pre-edit selected unit.

Impact:

- A successful DB save can appear to revert in the UI until a reload occurs.
- `self.units`, the calendar, list, timeline, and edit form can be refreshed with stale values.
- Conflict handling also uses `self.current_unit`, so the "local" values shown to the user may not be the values they just tried to save.

Recommendation:

- In `_on_save_finished()`, use `worker.unit` after narrowing `self.sender()` to `SaveWorker`.
- Update `self.current_unit` and `edit_form.current_unit` to the saved unit only after the DB write succeeds.
- Add an async GUI save test that edits a field, waits for the worker, and asserts the in-memory model and table show the edited value.

### Critical: GUI saves bypass optimistic locking because `updated_at` is not preserved

References:

- `gui/edit_form.py:286-306`
- `data/writer.py:29-35`
- `data/models.py:64-66`

`row_to_unit()` loads `updated_at`, and `save_unit()` only enforces optimistic locking when `unit.updated_at` is present. However, `EditForm._on_save()` creates a fresh `Unit` and does not copy `orig.updated_at`. That means normal GUI saves use the unlocked fallback path in `save_unit()`.

Impact:

- Concurrent edits can overwrite each other silently from the main GUI path.
- The conflict dialog is unlikely to appear for normal edit-form saves, despite the writer claiming to support optimistic locking.

Recommendation:

- Copy `updated_at=orig.updated_at` into the edited `Unit`.
- After a successful save, reload the row or update `unit.updated_at` from SQLite so the next save uses the new timestamp.
- Add a GUI-level stale timestamp test, not just a direct writer test.

### High: `save_unit()` uses `conn.total_changes` for row-match detection

Reference:

- `data/writer.py:36-70`

`conn.total_changes` is cumulative for the lifetime of the SQLite connection. Once the connection has performed any successful write, a later zero-row `UPDATE` can still leave `total_changes > 0`, so the code can miss a failed optimistic-lock check or missing COM.

Impact:

- Stale saves may be reported as successful.
- Missing COM numbers may not be detected consistently.
- Behavior depends on connection history, which makes failures intermittent.

Recommendation:

- Store the result of `conn.execute(...)` and inspect `cursor.rowcount`.
- Decide explicitly whether a missing COM should raise. The current test name says it should raise, while its comment says it should not.

### High: Multi-user sync infrastructure is mostly initialized but not used by saves

References:

- `gui/main_window.py:34`
- `gui/main_window.py:117-124`
- `gui/main_window.py:373-390`
- `gui/main_window.py:852-918`
- `sync/lock_manager.py:107-111`
- `sync/revision_store.py:61-111`

`MainWindow` imports and initializes `LockManager`, `RevisionStore`, `SharedCache`, session presence, and sync status state, but the actual save path calls only `save_unit()`. It does not acquire a lock, commit a revision, update the shared cache, or update the sync status widget.

Impact:

- `multi_user.enabled: true` gives the appearance of stronger coordination than the app actually uses.
- Revision conflicts tested in `sync/` are not enforced in the user-facing save flow.
- `_sync_save_blocked` is set when sync setup fails but is not checked before saving.

Recommendation:

- Either wire the sync layer into `_start_save_worker()`/`SaveWorker` or remove/disable the multi-user controls until the path is complete.
- Check `_sync_save_blocked` before starting a save.
- Add integration tests through `MainWindow.on_save_unit()`.

### High: Close-progress and shutdown cleanup code is orphaned

References:

- `gui/main_window.py:1207-1261`
- `gui/close_progress_dialog.py:141`

`MainWindow` defines `_begin_close_with_sync()`, `_tick_close_progress()`, and `_real_close()`, but there is no `MainWindow.closeEvent()` and no references to `_begin_close_with_sync()` outside its definition.

Impact:

- In-flight saves are not waited on during normal window close.
- Session heartbeat cleanup in `_real_close()` may not run.
- Debounced config writes may be lost on exit.
- `CloseProgressDialog` is tested but not integrated.

Recommendation:

- Implement `MainWindow.closeEvent()` to route through `_begin_close_with_sync()` when a save is active and through `_real_close()` otherwise.
- Ensure `_real_close()` calls the base close event path safely rather than recursively closing.

### Medium: List date preset code and tests are out of sync with the UI

References:

- `gui/list_panel.py:95-105`
- `gui/list_panel.py:138-183`
- `gui/list_panel.py:185-248`
- `gui/list_panel.py:361-374`
- `gui/list_panel.py:678-681`
- `tests/test_list_panel.py:194-213`
- `tests/test_list_panel.py:406-409`

`DATE_FILTER_PRESETS` and `_filter_by_date()` still exist, and tests expect `apply_filters(date_preset=...)` plus a `date_combo`. The current UI uses two `QDateEdit` widgets instead, and `apply_filters()` no longer accepts `date_preset`.

Impact:

- Nine list-panel tests fail.
- The orphaned preset code can mislead future changes.
- The default date range filters out units outside `today - 30` through `today + 90`, so "set units" and "clear filters" do not actually show all units.

Recommendation:

- Choose one model: restore a preset combo or remove the preset constant, `_filter_by_date()`, and stale tests.
- If "Clear Filters" should mean "show all", make the date range optional/disabled when cleared.

### Medium: Calendar writes a debug log file during normal UI refresh

References:

- `gui/calendar_panel.py:62-77`

`EventCalendarWidget.set_events()` appends to `calendar_debug.log` every time units are loaded/refreshed.

Impact:

- Creates unexpected files in the process working directory.
- Can grow indefinitely in daily use.
- May fail or slow down on locked/read-only deployment paths.

Recommendation:

- Remove the file writes or replace them with `logging.debug()`.

### Medium: `SyncStatusWidget.update()` overrides `QWidget.update()` with an incompatible signature

Reference:

- `gui/sync_status.py:59-103`

The widget defines `update(self, remaining, total)`, which shadows Qt's paint scheduling method `QWidget.update()`.

Impact:

- Type checkers correctly report an override error.
- Any Qt/framework code or maintainer calling `widget.update()` with normal Qt semantics will fail.

Recommendation:

- Rename this method to `set_progress()` or `update_progress()`.

### Medium: SSRS import assumes the default URL is non-null and uses optional dependencies not declared

References:

- `automation/import_atomsvc.py:109-131`
- `automation/import_atomsvc.py:133-159`
- `automation/import_atomsvc.py:176-198`
- `requirements.txt`

`run_ssrs_import()` accepts `ssrs_url: str | None`, then passes it to `build_ssrs_url()` as if it were a string. The module also attempts `requests`, `requests_ntlm`, `win32com`, and `pythoncom`, but those are not in `requirements.txt`.

Impact:

- Calling `run_ssrs_import(db_path, ssrs_url=None)` directly can fail before network access.
- Deployment behavior differs by machine depending on undeclared packages and installed tools.

Recommendation:

- Validate `ssrs_url` at function entry or make it required.
- Document optional auth backends or add extras such as `requirements-ssrs.txt`.

### Medium: Export confirmation says one sheet while exporter writes another

References:

- `gui/main_window.py:1051-1079`
- `automation/export_to_workbook.py:23-27`

The GUI says the export will overwrite the "Unedited Report" sheet, while the exporter writes `CURRENT_LIST_SHEET = "Current List"`.

Impact:

- Users may approve an export based on the wrong target sheet.
- Operationally risky because this action modifies an Excel workbook in place.

Recommendation:

- Align the dialog text, tooltip, function docstring, and exporter constant.

### Medium: `pyrightconfig.json` points at Python 3.14 despite project metadata requiring 3.10+

References:

- `pyproject.toml:4`
- `pyrightconfig.json:2-13`

The project declares `requires-python = ">=3.10"`, but Pyright is configured for Python 3.14 and hard-coded local site-packages paths.

Impact:

- Type analysis may not reflect the supported runtime.
- Other developers or build agents will inherit machine-specific paths.

Recommendation:

- Set `pythonVersion` to the supported deployment version, likely `3.10` or `3.11`.
- Remove machine-specific `pythonPath` and `extraPaths`, or move them to an untracked local config.

### Low: Several orphaned or stale artifacts remain

References:

- `data/loader.py:11-12` (`COLUMN_MAP`)
- `gui/timeline_panel.py:301-339` (`_draw_date_axis`)
- `gui/main_window.py:533-537` (`_release_save_worker`)
- `gui/main_window.py:771-804` (Excel wording in SQLite refresh cooldown)
- `main.py:32` (`config_path` parameter in `_validate_config_paths()`)

These items are unused or kept only for stale compatibility.

Recommendation:

- Remove them if no external callers depend on them.
- If retained intentionally, add comments that explain the compatibility contract and add tests for that contract.

### Low: Lint and typing hygiene are poor enough to hide real issues

References:

- `ruff check .`: 140 findings.
- `mypy .`: 126 findings.

Many findings are style-only, but several are real maintenance hazards:

- Undefined `QObject` annotation in `sync/session_registry.py:83`.
- Unused imports for important-looking sync concepts such as `RevisionConflictError`.
- Incompatible Qt overrides in GUI classes.
- Many stale comments/docstrings still reference Excel sync after the SQLite migration.

Recommendation:

- Run `ruff check --fix .` for safe mechanical cleanup, then review remaining findings manually.
- Decide whether mypy is a supported gate. If yes, tune the PyQt stubs/configuration and fix remaining errors incrementally.

## Test Failures Observed

With `QT_QPA_PLATFORM=offscreen pytest`, the failing tests were:

- `tests/test_list_panel.py::TestUnitListModelFiltering::test_filter_overdue`
- `tests/test_list_panel.py::TestUnitListModelFiltering::test_filter_next_7_days`
- `tests/test_list_panel.py::TestUnitListModelFiltering::test_filter_next_30_days`
- `tests/test_list_panel.py::TestUnitListModelFiltering::test_filter_excludes_null_due_dates`
- `tests/test_list_panel.py::TestListPanelWidget::test_set_units`
- `tests/test_list_panel.py::TestListPanelWidget::test_clear_filters`
- `tests/test_list_panel.py::TestListPanelWidget::test_date_combo_has_presets`
- `tests/test_list_panel.py::TestFilterSortIntegration::test_filter_overdue_sort_by_com`
- `tests/test_list_panel.py::TestFilterSortIntegration::test_filter_next_7_days_sort_by_status`
- `tests/test_writer.py::TestSaveUnit::test_com_number_not_found_raises`

Root causes:

- List-panel tests still expect date presets and `date_combo`, but the code now uses explicit from/to date edits.
- The list panel applies a default date range, so initial and cleared views do not show all rows.
- The writer test name and comment disagree about whether a missing COM should raise.

## Suggested Fix Order

1. Fix the GUI save path to preserve `updated_at` and commit the worker's saved unit back into memory.
2. Replace `conn.total_changes` with statement `rowcount` in `save_unit()`.
3. Decide whether multi-user sync is a real feature for this release; wire it in or remove the inactive surface area.
4. Reconcile the list-panel date filter design with tests and user expectations.
5. Add `MainWindow.closeEvent()` and integrate close-progress/session cleanup.
6. Remove debug file writes and stale Excel wording.
7. Run Ruff auto-fixes, then clean up the remaining static typing issues.
