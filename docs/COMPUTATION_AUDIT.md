# Computation Audit — Unit Tracker App

## Overview
This document catalogs every computed/derived field in the Unit Tracker app, where it's calculated, the data it depends on, and the business rationale.

---

## 1. DATABASE-PERSISTENT COMPUTED FIELDS
These are stored in the SQLite `units` table and survive across sessions.

### 1.1 `status_color`
| Attribute | Value |
|-----------|-------|
| **Stored in** | `units.status_color` (TEXT) |
| **Computed by** | `data/models.py` → `Unit.calculated_status_color` (property) |
| **Persisted by** | `data/writer.py` → `save_unit()` writes `unit.calculated_status_color` on every save |
| **Also set during import** | `automation/import_csv.py` → `upsert_row()` (indirectly via `status_color` column default) |
| **Type** | `Literal["gray", "yellow", "purple", "orange", "green", "red"]` |

**Calculation logic** (evaluated top-to-bottom, first match wins):
1. `percent_complete >= 100.0` → **green** (unit is done)
2. `detailing_due_date` is past today → **red** (overdue)
3. Capacity check (see §1.2 below) → **red** (behind schedule)
4. `percent_complete >= 95.0` → **orange** (checked & returned, 95-99%)
5. `percent_complete >= 90.0` → **purple** (ready for checking, 90-94%)
6. `percent_complete > 0.0` → **yellow** (in progress, 1-89%)
7. Default → **gray** (unassigned, 0%)

**Rationale**: Provides a single visual indicator that accounts for both completion state AND schedule risk. The capacity check (step 3) is what separates this from a simple percentage-based status — it answers "can this unit still make its due date given remaining work and available time?"

---

### 1.2 Capacity Check (sub-routine of `status_color`)
| Attribute | Value |
|-----------|-------|
| **Location** | `data/models.py` → `Unit.calculated_status_color`, lines 172-190 |
| **Inputs** | `department_hours`, `percent_complete`, `detailing_due_date`, `unit_moved_to_checking_date`, `unit_detailing_completion_date`, `working_days` (detailer schedule) |
| **Constants** | `HOURS_PER_DAY = 10.0` (40 hrs/week ÷ 4 working days), `CHECKING_OVERHEAD_WD = 4` (median working days in checking pipeline, from analysis of 884 completed units) |

**Formula**:
```
remaining_hours = department_hours × (1 - percent_complete / 100)
working_days = count_working_days(today, due_date, detailer_schedule)  # Mon-Thu default
if unit not yet in checking AND not yet complete:
    effective_working_days = working_days - 4  # reserve checking pipeline time
else:
    effective_working_days = working_days
available_hours = effective_working_days × 10.0
if remaining_hours > available_hours → RED (behind schedule)
```

**Why checking overhead is 4 days**: From analysis of 884 units with both `unit_moved_to_checking_date` and `unit_detailing_completion_date`, the median working-day duration in checking was 4 days. This is reserved for units that haven't entered checking yet — they need ~4 working days to clear the checker.

**Why some units skip the overhead**: Units already in checking (`unit_moved_to_checking_date` set) or already complete (`unit_detailing_completion_date` set) don't need to reserve checking time — they're past that bottleneck.

**Why 10 hrs/day**: Each detailer works 40 hrs/week across 4 working days (Mon-Thu default schedule). This is configurable per-detailer via the `detailers` table.

---

### 1.3 `working_days_in_checking`
| Attribute | Value |
|-----------|-------|
| **Stored in** | `units.working_days_in_checking` (INTEGER, nullable) |
| **First computed by** | `data/db.py` → `_working_days_between(start_str, end_str)` |
| **Migration/backfill** | `data/db.py` → `_migrate_schema()` — backfills existing rows on first run after column is added |
| **Recomputed on save** | `data/writer.py` → `save_unit()` recomputes from `unit_moved_to_checking_date` and `unit_detailing_completion_date` |
| **Recomputed on import** | `automation/import_csv.py` → `upsert_row()` — computed in `upsert_row()` via `_working_days_between()` |
| **Loaded by** | `data/db.py` → `row_to_unit()` reads from DB row |

**Formula**: Count Mon-Fri days between `unit_moved_to_checking_date` (inclusive) and `unit_detailing_completion_date` (inclusive). Returns NULL if either date is missing.

**Rationale**: Provides a persisted, queryable measure of how long each unit spends in the checking pipeline. Enables the checking surge detection (§2.3) and historical throughput analysis without recalculating from raw dates.

**Scope**: Only units that have entered checking. Units still in detailing have NULL — they haven't entered the checking stage yet.

---

### 1.4 `remaining_hours`
| Attribute | Value |
|-----------|-------|
| **Stored in** | `units.remaining_hours` (REAL) |
| **Computed by** | `automation/import_csv.py` → `upsert_row()` during CSV import |
| **Formula** | `department_hours × (1 - effective_percent_complete)` |
| **NOT recomputed on save** | Writer does not update this — it's only set during SSRS import |

**Subtlety for updates**: When a unit already exists in the DB, the import uses `current_percent_complete` (from DB) if not NULL, otherwise falls back to `csv_percent_complete`. This prevents the CSV from overwriting a manually-set completion percentage.

**Rationale**: Quick-read measure of remaining work for capacity planning without computing on every load. Import-only because it's derived from SSRS fields that only change on import.

---

### 1.5 `target_dept_hours`
| Attribute | Value |
|-----------|-------|
| **Stored in** | `units.target_dept_hours` (REAL) |
| **Computed by** | `gui/edit_form.py` → `_update_target_hours()` |
| **Formula** | `MAX(0, department_hours - iec_internal_hours)` |
| **Writers guard** | `data/writer.py` uses `MAX(0, ?)` to prevent negative values |

**Non-primary identical override**: When `is_non_primary_identical == True`, target is forced to 0 regardless of the calculation. This prevents double-counting hours for units that share a contract number.

**Rationale**: The detailer's actual hours to work = total department hours minus IEC internal hours (work done by a different team). This is the "real" hours burden on the assigned detailer.

---

### 1.6 `updated_at`
| Attribute | Value |
|-----------|-------|
| **Stored in** | `units.updated_at` (TEXT) |
| **Set by** | `data/writer.py` → `strftime('%Y-%m-%d %H:%M:%f', 'now')` — SQLite current timestamp |
| **Used for** | Optimistic locking (concurrent edit detection) |

**Rationale**: Prevents lost edits when two users modify the same unit simultaneously. The writer only succeeds if `updated_at` matches the value when the unit was loaded. If another user saved first, the save fails and the user sees a conflict dialog.

---

### 1.7 `dept_due_date_previous`
| Attribute | Value |
|-----------|-------|
| **Stored in** | `units.dept_due_date_previous` (TEXT, nullable) |
| **Set by** | `automation/import_csv.py` → `upsert_row()` |
| **Logic** | When a unit exists and its `detailing_due_date` changes between imports, the old date is pushed to `dept_due_date_previous` before updating |

**Rationale**: Tracks due date history. Used by the GUI to show a "due date changed" indicator (⚠) next to units whose due date was pushed.

---

## 2. RUNTIME-ONLY COMPUTED FIELDS
These are computed on-the-fly when a Unit object is accessed. They are NOT stored in the DB.

---

### 2.1 `Unit.alert_level`
| Attribute | Value |
|-----------|-------|
| **Location** | `data/models.py` → `Unit.alert_level` (property) |
| **Type** | `Literal["COMPLETE", "UNSET", "OVERDUE", "URGENT", "APPROACHING", "ON_TRACK"]` |
| **Used by** | Alert panel sorting (secondary sort after criticality), list panel filtering |

**Calculation**:
```
percent_complete >= 100.0 → COMPLETE
no due_date → UNSET
due_date < today → OVERDUE
calendar_days_until_due ≤ 7 → URGENT
calendar_days_until_due ≤ 14 → APPROACHING
otherwise → ON_TRACK
```

**Key distinction from `status_color`**: `alert_level` is purely calendar-date-based. It does NOT account for capacity, checking overhead, or department hours. It answers "how close is the due date?" not "can this unit make it?"

**Why both exist**: `status_color` is the "can we make it?" signal (capacity-aware). `alert_level` is the "how urgent is the deadline?" signal (calendar-aware). A unit can be ON_TRACK by calendar but CRITICAL by capacity (e.g., 20091: 14 working days out but 139h of unassigned work).

---

### 2.2 `Unit.is_stale`
| Attribute | Value |
|-----------|-------|
| **Location** | `data/models.py` → `Unit.is_stale` (property) |
| **Formula** | `detailing_due_date < today - 30 days` |
| **Constant** | `STALE_THRESHOLD_DAYS = 30` |
| **Used by** | Alert panel and list panel — stale units are excluded from display |

**Rationale**: Units with due dates more than 30 days in the past are considered stale/no longer actionable. They're hidden from the alert panel to reduce noise.

---

### 2.3 `Unit.milestones`
| Attribute | Value |
|-----------|-------|
| **Location** | `data/models.py` → `Unit.milestones` (property, cached) |
| **Returns** | Ordered list of `(label, date)` tuples |
| **Used by** | Timeline panel for visual milestone display |

**Order**: Detailing Start → Moved to Checking → Detailing Complete → Dept Due (prev) → Detailing Due

---

### 2.4 `Unit.working_days` (schedule)
| Attribute | Value |
|-----------|-------|
| **Location** | `data/models.py` → `Unit.working_days` field (NOT the same as `working_days_in_checking`) |
| **Set by** | `data/loader.py` → `load_units()` — loaded from `detailers` table via `get_detailer_schedules()` |
| **Format** | `list[int]` — weekday numbers (0=Mon, 4=Fri). Default: `[0,1,2,3]` (Mon-Thu) |
| **Used by** | `calculated_status_color` capacity check — determines how many working days are available |

**Rationale**: Different detailers work different schedules (e.g., Mon-Thu vs Tue-Fri). This field captures each detailer's working week so the capacity calculation uses the correct number of available days.

---

## 3. ALERT PANEL COMPUTATIONS
These are computed in the alert panel from collections of units.

---

### 3.1 Checking Surge Detection
| Attribute | Value |
|-----------|-------|
| **Location** | `gui/alert_panel.py` → `_detect_checking_surge(units)` |
| **Constant** | `CHECKING_SURGE_THRESHOLD = 3` |
| **Returns** | `set[str]` — COM numbers of units in a surge |

**Logic**: Group all non-stale, incomplete units that still need checking (not yet entered checking, not yet complete) by `detailing_due_date`. If 3+ units share the same due date, all are flagged as a surge.

**Display**: Surge units get a red "CHECK SURGE" badge with tooltip: "Checking surge: 3+ units due MM/DD/YYYY — checker bottleneck risk"

**Rationale**: The checker is a single bottleneck. When multiple units are due the same day, they all need to enter checking ~4 days prior. If the checker can't process them all in time, some will miss their due date. This flag tells the user "call in the cavalry" — bring in additional checking help or stagger the submissions.

**Current surges** (as of data analysis):
- 6/15: 3 units (20024, 19966, 19971)
- 6/18: 3 units (19967, 19969, 20015)
- 6/25: 4 units (20091, 20092, 20116, 20117) — includes 299h unassigned
- 7/21: 3 units (20123, 20127, 20134)
- 10/13: 4 units (20118-20121) — all unassigned

---

### 3.2 Criticality Sort Order
| Attribute | Value |
|-----------|-------|
| **Location** | `gui/alert_panel.py` → `CRITICALITY_ORDER` dict, `_sort_key_for_alert()` |
| **Order** | red(0) → orange(1) → purple(2) → yellow(3) → gray(4) → green(5) |
| **Secondary sort** | Due date (earliest first) within each color group |

**Rationale**: The alert panel sorts by `calculated_status_color` (capacity-aware criticality) rather than `alert_level` (calendar-only urgency). This ensures that units flagged red by the capacity check (like 20091) appear at the top even if their due date is weeks away.

---

### 3.3 Per-Detailer Capacity Warning
| Attribute | Value |
|-----------|-------|
| **Location** | `gui/alert_panel.py` → `_update_capacity_warning()` |
| **Constant** | `CAPACITY_HOURS_THRESHOLD = 160.0` (4 weeks × 40 hrs/week) |
| **Scope** | Only shown when a specific detailer is selected (not "All Detailers") |

**Formula**: Sum `department_hours × (1 - percent_complete/100)` for all non-stale units assigned to the selected detailer. If total > 160h, show "⚠️ OVERLOADED" warning.

**Rationale**: Quick indicator that a detailer has more work than they can handle in a month. 160h = 4 weeks at 40 hrs/week.

---

## 4. IMPORT PIPELINE COMPUTATIONS

### 4.1 `remaining_hours` (import)
See §1.4 above.

### 4.2 `working_days_in_checking` (import)
See §1.3 above.

### 4.3 `dept_due_date_previous` (import)
See §1.7 above.

### 4.4 `percent_complete` handling on import
| Attribute | Value |
|-----------|-------|
| **Location** | `automation/import_csv.py` → `upsert_row()` |
| **CSV format** | Percentage string (e.g., "65%") → parsed to float 0.65 |
| **DB storage** | Stored as 0-1.0 decimal in SQLite |
| **Unit object** | Multiplied by 100 → 0-100 scale in `row_to_unit()` |
| **Update rule** | Only set from CSV if currently NULL in DB (preserves manual entries) |

**Rationale**: The SSRS CSV is the source of truth for completion percentage, but manual edits in the GUI take precedence once set. This prevents a CSV re-import from overwriting someone's manual progress update.

---

## 5. LIST PANEL COMPUTATIONS

### 5.1 Tag Parsing
| Attribute | Value |
|-----------|-------|
| **Location** | `data/tag_parser.py` → `parse_description()` |
| **Input** | `unit.description` (free-text from SSRS) |
| **Output** | `ParsedTags` with `unit_type` and `features` list |
| **Used by** | List panel "Tags" column display |

**Rationale**: Extracts structured type/feature tags from free-text descriptions for filtering and display.

### 5.2 Unit Fingerprint
| Attribute | Value |
|-----------|-------|
| **Location** | `data/loader.py` → `unit_fingerprint()` |
| **Input** | All editable Unit fields |
| **Output** | SHA-256 hash (first 16 chars) |
| **Used by** | Optimistic conflict detection on save |

**Rationale**: Detects when a unit has been modified externally (by another user or import) since it was loaded into the edit form.

---

## 6. CONSTANTS REFERENCE

| Constant | Value | Location | Purpose |
|----------|-------|----------|---------|
| `STALE_THRESHOLD_DAYS` | 30 | `data/models.py` | Days past due before unit is hidden |
| `HOURS_PER_DAY` | 10.0 | `data/models.py` | 40 hrs/week ÷ 4 working days |
| `CHECKING_OVERHEAD_WD` | 4 | `data/models.py` | Median working days in checking pipeline |
| `CHECKING_SURGE_THRESHOLD` | 3 | `gui/alert_panel.py` | Units/day triggering surge flag |
| `CAPACITY_HOURS_THRESHOLD` | 160.0 | `gui/alert_panel.py` | 4 weeks × 40 hrs/week overload threshold |

---

## 7. DATA FLOW SUMMARY

```
SSRS CSV ──→ import_csv.py ──→ SQLite units table
                  │                    │
                  ├─ remaining_hours   │
                  ├─ working_days_in_checking
                  ├─ dept_due_date_previous
                  └─ percent_complete (0-1.0)
                           │
                           ▼
SQLite units table ──→ db.py row_to_unit() ──→ Unit dataclass
                                                    │
                                                    ├─ percent_complete (×100)
                                                    ├─ status_color (persisted)
                                                    ├─ working_days_in_checking (persisted)
                                                    └─ working_days (from config)
                                                           │
                                                           ▼
                                              Unit runtime properties:
                                                    ├─ calculated_status_color
                                                    ├─ alert_level
                                                    ├─ is_stale
                                                    ├─ milestones
                                                    └─ working_days_in_checking
                                                           │
                                                           ▼
                                              Alert panel:
                                                    ├─ _status_color_name()
                                                    ├─ _detect_checking_surge()
                                                    ├─ _sort_key_for_alert()
                                                    └─ _update_capacity_warning()
```

---

## 8. AUDIT TRAIL

Added in Sprint 2 (Data Integrity & Audit).

### 8.1 `_audit_log` Table
| Attribute | Value |
|-----------|-------|
| **Stored in** | `_audit_log` (SQLite table) |
| **Written by** | `data/db.py` → `log_field_changes()` |
| **Called from** | `data/writer.py` → `save_unit()` — after every successful save |
| **Schema** | `id`, `com_number`, `field_name`, `old_value`, `new_value`, `saved_by`, `saved_at` |
| **Indexes** | `idx_audit_com` (com_number), `idx_audit_saved_at` (saved_at) |

### 8.2 `previous_detailing_due_date` (Transient)
| Attribute | Value |
|-----------|-------|
| **Location** | `data/models.py` → `Unit.previous_detailing_due_date` |
| **Set by** | `UnitService.detect_changed_due_dates()` — compares old vs new unit lists on reload |
| **Cleared by** | `MainWindow.on_unit_selected()` — when user selects the unit |
| **Purpose** | Shows "due date changed" indicator in calendar/list + dialog with old date |

---

*Generated: 2026-06-15*
*Last updated: 2026-06-15 — Added audit trail (§8), previous_detailing_due_date, service layer architecture*
*DB state: 2,765 units, 885 with checking data, 15 active detailers*
*Architecture: Service layer extraction (ARCH-001) complete. 254 tests passing.*
