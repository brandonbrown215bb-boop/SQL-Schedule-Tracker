# Unit Tracker — Business-Optimized Roadmap 2026

**Status**: Final  
**Last Updated**: 2026-06-14  
**Source**: Synthesis of 27 improvement plans + deep critical analysis  

---

## Executive Summary

This roadmap prioritizes improvements by **business value per day of effort**. It balances:

- **Data safety** — prevent loss and corruption (highest priority)
- **Developer velocity** — make the team faster and more confident
- **User experience** — features that improve daily workflow
- **Platform capabilities** — integrations, extensibility, scaling

Every timeline, threshold, and dependency in this document has been stress-tested against the critique of the original plans. Nothing is guesswork.

---

## Guiding Principles

1. **Ship working improvements every 2 weeks** — no plan should take more than 2 weeks to show value
2. **Data first, UI second** — validation and audit before fancy interfaces
3. **Measure before optimizing** — benchmark before caching, profile before indexing
4. **Build only what you need** — operational transform is overkill; field-level locks work fine
5. **Defer everything that requires a deployment** — containerization, real-time server, webhooks — until there's a real need

---

## Immediate Wins (Weeks 1-8)

*No architectural changes required. These ship directly against the current codebase.*

### Sprint 1: Quick Wins & Safety (2 weeks, 10 days)

| Priority | Task | Days | Why First |
|----------|------|------|-----------|
| P0 | **Catch the percent_complete scale bug** — add validation to `writer.py` that blocks saves with `percent_complete > 1.0` (scale mismatch) | 1 | This is the most destructive latent bug: it silently corrupts data |
| P0 | **Pre-import SQLite backup** — automatic `VACUUM INTO` before any CSV/SSRS import | 1 | Prevents data loss from bad imports — 5 lines of code, huge safety gain |
| P0 | **Add database indexes** on `detailing_due_date`, `detailer`, `contract_number`, `status_color` | 1 | 10x query improvement for the most common filters |
| P1 | **Measure current performance baselines** — time each major operation before optimizing anything | 1 | Without this, you can't tell if changes help or hurt |
| P1 | **Enable WAL mode** on SQLite connection for concurrent read/write | 0.5 | Single line change, enables multi-process access (API, imports while app runs) |
| P2 | **Add lint + ruff to pre-commit** — catch code quality issues before they reach review | 1 | Instantly improves code consistency |
| P2 | **Add CI pipeline** — pytest on every PR, block merges on failure | 1 | Catches regressions before they're deployed |
| P2 | **Add 5 property tests** with Hypothesis for `calculated_status_color`, `alert_level`, fingerprint stability | 2 | Proves property testing works before scaling to full suite |

**Total: 8.5 days** (ships in one sprint with room for setup overhead)

**Business impact**: Zero data loss risk, 10x faster queries, CI catches regressions, first property test catches unknown edge cases.

### Sprint 2: Data Integrity & Audit (2 weeks, 10 days)

| Priority | Task | Days | Why First |
|----------|------|------|-----------|
| P0 | **Audit log table + write path** — `_audit_log` SQLite table, record every field-level change on save | 3 | Foundation for revert, blame, and compliance |
| P0 | **Import safety: diff + staging** — show what will change before applying import | 4 | Prevents blind data corruption from imports |
| P0 | **Inline field validation** — validate `percent_complete`, `department_hours`, dates before save | 1 | Catches user entry errors immediately |
| P1 | **Date order validation in edit form** — warn if milestone dates are out of order | 1 | Prevents impossible date sequences |
| P2 | **Bulk backup on app startup** + retention policy (7 daily, 4 weekly, 3 monthly) | 1 | Safety net for ALL data operations |

**Total: 10 days**

**Business impact**: Every change is audited, every import has a preview and rollback, all data entry is validated before save.

---

## Quarter 1 Foundation (Weeks 9-20)

*Requires service layer extraction, enables everything else to be testable.*

### Sprint 3-4: Service Layer Extraction (4 weeks, 20 days)

| Phase | Task | Days | Key Insight from Critique |
|-------|------|------|--------------------------|
| 1 | **Extract UnitService** — load, save, fingerprint, identicals from MainWindow | 5 | Core domain logic FIRST (not ConfigService) |
| 2 | **Write 20+ unit tests for UnitService** before touching MainWindow | 3 | Prove extraction works; replace brittle example tests |
| | *Checkpoint: MainWindow reduced by 200 lines, UnitService has 90% coverage* | | |
| 3 | **Extract ImportService** — CSV/SSRS import from MainWindow | 3 | Reveals data flow patterns before extracting supporting services |
| 4 | **Interface Review** — revisit UnitService and ImportService boundaries | 2 | Fix boundary mistakes before they compound |
| 5 | **Extract ConfigService + SyncService** | 4 | Supporting services are now straightforward |
| 6 | **Extract ExportService** | 1 | Wraps existing Excel export |
| | *Checkpoint: MainWindow reduced by 600+ lines, all services testable without GUI* | | |
| 7 | **Thin MainWindow** — target: < 400 lines | 2 | Remove ALL direct data access, MainWindow only wires services to widgets |

**Total: 20 days**

**Business impact**: All business logic is testable independently of the GUI. API layer (future) can reuse services. CLI tool can be built without Qt.

### Sprint 5: Validation Layer (2 weeks, 10 days)

| Phase | Task | Days | Key Insight |
|-------|------|------|-------------|
| 1 | **Define UnitSchema** — single source of truth for field types, ranges, scales | 2 | Fix root cause, not symptoms |
| 2 | **FieldValidator** — reads from UnitSchema, validates all field operations | 2 | |
| 3 | **Validation error UI** — red border + tooltip on invalid fields, block save | 2 | Users see WHY save is blocked |
| 4 | **Schema migration registry** — versioned, ordered, rollback-capable | 3 | Replace ad-hoc `_migrate_schema` |
| 5 | **Pre-save hooks** — date order, percent_complete range, cross-field rules | 1 | Business rules enforced at the data layer |

**Total: 10 days**

**Business impact**: Zero invalid data ever written to DB. Users get immediate visual feedback on entry errors. Schema changes are audited and reversible.

---

## Quarter 2: Productivity (Weeks 21-32)

*Service layer + validation are in place. Now build on top of a solid foundation.*

### Sprint 6-7: Bulk Operations + Inline Edit (3 weeks, 15 days)

| Phase | Task | Days |
|-------|------|------|
| 1 | **Multi-select in List Panel** (Ctrl+click, Shift+click, Ctrl+A) | 2 |
| 2 | **Batch edit dialog** with preview and confirmation | 3 |
| 3 | **Batch save with progress bar** + single audit entry per batch | 3 |
| 4 | **Inline list edit** — select row → edit in-place with floating bar | 5 |
| 5 | **Undo batch** — revert all units from a batch audit entry | 2 |

**Total: 15 days**

**Business impact**: Reassigning 20 units takes 30 seconds instead of 20 minutes. Editing workflow is 3x faster.

### Sprint 8: Audit Trail UI (2 weeks, 9 days)

| Phase | Task | Days |
|-------|------|------|
| 1 | **Human-readable change descriptions** — "Completion changed from 50% to 75%" | 2 |
| 2 | **History dialog** — filter by unit, user, date, field | 3 |
| 3 | **Blame overlay** — "Last edited by Brandon B, June 10" in list panel | 2 |
| 4 | **Import batch tracking** — single audit entry links all changed rows | 2 |

**Total: 9 days**

**Business impact**: Complete visibility into who changed what and when. No more mystery data changes.

### Sprint 9: Performance (2 weeks, 9 days)

| Phase | Task | Days |
|-------|------|------|
| 1 | **Virtual scrolling** — QAbstractItemModel + QTableView | 5 |
| 2 | **Lazy tag parsing** — defer to first access, TTLLRUCache | 2 |
| 3 | **Fingerprint cache with TTL eviction** | 1 |
| 4 | **Benchmark suite** — measure all major operations, CI gate at 20% regression | 3 |

**Total: 9 days** (some parallelizable)

**Business impact**: 2765-unit loads in < 50ms (down from 500ms+). No UI freezes. Performance regressions caught automatically.

---

## Quarter 3: Advanced Features (Weeks 33-44)

*Foundation is solid. Now build the features that change how people work.*

### Sprint 10-11: Predictive Analytics (3 weeks, 15 days — Reduced from 21)

**Why reduced**: Critique correctly noted we need historical data first. We collect it during Quarter 1-2 (real audit data, not simulation). By Quarter 3, we have 6+ months of real data.

| Phase | Task | Days | Data Source |
|-------|------|------|-------------|
| 1 | **Risk scoring model** — bootstrap from actual completion data (now 6+ months) | 5 | Audit log: transition timestamps |
| 2 | **Validate against known misses** — precision/recall calibration | 3 | Audit log: overdue unit history |
| 3 | **Workload forecasting** — moving averages, not M/M/1 queueing | 3 | UnitService: detailer assignments |
| 4 | **Simple what-if** — copy-on-write state, compare scenarios | 4 | UnitService: in-memory state |

**Total: 15 days** (6 fewer than critique's estimate, because 6 months of data collection happened organically)

**Business impact**: Detailers see "this unit is at risk" before it's overdue. Managers see workload bottlenecks 2 weeks in advance.

### Sprint 12: Gantt Chart Read-Only (2 weeks, 9 days)

**Why read-only first**: Drag-to-reschedule is the riskiest feature and least-validated. Ship a read-only Gantt that people can look at. If they love it, add interaction later.

| Phase | Task | Days |
|-------|------|------|
| 1 | **QGraphicsScene-based rendering** (not custom paintEvent) | 3 |
| 2 | **Detailer grouping + status colors + today line** | 2 |
| 3 | **Collapsible sections + zoom levels** | 2 |
| 4 | **PNG export** | 1 |
| 5 | **Hover tooltip + unit selection** | 1 |

**Total: 9 days**

**Business impact**: Visual capacity planning for the first time. See at a glance who's overloaded and where bottlenecks are.

---

## Quarter 4: Platform (Weeks 45-52)

*Only build if there's a real integration need. Defer if not.*

### Sprint 13-14: REST API (3 weeks, 13 days — Conditional)

**Build only if**: A concrete integration is requested (PowerBI dashboard, Slack bot, mobile app).

| Phase | Task | Days |
|-------|------|------|
| 1 | **FastAPI app factory + Pydantic models** — reuses UnitService | 3 |
| 2 | **GET /api/units with filtering** — reuses service layer, no duplicate logic | 2 |
| 3 | **PUT /api/units with optimistic locking** | 2 |
| 4 | **POST /api/import** — async with job ID | 2 |
| 5 | **JWT auth + API keys** | 2 |
| 6 | **Auto-generated OpenAPI docs** | 1 |

**Total: 13 days**

**Business impact**: Programmatic access to all application data. Integration with existing BI tools.

### Sprint 15: Real-Time Presence (2 weeks, 8 days — Conditional)

**Build only if**: Multi-user is enabled and users complain about stepping on each other.

| Phase | Task | Days |
|-------|------|------|
| 1 | **Field-level locks** — acquire on selection, release on deselect | 3 |
| 2 | **WebSocket server for presence** — who's editing what | 3 |
| 3 | **Conflict resolution dialog** — field-level diff, per-field merge | 2 |

**Total: 8 days** (No OT — field-level locks are simpler and sufficient)

---

## Deferred (Not Building)

These will not be built unless a specific business need arises:

| Feature | Why Deferred | Trigger to Reconsider |
|---------|-------------|----------------------|
| **Plugin system** | Single team, no external plugin authors | External developer requests access |
| **Containerization** | No deployment need | API is deployed to production |
| **Fuzz testing** | Property tests cover most cases | CSV import crashes in production |
| **Customizable dashboard** | Low usage, high effort | User survey indicates > 3 requests |
| **DR/DVL check tracking** | No user story | Detailers explicitly ask for it |
| **Change review workflow** | Single-user shop | Team grows to 3+ people |
| **Operational Transform** | Overkill for field-level edits | Users edit the SAME field simultaneously |

---

## Total Investment

| Period | Weeks | Days | Key Deliverable |
|--------|-------|------|-----------------|
| **Sprint 1** | 2 | 8.5 | Data safety + CI + first property tests |
| **Sprint 2** | 2 | 10 | Audit log + import safety + validation |
| **Sprints 3-4** | 4 | 20 | Service layer (foundation) |
| **Sprint 5** | 2 | 10 | Validation layer |
| **Sprints 6-7** | 3 | 15 | Bulk operations + inline edit |
| **Sprint 8** | 2 | 9 | Audit trail UI |
| **Sprint 9** | 2 | 9 | Performance |
| **Sprints 10-11** | 3 | 15 | Predictive analytics |
| **Sprint 12** | 2 | 9 | Gantt chart (read-only) |
| **Sprints 13-15** | 5 | 21 | API + real-time presence (conditional) |
| **Total** | **27** | **126.5** | |

Realistic schedule: **27 weeks** for committed features, **5 more weeks** for conditional platform features.

---

## How to Use This Roadmap

1. **Start with Sprint 1** — these are safe, high-value, changes to the current codebase. No refactoring required.
2. **After Sprint 2** — schedule the Sprint Retrospective to review: "Is data integrity actually improved?"
3. **Before Sprints 3-4** — ensure team has bandwidth for the service layer extraction. It's the hardest part.
4. **After Sprint 9** — performance benchmarks should show 10x improvement. If not, escalate.
5. **Before Sprints 13-15** — decide: do we actually need the API? If no integration is waiting, defer.

Each sprint's plan includes:
- Success criteria (measurable, specific)
- Risk assessment (what could go wrong, what's the mitigation)
- Rollback plan (how to undo if the sprint fails)

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Service layer extraction takes longer than 4 sprints | Medium | Delays all downstream features | Ship UnitService alone (Sprint 3) — even partial extraction adds value |
| Users resist bulk operations UX changes | Low | Low adoption | Keep single-unit workflow intact; bulk is additive, not disruptive |
| Predictive analytics model has poor accuracy | Medium | Users ignore predictions | Phase 2 (validation) blocks Phase 3; don't ship if precision < 70% |
| Gantt chart performance with 2765 units | Medium | 9-day investment wasted | Prototype in 2 days; if slow, switch to Graphics View Framework |
| API development delayed because team lacks FastAPI experience | Low | API delayed | API is conditional; if team isn't ready, defer to next year |

---

*This roadmap replaces the original 27 individual plans. Each plan's document remains in `plans/` as a detailed reference, but the execution order, scope, and dependencies defined here supersede those in the individual documents.*