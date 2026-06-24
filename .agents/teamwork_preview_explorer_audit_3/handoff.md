# Codebase Audit Report: Data Integrity & Synchronization Pitfalls

## 1. Observations
We performed a comprehensive read-only audit of the SQLite database access, multi-user sync code, locking manager, audit logs, and loaders/writers. The following key items were directly observed in the codebase:

### Observation A: Batch Edit Save Discard
* **File**: `gui/batch_edit_dialog.py`, lines 124–147:
  ```python
  for i, unit in enumerate(self._units):
      ...
      if changed:
          self._updated_units.append(unit)
          self.unit_saved.emit(unit)
  ```
* **File**: `gui/list_panel.py`, line 1114:
  ```python
  dlg.unit_saved.connect(self._on_inline_save)  # reuse same save handler
  ```
* **File**: `gui/list_panel.py`, lines 1038–1040:
  ```python
  def _on_inline_save(self, unit: Unit) -> None:
      self.unit_saved.emit(unit)
  ```
* **File**: `gui/main_window.py`, lines 744–763:
  ```python
  def _start_save_worker(self, unit: Unit) -> None:
      if self._services.sync_service.is_save_blocked():
          ...
          return
      if self._active_save_worker_running():
          logger.warning("Save already in progress — queuing")
          return
      ...
      worker = SaveWorker(self._svc, unit)
      ...
      worker.start()
  ```

### Observation B: Sync System Complete Bypass
* **Observation**: `SyncService` (defined in `services/sync_service.py`) provides wrappers for acquiring locks and committing revisions (`acquire_lock()`, `release_lock()`, `commit_revision()`). However, these methods are never actually invoked by the main GUI workflow during unit editing or saving.
* **Proof**: A search across `gui/main_window.py`, `gui/edit_form.py`, and `services/unit_service.py` reveals no calls to `acquire_lock` or `commit_revision`. `SaveWorker` simply invokes `self._unit_service.save(self.unit)`, which bypasses the revision store (`revisions.json`) and shared cache (`units.json`) entirely.

### Observation C: SQLite WAL Mode on Shared Drive
* **File**: `data/db.py`, line 34:
  ```python
  conn.execute("PRAGMA journal_mode=WAL")
  ```
* **File**: `automation/import_csv.py`, line 164:
  ```python
  conn.execute("PRAGMA journal_mode=WAL")
  ```

### Observation D: Transaction Integrity Failure in DDL Migrations
* **File**: `services/migration_registry.py`, lines 101–119:
  ```python
  try:
      self._conn.executescript(migration.up_sql)
      ...
  except Exception as e:
      self._conn.rollback()
      raise RuntimeError(f"Migration v{migration.version} failed: {e}") from e
  ```

### Observation E: Fingerprint Caching Stale Value Bug
* **File**: `data/loader.py`, lines 15, 27–56:
  ```python
  _fingerprint_cache: dict[str, str] = {}
  ...
  def unit_fingerprint(unit: Unit) -> str:
      uid = unit.com_number
      cached = _fingerprint_cache.get(uid)
      if cached is not None:
          return cached
      ...
      _fingerprint_cache[uid] = result
      return result
  ```

### Observation F: False Audit Logs from SQLite Integer Coercion
* **File**: `data/db.py`, lines 183–193:
  ```python
  old_str = str(old_val) if old_val is not None else None
  new_str = str(new_val) if new_val is not None else None

  if old_str != new_str:
      conn.execute(
          "INSERT INTO _audit_log (com_number, field_name, old_value, new_value, saved_by) "
          "VALUES (?, ?, ?, ?, ?)",
          (com_number, field, old_str, new_str, saved_by),
      )
  ```

### Observation G: New Unit Audit Log Blind Spot
* **File**: `data/db.py`, lines 172–173:
  ```python
  if old_row is None:
      return 0
  ```

### Observation H: Unchecked OS/Permission Errors in LockManager/SessionRegistry
* **File**: `sync/lock_manager.py`, lines 123–128:
  ```python
  def _remove_stale_lock(self, path: Path, info: LockInfo) -> None:
      current = self._read_lock(path)
      if current and current.token == info.token and current.is_stale:
          with suppress(FileNotFoundError):
              path.unlink()
  ```
* **File**: `sync/session_registry.py`, lines 133–143:
  ```python
  for entry in sessions_dir.iterdir():
      if not entry.name.endswith(".json"):
          continue
      ...
  ```

### Observation I: Optimistic Locking Bypass on Missing updated_at
* **File**: `data/writer.py`, lines 81–86:
  ```python
  if unit.updated_at:
      where_clause = "WHERE com_number = ? AND updated_at = ?"
      where_params: tuple = (unit.com_number, unit.updated_at)
  else:
      where_clause = "WHERE com_number = ?"
      where_params = (unit.com_number,)
  ```

---

## 2. Logic Chain

### Logic Chain A: Batch Edit Data Loss (Observation A)
1. When a user updates multiple units via `BatchEditDialog`, the dialog loops through the list of modified units and synchronously emits a `unit_saved` signal for each one (lines 124–147).
2. The `unit_saved` signal propagates to `MainWindow._start_save_worker(unit)` (lines 744–763).
3. The first unit's signal initiates `SaveWorker` (which runs asynchronously in a `QThread`).
4. The remaining units' signals are processed immediately afterward in the same loop iteration. However, because `SaveWorker` for the first unit is now running, `_active_save_worker_running()` evaluates to `True`.
5. Instead of queuing or delaying, `_start_save_worker` prints a warning and returns immediately without starting a worker or persisting the data.
6. **Conclusion**: Only the first unit in a batch edit is saved to the SQLite database. All subsequent changes are silently discarded from disk, resulting in silent data loss.

### Logic Chain B: Sync System Complete Bypass (Observation B)
1. `SyncService` implements file-based lock acquisition and revision incrementing intended to prevent concurrent save overrides.
2. The UI save pipeline (`SaveWorker` and `UnitService.save`) writes directly to SQLite using `save_unit`.
3. Nowhere in this pipeline is `SyncService.acquire_lock` or `commit_revision` called.
4. **Conclusion**: Lock files are never created during normal editing/saving, and the revision metadata (`revisions.json` / `units.json`) is never updated. The lock coordination system is completely dead code in production.

### Logic Chain C: WAL Mode Network Corruption (Observation C)
1. The database connection initialization executes `PRAGMA journal_mode=WAL` (line 34).
2. SQLite's WAL mode relies on shared-memory files (`.shm`) mapped to the same physical memory space.
3. Network filesystems (such as SMB, NFS, or DFS, which host the shared drive for this multi-user app) do not support shared-memory mappings (`mmap`).
4. **Conclusion**: Running WAL mode over a network filesystem will result in connection failures (e.g., `sqlite3.OperationalError: disk I/O error`) or silent lock coordination failures leading to database corruption.

### Logic Chain D: Migration Transaction Failure (Observation D)
1. `executescript(migration.up_sql)` is used to run migration SQL commands.
2. SQLite's `executescript` commits the database transaction before running and commits each individual SQL statement independently.
3. If an error occurs in the middle of `up_sql`, statements prior to the error are already permanently committed to the database.
4. The subsequent call to `_conn.rollback()` in the `except` block is a no-op for the statements that succeeded.
5. **Conclusion**: A failed migration script leaves the database schema in a corrupted, partially-applied state.

### Logic Chain E: Stale Fingerprints (Observation E)
1. `unit_fingerprint` caches calculated hashes in a module-level dictionary `_fingerprint_cache` keyed by `com_number`.
2. There is no mechanism in the cache to invalidate or update entries.
3. **Conclusion**: If a unit is modified and `unit_fingerprint` is called again for the same unit within the same session, it returns the stale, initial hash instead of the updated one.

### Logic Chain F: False Audit Logs from SQLite Type Affinity (Observation F)
1. SQLite's dynamic type affinity stores real numbers like `0.0` or `40.0` as integer `0` or `40` to save space if no precision is lost.
2. When read back, `old_row["percent_complete"]` yields `0`.
3. The newly saved value is represented in Python as a float (e.g. `0.0`).
4. Comparing string representations (`str(0) != str(0.0)`) yields `True`.
5. **Conclusion**: A false change entry is written to `_audit_log` even though the numeric value has not changed.

---

## 3. Caveats
* **Network Testing**: We did not verify performance or behavior over a physical network share (SMB/DFS). The WAL mode network constraints are based on SQLite's engine documentation and known network filesystem limitations.
* **Sync Integration Status**: We assumed that the lack of call paths to `SyncService.acquire_lock()` and `SyncService.commit_revision()` in the GUI is an oversight rather than intentional, as `AGENTS.md` and the ROADMAP plans describe this as an active/enabled feature when `multi_user.enabled` is `True`.

---

## 4. Conclusion & Recommendations
The SQL-Schedule-Tracker codebase contains critical concurrency, transaction, and data integrity vulnerabilities.

| File Path | Lines | Severity | Description | Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| `gui/main_window.py`<br>`gui/batch_edit_dialog.py` | 745–763<br>124-147 | **High** | Batch edit saves are silently discarded except for the first unit due to lack of a queue/concurrency mechanism. | Replace the single-worker lock with a FIFO queue or implement a batch save method in `UnitService` that performs all updates in a single transaction. |
| `gui/main_window.py`<br>`services/unit_service.py` | N/A | **High** | Multi-user locking (`LockManager`) and revision tracking (`RevisionStore`) are completely bypassed during normal saves. | Integrate `SyncService.acquire_lock` on form edit/select, and call `SyncService.commit_revision` inside the save worker pipeline. |
| `data/db.py`<br>`automation/import_csv.py` | 34<br>164 | **High** | SQLite WAL mode is executed on startup, which causes errors/corruption on network filesystems. | Check if the database path resides on a network share; if so, disable WAL mode and fallback to `journal_mode=DELETE` or use standard rollback journals. |
| `services/migration_registry.py` | 101–119 | **High** | DDL migration scripts are executed outside a transaction via `executescript()`, leaving schemas corrupted on failure. | Split the script by semicolon or execute statements individually within a single, explicit transaction context. |
| `data/loader.py` | 15, 27–56 | **Medium** | Stale fingerprints returned due to un-invalidated module-level fingerprint cache. | Remove the fingerprint cache completely (calculation is cheap) or invalidate the cache entry on unit save. |
| `data/db.py` | 183–193 | **Medium** | False audit logs written due to string comparison mismatching SQLite coerced integers vs Python floats (e.g. `0` vs `0.0`). | Normalize float/int comparisons numerically before converting to strings, or coerce both values to float before comparison. |
| `data/db.py` | 172–173 | **Medium** | Newly created units are not logged in the audit trail because `old_row is None` causes an immediate return. | Log new unit insertions as having `old_value = NULL` and `new_value` set to the initial values. |
| `sync/lock_manager.py`<br>`sync/session_registry.py` | 123-128<br>133-143 | **Medium** | Unhandled `OSError`/`PermissionError` when writing locks or iterating session dirs can crash the GUI heartbeat timer. | Wrap `Path.iterdir()` and `unlink()` operations in try-except blocks and gracefully log warnings/errors. |
| `data/writer.py` | 81–86 | **Medium** | Optimistic locking is bypassed entirely if `unit.updated_at` is empty or falsy. | Raise an error if `updated_at` is empty or ensure it is always initialized when units are loaded. |

---

## 5. Verification Method

### 1. Verification of Batch Edit Discard Bug
1. Start the application.
2. Select multiple units in the list panel.
3. Click "Batch Edit".
4. Select a field (e.g., set Detailer to "Brandon B") and click OK.
5. Check the log file/console. You will see warning entries like:
   `MainWindow: Save already in progress — queuing`
6. Close the app and reload. Observe that only the first selected unit had its detailer updated in the database.

### 2. Verification of Transactional Rollback Failure
1. Run pytest:
   ```bash
   .venv/Scripts/python -m pytest tests/test_migration_registry.py
   ```
2. Verify that `test_apply_failure_rolls_back` passes, but inspect the database state manually inside the test after failure. The table `t1` created in the bad migration will still exist in the database despite the rollback assertion.

### 3. Verification of Fingerprint Stale Value Bug
1. Instantiate a `Unit` object.
2. Call `unit_fingerprint(unit)`.
3. Modify a field on the unit (e.g. `unit.job_name = "New Name"`).
4. Call `unit_fingerprint(unit)` again.
5. The return value will be identical to the first hash, proving the cache is stale.
