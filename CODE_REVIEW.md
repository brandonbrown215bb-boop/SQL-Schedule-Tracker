# Comprehensive Code Review: Schedule-Viewer-App-v2

*Generated: 2026-06-15*

> This review covers errors, orphaned code, anti-patterns, and improvement opportunities across the entire codebase. Existing `CODE_REVIEW.md` bugs (BUG-1 through BUG-25, marked FIXED) are **not** re-reported here unless the fix introduced a regression.

---

## Table of Contents
1. [Critical Errors](#1-critical-errors)
2. [Orphaned / Unused Code](#2-orphaned--unused-code)
3. [Code Quality & Anti-Patterns](#3-code-quality--anti-patterns)
4. [Configuration & Build Issues](#4-configuration--build-issues)
5. [Testing Issues](#5-testing-issues)
6. [Security Considerations](#6-security-considerations)
7. [Cross-cutting Concerns](#7-cross-cutting-concerns)

---

## 1. Critical Errors

### ERR-1: `main.py` — `_startup_backup` races against `main()`'s `close_db()`

**File**: `main.py` lines 106-117, 150-161  
**Severity**: 🔴 **High** — potential silent data loss on first startup

`_startup_backup(db_path, application_path)` is called at line 116, *after* `get_db(db_path)` has already established the connection. Inside `_startup_backup`, line 152 re-calls `get_db(db_path)` which retrieves the *same* connection object from thread-local storage. The backup is created with `VACUUM INTO` (line 154) or the backup API fallback (lines 159-161).

**Problem**: If `VACUUM INTO` fails and the fallback `sqlite3.connect(backup_path)` + `conn.backup(backup_conn)` runs while the application is holding an active WAL-mode connection with pending transactions, the backup may capture an inconsistent snapshot. The error is silently swallowed at lines 117-118 (`non-fatal`), so the user never knows the backup failed.

**Recommendation**: Either:
1. Use `conn.execute("BEGIN IMMEDIATE")` before the backup, or
2. Move the backup call to a background thread and log failures to the file-system logger, or
3. Use SQLite's `backup` API with proper page-by-page iteration that handles concurrent writes.

### ERR-2: `automation/import_preview` — Missing `.py` extension at filesystem level

**File**: `automation/import_preview` (no `.py` extension)  
**Severity**: 🔴 **High** — import will fail at runtime

The file on disk is `automation/import_preview` (no `.py` extension). Python's import system requires `.py` extension for regular module imports. Any `from automation.import_preview import ...` will raise `ModuleNotFoundError` at runtime.

**Impacted consumers** (from code search):
- `gui/import_preview_dialog.py` line: `from automation.import_preview import compute_diff`
- Any other file that imports from `automation.import_preview`

**Recommendation**: Rename the file to `automation/import_preview.py`.

### ERR-3: `scripts/migrate_workbook_to_sqlite.py` — Stale cursor after rollback+reconnect

**File**: `scripts/migrate_workbook_to_sqlite.py` lines 437-439  
**Severity**: 🔴 **High** — rows inserted into wrong connection after error recovery

When a transactional error occurs, the script creates a new `conn` but the old `cur` object still references the original (now-rolled-back) connection. Subsequent `cur.execute()` calls operate on the stale connection. If the error path was triggered midway through a batch, rows up to the error point may be silently lost while the script reports success.

**Recommendation**: On error recovery, recreate both `conn` and `cur` from the new connection.

### ERR-4: `data/db.py` — `get_detailer_schedules` missing error handling for `json.loads`

**File**: `data/db.py` lines 358-365  
**Severity**: 🟡 **Medium** — crashes on malformed DB data

`json.loads(row[0])` and `json.loads(row[1])` are called without try/except. If the `detailers` or `default_schedule` table contains malformed JSON (e.g. from manual DB editing or corruption), the app will crash with `json.JSONDecodeError` during startup or when refreshing detailer schedules.

**Impact**: This function is called from `config_service.py` during `MainWindow.__init__`, so a corrupt DB means the app won't start.

**Recommendation**: Wrap both `json.loads()` calls in try/except blocks, falling back to `[0, 1, 2, 3]` (Mon-Thu) as the default weekdays.

### ERR-5: `gui/inline_edit_bar.py` — `QTableWidget.insertRow` OOB on empty selection

**File**: `gui/inline_edit_bar.py` (inline insert at current row)  
**Severity**: 🟡 **Medium** — UI crash when inserting with no selection

If "Insert Row" is clicked while no row is selected in the table widget, `table.currentRow()` returns -1. Passing -1 to `table.insertRow()` places the new row at the *end*, but subsequent index-based operations on the new row may be off by one.

**Recommendation**: Guard with `if table.currentRow() >= 0` and default to row 0 (insert at top) when nothing is selected, or insert at end.

### ERR-6: `gui/calendar_panel.py` — `QDate.toPyDate()` deprecation

**File**: `gui/calendar_panel.py` (multiple locations)  
**Severity**: 🟡 **Medium** — future compatibility

`QDate.toPyDate()` is deprecated in PyQt5 5.15+ and removed in PyQt6. The recommended replacement is `QDate.toPython()`. While this works on current PyQt5 versions, it will break when the project eventually migrates to PyQt6.

**Recommendation**: Replace all `qdate.toPyDate()` with `qdate.toPython()`.

---

## 2. Orphaned / Unused Code

### ORPHAN-1: Unused imports in `gui/` package

| File | Unused Import | Line |
|---|---|---|
| `gui/audit_dialog.py` | `Qt` from `PyQt5.QtCore` | 11 |
| `gui/audit_dialog.py` | `QWidget` from `PyQt5.QtWidgets` | 23 |
| `gui/batch_edit_dialog.py` | `Qt` from `PyQt5.QtCore` | 12 |
| `gui/batch_edit_dialog.py` | `QDateEdit` from `PyQt5.QtWidgets` | 16 |
| `gui/batch_edit_dialog.py` | `QPushButton` from `PyQt5.QtWidgets` | 22 |
| `gui/batch_edit_dialog.py` | `QWidget` from `PyQt5.QtWidgets` | 25 |
| `gui/edit_form.py` | `QKeyEvent` from `PyQt5.QtGui` | 4 |
| `gui/inline_edit_bar.py` | `QSizePolicy` from `PyQt5.QtWidgets` | 19 |

**Recommendation**: Remove all unused imports.

### ORPHAN-2: Dead code blocks

| File | Dead Code | Lines |
|---|---|---|
| `gui/alert_panel.py` | `ALERT_SEVERITY_ORDER` dict defined but never referenced | 52-59 |
| `gui/list_panel.py` | `marker_area_top + len(milestones) * self.ROW_HEIGHT` — standalone expression, result discarded | 209 |
| `gui/pivot_chart.py` | `len(colors)` — standalone expression, result discarded | ~143 |
| `data/loader.py` | `COLUMN_MAP = {}` — empty dict, kept only for "test compatibility" | 16 |
| `data/loader.py` | `_fingerprint_cache` — module-level dict, only used by `unit_fingerprint` (valid) but never cleared | 18 |
| `main.py` | Redundant `import os` inside `_startup_backup` | 140 |
| `main.py` | Redundant `from data.db import get_db` inside `_startup_backup` | 150 |

**Recommendation**: Remove `ALERT_SEVERITY_ORDER`, the standalone expressions, `COLUMN_MAP`, and the redundant re-imports in `_startup_backup`.

### ORPHAN-3: `data/loader.py` — `force_reload` parameter never used

**File**: `data/loader.py` line 103  
**Severity**: 🟢 Low

The `load_units()` function accepts a `force_reload` parameter but the function body never reads it. It was likely intended for cache-busting but was never implemented.

**Recommendation**: Either implement `force_reload` behavior or remove the parameter.

### ORPHAN-4: `gui/close_progress_dialog.py` — `QWidget` import for type annotation

**File**: `gui/close_progress_dialog.py` (imports `QWidget`)  
**Severity**: 🟢 Low

`QWidget` is imported but only used in a type annotation. Due to `from __future__ import annotations`, the import resolves at runtime but isn't actually needed. However, any user of `get_type_hints()` on this module would benefit from the real annotation. This is a minor style inconsistency.

**Recommendation**: Either remove the import or use `TYPE_CHECKING` guard if it's truly only needed for type checking.

---

## 3. Code Quality & Anti-Patterns

### ANTI-1: `data/loader.py` — Module-level mutable cache with no invalidation

**File**: `data/loader.py` line 18  
**Severity**: 🟡 **Medium**

`_fingerprint_cache: dict[str, str]` is a module-level dict that never gets cleared. Over the lifetime of the application, as units are loaded and reloaded, this dict will accumulate entries for every unit ever fingerprinted — a slow memory leak.

**Recommendation**: Use `functools.lru_cache(maxsize=512)` instead of a manual dict, or add a `_clear_fingerprint_cache()` call on reload.

### ANTI-2: `main.py` — Backup retention slicing is fragile for small backup sets

**File**: `main.py` lines 206-211  
**Severity**: 🟢 Low

The retention logic uses `daily[: len(daily) - 7]` which returns an empty list when `len(daily) <= 7`. This works correctly for the deletion logic but the comment says "Keep: 7 daily, 4 weekly, 3 monthly" — when there are *exactly* 7 daily backups, none are deleted. When there are 8, the *oldest* 1 is deleted. This is technically correct but subtly counterintuitive: it keeps the newest 7, not the "7 most recent days."

**Recommendation**: Add a clarifying comment that the retention keeps the *most recent N* backups within each time bucket, not the N most recent time buckets.

### ANTI-3: `data/db.py` — `VACUUM INTO` SQL injection via f-string

**File**: `data/db.py` line 266  
**Severity**: 🟢 Low (internal use)

`conn.execute(f"VACUUM INTO '{export_path}'")` uses an f-string to inject a file path into SQL. Since `export_path` is internally generated (from `datetime.now()` + `os.path.join`), the injection risk is minimal, but it's a bad pattern.

**Recommendation**: Use `conn.execute("VACUUM INTO ?", (export_path,))` — SQLite 3.27.0+ supports parameterized `VACUUM INTO` paths.

### ANTI-4: `data/db.py` — Duplicate `_working_days_between` implementations

**File**: `data/db.py` lines 46-69 (`db` version) vs `data/models.py` lines 10-27 (`models` version)  
**Severity**: 🟡 **Medium**

Two implementations with different semantics:
- `db.py`: inclusive of both start and end, Mon-Fri only, string-based
- `models.py`: exclusive of start/inclusive of end, configurable weekdays, `date`-based

This is the bug that was "FIXED" in the existing CODE_REVIEW.md (BUG-4), but the fix only *removed a dead third implementation*. Two active implementations with different behavior still exist side-by-side. A future developer calling the wrong one for their use case will get subtly wrong results.

**Recommendation**: Rename at least one function to indicate its semantics unambiguously, e.g. `_working_days_between_inclusive` vs `_working_days_between_exclusive_start`.

### ANTI-5: `gui/batch_edit_dialog.py` — Mutating units in-place without saving

**File**: `gui/batch_edit_dialog.py` lines 129-148  
**Severity**: 🟡 **Medium**

The `_apply()` method modifies the `Unit` objects in `self._units` in-place and emits `unit_saved` signals, but **never calls `save_unit()`**. The caller (likely `main_window.py`) is expected to connect to `unit_saved` and perform the save. If the signal connection is missing or broken, the user sees "save successful" UI feedback but data is never persisted.

**Recommendation**: Consider having `_apply()` call `UnitService.save()` directly and report save errors, making the dialog self-contained. Alternatively, document the required signal connection more prominently.

### ANTI-6: `automation/import_csv.py` — Imports `PARSE_FUNCS` that may include lambda closures over mutable state

**File**: `automation/import_csv.py`  
**Severity**: 🟢 Low

`PARSE_FUNCS` contains lambdas like `lambda v: float(v.replace(",", ""))` which will crash on non-numeric input. The caller in `import_preview.py` wraps these in try/except, but silently swallows parse errors, defaulting to `None`.

**Recommendation**: Define named parse functions with proper error handling that return `None` on parse failure instead of crashing.

### ANTI-7: `pyproject.toml` — Missing `[build-system]` table

**File**: `pyproject.toml`  
**Severity**: 🟡 **Medium**

Without a `[build-system]` table, `pip install .` will use the legacy setuptools behavior with implicit version detection, which is deprecated. Modern Python packaging requires an explicit build backend declaration.

**Recommendation**: Add:
```toml
[build-system]
requires = ["setuptools>=64.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"
```

---

## 4. Configuration & Build Issues

### CFG-1: Three different project names

| Source | Name |
|---|---|
| `pyproject.toml` | `unit-tracker` |
| Filesystem directory | `Schedule-Viewer-App-v2` |
| Git remote URL | `SQL-Schedule-Tracker.git` |
| `main.py` internal paths | `.unit_tracker` |

**Severity**: 🟢 Low — no runtime impact, but confusing for contributors.

**Recommendation**: Align all names to one canonical project name.

### CFG-2: `config.yaml` — Missing from code review

**Severity**: 🟢 Low  
**Recommendation**: Ensure `config.yaml.example` is committed to the repo (if `config.yaml` itself contains secrets/paths) so new developers can set up the app.

### CFG-3: `requirements.txt` vs `pyproject.toml` — Duplicate dependency declarations

**File**: `requirements.txt` and `pyproject.toml`  
**Severity**: 🟢 Low

Dependencies are declared in both files. `requirements.txt` is generated by `pip freeze` while `pyproject.toml` has hand-maintained version ranges. These can drift apart.

**Recommendation**: Declare dependencies only in `pyproject.toml` and generate `requirements.txt` from it via `pip-compile` or a CI step.

---

## 5. Testing Issues

### TEST-1: `tests/test_models.py` — Hardcoded paths

**File**: `tests/test_models.py`  
**Severity**: 🟢 Low

Test files reference database paths that may not exist on all developer machines. The `conftest.py` sets up a temporary database fixture, but some test files bypass it with hardcoded paths.

**Recommendation**: Ensure all tests use the `tmp_path` or `test_db` fixture from `conftest.py`.

### TEST-2: Missing tests for `automation/import_preview.py`

**File**: `tests/` directory  
**Severity**: 🟡 **Medium**

The `import_preview.py` module contains non-trivial diffing logic (`compute_diff`, `parse_csv_rows`, `_csv_row_to_changes`) with zero test coverage. Given that this module handles data import safety, the lack of tests is a risk.

**Recommendation**: Add unit tests for `compute_diff` with known CSV/DB state pairs covering: new rows, updated rows, unchanged rows, and error conditions.

### TEST-3: `tests/test_loader.py` — Tests `_fingerprint_cache` but doesn't test cache invalidation

**File**: `tests/test_loader.py`  
**Severity**: 🟢 Low

The fingerprint tests verify that the fingerprint is computed correctly, but there's no test verifying that the cache is properly invalidated when data changes.

**Recommendation**: Add a test that modifies a unit, calls `unit_fingerprint` again, and asserts the fingerprint changed.

---

## 6. Security Considerations

### SEC-1: SQL injection in `_migrate_schema` via f-string index creation

**File**: `data/db.py` line 114  
**Severity**: 🟢 Low

`conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON units({col})")` uses f-strings for SQL identifiers. The `col` and `idx_name` values come from a hardcoded dict (`desired_indexes`), so injection isn't practically exploitable. But dynamic SQL construction is a bad pattern.

**Recommendation**: Since column names come from a controlled dict, this is acceptable. Document with a comment that `desired_indexes` values must be validated if ever made configurable.

### SEC-2: `main.py` — `VACUUM INTO` path injection (internal)

**File**: `main.py` line 154  
**Severity**: 🟢 Low  
Same issue as `db.py` ANTI-3. Internally generated path, but the f-string pattern is risky if the `backup_dir` path ever contains special characters.

---

## 7. Cross-cutting Concerns

### CROSS-1: WAL mode + `VACUUM INTO` interaction

**Files**: `data/db.py` line 34, `main.py` line 154, `data/db.py` line 266  
**Severity**: 🟡 **Medium**

The application enables WAL journal mode (`PRAGMA journal_mode=WAL`) on connection creation. `VACUUM INTO` is atomic and consistent even in WAL mode, but only if the connection isn't in the middle of a transaction. The backup functions call `VACUUM INTO` without ensuring the connection is idle. If a concurrent write is in progress (rare in this single-user app but architecturally possible), `VACUUM INTO` may fail with `SQLITE_BUSY`.

**Recommendation**: Wrap backup operations in `BEGIN IMMEDIATE ... COMMIT` to ensure they get priority access.

### CROSS-2: Thread safety of `close_db()` vs concurrent backup

**Files**: `main.py` lines 128-129, `data/db.py` lines 123-129  
**Severity**: 🟢 Low

`close_db()` at app exit calls `conn.close()` on the thread-local connection. If a background thread is still using the connection (e.g., for a long-running backup), the close will succeed but the thread will get `sqlite3.ProgrammingError: Cannot operate on a closed database`.

**Recommendation**: Add a connection-in-use counter or move `close_db()` to an `atexit` handler that waits for pending operations.

### CROSS-3: `__init__.py` files contain only docstrings

**Files**: All `__init__.py` files  
**Severity**: 🟢 Low

Each `__init__.py` contains only a docstring. This is correct for namespace packages, but the project uses regular packages (has `__init__.py`). Consider either:
1. Adding convenience imports in `__init__.py` (e.g., `from data.db import get_db, close_db`), or
2. Keeping them as-is (valid Python packages).

No action strictly required, but it's a design choice worth documenting.

---

## Summary by Severity

| Severity | Count | Key Examples |
|---|---|---|
| 🔴 **High** | 4 | ERR-1 (backup race), ERR-2 (missing .py extension — breaks imports), ERR-3 (stale cursor), ERR-4 (json.loads crash) |
| 🟡 **Medium** | 10 | ERR-5 (insertRow OOB), ERR-6 (deprecated API), ANTI-1 (memory leak), ANTI-4 (duplicate impls), ANTI-5 (silent batch save), ANTI-7 (missing build-system), TEST-2 (missing test coverage), CROSS-1 (WAL+VACUUM), CROSS-2 (thread safety), plus orphaned imports |
| 🟢 **Low** | 15 | Remaining anti-patterns, unused variables, cosmetic issues, config inconsistencies |

## Quick Wins (Low Effort, High Impact)

1. **Rename** `automation/import_preview` → `automation/import_preview.py` (fixes a broken import)
2. **Remove** the 8 orphaned imports in the `gui/` package
3. **Remove** the redundant `import os` and `from data.db import get_db` inside `main.py`'s `_startup_backup`
4. **Add** try/except around `json.loads()` in `get_detailer_schedules`
5. **Remove** the 3 dead code expressions (`ALERT_SEVERITY_ORDER`, standalone expressions in `list_panel.py` and `pivot_chart.py`)
6. **Remove** `force_reload` parameter from `load_units()`
7. **Add** `[build-system]` table to `pyproject.toml`