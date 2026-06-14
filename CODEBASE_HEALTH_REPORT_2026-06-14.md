# Unit Tracker v2 — Codebase Health Report

**Date:** 2026-06-14
**Scope:** Full codebase review, test execution, document audit, breakage analysis
**Source:** `Schedule-Viewer-App-v2/` on external drive

---

## 1. Executive Summary

The Unit Tracker v2 codebase is in **good health**. 224 tests pass cleanly. The architecture has evolved from the v1 Excel-centric model to a SQLite-backed PyQt5 application with multi-user sync infrastructure. The business roadmap (27 plans, synthesized into `BUSINESS-ROADMAP-2026.md`) is well-structured and has already been through a rigorous critique pass.

**Key finding:** The codebase is solid for its current stage (Sprint 1-2 complete). The main risks are in the multi-user sync layer (untested against real network shares) and the import pipeline (no diff/staging UI yet). The roadmap correctly front-loads the independent, high-value work.

---

## 2. Business Roadmap Review

### 2.1 Roadmap Quality: Strong

`BUSINESS-ROADMAP-2026.md` is the synthesized execution plan derived from 27 individual plan documents + the deep critical analysis in `PLAN-REVIEW-DEEP-2026-06-13.md`. It's well-structured:

- **Immediate Wins (Weeks 1-8):** Data safety, CI, property tests, SQLite indexing — all independent, all high-value
- **Q1 Foundation (Weeks 9-20):** Service layer extraction, validation layer — the critical path
- **Q2 Productivity (Weeks 21-32):** Bulk ops, inline edit, audit UI, performance
- **Q3 Advanced (Weeks 33-44):** Predictive analytics, Gantt
- **Q4 Platform (Weeks 45-52):** REST API, real-time presence (conditional)

### 2.2 Critique Response: Mostly Aligned

The roadmap already incorporates the deep critique's key recommendations:

| Critique Finding | Roadmap Response | Status |
|---|---|---|
| ARCH-001 extraction order backwards | UnitService first in Sprint 3 | ✅ Addressed |
| percent_complete scale bug | P0 in Sprint 1 (1 day) | ✅ Addressed |
| No audit log | Sprint 2, P0 (3 days) | ✅ Addressed |
| OT overkill for real-time | Replaced with field-level locks | ✅ Addressed |
| Plugin system premature | Deferred | ✅ Addressed |
| MOC-C thresholds arbitrary | Phase 1 only, data-driven thresholds later | ✅ Addressed |
| No pre-import backup | Sprint 1, P0 (1 day) | ✅ Addressed |
| Missing WAL mode | Sprint 1, P1 (0.5 day) | ✅ Addressed |

### 2.3 Roadmap Gaps / Risks

1. **No v1→v2 migration plan.** The roadmap assumes SQLite is already populated. The `migrate_workbook_to_sqlite.py` script exists but isn't referenced in the roadmap. If this is a one-time migration, it should be a Sprint 0 task.

2. **No performance baselines documented.** Sprint 9 targets "10x improvement" but the roadmap doesn't say what we're measuring against. The `test_reload_performance.py` test checks 1000 rows < 1s, but there's no baseline for the current 2765-unit load.

3. **Conditional features need decision gates.** The API (Sprint 13-14) and real-time presence (Sprint 15) are marked "conditional" but there's no defined decision process or timeline for making the go/no-go call.

4. **No user research validation.** FEAT-016 (real-time), FEAT-020 (API), and the Gantt view all have technical specs but no user validation plan. The roadmap should include: "Show read-only Gantt to 3 detailers, measure usage, decide on interaction layer."

---

## 3. Codebase Architecture Review

### 3.1 Module Structure

```
main.py              — Entry point, config loading, startup backup
config.yaml          — Runtime configuration
data/
  models.py          — Unit dataclass, status color logic, alert levels
  db.py              — SQLite connection, schema migration, audit log, backup
  loader.py          — Load units from SQLite, fingerprinting, identicals
  writer.py          — Save units with validation + optimistic locking
  tag_parser.py      — Description parsing, novelty detection
gui/
  main_window.py     — Main window, workers, save/load orchestration
  list_panel.py      — Sortable/filterable table with column defs
  edit_form.py       — Unit editor with validation + dirty tracking
  calendar_panel.py  — Calendar view with status dots
  alert_panel.py     — Per-detailer alert dashboard
  timeline_panel.py  — Milestone visualization
  theme.py           — Light/dark/CVD/high-contrast theming
  onboarding.py      — First-launch walkthrough
  conflict_dialog.py — Optimistic lock conflict resolution
  due_date_changed_dialog.py — Due date change notification
  import_preview_dialog.py   — Import diff/staging (UI exists)
  sync_status.py     — Sync progress widget
  pivot_chart.py     — Scheduling dashboard charts
  a11y_dialog.py     — Accessibility settings
  loading_overlay.py — Loading spinner
  close_progress_dialog.py — Close-with-sync progress
sync/
  lock_manager.py    — File-based locking for shared drives
  revision_store.py  — Per-COM revision tracking
  session_registry.py — Heartbeat/presence detection
  shared_cache.py    — Per-COM shared state cache
automation/
  import_csv.py      — CSV import pipeline
  import_atomsvc.py  — SSRS online import
  export_to_workbook.py — Excel export
  create_db.py       — Database initialization
scripts/
  benchmark.py       — Performance benchmarks
  doc_check.py       — Documentation freshness check
  ensure_detailers.py — Detailer table maintenance
  migrate_workbook_to_sqlite.py — v1→v2 migration
```

### 3.2 Architecture Assessment

**Strengths:**
- Clean separation: data layer (models/db/loader/writer) is independent of GUI
- SQLite backend is well-designed: WAL mode, schema migration, indexes, audit log
- Multi-user sync infrastructure is thoughtful: file locks, revision store, session registry, shared cache
- Validation is layered: writer-level (hard blocks) + form-level (visual feedback)
- Theme system supports CVD modes and high contrast
- Test coverage is broad: 224 tests across models, writer, loader, audit, sync, UI, performance

**Concerns:**
- `main_window.py` is 1383 lines — the God class problem the roadmap identifies. ARCH-001 (service layer extraction) is the right fix.
- `list_panel.py` is 1126 lines — same issue. The UnitListModel class is well-extracted but the widget itself is large.
- The sync module (`lock_manager.py`, `revision_store.py`, `session_registry.py`, `shared_cache.py`) is designed for Excel file sharing but the app now uses SQLite. The sync layer needs a SQLite-specific path.
- `import_preview_dialog.py` exists but the roadmap's FEAT-019 (Advanced Import Pipeline) is still in progress. The diff/staging logic needs to be wired up.

### 3.3 Data Flow

```
SQLite → db.py (row_to_unit) → loader.py (load_units + identicals) → Unit dataclass
                                                                    ↓
GUI panels ← units list ← MainWindow
    ↓
edit_form.py (user edits) → writer.py (save_unit) → SQLite
                                    ↓
                              audit log (_audit_log table)
```

The flow is clean. The main complexity is in MainWindow's worker threads (LoadWorker, SaveWorker) and the multi-user sync coordination.

---

## 4. Test Results

### 4.1 Summary: 224 Passed, 0 Failed

| Test File | Tests | Status |
|---|---|---|
| test_models.py | 20 | ✅ All pass |
| test_writer.py | 11 | ✅ All pass |
| test_loader.py | 8 | ✅ All pass |
| test_audit.py | 9 | ✅ All pass |
| test_tag_parser.py | 14 | ✅ All pass |
| test_list_panel.py | 28 | ✅ All pass |
| test_edit_form.py | 12 | ✅ All pass |
| test_calendar_panel.py | 8 | ✅ All pass |
| test_close_progress_dialog.py | 13 | ✅ All pass |
| test_theme.py | 18 | ✅ All pass |
| test_sync.py | 2 | ✅ All pass |
| test_sync_status.py | 8 | ✅ All pass |
| test_multi_user_integration.py | 12 | ✅ All pass |
| test_property.py | 5 | ✅ All pass |
| test_reload_performance.py | 1 | ✅ All pass |
| test_contrast_audit.py | (included in count) | ✅ All pass |
| test_imports.py | (included in count) | ✅ All pass |

**Note:** `hypothesis` was missing from the venv. Installed it before running. This should be added to `requirements.txt` or `pyproject.toml` dependencies.

### 4.2 Test Coverage Gaps

1. **No GUI integration tests.** The roadmap's QA-002 plan calls for QTest-based UI tests (select unit → edit form populates, edit → save → table updates, etc.). These don't exist yet.

2. **No fuzz testing.** QA-003 (fuzz testing for CSV, tags, dates) is not implemented.

3. **No benchmark regression suite.** QA-004 (performance benchmarks with CI gate) is not implemented. The `test_reload_performance.py` test exists but there's no CI integration or historical tracking.

4. **Import pipeline untested.** `automation/import_csv.py` has no unit tests. The import preview dialog has no tests.

5. **Export untested.** `automation/export_to_workbook.py` has no tests.

---

## 5. Document Audit

### 5.1 Documents Reviewed

| Document | Status | Notes |
|---|---|---|
| `BUSINESS-ROADMAP-2026.md` | ✅ Current | 287 lines, well-structured, incorporates critique |
| `PLAN-REVIEW-DEEP-2026-06-13.md` | ✅ Current | 1130 lines, comprehensive critique of all 27 plans |
| `docs/COMPUTATION_AUDIT.md` | ✅ Current | Complete catalog of computed fields, data flow diagram |
| `docs/ONBOARDING_STEPS.md` | ✅ Current | 15-step walkthrough, feature coverage matrix |
| `code_review_report.md` | ⚠️ Stale | From June 8 — references bugs BUG-14 through BUG-25, status unclear |
| `tag_review.md` | ⚠️ Reference | Used by tag_parser.py whitelist, should be in docs/ |
| `agents.md` | ⚠️ Unclear | Purpose unclear — may be AI agent instructions |
| `README-Windows.md` | ⚠️ Needs review | Not read in full, may need updates for v2 |
| `pyproject.toml` | ✅ Current | Well-configured with ruff, mypy, pytest |
| `config.yaml` | ✅ Current | Runtime configuration |

### 5.2 Document Updates Needed

1. **`COMPUTATION_AUDIT.md`** — Last updated 2026-06-08. Needs update for:
   - `working_days_in_checking` recomputed on save (writer.py line 115-118)
   - Audit log fields (new since original audit)
   - `alert_level` property (used by list panel filtering)

2. **`ONBOARDING_STEPS.md`** — Last updated 2026-06-06. Needs update for:
   - Notes field in edit form (listed as 18 fields but notes may not be counted)
   - Alert filter in list panel
   - Column width persistence

3. **`code_review_report.md`** — Needs status update. The 4 open bugs from June 8 should be verified against current code.

4. **`tag_review.md`** — Should be moved to `docs/` for consistency.

5. **`agents.md`** — Should be reviewed and either updated or removed.

---

## 6. Breakage Analysis

### 6.1 Recent Changes Assessment

Based on the codebase state, the following significant changes have been made since the initial build:

**Sprint 1 (Complete):**
- ✅ SQLite indexes added (`db.py` migration)
- ✅ WAL mode enabled (`db.py`)
- ✅ Pre-import backup (`db.py` `backup_db()`)
- ✅ percent_complete validation (`writer.py` `_validate_unit()`)
- ✅ Audit log system (`db.py` `_ensure_audit_log`, `log_field_changes`, `get_audit_trail`)
- ✅ Inline field validation (`edit_form.py` `_validate_fields()`)
- ✅ Date order validation (`edit_form.py`)

**Sprint 2 (Complete):**
- ✅ Audit log write path (`writer.py` saves audit on every save)
- ✅ Import safety: diff + staging (partially — dialog exists, pipeline not fully wired)
- ✅ Startup backup with retention policy (`main.py` `_startup_backup()`)

### 6.2 Potential Breakage Areas

1. **`percent_complete` scale conversion.** The writer divides by 100 on save (`writer.py` line 103) and the loader multiplies by 100 on load (`db.py` line 303). This is correct but fragile. If any code path writes to SQLite without going through `writer.py`, the scale will be wrong. **Risk: Medium.** The `import_csv.py` path needs verification.

2. **`working_days_in_checking` recomputation.** The writer recomputes this on every save from `unit_moved_to_checking_date` and `unit_detailing_completion_date`. If these dates are null, the column is set to null. This is correct but means any manual DB edits to `working_days_in_checking` will be overwritten on the next save. **Risk: Low.**

3. **Optimistic locking.** The `updated_at` check in `writer.py` (lines 66-72) will fail if the DB row has no `updated_at` value (legacy data). The fallback to unlocked mode is correct but means legacy data won't get conflict protection. **Risk: Low.** Should be addressed by a migration that sets `updated_at` for all existing rows.

4. **Audit log table name.** The audit table is `_audit_log` (with underscore prefix). This is intentional (hidden from casual queries) but could cause confusion. The `FEAT-021` plan references `_audit_log` and `MOC-A` references `change_log` — these are the same table. **Risk: Low.** Already aligned in code.

5. **Sync module vs SQLite.** The sync module (`lock_manager.py`, `revision_store.py`, etc.) is designed for Excel file-based sharing. With SQLite as the backend, the sync layer needs a different approach (SQLite handles concurrent access via WAL). The file locks are still useful for cross-process coordination but the revision store and shared cache may be redundant with SQLite's own concurrency. **Risk: Medium.** Should be addressed before multi-user deployment.

6. **`hypothesis` missing from dependencies.** Property tests require `hypothesis` but it's not in `pyproject.toml` or `requirements.txt`. **Risk: Low.** Easy fix — add to dev dependencies.

### 6.3 No Critical Breakage Found

All 224 tests pass. The data flow from SQLite → Unit → GUI → save → SQLite is intact. The audit log system works end-to-end. The validation layer correctly blocks invalid data.

---

## 7. Recommendations

### 7.1 Immediate (This Week)

1. **Add `hypothesis` to dev dependencies** in `pyproject.toml`
2. **Verify `import_csv.py` percent_complete scale** — ensure it stores as 0-1 decimal, not 0-100
3. **Set `updated_at` for legacy rows** — migration to populate `updated_at` for rows where it's null
4. **Update `COMPUTATION_AUDIT.md`** — add audit log fields, alert_level, working_days_in_checking recompute

### 7.2 Sprint 3 Preparation (Service Layer)

5. **Start ARCH-001 extraction** — UnitService first, as the roadmap specifies. The current `main_window.py` (1383 lines) is the bottleneck.
6. **Define the SQLite sync path** — decide whether the file-based sync module is still needed or if SQLite WAL mode + optimistic locking is sufficient for multi-user.

### 7.3 Documentation

7. **Move `tag_review.md` to `docs/`**
8. **Update `ONBOARDING_STEPS.md`** for recent UI changes
9. **Review and update `code_review_report.md`** — verify BUG-14 through BUG-25 status
10. **Add migration plan to roadmap** — v1→v2 data migration as Sprint 0

---

## 8. Conclusion

The Unit Tracker v2 codebase is healthy, well-tested, and on track with the roadmap. The architecture is sound for the current stage. The main work ahead is:

1. **Service layer extraction** (ARCH-001) — the critical path for everything else
2. **Import pipeline completion** (FEAT-019) — the highest-risk data operation
3. **Test coverage expansion** — GUI integration tests, import/export tests, fuzz testing
4. **Documentation maintenance** — keep audit and onboarding docs in sync with code

The business roadmap is well-structured and the critique pass was thorough. The execution plan is realistic for a single developer over 27+ weeks.

---

*Report generated by Rook — 2026-06-14*
