# Action Plan & Roadmap: SQL Schedule Tracker

This roadmap outlines the execution path for all plans currently in [plans/begin](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin), reorganized by dependency order, technical impact, and product safety. Completed plans are slated for migration to `plans/fin/`.

---

## 🗺️ Phase-by-Phase Roadmap

```mermaid
graph TD
    classDef phase fill:#f9f,stroke:#333,stroke-width:2px;
    classDef cut fill:#f99,stroke:#333,stroke-width:2px;

    P1[Phase 1: Performance & State] :::phase
    P2[Phase 2: Import & Data Safety] :::phase
    P3[Phase 3: GUI Polish & UX Depth] :::phase
    P4[Phase 4: Gantt & Collaboration] :::phase
    P5[Phase 5: CI/CD & Testing] :::phase
    Cuts[Phase 6: Excluded / Cut Plans] :::cut

    P1 --> P2
    P2 --> P3
    P1 -.-> P3
    P3 --> P4
    P4 --> P5
```

---

## 🏃 Phase 1: Performance & State Management (Sprint 9)
*Focus: Address immediate bottleneck risks (2700+ units loading/scrolling) and establish clean state handling.*

### 1. [PERF-001: Virtual Scrolling](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/PERF-001-virtual-scrolling.md)
*   **Action Plan:** 
    *   Migrate list panel from `QTableWidget` to `QTableView` + `QAbstractTableModel`.
    *   Implement lazy calculation of rows.
    *   Write a custom `QStyledItemDelegate` for status colors, overdue flags, and novelty badges to replace manual widget construction.
*   **Why First:** Virtual scrolling is the foundation of rendering large datasets at 60 FPS.

### 2. [PERF-003: Lazy Loading & Caching](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/PERF-003-lazy-loading-cache.md)
*   **Action Plan:**
    *   Implement a `TTLLRUCache` for database results.
    *   Introduce lazy tag parsing for job descriptions.
    *   *Correction:* Add cache invalidation triggers to **all** data mutation paths (save, import, and sync).

### 3. [PERF-002: SQLite Indexing / Query Optimization](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/PERF-002-query-optimization.md)
*   **Action Plan:**
    *   Analyze active execution queries using `EXPLAIN QUERY PLAN`.
    *   Establish database indexes and transition SQLite to WAL (Write-Ahead Logging) mode.

### 4. [QA-004: Performance Benchmark Suite](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/QA-004-benchmark-regression.md)
*   **Action Plan:**
    *   Set up a benchmark suite utilizing `pytest-benchmark`.
    *   Fix outdated directory paths in the spec to target active code folders.

### 5. [ARCH-002: Centralized State Management](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/ARCH-002-state-management.md)
*   **Action Plan:**
    *   Unify state tracking into separate domains: `DomainState`, `UIState`, and `RuntimeState`.
    *   *Correction:* Defer full Command Pattern logic until Undo/Redo is explicitly required.

---

## 🛡️ Phase 2: Import & Data Safety (Sprint 10)
*Focus: Enhance CSV workbook parsing and multi-user safety.*

### 1. [FEAT-019: Advanced Import Pipeline](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/FEAT-019-advanced-import-pipeline.md)
*   **Action Plan:**
    *   Build the backend diff engine (`ImportService.diff_before_import()`).
    *   *Correction:* Build a **three-way diff** (CSV vs. DB vs. unsaved memory) to protect active edits.
    *   *Correction:* Use Windows Task Scheduler instead of `QTimer` for headless imports.

### 2. [DEVOPS-003: Auto Backup & Rollback](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/DEVOPS-003-auto-backup-rollback.md)
*   **Action Plan:**
    *   Implement the rollback interface utilizing the startup database copies.
    *   *Correction:* Store pre-change row states as JSON rather than fragile SQL strings.

### 3. [FEAT-12: Identical Unit Management](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/FEAT-12-identical-unit-management.md)
*   **Action Plan:**
    *   Display identical groups in the List panel using a group column and detail tooltips.
    *   *Correction:* Skip background row tinting to avoid visual conflict with status colors.

---

## 🎨 Phase 3: GUI Polish & UX Depth (Sprint 11)
*Focus: Implement the remaining layout improvements from the flow roadmap.*

### 1. [GUI-FLOW-IMPROVEMENTS.md](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/GUI-FLOW-IMPROVEMENTS.md) (Sprints 3–4)
*   **Action Plan:**
    *   Make the Timeline panel collapsible.
    *   Add a Batch Edit warning banner to the edit pane when multiple units are selected.
    *   Reposition the inline edit bar to sit above the table.
    *   Build a global notification toast overlay system (`gui/notification_panel.py`).

### 2. [FEAT-2: Novelty Alert System](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/FEAT-2-novelty-alert-system.md)
*   **Action Plan:**
    *   Render colored novelty icons (gold for type, blue for feature, purple for combo).
    *   Provide a right-click "Mark as familiar" option to dismiss false positives.

---

## 📊 Phase 4: Gantt & Collaboration (Sprint 12)
*Focus: Advanced scheduler views and multi-user collaboration controls.*

### 1. [FEAT-018: Gantt Chart View](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/FEAT-018-gantt-chart-view.md)
*   **Action Plan:**
    *   *Correction:* Rebuild using `QGraphicsScene` / `QGraphicsView` to handle thousands of items seamlessly.
    *   Implement drag-to-reschedule with validation checks.

### 2. [FEAT-016: Real-Time Collaboration](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/FEAT-016-realtime-collaboration.md)
*   **Action Plan:**
    *   *Correction:* Eliminate Operational Transform (OT).
    *   Use lightweight WebSocket broadcasts for cursor presence, and field-level optimistic locking with diff resolutions.

### 3. [MOC-B: Change Impact Analysis](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/MOC-B-CHANGE-IMPACT-ANALYSIS.md) & [MOC-C: Change Review Workflow](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/MOC-C-CHANGE-REVIEW-WORKFLOW.md)
*   **Action Plan:**
    *   Display warnings when a schedule change pushes other related tasks past their deadlines.

---

## 🤖 Phase 5: CI/CD, DevTools & Advanced Quality Assurance (Sprint 13)
*Focus: Standardize coding style, automate testing, and secure the release process.*

### 1. [DEVOPS-001: CI/CD Pipeline](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/DEVOPS-001-ci-cd-pipeline.md)
*   **Action Plan:**
    *   Configure GitHub Actions for automated unit tests.
    *   Run lint checking using Ruff.
    *   Automate headless smoke testing of the built PyInstaller executable.

### 2. [DEVOPS-002: Logging & Monitoring](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/DEVOPS-002-logging-monitoring.md) & [DEVOPS-004: Hotreload Dev](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/DEVOPS-004-hotreload-dev.md)
*   **Action Plan:**
    *   Unify diagnostic logging to standard outputs.
    *   Configure file-system watching for automated development hot-reloading.

### 3. [QA-001: Property-Based Testing](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/QA-001-property-based-testing.md), [QA-002: UI Integration Tests](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/QA-002-ui-integration-tests.md) & [QA-003: Fuzz Testing](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/QA-003-fuzz-testing.md)
*   **Action Plan:**
    *   Implement Hypothesis tests for core date range behaviors.
    *   Write QTest-based GUI workflows.
    *   Fuzz description tag parsing algorithms.

---

## 🚫 Phase 6: Excluded / Cut Plans
*These plans are over-engineered or irrelevant to a compiled native Windows desktop application and should be deleted.*

1.  **[DEVOPS-005-containerization.md](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/DEVOPS-005-containerization.md)**: Containerizing PyQt5 GUIs with X11 forwarding is fragile and serves no purpose for Windows desktop users.
2.  **[FEAT-020-rest-api.md](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/FEAT-020-rest-api.md)**: Exposing local FastAPI servers inside a single-user desktop client is unnecessary.
3.  **[ARCH-004-plugin-system.md](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/ARCH-004-plugin-system.md)**: Dynamic loading and sandboxing represent excessive overhead. Clean code interfaces are sufficient.
4.  **[FEAT-10-dr-dvl-check-tracking.md](file:///C:/Users/jbrow263/Downloads/Code%20Projects/SQL-Schedule-App/SQL-Schedule-Tracker/plans/begin/FEAT-10-dr-dvl-check-tracking.md)**: Stores free-text status values in database columns. Should be cut or rewritten to use standard status Enums.

---

## 🧹 Housekeeping: Completed Plans to Move
The following completed specs should be moved from `/plans/begin/` to `/plans/fin/`:
*   `ARCH-003-data-validation-layer.md`
*   `FEAT-021-audit-trail-ui.md`
*   `IMP-017-bulk-operations.md`
*   `IMP-13-batch-operations.md`
*   `IMP-14-inline-list-edit.md`
*   `MOC-A-CHANGE-AUDIT-TRAIL.md`
