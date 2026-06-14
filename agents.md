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

No ORM — raw SQL with manual row-to-dataclass mapping. No async — everything is synchronous with `QThread` workers for I/O.

---

## 2. Project Structure

```
.
├── main.py                       # Entry point, QApplication init, config loading
├── config.yaml                   # All configuration: db path, detailers, schedules, UI prefs
├── agents.md                     # ← You are here
├── docs/
│   └── COMPUTATION_AUDIT.md      # Canonical reference for all computed fields
├── automation/
│   ├── create_db.py              # Schema creation + detailer seeding
│   ├── import_csv.py             # CSV-to-SQLite import pipeline
│   ├── analyze_detailers.py      # Detailer load analysis
│   ├── cleanup_detailers.py      # Detailer cleanup operations
│   ├── export_to_workbook.py     # Export to Excel workbook
│   ├── import_atomsvc.py         # Alternate import format
├── data/
│   ├── models.py                 # Unit dataclass + all computed properties
│   ├── db.py                     # SQLite connection (per-thread), schema migration, row→Unit
│   ├── loader.py                 # load_units() from SQLite, identicals rule
│   ├── writer.py                 # save_unit() with optimistic locking
│   └── tag_parser.py             # Description parsing → unit type, features, flags
├── gui/
│   ├── main_window.py            # Main window, panel orchestration, menu actions
│   ├── list_panel.py             # Sortable/filterable table view
│   ├── calendar_panel.py         # Calendar view
│   ├── alert_panel.py            # Alert dashboard with capacity warnings, surge detection
│   ├── timeline_panel.py         # Milestone timeline for selected unit
│   ├── edit_form.py              # Unit editing form
│   ├── conflict_dialog.py        # Optimistic locking conflict UI
│   ├── due_date_changed_dialog.py# Due date change notification
│   ├── close_progress_dialog.py  # Progress close dialog
│   ├── pivot_chart.py            # Pivot chart
│   ├── sync_status.py            # Multi-user sync status indicator
│   ├── loading_overlay.py        # Loading spinner overlay
│   ├── onboarding.py             # First-run wizard
│   ├── theme.py                  # Dark/light theme
│   └── a11y_dialog.py            # Accessibility settings
├── sync/
│   ├── lock_manager.py           # File-based locking per unit (multi-user)
│   ├── revision_store.py         # Revision history
│   ├── session_registry.py       # Active session tracking
│   └── shared_cache.py           # Cross-instance cache
└── tests/
│   ├── conftest.py               # Shared fixtures
│   ├── test_models.py            # Unit model computation tests
│   ├── test_loader.py            # Loader tests
│   ├── test_writer.py            # Writer + optimistic locking tests
│   ├── test_tag_parser.py        # Tag parsing tests
│   ├── test_list_panel.py        # List panel tests
│   ├── test_calendar_panel.py    # Calendar panel tests
│   ├── test_edit_form.py         # Edit form tests
│   └── ...                       # Other test files
├── scripts/
│   ├── doc_check.py             # Documentation drift checker
│   ├── migrate_workbook_to_sqlite.py  # Excel → SQLite migration
│   ├── ensure_detailers.py      # Seed detailers table if missing
│   └── pre-commit               # Git pre-commit hook template
├── README-Windows.md            # Windows quick-start guide
├── setup.bat                    # Windows: create venv + install deps
├── migrate.bat                  # Windows: run workbook migration
├── run.bat                      # Windows: launch app
├── test.bat                     # Windows: run pytest suite
├── ensure_detailers.bat         # Windows: seed detailers table
└── cleanup_detailers.bat        # Windows: cleanup detailer names
```

---

## 3. Core Data Model: `Unit` Dataclass

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
- `status_color` — Persisted computed color (see §4.1)
- `working_days_in_checking` — Computed working days in checking pipeline
- `updated_at` — SQLite timestamp for optimistic locking

### Transient Fields (not persisted)
- `working_days` — Detailer's schedule (loaded from config per detailer)
- `due_date_changed` — Flag for UI indicator (cleared on selection)
- `is_non_primary_identical` — Set by identicals rule
- `excel_row`, `fingerprint`, `base_revision` — Legacy Excel sync metadata
- `_milestones_cache` — Cached milestone list

### Key Properties (runtime-computed)
- `calculated_status_color` — Capacity-aware status (see §4.1)
- `alert_level` — Calendar-only urgency (see §4.2)
- `is_stale` — Due date > 30 days past
- `milestones` — Ordered list of `(label, date)` tuples

---

## 4. Computation Architecture

**CRITICAL**: The canonical reference for ALL computed fields is `docs/COMPUTATION_AUDIT.md`. It documents the business rationale, formulas, constants, and data flow. Read it before modifying any computation.

### 4.1 `status_color` (Database-Persisted)

The primary visual indicator. Evaluated top-to-bottom, first match wins:

1. `percent_complete >= 100.0` → **green**
2. `detailing_due_date` is past → **red** (overdue)
3. Capacity check: `remaining_hours > available_hours` → **red** (behind schedule)
4. `percent_complete >= 95.0` → **orange**
5. `percent_complete >= 90.0` → **purple**
6. `percent_complete > 0.0` → **yellow**
7. Default → **gray**

**Constants**: `HOURS_PER_DAY = 10.0`, `CHECKING_OVERHEAD_WD = 4`

The capacity check (step 3) is what makes this smarter than percentage-based status. It answers "can this unit still make its due date?" by comparing remaining hours against available working days (minus 4 days checking pipeline overhead for units not yet in checking).

### 4.2 `alert_level` (Runtime-Only)

Calendar-date-based urgency: `COMPLETE` → `UNSET` → `OVERDUE` → `URGENT` (≤7 days) → `APPROACHING` (≤14 days) → `ON_TRACK`. Does NOT account for capacity.

### 4.3 `working_days_in_checking` (Database-Persisted)

Mon-Fri count between `unit_moved_to_checking_date` and `unit_detailing_completion_date`. Set on import and save. NULL if either date missing.

### 4.4 `target_dept_hours` (Database-Persisted)

`MAX(0, department_hours - iec_internal_hours)`. Forced to 0 for non-primary identicals.

### 4.5 `remaining_hours` (Database-Persisted, Import-Only)

`department_hours * (1 - effective_percent_complete)`. Only computed during CSV import, NOT recalculated on save.

### 4.6 Identicals Rule

Units sharing the same `contract_number` form a group. The unit with the earliest `detailing_due_date` is the **primary** (keeps normal target hours). All others get `target_department_hours = 0` and `is_non_primary_identical = True`. Applied in `data/loader.py` → `_apply_identicals()`.

---

## 5. Data Flow

### 5.1 Import Pipeline (`automation/import_csv.py`)
```
SSRS CSV → parse dates/percents/numbers → upsert_row() → SQLite
```
- Insert new rows, update existing by `com_number`
- `percent_complete` only set from CSV if currently NULL in DB (preserves manual edits)
- `dept_due_date_previous` set when due date changes between imports
- `working_days_in_checking` computed from date fields
- `remaining_hours` computed from department hours × (1 - percent_complete)

### 5.2 Load Pipeline (`data/loader.py`)
```
SQLite → row_to_unit() → Unit objects → _apply_identicals() → [Unit]
```
- Applies identicals rule (post-load, in-memory)
- Sets `working_days` per detailer from config schedules

### 5.3 Save Pipeline (`data/writer.py`)
```
Unit → UPDATE SQL → optimistic lock check → commit
```
- Writes `calculated_status_color` on every save
- Recomputes `working_days_in_checking` from dates
- Raises `ConcurrentEditError` if `updated_at` mismatched

---

## 6. Alert Panel Logic

Location: `gui/alert_panel.py`

### 6.1 Sorting
Primary sort by `CRITICALITY_ORDER`: red(0) → orange(1) → purple(2) → yellow(3) → gray(4) → green(5). Secondary sort by due date (earliest first).

### 6.2 Checking Surge Detection
Groups incomplete, non-checked units by due date. If 3+ share a due date, all are flagged as "CHECK SURGE". Threshold: `CHECKING_SURGE_THRESHOLD = 3`.

### 6.3 Capacity Warning
Only shown when a specific detailer is selected (not "All Detailers"). Sums remaining hours for all non-stale units assigned to that detailer. If > `CAPACITY_HOURS_THRESHOLD` (160.0), shows "⚠️ OVERLOADED" warning.

### 6.4 Stale Exclusion
Units with `detailing_due_date > 30 days past` are hidden from the alert panel. Controlled by `STALE_THRESHOLD_DAYS = 30` in `data/models.py`.

---

## 7. Tag Parsing System

Location: `data/tag_parser.py`

Parses unit descriptions into structured tags:
- **Unit type**: Prefix (O)2, I)3, OA)2, RTF)
- **Dimensions**: Physical dimensions (8X8X13)
- **Features**: Whitelisted tokens (46 kept after team review of 800 unique features)
- **Flags**: Asterisk-enclosed markers (*PRE-PAINT*)

The `UnitTagRepository` tracks what each detailer has done before, enabling novelty detection (new unit type or feature combo for a detailer). Built from all units, used for filtering and alerting.

### Feature Whitelist
Only 46 tokens survive as features. Everything else is dropped. Normalization maps variants to canonical forms (e.g., "ABASE" → "AL-BASE", "SEIS" → "SEIS-CERT"). See `_WHITELIST` and `_NORMALIZATION_MAP` in `tag_parser.py`.

---

## 8. Multi-User Sync System

Location: `sync/` directory

| Component | Purpose |
|-----------|---------|
| `lock_manager.py` | File-based per-unit lock with 60s timeout |
| `revision_store.py` | Revision history tracking |
| `session_registry.py` | Active session tracking |
| `shared_cache.py` | Cross-instance cache |

The sync system is disabled by default (`multi_user.enabled: false` in config.yaml). When enabled, it provides file-based locking per unit to prevent concurrent edits, with a fallback mode configurable to "block" or "warn".

### Optimistic Locking (Always Active)
Even without multi-user sync, the writer implements optimistic locking via the `updated_at` column. If `updated_at` doesn't match when loaded, save raises `ConcurrentEditError`.

---

## 9. Key Constants Reference

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

## 10. Configuration (`config.yaml`)

| Key | Purpose |
|-----|---------|
| `sqlite_path` | Path to SQLite database |
| `default_detailers` | Ordered list of detailer names for dropdown |
| `detailer_schedules` | Per-detailer working weekday arrays (0=Mon..4=Fri) |
| `csv_output_dir` | Directory for cached CSV exports |
| `ssrs_url` | SSRS report URL |
| `ui.theme` | "dark" or "light" |
| `ui.high_contrast` | Boolean for high contrast mode |
| `ui.colorblind_mode` | "none" or "deuteranopia" |
| `ui.last_view` | "calendar" or "list" |
| `multi_user.enabled` | Boolean for multi-user sync |
| `ssrs_lookahead_days` | Days to look ahead (default: 365) |
| `ssrs_lookback_days` | Days to look back (default: 30) |

---

## 11. Testing

Tests use pytest with a SQLite in-memory database. Summary:

| Test file | What it tests |
|-----------|---------------|
| `test_models.py` | `calculated_status_color`, `alert_level`, `is_stale`, `milestones`, `status_label` |
| `test_writer.py` | `save_unit`, `ConcurrentEditError`, field persistence |
| `test_loader.py` | `load_units`, `_apply_identicals`, schedule application |
| `test_tag_parser.py` | `parse_description`, `UnitTagRepository`, novelty detection |
| `test_list_panel.py` | List panel filtering, sorting, column visibility |
| `test_calendar_panel.py` | Calendar rendering, date selection |
| `test_edit_form.py` | Form population, dirty state, clearable dates |
| `test_sync.py` | Lock manager, session registry |
| `test_multi_user_integration.py` | Cross-instance conflict scenarios |
| `test_reload_performance.py` | Load timing benchmarks |
| `test_contrast_audit.py` | Accessibility contrast ratios |
| `test_theme.py` | Theme application |

Run tests: `python -m pytest tests/ -v`

---

## 12. Common Pitfalls & Gotchas

1. **percent_complete scaling**: Stored 0-1.0 in SQLite, 0-100 in Unit dataclass (multiplied by 100 in `row_to_unit()`). Division by 100 in `save_unit()`. Always check which scale you're working with.

2. **Two working day functions**: `data/models.py` has a private `_working_days_between` (configurable schedule, start exclusive), and `data/db.py` has a public `_working_days_between` (Mon-Fri only, both inclusive). The `writer.py` imports from `db.py` for checking computation. A third `working_days_between` in `db.py` (line 184) is dead code.

3. **Import preserves manual edits**: `percent_complete` is only set from CSV if currently NULL in DB. To force a CSV override, you'd need to NULL the column first.

4. **status_color is writable**: The `status_color` column is persisted but recalculated on every save via `calculated_status_color`. However, the model allows manual assignment too (see `status_color` docstring). The UI always shows `calculated_status_color`.

5. **Alert panel sorts by status_color, not alert_level**: The alert panel uses `CRITICALITY_ORDER` (based on `calculated_status_color`) not `ALERT_SEVERITY_ORDER` (based on `alert_level`). This is intentional — capacity-aware > calendar-aware.

6. **Check data before trusting checking surge**: The surge detection uses `CHECKING_OVERHEAD_WD = 4` (median from 885 units). This is a statistical heuristic, not exact.

7. **Detailer schedules are per-name**: The config maps detailer names to weekday arrays (0=Mon, 4=Fri). If a detailer name in the data doesn't match a config key, the "default" schedule is used.

8. **Non-primary identicals have zero target hours**: This prevents double-counting, but the `department_hours` field is NOT zeroed — those hours are tracked for capacity planning, just not assigned as the detailer's target.

9. **QTextEdit dirty tracking**: The `notes_edit` field (QTextEdit) must be explicitly connected to `_mark_dirty` — it's not handled by the generic `QLineEdit`/`QComboBox`/`QDateEdit`/`QDoubleSpinBox` loop in `edit_form.py`.

10. **Auto-reload vs unsaved edits**: `_on_load_finished()` in `main_window.py` must check `_form_dirty` before re-populating the edit form, or unsaved user edits are silently lost.

11. **Conflict dialog button roles**: Use `QDialogButtonBox.ActionRole` (not `AcceptRole`) for custom buttons in `conflict_dialog.py` to avoid double-firing signals.

12. **Fingerprint cache uses `id(unit)`**: The fingerprint cache in `loader.py` keys on Python's `id()`, which can collide if objects are garbage collected and new ones reuse the same address. Low risk in practice but theoretically incorrect.

13. **Tag parser compound feature ordering**: Compound features in `tag_parser.py` are matched via simple iteration — if compound A is a substring of compound B, A matching first prevents B from matching. Sort by length (longest first) to avoid this.

14. **RTF dimension case sensitivity**: The RTF parser checks `"X" in revision_or_dim.upper()` to distinguish dimensions from revision numbers. This works but the check should be consistently case-insensitive throughout.

---

## 13. Quick Start for Development

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

## 14. Database Schema (SQLite)

The `units` table has ~50 columns. Key ones:

```
com_number (PK) | detailing_due_date | job_name | top_level_number | description
build_date | department_hours | percent_complete (0-1.0) | detailer
unit_detailing_start_date | unit_moved_to_checking_date | unit_detailing_completion_date
dept_due_date_previous | remaining_hours | actual_hours
target_dept_hours | iec_internal_hours | checking_status | notes
status_color | working_days_in_checking | updated_at | created_at
```

Supporting tables: `detailers` (name, working_weekdays JSON, display_order), `default_schedule` (single row, working_weekdays JSON).

Full schema in `automation/create_db.py` → `SCHEMA_SQL`.

---

*Generated: 2026-06-06*
*Based on code analysis of 2765 unit capacity model with 15 detailers*