# Codebase Audit Handoff Report — SQL-Schedule-Tracker

This report presents the findings of a comprehensive, read-only audit of the services, models, and data logic layers of the SQL-Schedule-Tracker project.

---

## Summary of Core Findings

A detailed audit identified **8 logical and functional bugs** ranging from high-severity data loss risks in the multi-user sync and import preview engines, to capacity tracking gaps and connection leaks in the service registry and database layer.

---

## Detailed Bug Catalog

| # | File Path | Line Range | Severity | Description | Recommendation |
|---|---|---|---|---|---|
| **1** | `data/models.py` | 168-186 | **High** | Capacity-based red check is skipped when `working_days` is 0. This occurs when a unit is due today or on a non-working day. It causes a false-negative where incomplete units due today are marked gray/yellow instead of red. | If `working_days == 0` and `remaining_hours > 0`, return `"red"` immediately. |
| **2** | `services/unit_service.py` | 71-84, 174-181 | **Medium** | Connection leak in `get_by_com()`. It calls `_get_conn()` which creates a new `sqlite3.connect()` connection but never closes it. | Replace `_get_conn()` in `get_by_com()` with thread-local `get_db(self._db_path)`. |
| **3** | `data/writer.py` | 90-146 | **High** | `remaining_hours` is never updated on manual saves. This causes the database column and subsequent Excel exports to contain stale/incorrect values, breaking data integrity. | Recalculate `remaining_hours` in `save_unit()` and include it in the SQLite UPDATE query. |
| **4** | `data/loader.py` | 59-95 | **High** | Identicals rule forces target hours to 0.0 in-memory. When saved, this 0.0 is persisted. If the unit later becomes the primary unit, its target hours remain 0.0 instead of being recalculated. | Explicitly compute/restore `target_department_hours` for the primary unit in `_apply_identicals()`. |
| **5** | `sync/revision_store.py`<br>`sync/shared_cache.py` | 111-115<br>159-168 | **High** | Wiping of other users' revisions/cache. General `OSError` (e.g. transient sharing violations on Windows network drives) in `_read_all()` is caught and handles it by returning `{}`. This causes the subsequent commit/update to overwrite the file and delete all other records. | Do not catch general `OSError` (propagate it so the save is safely aborted or retried), or implement a retry mechanism. |
| **6** | `automation/import_preview.py` | 135-137 | **High** | Import preview hides blank CSV fields that will actually overwrite DB values with `NULL` (data deletion). Because it skips comparison when `new_val` is `None`, the diff shows "no changes", but the import executes an overwrite with `NULL`. | Compare existing value against `None` if the column is present in the CSV data. |
| **7** | `services/validation.py` | 260-299 | **Medium** | `validate_input` decorator fails to validate positional arguments because it only checks `kwargs`. | Bind arguments using `inspect.Signature.bind()` before validating. |
| **8** | `services/validation.py` | 74-154 | **Medium** | Missing date validation in `UNIT_FIELD_RULES`, allowing invalid date types (e.g., strings) to pass validation and subsequently crash on `isoformat()` in the writer. | Add FieldRules for date fields to enforce type checking (e.g., `date` object or `None`). |

---

## 1. Observation

### Observation 1: Capacity Red Check Skipped
In `data/models.py` line 168-186:
```python
            working_days = _working_days_between(today, self.detailing_due_date, self.working_days)
            if working_days > 0 and self.department_hours > 0:
                remaining_hours = self.department_hours * (1.0 - pct / 100.0)
                # ...
                if remaining_hours > available_hours:
                    return "red"
```
When `today == detailing_due_date`, `_working_days_between` returns `0`, which makes `working_days > 0` false, skipping the capacity check and returning `"gray"` or `"yellow"` instead of `"red"`.

### Observation 2: Connection Leak in get_by_com
In `services/unit_service.py` line 71-84:
```python
    def get_by_com(self, com_number: str) -> Unit | None:
        import sqlite3

        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM units WHERE com_number = ?", (com_number,)).fetchone()
        if row is None:
            return None
        return row_to_unit(row)
```
And line 174-181:
```python
    def _get_conn(self):
        """Get a raw SQLite connection (for internal queries only)."""
        import sqlite3

        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
```
The connection `conn` is opened but `conn.close()` is never called in `get_by_com()`.

### Observation 3: remaining_hours Out-Of-Sync
In `data/writer.py` line 88-146, the SQL statement does not include `remaining_hours`.
In `automation/export_to_workbook.py` line 39:
```python
    ("M", "remaining_hours", "float"),
```
Column M (remaining hours) is exported directly from the database column, which is now stale.

### Observation 4: Identicals Rule Persistent Data Loss
In `data/loader.py` line 59-95:
```python
        primary = min(group, key=_sort_key)

        for u in group:
            if u is not primary:
                u.target_department_hours = 0.0
                u.is_non_primary_identical = True
```
When a unit is primary, it is skipped. If it was previously saved with `0.0` target hours (from when it was secondary), its database column is `0.0`, and since it's skipped here, it remains `0.0` instead of restoring the correct calculation.

### Observation 5: Sync/Cache Data Wiping
In `sync/revision_store.py` line 111-115:
```python
    def _read_all(self) -> dict[str, dict[str, object]]:
        try:
            return json.loads(self.revision_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
```
In `sync/shared_cache.py` line 159-168:
```python
    def _read_all(self) -> dict[str, dict[str, object]]:
        try:
            data: dict = json.loads(self.cache_file.read_text(encoding="utf-8"))
            ...
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
```
If `read_text` raises `OSError` (e.g. sharing violation lock on Windows), they return `{}`. When writing back via `commit()` or `update()`, they save `{com_number: new_entry}` and overwrite the whole file, wiping out all other units.

### Observation 6: Blank Fields Hidden in Preview
In `automation/import_preview.py` line 134-137:
```python
    for field_name in import_fields:
        new_val = new_data.get(field_name)
        if new_val is None:
            continue
```
If a field is empty in the CSV, `new_val` is `None` and is skipped (no change reported), but the actual import writes `None` to the DB and clears it.

### Observation 7: validate_input Positional Ignored
In `services/validation.py` line 260-299:
```python
            for field_name, rule in field_rules.items():
                if field_name not in kwargs:
                    continue
                value = kwargs[field_name]
```
Arguments passed positionally are in `args` and not `kwargs`, so they bypass the loop completely.

### Observation 8: Date Validation Gap
In `services/validation.py` line 74-154, `UNIT_FIELD_RULES` contains no entries for `unit_detailing_start_date`, `unit_moved_to_checking_date`, `unit_detailing_completion_date`, `dept_due_date_previous`, `detailing_due_date`, or `build_date`.

---

## 2. Logic Chain

1. **Bug 1**: If a unit is due today, `_working_days_between` counts 0 working days left. Because the code checks `if working_days > 0`, it skips the capacity-based red check. Consequently, a unit with remaining hours due today is marked as on-track/gray instead of red (behind schedule).
2. **Bug 2**: In `services/unit_service.py`, `_get_conn()` returns a newly opened sqlite3 connection. Since `get_by_com()` calls `_get_conn()` but never calls `close()`, a connection handle is leaked every time a single unit is fetched (e.g., during conflict checks).
3. **Bug 3**: Since `save_unit()` does not include the `remaining_hours` column in its update query, manual saves fail to update this column in the DB. Because the Excel export directly writes this DB column to Column M, the exported workbook displays stale `remaining_hours` values after manual updates.
4. **Bug 4**: When `_apply_identicals` runs, it zeroes out `target_department_hours` for secondary identicals in-memory. If a user saves a secondary identical, this `0.0` is saved to the database. If that unit later becomes primary (due to dates/contracts shifting), it is skipped in `_apply_identicals` and therefore retains its stored `0.0` instead of restoring the correct calculation, resulting in permanent data loss.
5. **Bug 5**: In `sync/revision_store.py` and `sync/shared_cache.py`, any `OSError` (e.g. sharing violation on a network drive) caught during `_read_all()` causes it to return `{}`. When the store subsequently saves the new commit, it overwrites the file with only the single updated unit, deleting all other entries.
6. **Bug 6**: When `_csv_row_to_changes` in `import_preview.py` iterates over fields, it skips any field where the parsed CSV value is `None`. Since a blank CSV field parses as `None`, the preview reports no changes, even though the import will overwrite and delete the existing database value by writing `NULL`.
7. **Bug 7**: Since the `validate_input` decorator only checks `kwargs`, any decorated method called with positional arguments (e.g. `set_hours(5.0)`) will bypass all decorator validation checks.
8. **Bug 8**: Because date fields are missing from `UNIT_FIELD_RULES`, the validation layer does not type-check them. If a string is assigned to a date field, it will pass validation but crash with `AttributeError` when `isoformat()` is called during the save pipeline.

---

## 3. Caveats

- **Network-driven testing**: As the environment is in CODE_ONLY mode, network-driven features like the SSRS URL validation were audited statically rather than tested against a live SSRS endpoint.
- **UI Element Scope**: Audited only the logical layers and did not design QT UI widget layout alterations.

---

## 4. Conclusion

The SQL-Schedule-Tracker backend and service layers contain critical logical flaws that lead to data corruption (stale `remaining_hours` in Excel exports), permanent data loss (zeroed target hours when identicals shift; wiped revision/cache json files due to sharing violations), and false negatives in schedule tracking (skipping due-today capacity alerts). Addressing these issues in the database services and hook registry is necessary to ensure long-term stability and multi-user sync safety.

---

## 5. Verification Method

To verify these issues independently:
1. **Run Pytest**: Execute the existing test command:
   ```powershell
   .venv\Scripts\pytest -v
   ```
2. **Replicate identicals bug**:
   - Save two units under the same contract number with different due dates.
   - Edit the secondary unit and save it.
   - Swap their due dates (making the secondary one the primary).
   - Reload and verify that the new primary unit has `0.0` target hours instead of its original hours.
3. **Replicate capacity due-today bug**:
   - Create a unit due today with 40 department hours and 0% complete.
   - Verify that its `calculated_status_color` is evaluated as `"gray"` or `"yellow"` instead of `"red"`.
