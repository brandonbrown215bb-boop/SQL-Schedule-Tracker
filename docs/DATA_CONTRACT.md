# Data Contract — Data Model, Calculations, and Reporting

This document serves as the canonical reference for the database schema, data model fields, computed/derived metrics, validation rules, manual overrides, and reporting displays across the SQL Schedule Tracker application.

---

## 1. CORE DATA MODEL & SCHEMA

The primary entity is the `Unit` dataclass (defined in [models.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/data/models.py)). Below is the complete listing of database-persisted fields (columns in the SQLite `units` table) and transient (in-memory) fields.

### 1.1 Persisted Fields (SQLite `units` table)

| Column Name | Python Attribute | DB Type | Category | Description |
| :--- | :--- | :---: | :---: | :--- |
| `com_number` | `com_number` | `TEXT` | Identity | Unique COM identifier (Primary Key). |
| `job_name` | `job_name` | `TEXT` | Identity | Name of the project/job. |
| `top_level_number` | `contract_number` | `TEXT` | Identity | Contract or order number. |
| `description` | `description` | `TEXT` | Identity | Free-text description of the unit from the SSRS report. |
| `detailer` | `detailer` | `TEXT` | Assignment | Name of the assigned detailer. |
| `checking_status` | `checking_status` | `TEXT` | Assignment | Checking pipeline status, picked from `checking_statuses` in config.yaml (older free-text values are kept). |
| `checker` | `checker` | `TEXT` | Assignment | Detailer who checks the unit (any detailer). In the reporting feed. |
| `unit_state` | `unit_state` | `TEXT` | Status | Manufacturing Order Management State provided directly in `SCHDetailingReport` (`LineItemStateDesc` or `UnitState`: `Done`, `Fab-Eng`, `Fab-Load`, `Fab-Lock`, `Pre-Eng`, `Pre-Load`). |
| `notes` | `notes` | `TEXT` | Assignment | Free-text notes. |
| `dr_checks` | `dr_checks` | `TEXT` | Assignment | Status/log comments for Design Review checks. |
| `dvl_checks` | `dvl_checks` | `TEXT` | Assignment | Status/log comments for Design Verification Log checks. |
| `status_color` | `status_color` | `TEXT` | Status | Persisted capacity-aware status color. |
| `department_hours` | `department_hours` | `REAL` | Hours | Total allocated detailing hours for the department. |
| `target_dept_hours` | `unit_target_hours` | `REAL` | Hours | The unit's own target: `MAX(0, department_hours - iec_internal_hours + target_adjustment_hours)`. Derived; rewritten on every import and save. In memory, `target_department_hours` holds the *counted* value (see §2.6). |
| `target_adjustment_hours` | `target_adjustment_hours` | `REAL` | Hours | Scheduler correction for wrong imported Dept Hours. May be negative. Never touched by the import. |
| `target_adjustment_reason` | `target_adjustment_reason` | `TEXT` | Hours | Why the adjustment was made. Required when the adjustment is not 0. |
| `iec_internal_hours` | `iec_internal_hours` | `REAL` | Hours | Detailing hours performed internally by the IEC team. |
| `percent_complete` | `percent_complete` | `REAL` | Hours | Detailing completion percentage (stored as 0.0–1.0 in DB, scaled 0–100 in Python). |
| `actual_hours` | `actual_hours` | `REAL` | Hours | Actual hours charged (typically imported from SSRS). |
| `actual_hours_to_detail_unit`| `actual_hours_to_detail_unit`| `REAL` | Hours | Manually tracked actual detailing hours. |
| `hour_variance` | `hour_variance` | `REAL` | Hours | Variance between allocated and manual actual hours. |
| `remaining_demand` | `remaining_demand` | `REAL` | Hours | Manually tracked remaining hours of work. |
| `hours_checking` | `hours_checking` | `REAL` | Hours | Detailing checking hours. |
| `remaining_hours` | (N/A) | `REAL` | Audit | Calculated remaining hours: `department_hours * (1 - percent_complete)`. |
| `working_days_in_checking` | `working_days_in_checking` | `INTEGER` | Dates | Mon-Fri calendar days spent in checking. NULL if incomplete. |
| `unit_detailing_start_date`| `unit_detailing_start_date`| `TEXT` | Dates | Detailing start date (ISO format). |
| `unit_moved_to_checking_date`| `unit_moved_to_checking_date`| `TEXT` | Dates | Date unit entered checking (ISO format). |
| `unit_detailing_completion_date`| `unit_detailing_completion_date`| `TEXT` | Dates | Date detailing was completed (ISO format). |
| `dept_due_date_previous` | `dept_due_date_previous` | `TEXT` | Dates | Previous due date before a push (ISO format). |
| `detailing_due_date` | `detailing_due_date` | `TEXT` | Dates | Current detailing due date (ISO format). |
| `build_date` | `build_date` | `TEXT` | Dates | Production build date (ISO format). |
| `week_ending_friday` | `week_ending_friday` | `TEXT` | Dates | Friday of the week containing the due date (ISO format). |
| `updated_at` | `updated_at` | `TEXT` | Sync | SQLite timestamp for optimistic locking (`YYYY-MM-DD HH:MM:SS.SSS`). |

### 1.2 Transient Fields (In-Memory Only)

* **`working_days`** (`list[int]` | `None`) — List of weekday numbers representing the detailer's active schedule (e.g. `[0,1,2,3]` for Mon-Thu). Loaded from configuration on load.
* **`due_date_changed`** (`bool`) — High-priority visual alert trigger set on load if the detailing due date was modified during import. Cleared when selected.
* **`previous_detailing_due_date`** (`date` | `None`) — Holds the pre-pushed due date for display in warning dialogs.
* **`is_non_primary_identical`** (`bool`) — Indicates if the unit is a non-primary identical under the Identicals rule.
* **`detailed_on_com`** (`str`) — For a non-primary identical, the COM of the primary that carries its target hours.
* **`excel_row`** (`int` | `None`) — Row index for legacy Excel spreadsheet synchronization.
* **`fingerprint`** (`str`) — Stable SHA-256 hash representation of the editable fields.
* **`base_revision`** (`int`) — Base revision number for multi-user sync.

---

## 2. CALCULATIONS & AUTOMATIONS

This section outlines all business-logic calculations, including their formulas, execution triggers, and underlying rationale.

### 2.1 Capacity-Aware Status Color (`calculated_status_color`)

The primary visual indicator. Recalculated at runtime by `Unit.calculated_status_color` (property) and written to SQLite `units.status_color` on every save (both from GUI or import update).

#### Logic (evaluated top-to-bottom, first match wins):
1. `percent_complete >= 100.0` → **green** (Released / Done)
2. `detailing_due_date` is past today → **red** (Overdue)
3. **Capacity Check** → **red** (Behind Schedule / Potential Miss)
   * **Formula:**
     $$\text{remaining\_hours} = \text{department\_hours} \times \left(1.0 - \frac{\text{percent\_complete}}{100.0}\right)$$
     $$\text{working\_days} = \text{Count of working weekdays between today (exclusive) and due date (inclusive)}$$
     $$\text{needs\_checking} = \text{unit\_moved\_to\_checking\_date is NULL and unit\_detailing\_completion\_date is NULL}$$
     $$\text{effective\_working\_days} = \max(0, \text{working\_days} - (\text{needs\_checking} ? 4 : 0))$$
     $$\text{available\_hours} = \text{effective\_working\_days} \times 10.0$$
     $$\text{If } \text{remaining\_hours} > \text{available\_hours} \rightarrow \text{RED}$$
   * *Rationale:* Accounts for detailer capacity and checking bottleneck buffer. Units that haven't entered checking yet reserve `CHECKING_OVERHEAD_WD = 4` working days to clear the checker.
4. `percent_complete >= 95.0` → **orange** (Checked & Returned)
5. `percent_complete >= 90.0` → **purple** (Ready for Checking)
6. `percent_complete > 0.0` → **yellow** (In Progress)
7. Default → **gray** (Unassigned)

### 2.2 The Identicals Rule
* **Trigger:** Executed during `load_units()` in [loader.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/data/loader.py).
* **Logic:**
  * Units sharing a `contract_number` are detailed once. Groups units by `contract_number` (ignoring blanks), **leaving out cancelled units**.
  * Within each group, the earliest unit on the schedule is the **primary**: units the old workbook flagged `same_as` ("same-as…") go last, then earliest `detailing_due_date`, undated last, then lowest `com_number`. A cancelled unit is never the primary.
  * Contract numbers starting with `WO` are service-order buckets, not identicals: every unit under one counts its own target.
  * Non-primary units are flagged `is_non_primary_identical = True`, count `0.0` target hours, and get `detailed_on_com` = the primary's COM.
  * **The DB keeps each unit's own target** (`units.target_dept_hours`); the rule is applied whenever target hours are read, so it follows due-date changes automatically.
  * **SQL twin:** `COUNTED_TARGET_SQL` / `NON_PRIMARY_IDENTICAL_SQL` / `DETAILED_ON_COM_SQL` in `data/db.py`, used by `v_reporting_export` and the workbook export (column V). The view carries a version marker and is recreated automatically when its definition changes.

### 2.3 Working Days in Checking (`working_days_in_checking`)
* **Trigger:** Calculated during CSV import, manual unit saves, or database migrations.
* **Formula:** Number of Mon-Fri calendar days (inclusive of both start and end) between `unit_moved_to_checking_date` and `unit_detailing_completion_date`. Returns `NULL` if either date is missing.

### 2.4 Week-Ending Friday (`week_ending_friday`)
* **Trigger:** Calculated automatically during save.
* **Formula:**
  $$\text{week\_ending\_friday} = \text{detailing\_due\_date} + \left( (4 - \text{detailing\_due\_date.weekday()}) \pmod 7 \right)$$
  This shifts the current due date to the Friday of that week (where Monday = 0, Friday = 4, Sunday = 6). Evaluates to `NULL` if no due date exists.

### 2.5 Remaining Hours (`remaining_hours`)
* **Trigger:** Recomputed during CSV import and **on every manual save** in the database writer.
* **Formula:**
  $$\text{remaining\_hours} = \text{department\_hours} \times \left(1.0 - \frac{\text{percent\_complete}}{100.0}\right)$$
* **Correction:** *Unlike early system notes, the SQLite writer does update this value dynamically during manual save execution to guarantee synchronicity.*

### 2.6 Target Department Hours (`target_department_hours`)
* **Never typed directly.** Inputs: `department_hours` (SSRS only), `iec_internal_hours` (scheduler), `target_adjustment_hours` + reason (scheduler).
* **Unit target** (`Unit.unit_target_hours`, stored in `units.target_dept_hours`):
  $$\max(0.0, \text{department\_hours} - \text{iec\_internal\_hours} + \text{target\_adjustment\_hours})$$
* **Counted target** (`Unit.counted_target_hours`, held in `target_department_hours` after load/save, reported as `target_dept_hours` in the feed): the unit target, or `0.0` for cancelled units and non-primary identicals (§2.2).
* **Import:** recomputes `target_dept_hours` from the new Dept Hours and the stored IEC/adjustment; it never changes IEC or the adjustment.
* **Feed (`v_reporting_export`):** leaves out cancelled units. Columns: `target_dept_hours` (counted), `unit_target_hours`, `target_adjustment_hours`, `target_adjustment_reason`, `detailed_on_com`.
* **Migration (2026-10):** open units whose old hand-typed target differed from Dept − IEC kept the difference as an adjustment; all other old overrides were dropped.

### 2.7 Hour Variance (`hour_variance`)
* **Trigger:** Auto-calculated in the Inline Edit Bar when `actual_hours_to_detail_unit` changes.
* **Formula:**
  $$\text{hour\_variance} = \text{department\_hours} - \text{actual\_hours\_to\_detail\_unit}$$

### 2.8 Due Date Push History (`dept_due_date_previous`)
* **Trigger:** Checked during CSV import.
* **Logic:** If a unit already exists in the DB and the imported `detailing_due_date` differs from the existing record, the old due date is copied to `dept_due_date_previous` before the new one is written.

### 2.9 Description Tag Parsing & Novelty Detection
* **Trigger:** Computed on load via [tag_parser.py](file:///c:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/data/tag_parser.py).
* **Logic:** Extracts structural attributes from the raw unit description:
  * **Unit Type:** Recognized prefixes (e.g. `O)2`, `I)3`, `RTF`).
  * **Dimensions:** Patterns matching `L x W x H` structures (e.g., `8X8X13`).
  * **Features:** Extracted tokens checked against a strict whitelist of 46 reviewed terms (e.g. `VFD`, `UV`, `KDOWN`).
  * **Flags:** Markers enclosed in asterisks (e.g., `*PRE-PAINT*`).
  * **Novelty check:** If a detailer is assigned to a unit type or feature set they have not previously detailed (checked via the history database table `detailer_tags_history`), the unit displays a novelty badge (`✦`).

---

## 3. OVERRIDE CAPABILITIES (EDITABLE FIELDS & GUARDS)

Operators can edit scheduling details through two interfaces: the **Main Edit Form** (detailed, dialog-based) and the **Inline Edit Bar** (streamlined, layout-level). Below is a mapping of edit permissions and validation rules.

| Field | Main Edit Form | Inline Edit Bar | Constraints / Validation Guards |
| :--- | :---: | :---: | :--- |
| **COM Number** | Read-Only | Read-Only | Cannot be empty, must be unique primary key. |
| **Job Name** | **Editable** | Read-Only | Limited to 255 characters. |
| **Contract #** | **Editable** | Read-Only | Limited to 50 characters. |
| **Description** | **Editable** | Read-Only | Limited to 500 characters. |
| **Detailer** | **Editable** | **Editable** | Must be selected from whitelisted detailer config. |
| **Checking Status** | **Editable** | **Editable** | Free text. |
| **DR Check** | **Editable** | **Editable** | Free text. |
| **DVL Check** | **Editable** | **Editable** | Free text. |
| **Notes** | **Editable** | Read-Only | Free text. |
| **Status Color** | Read-Only | Read-Only | Recalculated dynamically at runtime/save. |
| **Dept Hours** | Read-Only | Read-Only | From the SSRS import only. |
| **IEC Hours** | **Editable** | **Editable** | Must be non-negative. Modifies `target_department_hours`. |
| **Target Adjustment** | **Editable** | Read-Only | May be negative. Requires an Adjustment Reason when not 0. |
| **Target Hrs** | Read-Only | Read-Only | Calculated: Dept − IEC + Adjustment; `0.0` for cancelled units and non-primary identicals. |
| **% Complete** | **Editable** | **Editable** | Must be in range `0.0` to `100.0`. |
| **Actual Hours** | **Editable** | Read-Only | Must be non-negative. Represents SSRS actual hours. |
| **Actual Hours to Detail** | Read-Only | **Editable** | Must be non-negative. Represents manually tracked detail hours. |
| **Hour Variance** | Read-Only | **Editable** | Auto-calculated, but can be manually adjusted inline. |
| **Remaining Demand** | Read-Only | **Editable** | Auto-calculated, but can be manually adjusted inline. |
| **Hours Checking** | Read-Only | **Editable** | Must be non-negative. |
| **Start Date** | **Editable** | **Editable** | Must be before checking/completion dates. |
| **Checking Date** | **Editable** | **Editable** | Must be after start date and before completion date. |
| **Completion Date** | **Editable** | **Editable** | Must be after start and checking dates. |
| **Prev Due Date** | **Editable** | Read-Only | Calendar selection. |
| **Due Date** | **Editable** | Read-Only | Calendar selection. Triggers due date change history if modified. |
| **Build Date** | **Editable** | Read-Only | Calendar selection. |

### 3.1 Edit Guards & Validation
* **Date Sequence validation:** The system checks that $\text{Start Date} \le \text{Checking Date} \le \text{Completion Date}$ and alerts the operator if they are out of chronological order.
* **Optimistic Concurrency Lock:** Saves compare the unit's loaded `updated_at` timestamp with the database. If they mismatch (indicating another scheduler modified the unit in the background), the save is rejected, raising a `ConcurrentEditError` and launching a side-by-side **Conflict Resolution Dialog**.

---

## 4. UI REPORTING & VISIBILITY

Fields are reported in-app across several visual panels:

### 4.1 List View (`ListPanel`)
* Displays columns for all fields. Default visible columns: `COM`, `Due Date`, `Prev Due`, `Job Name`, `Detailer`, `Status` (color badge), `% Complete`, and `Tags` (parsed summary).
* Users can toggle visibility for additional columns: `Dept Hours`, `Actual Hours`, `Target Hrs`, `Checking`, `DR Check`, `DVL Check`, `Contract #`, `Build Date`, `Start Date`, `Check WD`, `Notes`, and `Alert`.
* Displays a due date change warning (`⚠`) adjacent to pushed due dates.
* Displays a novelty indicator (`✦`) next to novel tags.
* Soft-color background bands highlight matching `Contract #` or `Due Date` values to help identify group clusters.

### 4.2 Calendar View (`CalendarPanel`)
* Renders unit blocks on their `detailing_due_date`.
* Colors cards using their capacity-aware `calculated_status_color`.
* Displays due date change warnings (`⚠`) if the due date shifted since import.

### 4.3 Alert Dashboard (`AlertPanel`)
* Aggregates active alerts, sorted by `calculated_status_color` risk level (red first) and then due date.
* **Checking Surge Detection:** Displays a `CHECK SURGE` warning badge on units when 3 or more incomplete units share a detailing due date, representing a checking pipeline bottleneck.
* **Capacity Warning:** Displays a large `⚠️ OVERLOADED` warning when a selected detailer's assigned units exceed 160 hours of total remaining demand.
* Excludes stale units (> 30 days past due).

### 4.4 Milestone Timeline (`TimelinePanel`)
* Displays a chronological progress track for the selected unit: `Detailing Start` → `Moved to Checking` → `Detailing Complete` → `Dept Due (prev)` → `Detailing Due`.
* Highlights nodes and track lines with the unit's `calculated_status_color`.

### 4.5 Audit Trail Dialog (`AuditDialog`)
* Accessible by clicking the audit trail button on a unit. Displays the historical ledger of all changes, showing: `Field Name`, `Old Value`, `New Value`, `Modified By`, and `Modified At`.

---

## 5. KEY CONSTANTS REFERENCE

These parameters govern the capacity formulas and alert thresholds across the system:

| Constant Name | Value | Defined In | Purpose |
| :--- | :---: | :--- | :--- |
| `STALE_THRESHOLD_DAYS` | 30 | `data/models.py` | Days past due before a unit is considered stale and hidden. |
| `HOURS_PER_DAY` | 10.0 | `data/models.py` | Default standard daily working capacity per detailer (40 hrs/week ÷ 4 days). |
| `CHECKING_OVERHEAD_WD` | 4 | `data/models.py` | Reserved working days for a unit in the checking pipeline. |
| `CHECKING_SURGE_THRESHOLD` | 3 | `gui/alert_panel.py` | Minimum units due on the same day to trigger a checking bottleneck alert. |
| `CAPACITY_HOURS_THRESHOLD` | 160.0 | `gui/alert_panel.py` | Maximum hours threshold for overloading a detailer's monthly backlog. |

---

## 6. DATA FLOW SUMMARY

```
SSRS CSV ──→ import_csv.py ──→ SQLite units table
                  │                    │
                  ├─ remaining_hours   │
                  ├─ working_days_in_checking
                  ├─ dept_due_date_previous
                  ├─ percent_complete (0-1.0)
                  └─ week_ending_friday
                           │
                           ▼
SQLite units table ──→ db.py row_to_unit() ──→ Unit dataclass
                                                     │
                                                     ├─ percent_complete (×100)
                                                     ├─ status_color (persisted)
                                                     ├─ working_days_in_checking (persisted)
                                                     ├─ week_ending_friday (persisted)
                                                     ├─ actual_hours_to_detail_unit (persisted)
                                                     ├─ hour_variance (persisted)
                                                     ├─ remaining_demand (persisted)
                                                     ├─ hours_checking (persisted)
                                                     ├─ dr_checks / dvl_checks (persisted)
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
                                               Alert panel & UI Views:
                                                     ├─ _status_color_name()
                                                     ├─ _detect_checking_surge()
                                                     ├─ _sort_key_for_alert()
                                                     ├─ _update_capacity_warning()
                                                     └─ Group highlighting (contract/due date)
```
