# Code Review: Schedule-Viewer-App-v2

*Last updated: 2026-06-08*

---

## Bugs Found

### BUG-1: `unit_fingerprint` missing `notes` field
**File**: `data/loader.py` lines 36-55
**Severity**: Low
**Status**: **FIXED**
**Issue**: The `unit_fingerprint` payload did not include `notes`. If someone edited only the notes field, the fingerprint wouldn't change, and the sync layer's conflict detection would miss it. The `updated_at` optimistic lock would still catch it, but the fingerprint-based check would not.
**Resolution**: `notes` added to the fingerprint payload at line 43.

---

### BUG-2: `percent_complete` scale mismatch (DB 0-1 vs model 0-100)
**File**: `data/db.py` line 126, `data/writer.py` line 67
**Severity**: Medium
**Status**: **DOCUMENTED — working as designed**
**Issue**: The DB stores `percent_complete` as 0.0-1.0. `row_to_unit` multiplies by 100 on load; `save_unit` divides by 100 on write. Correct but fragile — direct DB access without helpers will get it wrong.
**Current state**: All code paths use the helpers. Documented in `docs/COMPUTATION_AUDIT.md`.

---

### BUG-3: `_apply_identicals` mutates units in-place without signaling
**File**: `data/loader.py` lines 62-97
**Severity**: Medium
**Status**: **FIXED**
**Issue**: `_apply_identicals` modifies `target_department_hours` and `is_non_primary_identical` on Unit objects in-place during `load_units()`. If a unit is displayed in the edit form during a background reload, the form won't reflect the updated values until the user re-selects the unit.
**Resolution**: `_on_load_finished` in `main_window.py` now updates `current_unit` and re-populates the edit form with the post-identicals unit object if a unit was currently displayed.

---

### BUG-4: Duplicate `working_days_between` implementations
**File**: `data/db.py` lines 44-65 and 184-199, `data/models.py` lines 10-27
**Severity**: Low
**Status**: **FIXED**
**Issue**: Three implementations exist with different semantics:
- `models.py` `_working_days_between(start: date, end: date, weekdays)` — start exclusive, end inclusive. Used by `calculated_status_color`.
- `db.py` `_working_days_between(start_str, end_str)` — string-based, both inclusive. Used by `writer.py` and `import_csv.py`.
- `db.py` `working_days_between(start: date, end: date, weekdays)` — **removed**. Dead code, never called.
**Resolution**: The two active implementations serve different purposes (runtime vs DB-level) and have different signatures. The dead code at line 184 was removed. Kept `models.py` version as `_working_models` (private) and `db.py` version as the public-facing name.

---

### BUG-5: `status_color` not persisted across reloads
**File**: `data/db.py` line 122
**Severity**: Low
**Status**: **FIXED**
**Issue**: `row_to_unit` hardcoded `status_color="gray"` because the DB didn't store it. Manual assignments (purple/orange) were lost on reload.
**Resolution**: `status_color` column added to schema. Writer persists `calculated_status_color` on every save. `row_to_unit` reads the persisted value. Verified: unit 20087 has status_color "yellow" in DB.

---

### BUG-6: `edit_form.py` QComboBox dirty tracking false positive
**File**: `gui/edit_form.py` lines 181-182
**Severity**: Low
**Status**: **FIXED**
**Issue**: `currentIndexChanged` fires when the combo box is first populated during `load_unit()`, potentially triggering a false "unsaved changes" warning. The `_loading` flag likely prevents this in practice, but the connection order is fragile.
**Resolution**: `_loading` flag is now set to `True` before form population and cleared in the `finally` block, so `_mark_dirty` correctly ignores signal emissions during loading.

---

### BUG-7: Calendar only shows `detailing_due_date`
**File**: `gui/calendar_panel.py` lines 62-73
**Severity**: Low
**Status**: **NOT DESIRED**
**Issue**: The calendar only maps `detailing_due_date`. Other dates (`build_date`, `unit_detailing_start_date`, `unit_detailing_completion_date`) are invisible.
**Resolution**: User decided this is not needed.

---

### BUG-8: List panel search doesn't include `description` or `notes`
**File**: `gui/list_panel.py` lines 180-187
**Severity**: Medium
**Status**: **FIXED**
**Issue**: The COM search filter only searches `com_number`, `job_name`, and `contract_number`. Users searching for unit types (e.g., "O)2") or note keywords won't find results.
**Resolution**: `description` and `notes` fields added to the search filter in `UnitListModel.apply_filters()`.

---

### BUG-9: `tag_parser.py` RTF revision number handling
**File**: `data/tag_parser.py` lines 159-170
**Severity**: Medium
**Status**: **FIXED**
**Issue**: The RTF handling strips trailing revision numbers by checking if the next token is a digit. "RTF 9X9X18" would have "9" stripped, leaving "X9X18" which fails dimension parsing. Fragile for edge cases.
**Resolution**: Replaced split-and-check logic with a regex that explicitly matches "RTF" + optional dimension pattern, preserving full dimensions while correctly discarding lone revision digits.

---

### BUG-10: `pivot_chart.py` hardcoded color strings
**File**: `gui/pivot_chart.py` lines 21-26
**Severity**: Low
**Status**: **FIXED**
**Issue**: The `COLORS` dict uses hardcoded hex strings (`#4472C4`, etc.) instead of referencing the theme system. Poor contrast in dark mode.
**Resolution**: Replaced the `COLORS` hardcoded dict with `COLOR_KEYS` that map to theme token names. Colors are resolved at runtime via `get_status_colors()` and theme tokens, respecting dark mode and CVD settings.

---

### BUG-11: `alert_level` used wrong threshold for COMPLETE
**File**: `data/models.py` line 140
**Severity**: High
**Status**: **FIXED**
**Issue**: `percent_complete >= 1.0` caught everything at 1%+ as COMPLETE (scale is 0-100). Nearly every non-stale unit showed as COMPLETE in the alert panel, hiding real alerts.
**Resolution**: Changed to `percent_complete >= 100.0`.

---

### BUG-12: Alert panel empty on first view
**File**: `gui/main_window.py` lines 358-359, `gui/alert_panel.py` line 177
**Severity**: Medium
**Status**: **FIXED**
**Issue**: `_current_detailer` initialized to `"All"` but combo box item is `"All Detailers"`. Filter tried `detailer == "All"` which matched nothing.
**Resolution**: Changed init to `"All Detailers"`. Removed `if self.units:` guard on `set_units()` when switching to alerts view.

---

### BUG-13: Alert panel sort didn't reflect capacity-critical units
**File**: `gui/alert_panel.py` → `_sort_key_for_alert()`
**Severity**: Medium
**Status**: **FIXED**
**Issue**: Sort used `alert_level` (calendar-day buckets) instead of `calculated_status_color` (capacity-aware). Units flagged red by capacity (like 20091) sorted below ON_TRACK units.
**Resolution**: Sort now uses `calculated_status_color` via `CRITICALITY_ORDER`. Red/critical units sort to top.

---

## New Bugs Found This Session (2026-06-08)

### BUG-14: `edit_form.py` QTextEdit (`notes_edit`) not connected to dirty tracking
**File**: `gui/edit_form.py` lines 178-186
**Severity**: High
**Status**: **FIXED** (by subagent)
**Issue**: The `_fields` tuple included `self.notes_edit` (a `QTextEdit`), but the `isinstance` loop only handled `QLineEdit`, `QComboBox`, `QDateEdit`, and `QDoubleSpinBox`. `QTextEdit` matched none of these, so its `textChanged` signal was never connected. **Changes to the Notes field never marked the form dirty**, meaning the user could edit notes, navigate away, and lose changes without any warning.
**Resolution**: Added an explicit `elif isinstance(f, QTextEdit): f.textChanged.connect(self._mark_dirty)` branch.

---

### BUG-15: `main_window.py` auto-reload silently discards unsaved form edits
**File**: `gui/main_window.py` lines 649-657
**Severity**: High
**Status**: **FIXED** (by subagent)
**Issue**: In `_on_load_finished()`, after a data reload (triggered by file watcher, auto-refresh, or manual refresh), the code unconditionally called `self.edit_form.set_unit(new_unit)` for the currently selected unit. This **silently overwrote** any unsaved changes the user had in the form. If an auto-refresh fired while the user was editing, their edits were lost without warning.
**Resolution**: Added a `if not self._form_dirty:` guard so the form is only re-populated when there are no unsaved changes.

---

### BUG-16: `conflict_dialog.py` double-connection causes duplicate confirmation dialogs
**File**: `gui/conflict_dialog.py` lines 133-151
**Severity**: High
**Status**: **FIXED** (by subagent)
**Issue**: `overwrite_btn` was added with `QDialogButtonBox.AcceptRole`, which triggers `btn_box.accepted`. Then `btn_box.accepted.connect(self._on_overwrite)` was connected. Additionally, `overwrite_btn.clicked.connect(self._on_overwrite)` was also connected. Clicking "Overwrite" fired `_on_overwrite` **twice**, showing the confirmation dialog twice in succession.
**Resolution**: Changed both `overwrite_btn` and `reload_btn` to `QDialogButtonBox.ActionRole` (which does NOT trigger `btn_box.accepted`), removed the `btn_box.accepted.connect(...)` and `btn_box.rejected.connect(...)` lines, and kept only the direct `clicked` connections.

---

### BUG-17: `list_panel.py` — Missing status label update in incremental refresh
**File**: `gui/list_panel.py` line ~761
**Severity**: Medium
**Status**: **FIXED** (by subagent)
**Issue**: `_refresh_table_incremental()` ended with a comment `# Update status label` but never actually called `self.status_label.setText(...)`. The full-refresh path (`_refresh_table_full`) properly updated the label, but the incremental path (used for tables >50 rows) left the status bar stale after every save/refresh cycle.
**Resolution**: Added the missing `self.status_label.setText(...)` call with the same logic as `_refresh_table_full`.

---

### BUG-18: `calendar_panel.py` — Clicking empty dates doesn't clear event list
**File**: `gui/calendar_panel.py` lines 40-42
**Severity**: Medium
**Status**: **FIXED** (by subagent)
**Issue**: `_emit_date_clicked` only emitted `date_clicked` when `date in self.events_by_date`. Clicking a date with no events was silently ignored, leaving the event list showing the previous date's events — stale data that misleads the user.
**Resolution**: Removed the `if date in self.events_by_date:` guard so all date clicks emit the signal. The `_on_date_clicked` slot already handles empty lists correctly.

---

### BUG-19: `loading_overlay.py` — Repeated `hide()` calls create duplicate timers
**File**: `gui/loading_overlay.py` lines 82-89
**Severity**: Low
**Status**: **FIXED** (by subagent)
**Issue**: If `hide()` was called multiple times (e.g., rapid load/error sequences), each call could schedule a new `QTimer.singleShot` without canceling the previous one. This could cause the overlay to hide at unexpected times or the spinner to stop prematurely.
**Resolution**: Added an early `if not self.isVisible(): return` guard at the top of `hide()`.

---

### BUG-20: `edit_form.py` — Read-only `target_hours_spin` unnecessarily in dirty-tracking/signal-block loops
**File**: `gui/edit_form.py` lines 172, 229
**Severity**: Low
**Status**: **FIXED** (by subagent)
**Issue**: `self.target_hours_spin` (set to `setReadOnly(True)`) was included in both the dirty-tracking `_fields` tuple and the signal-blocking loop in `set_unit()`. While not a crash bug, it added unnecessary signal blocking/unblocking overhead.
**Resolution**: Removed `target_hours_spin` from both `_fields` tuples.

---

### BUG-21: `tag_parser.py` — Compound feature matching is order-dependent and can miss overlaps
**File**: `data/tag_parser.py` lines 290-298
**Severity**: Medium
**Status**: **OPEN**
**Issue**: The compound feature detection iterates `_COMPOUND_FEATURES` and does `text_upper.replace(compound, "", 1)` for each match. If compound A is a substring of compound B (e.g., "FLOOD" is a substring of "FLOOD TEST"), and A is iterated first, B will never match. The current `_COMPOUND_FEATURES` set has "FLOOD TEST" but not bare "FLOOD", so this doesn't fire today, but it's a fragile design. Additionally, `AL BASE` (in compound features) normalizes to `AL-BASE` (in whitelist), but the compound check runs against raw `text_upper` — if the text has "AL BASE" it matches the compound, gets normalized via `_NORMALIZATION_MAP`, and lands on `AL-BASE`. This works but is implicit.
**Recommendation**: Sort compound features by length (longest first) before matching to prevent substring collisions. Consider doing compound matching on already-normalized tokens.

---

### BUG-22: `tag_parser.py` — RTF dimension pattern discards valid dimension data
**File**: `data/tag_parser.py` lines 262-281
**Severity**: Medium
**Status**: **FIXED**
**Issue**: The RTF regex captures dimension data, but a case-sensitive check could miss lowercase "x" in input like "RTF 9x9x18".
**Resolution**: The check at line 288 already uses `.upper()`: `if "X" in revision_or_dim.upper()`. Verified with test input "RTF 9x9x18" → dimensions correctly extracted as "9X9X18".

---

### BUG-23: `db.py` — `_working_days_between` doesn't handle end < start for `working_days` version
**File**: `data/db.py` lines 184-199
**Severity**: Low
**Status**: **FIXED**
**Issue**: The public `working_days_between` (dead code, now removed) returned 0 when `end <= start`, but the private `_working_days_between` returns `None` when `e < s`. Inconsistent return types for the same edge case.
**Resolution**: Dead public function removed. The private `_working_days_between` correctly returns `None` for `e < s` (NULL = "unknown"), which is the right semantics for the writer.

---

### BUG-24: `writer.py` — `notes` field not in UPDATE SQL
**File**: `data/writer.py` lines 37-83
**Severity**: Medium
**Status**: **NEEDS VERIFICATION**
**Issue**: Looking at the UPDATE statement, `notes` IS included at line 55 in the column list. However, verify that the parameter tuple at lines 60-83 has `unit.notes` at the correct position. Counting the `?` placeholders vs the values: there are 19 `?` columns + 1 or 2 WHERE params. The values tuple has 19 entries including `unit.notes` at position 18 (0-indexed: 17). This appears correct, but any future column addition must maintain exact positional correspondence.

---

### BUG-25: `loader.py` — Fingerprint cache keyed on `id(unit)` can collide
**File**: `data/loader.py` lines 30-58
**Severity**: Low
**Status**: **OPEN**
**Issue**: `_fingerprint_cache` uses `id(unit)` as the key. Python's `id()` returns the memory address, which can be reused after an object is garbage collected. If a Unit is deleted and a new one allocated at the same address, the cache would return a stale fingerprint. In practice, this is unlikely given the app's usage pattern, but it's a correctness issue in theory.
**Recommendation**: Use the `com_number` as the cache key instead, or use a `WeakValueDictionary`.

---

## Improvements

### IMP-1: Add `notes` to `unit_fingerprint` payload
**Status**: **FIXED** (see BUG-1)

---

### IMP-2: Persist `status_color` to the database
**Status**: **FIXED** (see BUG-5)

---

### IMP-3: Unify `working_days_between` implementations
**Status**: **FIXED** (see BUG-4)
The two active implementations serve different purposes and have different signatures. Dead code removed.

---

### IMP-4: Extend calendar to show multiple date types
**Status**: **NOT DESIRED** (see BUG-7)

---

### IMP-5: Extend search to include description and notes
**Status**: **FIXED** (see BUG-8)

---

### IMP-6: Add feature-based filtering
**Status**: **SPEC WRITTEN** — see `plans/IMP-6-feature-filtering.md`

---

### IMP-7: Add unit type filtering
**Status**: **SPEC WRITTEN** — see `plans/IMP-7-unit-type-filtering.md`

---

### IMP-8: Improve RTF parsing in tag_parser
**Status**: **FIXED** (see BUG-9)

---

### IMP-9: Add database migration system
**Status**: **FIXED**
`_migrate_schema()` in `data/db.py` handles incremental schema changes:
- `status_color` column (earlier migration)
- `working_days_in_checking` column (this session, with backfill of 885 rows)

---

### IMP-10: Add `manufacturing_location` to the UI
**Status**: **SPEC WRITTEN** — see `plans/IMP-10-manufacturing-location-UI.md`

---

### IMP-11: Theme-aware pivot chart colors
**Status**: **FIXED** (see BUG-10)

---

### IMP-12: Add keyboard shortcuts
**Status**: **SPEC WRITTEN** — see `plans/IMP-12-keyboard-shortcuts.md`

---

### IMP-13: Batch operations
**Status**: **SPEC WRITTEN** — see `plans/IMP-13-batch-operations.md`

---

### IMP-14: Export filtered results
**Status**: **SPEC WRITTEN** — see `plans/IMP-14-export-filtered.md`

---

### IMP-15: Undo/redo support
**Status**: **SPEC WRITTEN** — see `plans/IMP-15-undo-redo.md`

---

### IMP-16: Add `working_days_in_checking` computed column
**Status**: **IMPLEMENTED**

---

### IMP-17: Add checking surge detection
**Status**: **IMPLEMENTED**

---

### IMP-18: Add computation audit document
**Status**: **IMPLEMENTED**
`docs/COMPUTATION_AUDIT.md` documents every computed field, formula, data dependency, and business rationale.

---

### IMP-19: Migrate image file paths on vault relocation
**Status**: **IMPLEMENTED**
`catalogStore.ts` (Gallery Viewer) now auto-migrates absolute Windows file paths to Linux paths when loading the catalog. Fixes the ENOENT errors when opening files after vault migration.

---

## Future Features (Schema-Enabled)

### FEAT-1: Detailer Workload Dashboard
**Status**: **PARTIALLY IMPLEMENTED**

### FEAT-2: Novelty Alert System
**Status**: **SPEC WRITTEN** — see `plans/FEAT-2-novelty-alert-system.md`

### FEAT-3: Schedule Conflict Detection
**Status**: **PARTIALLY IMPLEMENTED**

### FEAT-4: Build Date Tracking & Alerts
**Status**: **SPEC WRITTEN** — see `plans/FEAT-4-build-date-tracking.md`

### FEAT-5: Feature Frequency Analysis
**Status**: **SPEC WRITTEN** — see `plans/FEAT-5-feature-frequency-analysis.md`

### FEAT-6: Unit Type Templates
**Status**: **SPEC WRITTEN** — see `plans/FEAT-6-unit-type-templates.md`

### FEAT-7: Checking Status Workflow
**Status**: **PARTIALLY IMPLEMENTED**

### FEAT-8: Variance Tracking
**Status**: **SPEC WRITTEN** — see `plans/FEAT-8-variance-tracking.md`

### FEAT-9: Multi-Location Support
**Status**: **SPEC WRITTEN** — see `plans/FEAT-9-multi-location-support.md`

### FEAT-10: DR/DVL Check Tracking
**Status**: **SPEC WRITTEN** — see `plans/FEAT-10-dr-dvl-check-tracking.md`

### FEAT-11: Historical Trend Analysis
**Status**: **SPEC WRITTEN** — see `plans/FEAT-11-historical-trend-analysis.md`

### FEAT-12: Identical Unit Management
**Status**: **SPEC WRITTEN** — see `plans/FEAT-12-identical-unit-management.md`

### FEAT-13: Remaining Demand Forecasting
**Status**: **SPEC WRITTEN** — see `plans/FEAT-13-remaining-demand-forecasting.md`

### FEAT-14: Tag-Based Smart Search
**Status**: **SPEC WRITTEN** — see `plans/FEAT-14-tag-based-smart-search.md`

### FEAT-15: Automated Status Color Sync
**Status**: **FIXED**
