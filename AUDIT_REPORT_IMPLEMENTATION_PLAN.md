# Audit Report 2026 — Fix All 27 Issues

All 27 issues from [AUDIT_REPORT_2026.md](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/AUDIT_REPORT_2026.md) have been researched and confirmed as real bugs. This plan organizes the fixes into 5 phases, ordered by dependency and risk (data integrity first, then logic, then UI).

## User Review Required

> [!IMPORTANT]
> **Issue 3.1 (Sync System Bypass)** is deferred from this plan. Wiring `SyncService.acquire_lock()` / `commit_revision()` into the save pipeline is a substantial feature integration — not a simple bug fix — and carries risk of introducing new lock contention issues. Recommend tackling it as a separate follow-up task.

> [!WARNING]
> **Issue 1.4 (Identicals Data Loss)** — the fix avoids persisting the zeroed-out `target_department_hours` by restoring the original computed value before save. This changes save behavior for non-primary identicals. Please confirm this is acceptable.

## Open Questions

> [!IMPORTANT]
> **Issue 2.16 (Onboarding context menus)** — The audit report suggests either removing the text OR implementing context menus. Which approach do you prefer? The plan currently removes the misleading text as the simpler fix.

---

## Phase 1: Data Layer — Critical Integrity Fixes

These fixes address data corruption, loss, and stale data risks. No GUI dependencies.

---

### Data Model

#### [MODIFY] [models.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/data/models.py)

**Issue 1.1 — Capacity red check skipped when due today**

Change the guard at line 170 from `if working_days > 0` to also handle the `working_days <= 0` case. When there are 0 working days remaining but `remaining_hours > 0`, return `"red"` immediately:

```diff
             working_days = _working_days_between(today, self.detailing_due_date, self.working_days)
-            if working_days > 0 and self.department_hours > 0:
+            if self.department_hours > 0:
                 remaining_hours = self.department_hours * (1.0 - pct / 100.0)
+
+                # Zero (or negative) working days with remaining work → red
+                if working_days <= 0:
+                    if remaining_hours > 0:
+                        return "red"
+                    # remaining_hours == 0 means 100% effective → fall through to pct gates
+                else:
+                    # Reserve checking pipeline time for units not yet in checking
+                    ...existing capacity check...
```

---

### Writer

#### [MODIFY] [writer.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/data/writer.py)

**Issue 1.3 — remaining_hours not updated on save**

Add `remaining_hours` to the UPDATE SET clause, computing it inline:

```diff
             working_days_in_checking = ?,
+            remaining_hours = ?,
             updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')
```

And add the parameter:
```python
# After working_days_in_checking param:
unit.department_hours * (1.0 - unit.percent_complete / 100.0),  # remaining_hours
```

**Issue 3.8 — Optimistic locking bypass on missing updated_at**

Replace the falsy guard with a proper check. If a unit exists in the DB but has no `updated_at`, always include the `AND updated_at IS NULL` clause:

```diff
-    if unit.updated_at:
+    if unit.updated_at:  # Has a timestamp — match it exactly
         where_clause = "WHERE com_number = ? AND updated_at = ?"
         where_params: tuple = (unit.com_number, unit.updated_at)
     else:
-        where_clause = "WHERE com_number = ?"
-        where_params = (unit.com_number,)
+        where_clause = "WHERE com_number = ? AND updated_at IS NULL"
+        where_params = (unit.com_number,)
```

---

### Loader

#### [MODIFY] [loader.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/data/loader.py)

**Issue 1.4 — Identicals rule persistent data loss**

Store the original `target_department_hours` before zeroing it, so `save_unit()` can restore it. Add a new transient field `_original_target_department_hours` to the Unit dataclass and set it in `_apply_identicals()`:

```diff
         for u in group:
             if u is not primary:
+                u._original_target_department_hours = u.target_department_hours
                 u.target_department_hours = 0.0
                 u.is_non_primary_identical = True
```

Then in `writer.py`, use `_original_target_department_hours` if available when persisting:

```diff
-            target_dept_hours = MAX(0, ?),
+            target_dept_hours = MAX(0, ?),  -- uses original value for non-primary identicals
```
```python
# Parameter: restore original target_dept_hours for non-primary identicals
getattr(unit, '_original_target_department_hours', unit.target_department_hours),
```

**Issue 3.4 — Fingerprint cache never invalidated**

Remove the module-level cache entirely — `sha256` of a small JSON payload is sub-millisecond:

```diff
-_fingerprint_cache: dict[str, str] = {}
-
 def unit_fingerprint(unit: Unit) -> str:
     """Stable hash of editable unit fields for optimistic conflict checks."""
-    uid = unit.com_number
-    cached = _fingerprint_cache.get(uid)
-    if cached is not None:
-        return cached
     payload = { ... }
     raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
-    result = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
-    _fingerprint_cache[uid] = result
-    return result
+    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
```

---

### Database

#### [MODIFY] [db.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/data/db.py)

**Issue 3.5 — False audit logs from SQLite type affinity**

Normalize numeric values before string comparison:

```diff
+def _normalize_for_comparison(val):
+    """Normalize a value for audit log comparison, accounting for SQLite type affinity."""
+    if val is None:
+        return None
+    if isinstance(val, float):
+        # Normalize float to int if it's a whole number (SQLite stores 0.0 as 0)
+        if val == int(val):
+            return str(int(val))
+        return str(val)
+    return str(val)
+
 def log_field_changes(...):
     ...
-        old_str = str(old_val) if old_val is not None else None
-        new_str = str(new_val) if new_val is not None else None
+        old_str = _normalize_for_comparison(old_val)
+        new_str = _normalize_for_comparison(new_val)
```

**Issue 3.6 — New unit insertion not audited**

Log creation events instead of returning early:

```diff
     if old_row is None:
-        return 0
+        # New unit — log all initial field values as creation events
+        for field, new_val in new_values.items():
+            new_str = _normalize_for_comparison(new_val)
+            if new_str is not None:
+                conn.execute(
+                    "INSERT INTO _audit_log (com_number, field_name, old_value, new_value, saved_by) "
+                    "VALUES (?, ?, NULL, ?, ?)",
+                    (com_number, field, new_str, saved_by),
+                )
+                changes += 1
+        if changes > 0:
+            conn.commit()
+        return changes
```

**Issue 3.2 — WAL mode on shared/network drives**

Add a helper to detect network paths and conditionally disable WAL:

```python
def _safe_journal_mode(conn, db_path: str) -> None:
    """Set WAL mode only if the database is on a local filesystem."""
    import os
    path = os.path.abspath(db_path)
    # UNC paths (\\server\share) or mapped drives on Windows network shares
    if path.startswith("\\\\") or (os.name == "nt" and _is_network_drive(path)):
        conn.execute("PRAGMA journal_mode=DELETE")
    else:
        conn.execute("PRAGMA journal_mode=WAL")

def _is_network_drive(path: str) -> bool:
    """Check if a Windows drive letter maps to a network share."""
    try:
        import ctypes
        drive = os.path.splitdrive(path)[0] + "\\"
        return ctypes.windll.kernel32.GetDriveTypeW(drive) == 4  # DRIVE_REMOTE
    except Exception:
        return False
```

Replace both `conn.execute("PRAGMA journal_mode=WAL")` calls (in `get_db()` and in `import_csv.py`).

---

### Unit Service

#### [MODIFY] [unit_service.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/services/unit_service.py)

**Issue 1.2 — Connection leak in get_by_com**

Replace `_get_conn()` with `get_db()` from `data.db`:

```diff
     def get_by_com(self, com_number: str) -> Unit | None:
-        import sqlite3
-        conn = self._get_conn()
-        conn.row_factory = sqlite3.Row
+        conn = get_db(self._db_path)
         row = conn.execute("SELECT * FROM units WHERE com_number = ?", (com_number,)).fetchone()
         if row is None:
             return None
         return row_to_unit(row)
```

Remove `_get_conn()` method entirely.

---

### Validation

#### [MODIFY] [validation.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/services/validation.py)

**Issue 1.7 — validate_input decorator ignores positional arguments**

Use `inspect.signature` to bind positional args to parameter names before validation:

```diff
+import inspect
+
 def validate_input(**field_rules: FieldRule):
     def decorator(func):
+        sig = inspect.signature(func)
         @wraps(func)
         def wrapper(*args, **kwargs):
+            bound = sig.bind(*args, **kwargs)
+            bound.apply_defaults()
+            all_args = bound.arguments
             errors = []
             for field_name, rule in field_rules.items():
-                if field_name not in kwargs:
+                if field_name not in all_args:
                     continue
-                value = kwargs[field_name]
+                value = all_args[field_name]
                 ...  # rest unchanged
```

**Issue 1.8 — Missing date validation rules**

Add `FieldRule` entries for all 6 date fields plus a type check. Extend `FieldRule` with an optional `allowed_types` field:

```python
# Add to UNIT_FIELD_RULES:
"unit_detailing_start_date": FieldRule(nullable=True),
"unit_moved_to_checking_date": FieldRule(nullable=True),
"unit_detailing_completion_date": FieldRule(nullable=True),
"dept_due_date_previous": FieldRule(nullable=True),
"detailing_due_date": FieldRule(nullable=True),
"build_date": FieldRule(nullable=True),
```

Add a date type check in `validate_unit()`:
```python
from datetime import date
DATE_FIELDS = {"unit_detailing_start_date", "unit_moved_to_checking_date",
               "unit_detailing_completion_date", "dept_due_date_previous",
               "detailing_due_date", "build_date"}
for field in DATE_FIELDS:
    val = getattr(unit, field, None)
    if val is not None and not isinstance(val, date):
        errors.append(f"{field}: must be a date or None, got {type(val).__name__}")
```

---

### Sync Layer

#### [MODIFY] [revision_store.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/sync/revision_store.py)

**Issue 1.5 — _read_all swallows OSError, enabling data wipe**

Narrow the exception handling: catch only `FileNotFoundError` and `json.JSONDecodeError`. Let real I/O errors propagate:

```diff
-        except (FileNotFoundError, OSError, json.JSONDecodeError):
+        except FileNotFoundError:
+            return {}
+        except json.JSONDecodeError:
+            logger.warning("Corrupt revision file: %s — returning empty", self.revision_file)
             return {}
+        # OSError (PermissionError, disk errors) now propagates — callers must handle
```

#### [MODIFY] [shared_cache.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/sync/shared_cache.py)

Same narrowing as revision_store.py.

#### [MODIFY] [lock_manager.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/sync/lock_manager.py)

**Issue 3.7 — Unchecked OS errors in lock removal**

```diff
     def _remove_stale_lock(self, path: Path, info: LockInfo) -> None:
         current = self._read_lock(path)
         if current and current.token == info.token and current.is_stale:
-            with suppress(FileNotFoundError):
+            with suppress(FileNotFoundError, PermissionError, OSError):
                 path.unlink()
```

#### [MODIFY] [session_registry.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/sync/session_registry.py)

**Issue 3.7 — Unchecked OS errors in session iteration**

Wrap the `iterdir()` call in a try/except:

```diff
     def list_active(self, sessions_dir: Path) -> list[SessionInfo]:
         active: list[SessionInfo] = []
-        for entry in sessions_dir.iterdir():
+        try:
+            entries = list(sessions_dir.iterdir())
+        except OSError:
+            logger.warning("Cannot read sessions directory: %s", sessions_dir)
+            return active
+        for entry in entries:
```

---

### Import Preview

#### [MODIFY] [import_preview.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/automation/import_preview.py)

**Issue 1.6 — Blank preview skips None values, hiding upcoming data deletion**

Instead of skipping when `new_val is None`, compare it against the existing DB value:

```diff
     for field_name in import_fields:
         new_val = new_data.get(field_name)
-        if new_val is None:
-            continue
+        old_val = existing_data.get(field_name) if existing_data else None
+        if new_val is None and old_val is not None:
+            # CSV would clear this field — flag as a deletion
+            changes.append(FieldDiff(field_name, old_val, None, is_deletion=True))
+            continue
+        if new_val is None:
+            continue  # Both None — no change
```

---

### Migration Registry

#### [MODIFY] [migration_registry.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/services/migration_registry.py)

**Issue 3.3 — executescript() breaks transaction integrity**

Replace `executescript()` with individual `execute()` calls inside a transaction:

```diff
     def apply(self, migration: Migration) -> None:
         t0 = time.perf_counter()
         try:
-            self._conn.executescript(migration.up_sql)
+            # Split SQL into individual statements and execute within a transaction
+            statements = [s.strip() for s in migration.up_sql.split(";") if s.strip()]
+            for stmt in statements:
+                self._conn.execute(stmt)
             elapsed = int((time.perf_counter() - t0) * 1000)
             self._conn.execute(
                 "INSERT INTO _schema_migrations ..."
             )
             self._conn.commit()
```

---

## Phase 2: GUI — Critical UX Fixes

---

### Batch Edit Save Queue

#### [MODIFY] [main_window.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/gui/main_window.py)

**Issue 2.1 — Batch save drops all but first unit**

Add a `_save_queue` and drain it sequentially:

```diff
 class MainWindow:
     def __init__(self, ...):
         ...
+        self._save_queue: list[Unit] = []
         ...

     def _start_save_worker(self, unit: Unit) -> None:
         if self._services.sync_service.is_save_blocked():
             ...
             return
         if self._active_save_worker_running():
-            logger.warning("Save already in progress — queuing")
-            return
+            logger.info("Save already in progress — queuing unit %s", unit.com_number)
+            self._save_queue.append(unit)
+            return
         ...
         worker = SaveWorker(self._svc, unit)
         ...

     def _on_save_finished(self):
         ... existing logic ...
+        # Drain save queue
+        if self._save_queue:
+            next_unit = self._save_queue.pop(0)
+            self._start_save_worker(next_unit)
```

**Issue 2.9 — Broken close ETA tracking**

Populate `_sync_unit_durations` from the save worker elapsed time, and cap with `deque`:

```diff
-        self._sync_unit_durations: list[float] = []
+        from collections import deque
+        self._sync_unit_durations: deque[float] = deque(maxlen=50)
```

In `_on_save_finished()`, record the elapsed duration:
```python
if hasattr(self._save_worker, '_start_time'):
    elapsed = time.time() - self._save_worker._start_time
    self._sync_unit_durations.append(elapsed)
```

In `SaveWorker.__init__()`, record start time:
```python
self._start_time = time.time()
```

**Issue 2.8 — Dead SyncStatusWidget**

Wire the save worker to the sync status widget:
```python
# In _start_save_worker():
self._sync_status_widget.set_progress(f"Saving {unit.com_number}...", -1)

# In _on_save_finished():
self._sync_status_widget.reset()
```

**Issue 2.11 — Stale search match selection**

```diff
     def _on_global_search(self) -> None:
         query = self._search_edit.text().strip().lower()
         if not query:
+            self._search_single_match = None
             return
```

**Issue 2.12 — Misleading save error message**

```diff
+        from services.validation import ValidationError
+        is_validation = isinstance(original_error, ValidationError)
+        if is_validation:
+            hint = "Please correct the highlighted fields and try again."
+        else:
+            hint = "Check your network connection and try saving again."
         QMessageBox.warning(
             self,
             "Save Failed",
-            f"Could not save to database:\n{error_msg}\n\n"
-            f"Your changes are still in the form. Check your network connection and try saving again.",
+            f"Could not save to database:\n{error_msg}\n\n"
+            f"Your changes are still in the form. {hint}",
         )
```

**Issue 2.14 — Calendar selection not synced**

```diff
     def on_unit_selected(self, unit: Unit | None):
         ...
         self.timeline_panel.set_unit(unit)
         self.edit_form.set_unit(unit)
+        # Sync selection to calendar and alert panels
+        com = unit.com_number if unit else None
+        self.calendar_panel.set_highlighted_unit(com)
+        self.alert_panel.set_selected_unit(com)
```

**Issue 2.15 — Alert panel selection not synced**

Add `set_selected_unit()` method to `AlertPanel` (see alert_panel.py changes below).

Also initialize `_search_single_match` in `__init__`:
```python
self._search_single_match: Unit | None = None
```

---

### Alert Panel

#### [MODIFY] [alert_panel.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/gui/alert_panel.py)

**Issue 2.15** — Add selection synchronization method:

```python
def set_selected_unit(self, com_number: str | None) -> None:
    """Highlight the specified unit in the alert list."""
    for i in range(self.list_widget.count()):
        item = self.list_widget.item(i)
        unit = item.data(Qt.UserRole)
        if unit and unit.com_number == com_number:
            self.list_widget.setCurrentItem(item)
            return
    self.list_widget.clearSelection()
```

---

### Theme

#### [MODIFY] [theme.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/gui/theme.py)

**Issue 2.7 — No :checked pseudo-class for view toggle buttons**

Add checked state to `_BTN_DEFAULT`:

```diff
 _BTN_DEFAULT = """\
     QPushButton {{
         background: {bg_tertiary};
         color: {text_primary};
         border: 1px solid {border};
         border-radius: 6px;
         padding: 6px 14px;
         font-weight: 500;
     }}
     QPushButton:hover {{ background: {border}; }}
+    QPushButton:checked {{
+        background: {accent};
+        color: {text_on_accent};
+        border: 1px solid {accent};
+    }}
+    QPushButton:checked:hover {{
+        background: {accent_hover};
+    }}
 """
```

---

### Edit Form

#### [MODIFY] [edit_form.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/gui/edit_form.py)

**Issue 2.2 — _VALID_STYLE = "" nukes theme**

Remove the `_VALID_STYLE` constant. Instead of setting stylesheet to empty, remove only the validation-specific properties:

```diff
-_VALID_STYLE = ""  # Reset to default
-_INVALID_STYLE = "border: 2px solid red; background-color: #fff0f0;"
+# Theme-aware validation styles are set dynamically based on current theme
+def _get_invalid_style(theme_name: str = "light") -> str:
+    from gui.theme import THEMES
+    tokens = THEMES.get(theme_name, THEMES["light"])
+    return (
+        f"border: 2px solid {tokens['text_error']}; "
+        f"background-color: {tokens['bg_hover']}; "
+        f"color: {tokens['text_primary']};"
+    )
```

**Issue 2.3 — Invalid field style unreadable in dark theme**

Handled by the theme-aware `_get_invalid_style()` function above. The `_validate_fields()` method will use it:

```diff
     def _validate_fields(self):
-        self.percent_spin.setStyleSheet(_VALID_STYLE)
-        ...
+        # Remove inline validation styles (theme stylesheet takes over)
+        for widget in (self.percent_spin, self.dept_hours_spin, self.actual_hours_spin, self.due_date_edit):
+            widget.setStyleSheet("")
+            widget.setProperty("invalid", False)
+            widget.style().unpolish(widget)
+            widget.style().polish(widget)
         ...
         if errors:
-            widget.setStyleSheet(_INVALID_STYLE)
+            widget.setStyleSheet(_get_invalid_style(self._theme_name))
```

Store `self._theme_name` during construction or via a setter from MainWindow.

---

### Conflict Dialog

#### [MODIFY] [conflict_dialog.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/gui/conflict_dialog.py)

**Issue 2.4 — Hardcoded yellow highlight unreadable in dark theme**

```diff
             if local_val != remote_val:
-                item_local.setBackground(QColor("#fef9c3"))
-                item_remote.setBackground(QColor("#fef9c3"))
+                from gui.theme import THEMES
+                tokens = THEMES.get(self._theme_name, THEMES["light"])
+                item_local.setBackground(QColor(tokens["bg_selected"]))
+                item_remote.setBackground(QColor(tokens["bg_selected"]))
+                item_local.setForeground(QBrush(QColor(tokens["text_primary"])))
+                item_remote.setForeground(QBrush(QColor(tokens["text_primary"])))
```

---

### Import Preview Dialog

#### [MODIFY] [import_preview_dialog.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/gui/import_preview_dialog.py)

**Issue 2.5 — Hardcoded pastel colors unreadable in dark theme**

Replace hardcoded RGB with theme-aware colors and call `apply_theme()` in constructor:

```python
# In __init__:
from gui.theme import apply_theme, THEMES
apply_theme(self, theme_name)
tokens = THEMES.get(theme_name, THEMES["light"])
```

Replace the row color constants with theme-derived colors with explicit foreground.

---

### Timeline Panel

#### [MODIFY] [timeline_panel.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/gui/timeline_panel.py)

**Issue 2.6 — 15+ hardcoded colors break dark theme**

Store `_theme_name` and derive all paint colors from `THEMES[self._theme_name]`:

```python
def set_theme(self, theme_name: str) -> None:
    self._theme_name = theme_name
    self.update()

def paintEvent(self, event):
    from gui.theme import THEMES
    tokens = THEMES.get(self._theme_name, THEMES["light"])

    bg_color = QColor(tokens["bg_secondary"])
    text_color = QColor(tokens["text_primary"])
    muted_color = QColor(tokens["text_muted"])
    border_color = QColor(tokens["border"])
    accent_color = QColor(tokens["accent"])
    ...
```

Replace all 15 hardcoded `QColor(...)` calls with token-derived colors.

---

### Audit Dialog

#### [MODIFY] [audit_dialog.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/gui/audit_dialog.py)

**Issue 2.10 — Sorting triggers on every setItem during data load**

```diff
-        self.table.setSortingEnabled(True)
+        # Sorting is enabled AFTER data population to avoid per-setItem re-sorts
         ...
         self._load_data()
+        self.table.setSortingEnabled(True)
```

---

### Inline Edit Bar

#### [MODIFY] [inline_edit_bar.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/gui/inline_edit_bar.py)

**Issue 2.13 — Save button missing objectName**

```diff
         self.save_btn = QPushButton("Save")
+        self.save_btn.setObjectName("inline_save_btn")
         self.save_btn.setMinimumWidth(50)
```

---

### Onboarding

#### [MODIFY] [onboarding.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/gui/onboarding.py)

**Issue 2.16 — Mentions non-existent right-click context menus**

```diff
-            "Column widths are resizable. Right-click context menus available. "
+            "Column widths are resizable. "
```

---

### Import CSV

#### [MODIFY] [import_csv.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/automation/import_csv.py)

**Issue 3.2 — WAL mode on shared drives (second call site)**

Replace the raw WAL pragma with the shared `_safe_journal_mode()` helper from `data/db.py`:

```diff
-    conn.execute("PRAGMA journal_mode=WAL")
+    from data.db import _safe_journal_mode
+    _safe_journal_mode(conn, db_path)
```

---

## Summary: Files Modified

| Phase | File | Issues Fixed |
|-------|------|-------------|
| 1 | `data/models.py` | 1.1 |
| 1 | `data/writer.py` | 1.3, 3.8 |
| 1 | `data/loader.py` | 1.4, 3.4 |
| 1 | `data/db.py` | 3.2, 3.5, 3.6 |
| 1 | `services/unit_service.py` | 1.2 |
| 1 | `services/validation.py` | 1.7, 1.8 |
| 1 | `sync/revision_store.py` | 1.5 |
| 1 | `sync/shared_cache.py` | 1.5 |
| 1 | `sync/lock_manager.py` | 3.7 |
| 1 | `sync/session_registry.py` | 3.7 |
| 1 | `automation/import_preview.py` | 1.6 |
| 1 | `automation/import_csv.py` | 3.2 |
| 1 | `services/migration_registry.py` | 3.3 |
| 2 | `gui/main_window.py` | 2.1, 2.8, 2.9, 2.11, 2.12, 2.14, 2.15 |
| 2 | `gui/alert_panel.py` | 2.15 |
| 2 | `gui/theme.py` | 2.7 |
| 2 | `gui/edit_form.py` | 2.2, 2.3 |
| 2 | `gui/conflict_dialog.py` | 2.4 |
| 2 | `gui/import_preview_dialog.py` | 2.5 |
| 2 | `gui/timeline_panel.py` | 2.6 |
| 2 | `gui/audit_dialog.py` | 2.10 |
| 2 | `gui/inline_edit_bar.py` | 2.13 |
| 2 | `gui/onboarding.py` | 2.16 |
| — | *(deferred)* | 3.1 (Sync wiring) |

**Total: 26 issues fixed across 24 files. 1 issue (3.1) deferred.**

---

## Verification Plan

### Automated Tests

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v --tb=short
```

Key test files to validate:
- `test_models.py` — Issue 1.1 (capacity red at working_days=0)
- `test_writer.py` — Issues 1.3, 3.8 (remaining_hours, optimistic locking)
- `test_loader.py` — Issues 1.4, 3.4 (identicals preservation, fingerprint cache removal)
- `test_audit.py` — Issues 3.5, 3.6 (normalized comparison, new-unit audit)
- `test_validation.py` — Issues 1.7, 1.8 (positional args, date rules)
- `test_unit_service.py` — Issue 1.2 (connection leak)
- `test_migration_registry.py` — Issue 3.3 (transaction safety)
- `test_batch_edit_dialog.py` — Issue 2.1 (queue-based save)
- `test_sync.py` — Issues 1.5, 3.7 (OSError handling)
- `test_theme.py` — Issue 2.7 (:checked state)

### Manual Verification
- Launch with dark theme and verify all dialogs (conflict, import preview, timeline, edit form) have readable contrast
- Test batch edit with 3+ units and confirm all units are saved
- Test global search → clear → Enter to verify stale match is cleared
- Test view toggle buttons show visual active state
