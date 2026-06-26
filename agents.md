# Unit Tracker App — Agent Reference

This document is for future AI agents (or humans) joining this project. It describes the architecture, data flow, key computation logic, and conventions so you can work effectively without reading every file.

---

## 1. Tech Stack

| Layer       | Technology                          |
|-------------|-------------------------------------|
| UI          | PyQt5 (QtWidgets, QtCore, QtGui)   |
| Storage     | SQLite via `sqlite3` (stdlib)       |
| Import      | CSV ingestion from SSRS reports     |
| Sync        | File-based lock manager + SQLite    |
| Build       | PyInstaller (frozen executable)     |
| Services    | Pure Python (zero Qt dependencies)  |

No ORM — raw SQL with manual row-to-dataclass mapping. No async — everything is synchronous with `QThread` workers for I/O.

---

## 2. Project Structure

```
.
├── main.py                       # Entry point: config loading, ServiceRegistry, QApplication
├── config.yaml                   # All configuration: db path, detailers, schedules, UI prefs
├── agents.md                     # ← You are here
├── docs/
│   ├── DATA_CONTRACT.md          # Canonical reference for all computed fields
│   └── ONBOARDING_STEPS.md       # First-launch walkthrough step reference
├── automation/
│   ├── create_db.py              # Schema creation + detailer seeding
│   ├── import_csv.py             # CSV-to-SQLite import pipeline
│   ├── analyze_detailers.py      # Detailer load analysis
│   ├── cleanup_detailers.py      # Detailer cleanup operations
│   ├── export_to_workbook.py     # Export to Excel workbook
│   ├── import_preview.py         # Import diff/staging preview (FEAT-019)
│   └── import_atomsvc.py         # Alternate import format
├── data/
│   ├── models.py                 # Unit dataclass + all computed properties
│   ├── db.py                     # SQLite connection (per-thread), schema migration, row→Unit, audit log
│   ├── loader.py                 # load_units() from SQLite, identicals rule, fingerprinting
│   ├── writer.py                 # save_unit() with optimistic locking + audit trail
│   └── tag_parser.py             # Description parsing → unit type, features, flags, novelty
├──gui/
│   ├── main_window.py            # Thin orchestration layer (ServiceRegistry → widgets)
│   ├── list_panel.py             # Sortable/filterable table view
│   ├── calendar_panel.py         # Calendar view
│   ├── alert_panel.py            # Alert dashboard with capacity warnings, surge detection
│   ├── timeline_panel.py         # Milestone timeline for selected unit
│   ├── edit_form.py              # Unit editing form
│   ├── conflict_dialog.py        # Optimistic locking conflict UI
│   ├── due_date_changed_dialog.py# Due date change notification
│   ├── import_preview_dialog.py  # Import diff/staging preview UI
│   ├── close_progress_dialog.py  # Close-with-sync progress dialog
│   ├── pivot_chart.py            # Scheduling dashboard charts
│   ├── sync_status.py            # Multi-user sync status indicator
│   ├── loading_overlay.py        # Loading spinner overlay
│   ├── notification_panel.py     # Toast notification system for transient UI feedback
│   ├── onboarding.py             # First-run wizard
│   ├── reference_dialog.py       # Reference guide dialog (glossary, legend, shortcuts)
│   ├── theme.py                  # Dark/light theme + CVD modes
│   ├── batch_edit_dialog.py      # Bulk edit dialog
│   ├── inline_edit_bar.py        # Inline editing bar
│   ├── audit_dialog.py           # Audit trail viewer
│   └── a11y_dialog.py            # Accessibility settings
├── services/                     # ★ Business logic layer (zero Qt dependencies)
│   ├── __init__.py               # Exports: UnitService, ImportService, ExportService, SyncService, ConfigService
│   ├── unit_service.py           # Unit CRUD: load, save, fingerprint, identicals, due date changes, audit
│   ├── import_service.py         # CSV/SSRS import with ImportResult stats + diff preview
│   ├── export_service.py         # Excel/CSV export
│   ├── sync_service.py           # Multi-user sync: locks, revisions, sessions, shared cache
│   ├── config_service.py         # Config load/validate/save with deep merge + defaults
│   ├── validation.py             # ★ FieldRule, validate_unit, ValidationError, decorators
│   ├── sanitizer.py              # ★ InputSanitizer: clean_date, clean_percent, clean_com, clean_string
│   ├── pre_save_hooks.py         # ★ PreSaveHookRegistry: date order, target hours, non-negative, percent range
│   └── migration_registry.py     # ★ Schema migration registry (versioned, ordered)
├── sync/
│   ├── lock_manager.py           # File-based locking per unit (multi-user)
│   ├── revision_store.py         # Revision history with conflict detection
│   ├── session_registry.py       # Active session heartbeat tracking
│   └── shared_cache.py           # Cross-instance unit cache for conflict diffs
├── tests/
│   ├── conftest.py               # Shared fixtures (db_path, db_with_units, sample_unit, etc.)
│   ├── test_models.py            # Unit model computation tests
│   ├── test_loader.py            # Loader + identicals tests
│   ├── test_writer.py            # Writer + optimistic locking + audit trail tests
│   ├── test_audit.py             # Audit log system tests
│   ├── test_tag_parser.py        # Tag parsing + novelty detection tests
│   ├── test_list_panel.py        # List panel filtering, sorting, column tests
│   ├── test_calendar_panel.py    # Calendar panel tests
│   ├── test_edit_form.py         # Edit form tests
│   ├── test_unit_service.py      # ★ UnitService tests (37 tests: load, save, fingerprint, identicals, due date, audit)
│   ├── test_validation.py        # ★ Validation layer tests (field rules, validate_unit, decorators)
│   ├── test_pre_save_hooks.py    # ★ Pre-save hook tests (date order, target hours, non-negative)
│   ├── test_migration_registry.py # ★ Schema migration registry tests
│   ├── test_sanitizer.py         # ★ InputSanitizer tests (clean_date, clean_percent, clean_com)
│   ├── test_batch_edit_dialog.py # ★ Batch edit dialog tests (8 tests)
│   ├── test_inline_edit_bar.py   # ★ Inline edit bar tests
│   ├── test_sync.py              # Lock manager + revision store tests
│   ├── test_multi_user_integration.py  # Cross-instance conflict scenarios
│   ├── test_property.py          # Hypothesis property-based tests
│   ├── test_reload_performance.py # Load timing benchmarks
│   ├── test_contrast_audit.py    # Accessibility contrast ratio tests
│   ├── test_theme.py             # Theme + CVD tests
│   ├── test_sync_status.py       # Sync status widget tests
│   ├── test_close_progress_dialog.py  # Close progress dialog tests
│   ├── test_imports.py           # Import validation tests
│   ├── test_notification_panel.py # Notification panel (toast) tests
│   ├── test_reference_dialog.py  # Reference guide dialog tests
│   └── test_workers.py           # Background worker thread tests
├── scripts/
│   ├── doc_check.py              # Documentation drift checker
│   ├── benchmark.py              # Performance benchmarks
│   ├── migrate_workbook_to_sqlite.py  # Excel → SQLite migration
│   └── ensure_detailers.py       # Seed detailers table if missing
└── plans/
    ├── BUSINESS-ROADMAP-2026.md    # Synthesized execution plan (27 weeks)
    └── *.md                       # 27 individual improvement plans (reference)
```

---

## 3. Architecture: Service Layer

The business logic has been extracted from `MainWindow` into a **service layer** (`services/` package). Each service is a pure Python class with zero Qt dependencies, making it independently testable.

### Service Registry

`main.py` creates a `ServiceRegistry` that holds all service instances and injects them into `MainWindow`:

```python
from gui.main_window import MainWindow, ServiceRegistry
services = ServiceRegistry(config, config_path, db_path)
window = MainWindow(services)
```

### Service Responsibilities

| Service | File | Key Methods | Wraps |
|---------|------|-------------|-------|
| `UnitService` | `services/unit_service.py` | `load_all()`, `save()`, `get_by_com()`, `compute_fingerprint()`, `apply_identicals()`, `detect_changed_due_dates()`, `get_audit_trail()` | `data/loader.py`, `data/writer.py`, `data/db.py` |
| `ImportService` | `services/import_service.py` | `from_csv()`, `from_ssrs()`, `diff_before_import()` | `automation/import_csv.py`, `automation/import_atomsvc.py`, `automation/import_preview.py` |
| `ExportService` | `services/export_service.py` | `to_excel()`, `to_csv()` | `automation/export_to_workbook.py` |
| `SyncService` | `services/sync_service.py` | `is_enabled()`, `acquire_lock()`, `release_lock()`, `get_revision()`, `commit_revision()`, `get_active_sessions()`, `start_heartbeat()`, `stop_heartbeat()` | `sync/lock_manager.py`, `sync/revision_store.py`, `sync/session_registry.py`, `sync/shared_cache.py` |
| `ConfigService` | `services/config_service.py` | `load()`, `validate()`, `save()`, `merge_ui_defaults()`, `get_detailer_schedules()` | (static methods) |

### Data Flow with Services

```
MainWindow → services.unit_service.load_all() → data/loader.py → [Unit]
MainWindow → services.unit_service.save(unit)  → data/writer.py → SQLite
MainWindow → services.import_service.from_csv() → automation/import_csv.py → SQLite
MainWindow → services.export_service.to_excel() → automation/export_to_workbook.py
MainWindow → services.sync_service.get_active_sessions() → sync/session_registry.py
MainWindow → services.config_service.save() → config.yaml
```

---

## 4. Core Data Model: `Unit` Dataclass

Location: `data/models.py`

### Persisted Fields (SQLite columns)
- `com_number` (TEXT, PK) — Unique COM identifier
- `job_name`, `contract_number`, `description` — Identity fields
- `detailer` — Assigned detailer name
- `checking_status`, `notes` — Status & free-text
- `department_hours`, `target_department_hours`, `iec_internal_hours` — Hours breakdown
- `percent_complete` — 0-100 scale (stored 0-1.0 in SQLite)
- `actual_hours` — Actual hours logged
- Dates: `unit_detailing_start_date`, `unit_moved_to_checking_date`, `unit_detailing_completion_date`, `detailing_due_date`, `dept_due_date_previous`, `build_date`
- `status_color` — Persisted computed color (see §5.1)
- `working_days_in_checking` — Computed working days in checking pipeline
- `updated_at` — SQLite timestamp for optimistic locking

### Transient Fields (not persisted)
- `working_days` — Detailer's schedule (loaded from config per detailer)
- `due_date_changed` — Flag for UI indicator (cleared on selection)
- `previous_detailing_due_date` — Previous due date when changed (for "due date changed" dialog)
- `is_non_primary_identical` — Set by identicals rule
- `excel_row`, `fingerprint`, `base_revision` — Legacy Excel sync metadata
- `_milestones_cache` — Cached milestone list

### Key Properties (runtime-computed)
- `calculated_status_color` — Capacity-aware status (see §5.1)
- `alert_level` — Calendar-only urgency (see §5.2)
- `is_stale` — Due date > 30 days past
- `milestones` — Ordered list of `(label, date)` tuples

---

## 5. Computation Architecture

**CRITICAL**: The canonical reference for ALL computed fields is `docs/DATA_CONTRACT.md`. It documents the business rationale, formulas, constants, and data flow. Read it before modifying any computation.

### 5.1 `status_color` (Database-Persisted)

The primary visual indicator. Evaluated top-to-bottom, first match wins:

1. `percent_complete >= 100.0` → **green**
2. `detailing_due_date` is past → **red** (overdue)
3. Capacity check: `remaining_hours > available_hours` → **red** (behind schedule)
4. `percent_complete >= 95.0` → **orange**
5. `percent_complete >= 90.0` → **purple**
6. `percent_complete > 0.0` → **yellow**
7. Default → **gray**

**Constants**: `HOURS_PER_DAY = 10.0`, `CHECKING_OVERHEAD_WD = 4`

### 5.2 `alert_level` (Runtime-Only)

Calendar-date-based urgency: `COMPLETE` → `UNSET` → `OVERDUE` → `URGENT` (≤7 days) → `APPROACHING` (≤14 days) → `ON_TRACK`. Does NOT account for capacity.

### 5.3 `working_days_in_checking` (Database-Persisted)

Mon-Fri count between `unit_moved_to_checking_date` and `unit_detailing_completion_date`. Set on import and save. NULL if either date missing.

### 5.4 `target_dept_hours` (Database-Persisted)

`MAX(0, department_hours - iec_internal_hours)`. Forced to 0 for non-primary identicals.

### 5.5 `remaining_hours` (Database-Persisted, Import-Only)

`department_hours * (1 - effective_percent_complete)`. Only computed during CSV import, NOT recalculated on save.

### 5.6 Identicals Rule

Units sharing the same `contract_number` form a group. The unit with the earliest `detailing_due_date` is the **primary** (keeps normal target hours). All others get `target_department_hours = 0` and `is_non_primary_identical = True`. Applied in `data/loader.py` → `_apply_identicals()`, wrapped by `UnitService.apply_identicals()`.

### 5.7 Audit Trail (`_audit_log` table)

Every save records field-level changes to `_audit_log` (SQLite table). Each row: `com_number`, `field_name`, `old_value`, `new_value`, `saved_by`, `saved_at`. Written by `data/db.py` → `log_field_changes()`, called from `data/writer.py` → `save_unit()`. Retrieved via `UnitService.get_audit_trail()`.

---

## 6. Data Flow

### 6.1 Import Pipeline
```
SSRS CSV → ImportService.from_csv() → automation/import_csv.py → SQLite
                              ↓
                        ImportResult(inserted, updated, skipped, errors)
```
- Backs up database before import
- Insert new rows, update existing by `com_number`
- `percent_complete` only set from CSV if currently NULL in DB (preserves manual edits)
- `dept_due_date_previous` set when due date changes between imports

### 6.2 Load Pipeline
```
SQLite → UnitService.load_all() → data/loader.py → row_to_unit() → [Unit]
                                          ↓
                                    _apply_identicals() (in-memory)
                                    set working_days from config
```
- `UnitService` wraps `load_units()` and adds due date change detection

### 6.3 Save Pipeline
```
Unit → UnitService.save() → data/writer.py → _validate_unit()
                                          → UPDATE SQL (optimistic lock)
                                          → log_field_changes() → _audit_log
                                          → COMMIT
```
- Writes `calculated_status_color` on every save
- Recomputes `working_days_in_checking` from dates
- Raises `ConcurrentEditError` if `updated_at` mismatched

### 6.4 Config Pipeline
```
ConfigService.load(path) → yaml.safe_load() → deep merge with DEFAULTS → dict
ConfigService.validate(config) → list[warnings]
ConfigService.save(path, config) → yaml.safe_dump()
```

---

## 7. Alert Panel Logic

Location: `gui/alert_panel.py`

### 7.1 Sorting
Primary sort by `CRITICALITY_ORDER`: red(0) → orange(1) → purple(2) → yellow(3) → gray(4) → green(5). Secondary sort by due date (earliest first).

### 7.2 Checking Surge Detection
Groups incomplete, non-checked units by due date. If 3+ share a due date, all are flagged as \"CHECK SURGE\". Threshold: `CHECKING_SURGE_THRESHOLD = 3`.

### 7.3 Capacity Warning
Only shown when a specific detailer is selected (not \"All Detailers\"). Sums remaining hours for all non-stale units assigned to that detailer. If > `CAPACITY_HOURS_THRESHOLD` (160.0), shows "⚠️ OVERLOADED" warning.

### 7.4 Stale Exclusion
Units with `detailing_due_date > 30 days past` are hidden from the alert panel. Controlled by `STALE_THRESHOLD_DAYS = 30` in `data/models.py`.

---

## 8. Tag Parsing System

Location: `data/tag_parser.py`

Parses unit descriptions into structured tags:
- **Unit type**: Prefix (O)2, I)3, OA)2, RTF)
- **Dimensions**: Physical dimensions (8X8X13)
- **Features**: Whitelisted tokens (46 kept after team review of 800 unique features)
- **Flags**: Asterisk-enclosed markers (*PRE-PAINT*)

The `UnitTagRepository` tracks what each detailer has done before, enabling novelty detection (new unit type or feature combo for a detailer).

---

## 9. Multi-User Sync System

Location: `sync/` directory, wrapped by `services/sync_service.py`

| Component | Purpose |
|-----------|---------|
| `lock_manager.py` | File-based per-unit lock with 60s timeout |
| `revision_store.py` | Revision history with conflict detection |
| `session_registry.py` | Active session heartbeat tracking |
| `shared_cache.py` | Cross-instance unit cache for conflict diffs |

The sync system is disabled by default (`multi_user.enabled: false` in config.yaml). When enabled, it provides file-based locking per unit to prevent concurrent edits.

### Optimistic Locking (Always Active)
Even without multi-user sync, the writer implements optimistic locking via the `updated_at` column. If `updated_at` doesn't match when loaded, save raises `ConcurrentEditError`.

---

## 10. Key Constants Reference

| Constant | Value | File | Purpose |
|----------|-------|------|---------|
| `STALE_THRESHOLD_DAYS` | 30 | `data/models.py` | Days past due before unit is hidden |
| `HOURS_PER_DAY` | 10.0 | `data/models.py` | 40 hrs/week ÷ 4 working days |
| `CHECKING_OVERHEAD_WD` | 4 | `data/models.py` | Median working days in checking pipeline |
| `CHECKING_SURGE_THRESHOLD` | 3 | `gui/alert_panel.py` | 3+ units/day triggers surge flag |
| `CAPACITY_HOURS_THRESHOLD` | 160.0 | `gui/alert_panel.py` | 4 weeks × 40 hrs/week overload threshold |
| `LOCK_TIMEOUT` | 60 | `sync/lock_manager.py` | Seconds before lock is considered stale |
| `ACQUIRE_TIMEOUT` | 10 | `sync/lock_manager.py` | Max seconds to wait for lock |

---

## 11. Configuration (`config.yaml`)

| Key | Purpose |
|-----|---------|
| `sqlite_path` | Path to SQLite database |
| `default_detailers` | Ordered list of detailer names for dropdown |
| `detailer_schedules` | Per-detailer working weekday arrays (0=Mon..4=Fri) |
| `csv_output_dir` | Directory for cached CSV exports |
| `ssrs_url` | SSRS report URL |
| `ui.theme` | "dark" or "light" |
| `ui.high_contrast` | Boolean for high contrast mode |
| `ui.colorblind_mode` | "none", "deuteranopia", "protanopia", or "tritanopia" |
| `ui.last_view` | "calendar", "list", or "alerts" |
| `multi_user.enabled` | Boolean for multi-user sync |
| `ssrs_lookahead_days` | Days to look ahead (default: 365) |
| `ssrs_lookback_days` | Days to look back (default: 30) |

---

## 12. Testing

Tests use pytest with a SQLite database fixture (`db_path`, `db_with_units`). The `services/` package is independently testable without Qt.

| Test file | What it tests |
|-----------|---------------|
| `test_models.py` | `calculated_status_color`, `alert_level`, `is_stale`, `milestones`, `status_label` |
| `test_writer.py` | `save_unit`, `ConcurrentEditError`, field persistence |
| `test_loader.py` | `load_units`, `_apply_identicals`, schedule application |
| `test_audit.py` | Audit log: `log_field_changes`, `get_audit_trail`, save integration |
| `test_unit_service.py` | ★ `UnitService` (37 tests): load, save, fingerprint, identicals, due date changes, audit |
| `test_validation.py` | ★ Validation layer (29 tests): field rules, validate_unit, ValidationError, decorators |
| `test_pre_save_hooks.py` | ★ Pre-save hooks (12 tests): date order, target hours, non-negative, percent range |
| `test_migration_registry.py` | ★ Schema migration registry (5 tests) |
| `test_sanitizer.py` | ★ InputSanitizer (14 tests): clean_date, clean_percent, clean_com, clean_string |
| `test_batch_edit_dialog.py` | ★ Batch edit dialog (8 tests): apply, emit, get_updated_units |
| `test_inline_edit_bar.py` | ★ Inline edit bar (10 tests): load, save, dirty, clear |
| `test_tag_parser.py` | `parse_description`, `UnitTagRepository`, novelty detection |
| `test_list_panel.py` | List panel filtering, sorting, column visibility |
| `test_calendar_panel.py` | Calendar rendering, date selection |
| `test_edit_form.py` | Form population, dirty state, clearable dates |
| `test_sync.py` | Lock manager, session registry |
| `test_multi_user_integration.py` | Cross-instance conflict scenarios |
| `test_property.py` | Hypothesis property-based tests (status color, alert level, fingerprint) |
| `test_reload_performance.py` | Load timing benchmarks |
| `test_contrast_audit.py` | Accessibility contrast ratios |
| `test_theme.py` | Theme application + CVD overrides |
| `test_sync_status.py` | Sync status widget tests |
| `test_close_progress_dialog.py`  | Close progress dialog tests |
| `test_imports.py` | Import validation tests |
| `test_notification_panel.py` | Notification panel (toast) tests |
| `test_reference_dialog.py` | Reference guide dialog tests |
| `test_workers.py` | Background worker thread tests |

Run tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -v`

---

## 13. Common Pitfalls & Gotchas

1. **percent_complete scaling**: Stored 0-1.0 in SQLite, 0-100 in Unit dataclass (multiplied by 100 in `row_to_unit()`). Division by 100 in `save_unit()`. Always check which scale you're working with.

2. **Two working day functions**: `data/models.py` has a private `_working_days_between` (configurable schedule, start exclusive), and `data/db.py` has a public `_working_days_between` (Mon-Fri only, both inclusive). The `writer.py` imports from `db.py` for checking computation.

3. **Import preserves manual edits**: `percent_complete` is only set from CSV if currently NULL in DB.

4. **status_color is writable but recalculated**: The UI always shows `calculated_status_color`.

5. **Alert panel sorts by status_color, not alert_level**: Capacity-aware > calendar-aware.

6. **Detailer schedules are per-name**: If a detailer name doesn't match a config key, the "default" schedule is used.

7. **Non-primary identicals have zero target hours**: `department_hours` is NOT zeroed — tracked for capacity planning, just not as the detailer's target.

8. **QTextEdit dirty tracking**: The `notes_edit` field must be explicitly connected to `_mark_dirty`.

9. **Auto-reload vs unsaved edits**: `_on_load_finished()` must check `_form_dirty` before re-populating the edit form.

10. **Fingerprint cache**: `unit_fingerprint()` in `data/loader.py` uses a module-level cache keyed by `com_number`. Cache is never invalidated within a session.

11. **Service layer is Qt-free**: Services import from `data.*` and `sync.*` only — never from `gui.*`. This ensures testability without `QApplication`.

12. **MainWindow constructor changed**: Takes `ServiceRegistry`, not raw `config`/`db_path`. All service access via `self._services.<service>`.

---

## 14. Quick Start for Development

```bash
# Set up
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create database
python -m automation.create_db --db schedule.db

# Import data
python -m automation.import_csv --source csv --csv-path your_export.csv --db schedule.db

# Run app
python main.py

# Run tests
python -m pytest tests/ -v
```

---

## 15. Database Schema (SQLite)

The `units` table has ~50 columns. Key ones:

```
com_number (PK) | detailing_due_date | job_name | top_level_number | description
build_date | department_hours | percent_complete (0-1.0) | detailer
unit_detailing_start_date | unit_moved_to_checking_date | unit_detailing_completion_date
dept_due_date_previous | remaining_hours | actual_hours
target_dept_hours | iec_internal_hours | checking_status | notes
status_color | working_days_in_checking | updated_at | created_at
```

Supporting tables: `detailers` (name, working_weekdays JSON, display_order), `default_schedule` (single row, working_weekdays JSON), `_audit_log` (com_number, field_name, old_value, new_value, saved_by, saved_at).

Full schema in `automation/create_db.py` → `SCHEMA_SQL`.

---

*Last updated: 2026-06-24*
*Architecture: Sprints 1-8 complete. Service layer + validation layer + bulk ops + audit UI. 398 tests passing. Lint clean.*
*Fixes applied 2026-06-16: PARSE_FUNCS→SANITIZE_FUNCS import in import_preview.py (broke 7 test files), batch_edit_dialog test fixture missing "Brandon B" detailer, inline_edit_bar nested-if SIM102, import_service E402 mid-file import.*
