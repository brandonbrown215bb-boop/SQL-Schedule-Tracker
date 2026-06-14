# Deep Critical Analysis: Individual Plan Markup

*Each plan gets: (1) What's wrong, (2) What's missing, (3) The better version.*

---

## ARCH-001: Service Layer Extraction

### Critique

**The good:** The problem statement is the strongest in the entire backlog. A 1378-line God class is a real, measurable problem. The phased approach is sensible. The service interfaces are well-defined.

**What's wrong:**

1. **The extraction order is backwards.** ConfigService is Phase 1 because it's "easy" — but it's not the highest-value extraction. UnitService (Phase 2) is the one that every other service depends on. Extract the core domain logic first, the supporting services after. You'll learn the most from the hardest extraction and apply those lessons to the easier ones.

2. **No mention of the existing test suite.** The plan says "all existing tests pass without modification" as a success criterion, but the existing tests are example-based and test through the GUI. After extraction, those tests should be *replaced* with service-level unit tests. The plan treats the existing tests as sacred when they're actually technical debt.

3. **"Thin MainWindow" is Phase 6 — too late.** Every phase should leave MainWindow thinner. If you extract ConfigService in Phase 1 but MainWindow still has 1350 lines, you've learned nothing about whether your service boundaries are right. Each phase should reduce MainWindow by 200+ lines.

4. **No interface versioning strategy.** The service interfaces are defined once, up front. In practice, you'll discover the wrong boundaries after 3 extractions. The plan needs an explicit "interface iteration" step after Phase 3 where you revisit the first two services.

5. **The 23-day estimate is naive.** It assumes each phase is independent with no rework. In reality, Phase 2 will reveal that Phase 1's ConfigService interface is wrong. Budget 30% rework time.

### The Better Version

```
Phase 1: UnitService (5 days) — the core. Everything depends on this.
  - Extract load/save/fingerprint/identicals from MainWindow
  - Write 20+ unit tests for UnitService BEFORE touching MainWindow
  - Reduce MainWindow by 200 lines

Phase 2: ImportService (4 days) — reveals data flow patterns
  - Extract CSV/SSRS import
  - Write integration tests with mock HTTP
  - Reduce MainWindow by 150 lines

Phase 3: Interface Review (2 days) — iterate on what you learned
  - Revisit UnitService and ImportService interfaces
  - Fix boundary mistakes before they compound

Phase 4: ConfigService + SyncService (5 days) — supporting services
  - Now that the core is stable, extract the supporting cast
  - Reduce MainWindow by 200 lines

Phase 5: ExportService (2 days) — straightforward after the above

Phase 6: Thin MainWindow (5 days) — now it's actually thin
  - Target: < 400 lines (not 600)
  - Remove all direct data access from MainWindow
  - MainWindow should only create services and wire signals

Total: 23 days (same estimate, better sequencing)
```

---

## ARCH-002: Centralized State Management

### Critique

**The good:** Observer pattern + Command pattern is the right architecture. The event type constants are well-defined. The undo/redo design is sound.

**What's wrong:**

1. **The AppState dataclass is a God object in disguise.** It has `units`, `current_unit`, `form_dirty`, `io_busy`, `last_error`, `ui`, `sync` — that's the same problem as MainWindow, just moved to a different class. The state should be split into domain state (units, current_unit), UI state (filters, view, theme), and runtime state (io_busy, errors). Each with its own event stream.

2. **No migration strategy for existing code.** The plan says "migrate CalendarPanel, ListPanel, EditForm, TimelinePanel, AlertPanel" in Phase 3. That's 5 panels in 5 days — one per day. That's not enough time per panel. Each panel has dozens of direct state accesses that need to be converted to subscriptions. Budget 2 days per panel minimum.

3. **The Command pattern is over-engineered for the current needs.** The plan defines `SelectUnitCommand`, `SaveUnitCommand`, `BatchEditCommand` — but the app currently only has single-unit edits. Start with a simple `set()` method for state mutations and add the Command pattern only when you actually need undo/redo. YAGNI.

4. **"State persistence" (Phase 4) is an afterthought.** It should be built in from Phase 1. If the state dataclass isn't serializable from day one, you'll discover in Phase 4 that some state can't be serialized (Qt widget references, file handles, etc.).

5. **No performance analysis.** The event bus emits on every state mutation. With 2765 units, a full reload emits 2765+ events. The plan mentions "debounce/throttle" in the risk assessment but doesn't design the solution. This will be a performance regression.

### The Better Version

```
Phase 1: Split State + Event Bus (4 days)
  - Three state domains: DomainState (units), UIState (view, filters), RuntimeState (io_busy)
  - Event bus with batch emission (collect changes, emit once per frame)
  - All state is JSON-serializable from day one
  - Simple set() method, no Command pattern yet

Phase 2: Migrate ListPanel (3 days)
  - ListPanel first because it has the most state dependencies
  - Prove the event-driven model works with the most complex panel
  - Fix performance issues with batch event emission

Phase 3: Migrate remaining panels (6 days)
  - 2 days each: CalendarPanel, EditForm, TimelinePanel, AlertPanel
  - Each migration includes removing direct state access

Phase 4: Undo/Redo via Command pattern (3 days)
  - NOW add the Command pattern, once the event model is proven
  - Implement undo for selection and field edits only
  - Save undo is explicitly excluded (requires DB reverse)

Total: 16 days (3 more, but actually works)
```

---

## ARCH-003: Data Validation Layer

### Critique

**The good:** Fixes a real, existing bug (percent_complete scale mismatch). The four-component architecture is clean.

**What's wrong:**

1. **The percent_complete bug is a symptom, not a disease.** The real problem is that the DB schema and the Python model have no single source of truth. A field's type, range, and scale should be defined *once* and enforced everywhere. The plan adds validation on top instead of fixing the root cause.

2. **No schema versioning strategy.** The plan mentions "SchemaMigrationRegistry" but doesn't define how versions are tracked, how migrations are ordered, or how rollbacks work. This is the hardest part of schema management and it's hand-waved.

3. **"PreSaveHookRegistry" is a band-aid.** Business rules like "target_hours = dept_hours - iec_hours" shouldn't be hooks — they should be computed properties on the Unit model. The plan adds extensibility where there should be correctness.

4. **No validation error reporting to the user.** The plan defines validation rules but doesn't say what happens when validation fails. Does the user see an error? Which field? In what format? Validation without user feedback is just silent data rejection.

### The Better Version

```
Phase 1: Single Source of Truth (3 days)
  - Define a UnitSchema that declares every field's type, range, scale, and DB mapping
  - Generate both the Python dataclass and the CREATE TABLE statement from the schema
  - Fix the percent_complete mismatch at the schema level

Phase 2: Validation + Error Reporting (4 days)
  - FieldValidator that reads from UnitSchema
  - Validation errors returned as structured dicts: {field: [error_messages]}
  - EditForm displays validation errors next to fields (red border + tooltip)
  - Save is blocked until all validation passes

Phase 3: Migration Registry (3 days)
  - Schema version tracked in a `schema_info` table
  - Migrations are numbered, ordered, and idempotent
  - Each migration has an up() and down() function
  - On startup, run pending migrations before any data access

Total: 10 days (same, but fixes the root cause)
```

---

## ARCH-004: Plugin Architecture

### Critique

**The good:** Clean base class hierarchy. Manifest-based discovery. Sandbox concept for external plugins.

**What's wrong:**

1. **This is premature optimization for a team of one.** The plan acknowledges "may not fit small-shop culture" but doesn't answer: who is going to write plugins? If it's just your team, you don't need a plugin system — you need good module boundaries.

2. **The sandbox is a stub.** "Sandboxed plugin loading not yet implemented" is listed as a risk but not resolved. If you're going to claim sandbox support, you need to define the subprocess protocol, the IPC mechanism, and the resource limits. Otherwise cut it.

3. **Plugin dependency resolution is naive.** The plan says "check dependencies and load them first" but doesn't handle circular dependencies, version conflicts, or missing dependencies. This is a graph problem being treated as a list problem.

4. **No plugin lifecycle management.** What happens when a plugin fails to load? When it crashes at runtime? When it's disabled while in use? The plan defines `initialize` and `shutdown` but not error handling.

5. **The "Plugin Marketplace UI" (Phase 4) is 5 days of work for a feature nobody asked for.** Cut it. If plugins exist, a simple enable/disable checkbox list is sufficient.

### The Better Version

```
Phase 1: Internal Plugin Boundaries (3 days)
  - Define ImportPlugin, ExportPlugin, SyncPlugin ABCs
  - Refactor existing import/export to implement these ABCs
  - NO external plugin support yet — just clean internal boundaries

Phase 2: Plugin Manager (2 days)
  - Discovery, loading, error handling
  - Dependency resolution with cycle detection
  - Simple enable/disable in config.yaml (no UI yet)

Phase 3: External Plugin Support (3 days, only if needed)
  - Subprocess isolation with JSON-RPC
  - Resource limits (CPU, memory, filesystem)
  - Only build this if a real external plugin use case exists

Cut: Plugin Marketplace UI (save 5 days)
```

---

## FEAT-016: Real-Time Multi-User Collaboration

### Critique

**The good:** WebSocket + OT is the right technical choice. Presence awareness is well-defined.

**What's wrong:**

1. **Operational Transform is overkill.** OT is designed for Google Docs-style simultaneous editing of the same document. Your app edits *different fields of different units*. You don't need OT — you need optimistic locking with field-level merge. OT adds enormous complexity for a problem that doesn't exist.

2. **The WebSocket server is a new deployment surface.** The plan doesn't address: who hosts it? How is it secured? What happens when it goes down? How do clients discover it? This is an infrastructure project, not a feature.

3. **No conflict resolution UX.** The plan says "conflict-free collaborative editing" but OT doesn't eliminate conflicts — it transforms them. When two users edit the same unit simultaneously, what does the user see? The plan doesn't define the conflict UI.

4. **16 days is optimistic.** WebSocket server + client integration + OT engine + presence + fallback to file-based sync. This is a 30+ day effort for a team that hasn't built real-time systems before.

5. **The fallback strategy is undefined.** "Fallback to file-based sync" is mentioned but not designed. When does fallback trigger? How do you merge state after fallback? This is the hardest part.

### The Better Version

```
Replace OT with field-level optimistic locking:
  - Each field has a version stamp
  - On save, include field-level versions
  - If versions match, save succeeds
  - If versions conflict, show field-level diff and let user choose

Phase 1: WebSocket Server + Presence (5 days)
  - Simple asyncio WebSocket server
  - Broadcast presence (who's online)
  - Broadcast unit locks (who's editing what)

Phase 2: Client Integration (5 days)
  - Connect to WebSocket on startup
  - Show presence indicators in UI
  - Acquire/release locks on unit selection

Phase 3: Field-Level Conflict Resolution (5 days)
  - On save conflict, show field-level diff dialog
  - User chooses: keep mine, take theirs, or merge per-field
  - No OT needed — just version stamps

Cut: Fallback to file-based sync (defer until needed)
Total: 15 days (vs 16, but actually buildable)
```

---

## FEAT-017: Predictive Analytics

### Critique

**The good:** The most technically rigorous spec in the backlog. Monte Carlo simulation, queueing theory, what-if modeling — all well-explained.

**What's wrong:**

1. **The Monte Carlo simulation requires historical completion time data that doesn't exist.** The plan says "sample from historical completion times" but the app doesn't track when units move from "in progress" to "completed." You'd need to add that tracking first, collect weeks of data, *then* build the model. This is a 3-phase project disguised as 1 plan.

2. **The M/M/1 queueing model is wrong for this domain.** M/M/1 assumes Poisson arrivals and exponential service times. Unit arrivals are batched (imports), not Poisson. Service times are determined by unit complexity, not random. A discrete-event simulation would be more accurate and not much harder.

3. **The what-if engine requires a full copy of the application state.** "deep_copy(baseline_state)" works for 2765 units but doesn't scale. And the plan doesn't address: what about units that are being edited by other users while you're running what-if?

4. **No validation strategy.** How do you know the predictions are right? The plan should include: run the model against the last 3 months of actual outcomes, measure precision/recall, calibrate thresholds. Without this, the model is just math with no connection to reality.

5. **The dashboard (Phase 5) is 5 days for 6 chart types.** That's less than 1 day per chart including data binding, layout, and interaction. Not realistic.

### The Better Version

```
Phase 1: Data Collection (3 days)
  - Add completion tracking: when does a unit move to each status?
  - Store historical transition timestamps in a new table
  - Collect 2-4 weeks of data before building models

Phase 2: Risk Scoring (5 days)
  - Bootstrap resampling from actual completion data
  - Validate against known misses from the last 3 months
  - Tune thresholds based on precision/recall

Phase 3: Discrete-Event Simulation (5 days)
  - Replace M/M/1 with DES that models actual arrival patterns
  - Validate against actual queue lengths

Phase 4: What-If Engine (3 days)
  - Copy-on-write state for scenario modeling
  - Compare scenarios side-by-side

Phase 5: Dashboard (5 days)
  - 2 charts per sprint, validated with users
  - Start with risk score + queue length (the two most valuable)

Total: 21 days (vs 16, but actually produces valid predictions)
```

---

## FEAT-018: Gantt Chart View

### Critique

**The good:** Clear mockup. Well-defined widget architecture. Solves real problems (no duration visibility, no overlap detection).

**What's wrong:**

1. **Custom paintEvent is the wrong approach.** The plan defines `GanttWidget` with a custom `paintEvent`. This means every redraw is manual — no accessibility, no screen reader support, no style sheet theming. Use Qt's Graphics View Framework (`QGraphicsScene` + `QGraphicsRectItem`) instead. It gives you hit detection, selection, drag-and-drop, and accessibility for free.

2. **"Replaces calendar panel" is a non-decision.** The plan says "opt-in" in the header but "remove or deprecate calendar panel" in Phase 4. Which is it? If Gantt is better, replace it. If calendar has unique value, keep both. Decide now.

3. **Drag-to-reschedule is the riskiest feature and it's in Phase 2.** The plan should start with read-only rendering (Phase 1), add filtering/grouping (Phase 2), then add interaction (Phase 3). Shipping a read-only Gantt that people can look at is better than shipping a broken drag-and-drop.

4. **No virtual scrolling.** The plan doesn't address performance with 2765 units. A custom paintEvent that draws 2765 rectangles will be slow. The Graphics View Framework handles this with `QGraphicsView`'s viewport update modes.

5. **Dependency lines are under-specified.** "Arrows showing identical unit relationships" — what about units that span different detailers? What about units with no start date? The routing algorithm for dependency lines is a research problem, not a 1-day task.

### The Better Version

```
Phase 1: Read-Only Gantt with Graphics View (5 days)
  - QGraphicsScene-based rendering
  - One rectangle per unit, color-coded by status
  - Detailer grouping with collapsible sections
  - Virtual scrolling via QGraphicsView
  - Today line overlay

Phase 2: Interaction (4 days)
  - Hover tooltip with unit details
  - Click to select (wires into existing unit_selected signal)
  - Detailer filter + zoom levels

Phase 3: Drag-to-Reschedule (4 days)
  - Drag bar endpoints to change dates
  - Validation: can't drag past build date, can't drag to stale
  - Confirmation dialog with impact preview (hooks into MOC-B)

Phase 4: Dependency Lines + Export (2 days)
  - Simple horizontal routing for same-detailer dependencies
  - PNG export via QPixmap.grab()

Decision: Keep calendar panel as a separate view. Gantt replaces it for
capacity planning but calendar is better for "what's due today" scanning.
```

---

## FEAT-019: Advanced Import Pipeline

### Critique

**The good:** Diff viewer, staging, rollback, scheduling — all critical safety features. Well-phased.

**What's wrong:**

1. **The diff viewer compares staging vs. live, but what about the *current* state?** If a user has made manual edits after the last import, the diff should show: import changes + manual changes vs. current DB. The plan only handles import-vs-DB.

2. **Rollback stores "reverse SQL" — this is fragile.** If the schema changes, the reverse SQL breaks. Store the pre-change row state (JSON) instead. Rollback = re-insert the old row state. Schema-version-independent.

3. **The scheduler uses QTimer which requires the app to be running.** If the app is closed at 2 AM when the scheduled import fires, it misses the window. For a scheduling tool, this is a critical gap. Use the OS scheduler (cron/Task Scheduler) for reliability, with QTimer as a fallback for "every N minutes while running."

4. **The webhook endpoint is a separate process but the plan doesn't say how it shares the DB.** If the webhook triggers an import while the GUI is running, you have two processes writing to the same SQLite file. SQLite handles this with WAL mode, but the plan doesn't mention it.

5. **No import validation beyond schema.** The plan should include: duplicate detection, referential integrity (does the detailer exist?), and business rule validation (is the due date in the past?).

### The Better Version

```
Phase 1: Diff Viewer + Staging (5 days)
  - Three-way diff: import vs. DB vs. current in-memory state
  - Color-coded: added (green), modified (yellow), removed (red), conflict (orange)
  - Side-by-side field-level comparison

Phase 2: Rollback (2 days)
  - Store pre-change row state as JSON, not reverse SQL
  - Rollback = restore old row state + re-save
  - Schema-version-independent

Phase 3: Validation (2 days, NEW)
  - Duplicate detection (same COM number)
  - Referential integrity (detailer exists, contract exists)
  - Business rules (due date not in past, hours non-negative)
  - Validation report before merge is allowed

Phase 4: Scheduler (3 days)
  - OS-level scheduler (cron/Task Scheduler) for reliability
  - QTimer fallback for "every N minutes while running"
  - System tray notification on completion/failure

Phase 5: Webhook (3 days)
  - Enable WAL mode on SQLite for concurrent access
  - Webhook runs import in a background thread
  - API key auth + rate limiting

Total: 15 days (vs 14, but actually safe)
```

---

## FEAT-020: REST API Layer

### Critique

**The good:** Complete endpoint specs, Pydantic models, auth middleware. Well-structured.

**What's wrong:**

1. **The API duplicates the GUI's filtering logic.** `GET /api/units` has detailer/status/date/search/sort/pagination params — this is the same logic as the list panel. If the service layer (ARCH-001) is extracted first, the API should just call the same UnitService methods. The plan doesn't reference ARCH-001's service interfaces.

2. **Authentication is API keys only.** For a desktop app that might have a mobile companion, you need session-based auth (JWT) from the start. API keys are fine for server-to-server, not for user-facing clients.

3. **The WebSocket endpoint broadcasts all changes to all clients.** With 2765 units changing, this will flood clients. The subscribe/unsubscribe pattern is mentioned but not designed. How does a client subscribe to "only units assigned to Jackie H"?

4. **No rate limiting.** The plan mentions it in Phase 4 but doesn't define limits. Without rate limiting, a buggy client can DOS the API.

5. **The API runs in the same process as the GUI.** This means the API is only available when the app is running. For integrations (PowerBI, Slack), the API needs to be a standalone process. The plan should address this deployment model.

### The Better Version

```
Phase 1: Service-Layer API (4 days)
  - Reuse UnitService from ARCH-001 — don't duplicate filtering logic
  - GET/POST/PUT for units, imports, analytics
  - JWT auth for user sessions + API keys for server-to-server

Phase 2: Filtered WebSocket (2 days)
  - Subscribe to specific detailers, status levels, or COM numbers
  - Server-side filtering, not client-side
  - Heartbeat to detect disconnected clients

Phase 3: Standalone Mode (3 days, NEW)
  - API can run as a separate process: python -m api
  - Shared SQLite with WAL mode
  - Configurable port, host, CORS

Phase 4: Rate Limiting + Docs (2 days)
  - 100 req/min for read, 20 req/min for write
  - Auto-generated OpenAPI docs at /docs
  - curl examples in README

Total: 11 days (vs 12, but actually reusable)
```

---

## FEAT-021: Audit Trail UI

### Critique

**The good:** Implements MOC-A. Clear schema. History dialog with revert.

**What's wrong:**

1. **The audit log is a separate table from the change_log in MOC-A.** FEAT-021 creates `_audit_log`, MOC-A creates `change_log`. These are the same thing. The plans need to be merged or one needs to reference the other.

2. **Revert is dangerous without impact analysis.** The plan lets users revert any field to any previous value. But reverting a due date doesn't recalculate capacity. Reverting a detailer doesn't redistribute hours. Revert should trigger MOC-B's impact analysis before applying.

3. **No audit log for imports.** The plan only tracks manual edits. Imports (which can change hundreds of units) should be logged as a single "batch change" that can be reverted as a unit.

4. **The history dialog shows raw field names and values.** "percent_complete: 50 → 75" means nothing to most users. Show human-readable descriptions: "Completion changed from 50% to 75% by Brandon B on June 10."

5. **No retention policy.** The audit log will grow indefinitely. After a year of daily use, it could have hundreds of thousands of rows. The plan needs a configurable retention period.

### The Better Version

```
Phase 1: Unified Audit Log (4 days)
  - Merge with MOC-A's change_log schema
  - Add import batch tracking (one log entry per import, linking to all changed rows)
  - Add retention policy: configurable, default 90 days

Phase 2: History Dialog (3 days)
  - Human-readable change descriptions
  - Filter by unit, user, date range, field
  - Show batch changes (imports) as expandable groups

Phase 3: Revert with Impact Analysis (2 days)
  - Revert triggers MOC-B impact preview
  - User sees consequences before confirming
  - Revert creates its own audit entry (revert of revert = original change)

Total: 9 days (same, but safe)
```

---

## FEAT-02 (Novelty Alert System)

### Critique

**The good:** Phased approach. Enhances existing infrastructure.

**What's wrong:**

1. **The novelty detection is binary (novel/not novel) but the UI shows it as a single ✦.** There are different *kinds* of novelty: new unit type, new feature, new combination. The plan mentions "gold for unit type, blue for feature" but doesn't define the detection logic for each.

2. **Phase 3 (assignment notification) requires the edit form to know the *previous* detailer.** Currently, the edit form only knows the current detailer. You'd need to load the unit's history to detect a detailer change. This is a data access problem, not a UI problem.

3. **No "mark as not novel" action.** Once a detailer has done a unit type, it's no longer novel. But what if the detection is wrong? There should be a way to dismiss a novelty flag.

### The Better Version

```
Phase 1: Enhanced Indicator (2 days)
  - Three novelty types: type (gold), feature (blue), combo (purple)
  - Tooltip shows exactly what's novel
  - "Show novel only" filter in list panel

Phase 2: Novelty Summary Dialog (2 days)
  - Group by detailer
  - Show novelty type + unit count
  - Link to each novel unit

Phase 3: Assignment Notification (2 days)
  - On detailer change in edit form, check novelty for NEW detailer
  - Show warning: "This unit type (RTF) is new for Jane Smith"
  - One-line fix: compare against DetailerExperience before saving

Phase 4: Dismiss Novelty (1 day, NEW)
  - Right-click → "Mark as familiar" 
  - Adds an override to DetailerExperience
  - Prevents false positives from one-off assignments

Total: 7 days (vs "Medium" effort, more complete)
```

---

## FEAT-10 (DR/DVL Check Tracking)

### Critique

**The good:** Simple, well-scoped.

**What's wrong:**

1. **There is no user story.** The spec says "columns exist in DB, not in UI" but never says *who needs to see them* or *what decision they enable*. This is completeness-driven development.

2. **The columns store free-text strings ("Done", "Pending", "N/A").** If they're just text, why not use the notes field? If they're structured, they should be an enum. The plan should address the data model, not just the UI.

3. **No validation.** What stops a user from entering "Banana" in the DR Check field?

### The Better Version

```
Option A: Cut it. If nobody's asking for it, don't build it.

Option B: If a user actually needs this:
  - Make DR/DVL a status enum: Not Started / In Progress / Done / N/A
  - Add to list panel as a filterable column (not just display)
  - Add to edit form as a dropdown (not free text)
  - 2 days total
```

---

## FEAT-12 (Identical Unit Management)

### Critique

**The good:** The problem is real and well-explained.

**What's wrong:**

1. **The plan tries to do everything at once.** Visualization + dialog + reassignment + break relationship. That's 4 features in one plan.

2. **"Break identical relationship" is dangerous with no undo.** If a user breaks a relationship, target hours recalculate. If they made a mistake, there's no way back except manual re-entry.

3. **The group tinting will conflict with status color.** The plan says "subtle background tint" but the list already uses status colors for row backgrounds. Two color systems on the same row = visual clutter.

4. **Primary reassignment changes target hours for multiple units.** This is a batch operation disguised as a single-unit edit. It should go through the batch ops pipeline (IMP-13) with proper audit logging.

### The Better Version

```
FEAT-12a: Group Visualization (3 days)
  - Group number column (small, right-aligned)
  - Tooltip: "Identical group: order #12345 (3 units)"
  - NO row tinting — too much visual conflict with status colors
  - Click group number → open group dialog

FEAT-12b: Group Management (5 days)
  - Group dialog: table of all units in group
  - Primary reassignment with impact preview (MOC-B)
  - Break relationship with confirmation + audit log
  - Undo support via audit trail

Total: 8 days (split into two shippable stories)
```

---

## IMP-12 (Keyboard Shortcuts)

### Critique

**The good:** Concise, well-scoped.

**What's wrong:**

1. **"Delete key for date fields" is already implemented.** The ClearableDateEdit already handles Delete/Backspace. The spec lists it as remaining work. This is a spec error.

2. **Tooltip documentation is the lowest-value work.** Adding "Save Changes (Ctrl+S)" to a tooltip takes 5 minutes. Don't plan a whole phase for it.

3. **No accessibility consideration.** Keyboard shortcuts are good, but the plan doesn't mention screen reader support or focus indicators.

### The Better Version

```
Single phase: 1 day
  - Fix the spec: Delete key is already done
  - Add tooltip hints (30 minutes)
  - Add focus indicators for keyboard navigation (2 hours)
  - Verify all buttons have keyboard access (2 hours)
  - Done
```

---

## IMP-13 (Batch Operations)

### Critique

**The good:** Well-scoped phases. Good edge case analysis.

**What's wrong:**

1. **Phase 1 changes selection mode from Single to Extended.** This is a fundamental behavior change that affects every existing workflow. Users who are used to single-click selection will suddenly have multi-select. This needs a transition plan.

2. **The batch dialog has 6 fields but no "preview changes" step.** Users should see what will change before they apply. The plan jumps from dialog → apply.

3. **No integration with MOC-A.** Batch changes should be logged as a single audit entry linking to all changed units. The plan doesn't mention audit logging.

4. **"Undo batch" (Phase 4) is marked stretch but is actually essential.** Without undo, batch operations are dangerous. If you reassign 20 units to the wrong detailer, you need to undo all 20 at once.

### The Better Version

```
Phase 1: Multi-Select + Selection Count (2 days)
  - ExtendedSelection mode
  - Status label: "12 selected"
  - Keep single-click behavior: click selects, Ctrl+click adds

Phase 2: Batch Dialog + Preview (3 days)
  - Dialog with field changes
  - Preview: "This will change 12 units: 12 detailers, 0 dates, ..."
  - Apply button is disabled until preview is shown

Phase 3: Save + Audit (3 days)
  - Save each unit individually (reuses existing save pipeline)
  - Single audit log entry linking all 12 changes
  - Progress bar in status bar

Phase 4: Undo Batch (2 days, NOT stretch)
  - Revert all units from a batch operation
  - Uses audit log to find all units from a batch
  - Confirmation dialog showing what will be reverted

Total: 10 days (vs "Large", actually safe)
```

---

## IMP-14 (Inline List Edit)

### Critique

**The good:** Thorough spec. Good field selection. Reuses existing save pipeline.

**What's wrong:**

1. **The bar takes vertical space that could be used for table rows.** With 135 units, every pixel of table space matters. The plan should consider: can the bar overlay the table (like a floating toolbar) instead of pushing it down?

2. **No mention of the right-panel EditForm sync.** If the user edits inline, then clicks the unit in the right panel, the EditForm should show the updated values. The plan says "this already works via _commit_unit_to_memory" but doesn't verify that the EditForm repopulates on selection change.

3. **The bar is always visible when a row is selected.** Some users will find this distracting. A "pin" or "collapse" toggle should be in v1, not deferred.

4. **No keyboard shortcut to activate the bar.** Power users should be able to press Enter on a selected row to start editing inline, without reaching for the Save button.

### The Better Version

```
Changes to the original plan:
  - Bar overlays the table bottom (like a status bar) instead of pushing content down
  - Collapse/pin toggle in v1
  - Enter on selected row activates inline edit
  - Escape collapses the bar
  - Verify EditForm sync: after inline save, right-panel shows updated values
  - Add to testing: EditForm sync verification

Same effort: Medium
```

---

## PERF-001 (Virtual Scrolling)

### Critique

**The good:** QTableView + QAbstractItemModel is the right approach.

**What's wrong:**

1. **The plan doesn't address the existing incremental diffing (US-020b).** The current code has `_refresh_table_incremental` that does fingerprint-based diffing. This was built for QTableWidget and needs to be completely reworked for QAbstractItemModel. The plan should explicitly call this out.

2. **No migration plan for custom cell rendering.** The current table has status color blocks, overdue highlighting, due date change indicators, and novelty badges. All of this is custom `QTableWidgetItem` rendering that needs to be converted to a custom `QStyledItemDelegate`. The plan doesn't mention delegates.

3. **"Render only visible rows" is the goal but the plan doesn't define how.** With QAbstractItemModel, you still need to return data for all rows — the view just doesn't paint them. The model needs to be lazy: compute row data on demand, not upfront.

### The Better Version

```
Phase 1: Model + Basic View (3 days)
  - QAbstractTableModel subclass with lazy data access
  - QTableView with vertical scroll
  - Basic text display only (no custom rendering)

Phase 2: Custom Delegate (3 days)
  - QStyledItemDelegate for status colors, overdue highlighting
  - Convert all existing QTableWidgetItem logic to delegate paint()
  - This is the hardest part — budget accordingly

Phase 3: Performance Validation (2 days)
  - Benchmark: 2765 units, measure scroll FPS
  - Target: 60 FPS with 2765 units
  - If not met: implement row height caching + visible-range precomputation

Total: 8 days (same, but addresses the hard parts)
```

---

## PERF-002 (SQLite Indexing)

### Critique

**The good:** Specific index recommendations. No dependencies. Quick win.

**What's wrong:**

1. **The plan doesn't analyze current query patterns.** It recommends indexes but doesn't show which queries will benefit. Run `EXPLAIN QUERY PLAN` on the actual queries first.

2. **No WAL mode.** The plan mentions connection pooling but not WAL (Write-Ahead Logging) mode. WAL allows concurrent reads during writes, which is critical if the API (FEAT-020) runs in the same process.

3. **Index recommendations may conflict with the existing `_migrate_schema` pattern.** The current code uses additive `ALTER TABLE ADD COLUMN` migrations. Adding indexes should follow the same pattern.

### The Better Version

```
Phase 1: Query Analysis (1 day, NEW)
  - Run EXPLAIN QUERY PLAN on all queries in the load path
  - Identify which queries do full table scans
  - Document before/after query plans

Phase 2: Index Creation (2 days)
  - Add indexes based on actual query patterns
  - Enable WAL mode for concurrent read/write
  - Add indexes to the migration pattern

Phase 3: Validation (2 days)
  - Re-run EXPLAIN QUERY PLAN, verify index usage
  - Benchmark: 10K rows, measure query times
  - Target: 10x improvement on filtered queries

Total: 5 days (same, but data-driven)
```

---

## PERF-003 (Lazy Loading + Caching)

### Critique

**The good:** TTLLRUCache is well-designed. Lazy tag parsing is the right call.

**What's wrong:**

1. **The cache invalidation strategy is incomplete.** The plan invalidates on save, but what about on import? On SSRS fetch? On manual DB edit? Every data mutation path needs invalidation.

2. **The `calculated_status_color` property is recalculated on every access.** The plan says "no memoization per save cycle" but doesn't fix it. This should be cached at the model level, not the service level.

3. **Background pre-computation (Phase 3) is vague.** "Schedule background computation of aggregations" — which aggregations? For what purpose? This needs to be specific.

### The Better Version

```
Phase 1: TTLLRUCache + Fingerprint Caching (2 days)
  - Same as original
  - Add invalidation hooks for ALL data mutation paths (save, import, SSRS)

Phase 2: Lazy Tag Parsing (2 days)
  - Same as original
  - Add calculated_status_color memoization per save cycle

Phase 3: Background Aggregation (1 day)
  - Specifically: pre-compute alert counts by severity
  - Used by the alert panel summary widget
  - QTimer.singleShot(0, ...) after load completes

Total: 5 days (same, but complete)
```

---

## QA-001 (Property-Based Testing)

### Critique

**The good:** Excellent strategy definitions. Good invariant tests.

**What's wrong:**

1. **The `unit_strategy()` generates random Units that may not match real data distributions.** Random strings for job names, random floats for hours — these won't catch the edge cases that actually occur in production. The strategies should be seeded with production data analysis.

2. **No regression test for the `percent_complete` scale bug.** The plan should explicitly include a property test that catches the 0-1 vs 0-100 mismatch. This is the kind of bug property testing is perfect for.

3. **2000 examples per test is too many for CI.** The plan should define a CI profile (100 examples, fast) and a nightly profile (10000 examples, thorough).

### The Better Version

```
Phase 1: Strategies + CI Profile (2 days)
  - Analyze production data distributions (min/max/mean for each field)
  - Tune strategies to match real data
  - Define CI profile: 100 examples, < 30 seconds per test

Phase 2: Core Invariants (2 days)
  - calculated_status_color always valid
  - alert_level always valid
  - percent_complete always 0-100 (catches the scale bug)
  - fingerprint stable for same unit

Phase 3: Roundtrip Properties (2 days)
  - Unit → DB → Unit preserves all fields
  - CSV → Unit → CSV preserves all fields

Phase 4: Nightly Extended Run (2 days)
  - 10000 examples per test
  - Run nightly in CI, not on every PR
  - Includes adversarial inputs (empty strings, max values, unicode)

Total: 8 days (same, but catches real bugs)
```

---

## QA-002 (UI Integration Tests)

### Critique

**The good:** QTest is the right framework. Screenshot diffing catches visual regressions.

**What's wrong:**

1. **The plan depends on ARCH-001 but doesn't say which parts.** UI integration tests can be written against the current GUI — they don't need the service layer. The dependency should be removed or clarified.

2. **Screenshot diffing is fragile across platforms.** Fonts, DPI, and rendering differ between Linux and Windows. The plan should define tolerance levels or use structural comparison (widget tree) instead of pixel comparison.

3. **No test data management.** UI tests need consistent test data. The plan should define a test fixture that creates a known database state before each test.

### The Better Version

```
Phase 1: Test Infrastructure (3 days)
  - QTest fixtures with known database state
  - Test data: 50 units with predictable values
  - Remove ARCH-001 dependency — test through the GUI

Phase 2: Critical Path Tests (4 days)
  - Select unit → edit form populates
  - Edit field → save → table updates
  - Filter → table filters
  - Import → diff → merge → table updates

Phase 3: Visual Regression (2 days)
  - Structural comparison (widget tree) not pixel comparison
  - Tolerance for cross-platform differences
  - Run on Linux + Windows in CI

Total: 9 days (same, but actually cross-platform)
```

---

## QA-003 (Fuzz Testing)

### Critique

**The good:** Targets the right components (CSV, tags, dates).

**What's wrong:**

1. **"atheris for native/C-level fuzzing" — there are no C extensions.** The entire app is Python. Atheris is irrelevant. Cut it.

2. **60 seconds per target in CI is too short.** Fuzz testing needs time to explore the input space. 60 seconds will only find the most obvious crashes. Either increase to 5 minutes or run fuzzing nightly, not in CI.

3. **The seed corpus is good but incomplete.** 2765 descriptions + 50 CSV files. What about edge cases? Empty files? Files with 1 row? Files with 100K rows? Unicode? The seed corpus should include adversarial examples.

### The Better Version

```
Phase 1: Fuzz Targets (3 days)
  - CSV import fuzzer
  - Tag parser fuzzer
  - Date parser fuzzer
  - NO atheris — pure Python + Hypothesis

Phase 2: Seed Corpus + Adversarial Inputs (2 days)
  - Production data (2765 descriptions)
  - Adversarial: empty, max-size, unicode, malformed
  - Edge case: 1 row, 100K rows, missing columns

Phase 3: CI Integration (2 days)
  - 60-second smoke test in CI (catches obvious crashes)
  - 30-minute nightly run (explores input space)
  - Automatic crash reporting with reproducer

Total: 7 days (same, but actually useful)
```

---

## QA-004 (Performance Benchmark Suite)

### Critique

**The good:** pytest-benchmark is the right tool. CI regression gate at 20% is reasonable.

**What's wrong:**

1. **The baseline numbers are guesses.** "Load 1000 units: < 100ms" — is this measured or assumed? The plan should measure current performance first, then set baselines.

2. **The benchmark code references `src.data_model`, `src.parser`, etc.** — these modules don't exist in the current codebase. The package structure is `data/`, `gui/`, `services/`. The plan was written for a different project structure.

3. **No warm-up runs.** JIT compilation, SQLite caching, and Qt initialization affect the first run. The benchmark should include warm-up rounds.

### The Better Version

```
Phase 1: Measure Current Performance (1 day, NEW)
  - Run existing operations, measure actual times
  - Set baselines from real data, not guesses

Phase 2: Benchmark Suite (3 days)
  - Fix package references to match actual codebase
  - Add warm-up rounds (3 runs before measurement)
  - 8 benchmark scenarios with measured baselines

Phase 3: CI Integration (1 day)
  - Regression gate at 20%
  - Run on dedicated CI runner (not shared)
  - Historical tracking in benchmarks.json

Total: 5 days (same, but baselines are real)
```

---

## DEVOPS-001 (CI/CD Pipeline)

### Critique

**The good:** Complete YAML. Pre-commit hooks. Branch protection.

**What's wrong:**

1. **The workflow references `main` and `develop` branches but the project may not use Git Flow.** Verify the branch strategy first.

2. **"Fix all existing lint errors" (Phase 1) could be a multi-day project.** The plan allocates 1 day for the entire phase including fixing lint errors. If there are 200+ lint errors, this will take longer.

3. **The build job uses `--onefile` PyInstaller.** This is fine for distribution but makes startup slow (everything unpacks to temp on each launch). Consider `--onedir` for faster startup.

4. **No smoke test for the built binary.** The plan says "test binary: launch, connect to SQLite, verify main window" but doesn't automate this. Add an automated smoke test.

### The Better Version

```
Phase 1: Pre-commit + Lint (2 days, was 1)
  - Create .pre-commit-config.yaml
  - Fix existing lint errors (budget a full day for this)
  - Add ruff config to pyproject.toml

Phase 2: Test Pipeline (1 day)
  - Same as original

Phase 3: Build Pipeline (2 days)
  - Use --onedir instead of --onefile for faster startup
  - Add automated smoke test: launch binary, verify window title

Phase 4: Release Automation (1 day)
  - Same as original

Total: 6 days (1 more, but realistic)
```

---

## MOC-A (Change Audit Trail)

### Critique

**The good:** Best-written spec in the backlog. Complete schema. Good phased approach.

**What's wrong:**

1. **The diff logic compares old vs. new Unit objects, but where does the "old" Unit come from?** The plan says "diffs the old Unit (from DB) vs new Unit (from form)" — but this requires loading the current DB state before every save. That's an extra query per save. The plan should address this performance cost.

2. **No batch import audit.** Imports can change hundreds of units. The plan should define how batch changes are logged (one entry per import, linking to all changed rows).

3. **The "Revert Selected" button in Phase 2 is dangerous.** Reverting a due date doesn't recalculate capacity. Reverting a detailer doesn't redistribute hours. Revert should show impact analysis first (MOC-B integration).

### The Better Version

```
Phase 1: Change Log Table + Diff (5 days)
  - Same as original
  - Add batch import audit: one log entry per import
  - Cache the pre-save DB state to avoid extra queries

Phase 2: History Dialog (3 days)
  - Same as original
  - Remove "Revert Selected" — move to Phase 3 with impact analysis

Phase 3: Revert with Impact (3 days, NEW)
  - Revert triggers MOC-B impact preview
  - User sees consequences before confirming
  - Revert creates its own audit entry

Total: 11 days (vs "Medium", but safe)
```

---

## MOC-B (Change Impact Analysis)

### Critique

**The good:** Excellent problem scenarios. Well-defined analyzer interface.

**What's wrong:**

1. **The analyzer iterates over all units for every save.** With 2765 units, this adds latency to the save operation. The plan mentions "50-200ms" but doesn't measure it. This needs to be async — show the warning *after* the save, not before.

2. **"Minor change" filter is undefined.** The plan says "don't show warnings for trivial changes" but doesn't define the threshold. This is the most important design decision in the entire plan and it's deferred.

3. **No integration with the inline edit bar (IMP-14).** If the user changes a detailer in the inline bar, should impact analysis fire? The plan only considers the EditForm.

### The Better Version

```
Phase 1: Async Impact Analyzer (4 days, was 3)
  - Run analysis AFTER save, not before
  - Show non-blocking notification if impacts detected
  - Define "minor change" threshold: < 5% capacity change = minor

Phase 2: Batch Impact (3 days)
  - Same as original

Phase 3: Post-Save Ripple (3 days)
  - Same as original
  - Include inline edit bar integration

Total: 10 days (vs "Medium-Large", but actually usable)
```

---

## MOC-C (Change Review & Approval Workflow)

### Critique

**The good:** The classification table is a good start.

**What's wrong:**

1. **This is the weakest MOC spec.** The thresholds are arbitrary. The review queue is undesigned. The roles are undefined. The agentic review assistant is a distraction.

2. **"Start with Phase 1 (classification + logging, no blocking)"** — this is the right call, but it means the actual review workflow (Phases 2-5) is indefinitely deferred. The plan should be honest about this: Phase 1 is the plan, Phases 2-5 are a vision.

3. **The classification table has no data to support it.** "Due date shift: < 3 days = Low, 3-7 days = Medium, >= 7 days = High" — why these numbers? They should be calibrated against actual miss data.

4. **No consideration of the single-user case.** If there's only one person using the app, who reviews their own changes? The plan assumes a multi-user team with distinct roles.

### The Better Version

```
Phase 1: Classification + Logging (3 days)
  - Log every change with a severity classification
  - NO blocking, NO review queue
  - Use the classification data to calibrate thresholds over 2 weeks

Phase 2: Data-Driven Thresholds (2 days, NEW)
  - After 2 weeks of data, analyze: what changes correlate with misses?
  - Set thresholds based on actual impact, not guesses

Phase 3+: Review Queue (DEFERRED)
  - Only build if the team grows to 3+ people with distinct roles
  - Revisit after Phase 2 data is available

Total: 5 days for now, defer the rest
```

---

## Summary: The Better Roadmap

### Immediate (No Dependencies)
| Plan | Days | Impact |
|---|---|---|
| DEVOPS-001: CI/CD | 6 | Enables everything |
| QA-001: Property Testing | 8 | Finds real bugs |
| PERF-002: SQLite Indexing | 5 | 10x query improvement |
| PERF-003: Lazy Loading | 5 | Faster startup |
| MOC-A: Audit Trail | 11 | Foundational |
| FEAT-019 Phase 1: Import Safety | 5 | Prevents data loss |

**Subtotal: 40 days**

### Quarter 1 (After Immediate)
| Plan | Days | Impact |
|---|---|---|
| ARCH-001: Service Layer | 23 | Testable, reusable |
| ARCH-003: Validation | 10 | Data integrity |
| IMP-14: Inline Edit | 8 | Faster editing |
| FEAT-021: Audit UI | 9 | Audit trail UX |
| IMP-13: Batch Ops | 10 | Bulk operations |

**Subtotal: 60 days**

### Quarter 2+ (Platform)
| Plan | Days | Impact |
|---|---|---|
| ARCH-002: State Management | 13 | Undo/redo |
| ARCH-004: Plugins | 8 | Extensibility |
| FEAT-020: REST API | 11 | Integrations |
| FEAT-018: Gantt | 15 | Capacity planning |
| FEAT-017: Predictive Analytics | 21 | Risk forecasting |
| FEAT-016: Real-Time Collab | 15 | Multi-user |

**Subtotal: 83 days**

### Deferred / Cut
| Plan | Reason |
|---|---|
| FEAT-10 (DR/DVL) | No user story |
| MOC-C Phases 2+ | Single-user shop, no review need |
| IMP-020 (Dashboard) | Nice-to-have, low usage |
| QA-003 (Fuzz) | Lower priority than other QA |
