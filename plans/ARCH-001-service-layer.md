# ARCH-001: Service Layer Extraction

**Status**: Draft  
**Priority**: Critical  
**Effort**: XL (3-4 weeks)  
**Depends on**: None  
**Required by**: ARCH-002, ARCH-003, QA-001, QA-002  

---

## Problem Statement

`gui/main_window.py` is a 1378-line God class that directly orchestrates data loading, saving, CSV import, SSRS fetching, Excel export, theme management, multi-user sync, UI state, config persistence, and keyboard shortcuts. This violates the Single Responsibility Principle and makes the class:

- **Untestable** — you cannot test business logic without instantiating `QApplication` and a full widget tree
- **Unmaintainable** — any change risks side effects across unrelated concerns
- **Unreusable** — no other consumer (CLI, REST API, test harness) can access business logic without importing the GUI
- **Coupling nightmare** — the `MainWindow` knows about file paths, SQL queries, CSV parsing, SSRS URL construction, lock files, sessions, and UI pixel dimensions

---

## Proposed Solution

Extract four service classes from `MainWindow`, each with a clear interface, zero Qt dependencies, and full testability. `MainWindow` becomes a thin orchestration layer that creates services and wires their results to widgets.

### Architecture

```
┌────────────────────────────────────────────────┐
│                  MainWindow (thin)             │
│  ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ ViewModel │ │ Commands │ │ ConfigManager │  │
│  └────┬─────┘ └────┬─────┘ └───────┬───────┘  │
│       │            │               │          │
└───────┼────────────┼───────────────┼──────────┘
        │            │               │
┌───────┼────────────┼───────────────┼──────────┐
│       ▼            ▼               ▼          │
│  ┌─────────────────────────────────────────┐  │
│  │           Service Layer                  │  │
│  │  ┌──────────────┐  ┌──────────────┐     │  │
│  │  │  UnitService  │  │ ImportService │     │  │
│  │  └──────┬───────┘  └──────┬───────┘     │  │
│  │  ┌──────────────┐  ┌──────────────┐     │  │
│  │  │  SyncService  │  │ ExportService │     │  │
│  │  └──────┬───────┘  └──────┬───────┘     │  │
│  └─────────┼─────────────────┼─────────────┘  │
│            │                 │                 │
│  ┌─────────▼─────────────────▼─────────────┐  │
│  │           Data Layer (existing)          │  │
│  │  data/db.py  data/loader.py  data/writer │  │
│  └─────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
```

### Service Interfaces

**`services/unit_service.py`**
```python
class UnitService:
    def __init__(self, db_path: str, detailer_schedules: dict | None = None):
        ...
    
    def load_all(self, force: bool = False) -> list[Unit]:
        """Load units from DB, apply identicals rule, return ordered list."""
    
    def save(self, unit: Unit, version_stamp: str) -> Unit:
        """Save with optimistic locking. Raises ConcurrentEditError."""
    
    def get_by_com(self, com: str) -> Unit | None:
        """Fetch single unit (for conflict dialog reload)."""
    
    def apply_identicals(self, units: list[Unit]) -> None:
        """In-place identicals rule application."""
    
    def compute_fingerprint(self, unit: Unit) -> str:
        """Stable hash of editable fields."""
    
    def detect_changed_due_dates(self, old: list[Unit], new: list[Unit]) -> list[Change]:
        """Return list of (unit, old_date) for units whose due date changed."""
```

**`services/import_service.py`**
```python
class ImportService:
    def from_csv(self, csv_path: str) -> ImportResult:
        """Upsert CSV rows into SQLite. Returns stats."""
    
    def from_ssrs(self, url: str, lookback: int, lookahead: int) -> ImportResult:
        """Fetch CSV from SSRS, parse, upsert. Returns stats."""
    
    def diff_before_import(self, csv_path: str) -> ImportDiff:
        """Preview what would change. (FEAT-019)"""
```

**`services/sync_service.py`**
```python
class SyncService:
    def is_enabled(self) -> bool: ...
    def acquire_lock(self, com: str, purpose: str = "") -> bool: ...
    def release_lock(self, com: str) -> None: ...
    def get_revision(self, com: str) -> int: ...
    def commit_revision(self, com: str, base: int, fp: str, user: str) -> Revision: ...
    def get_active_sessions(self) -> list[SessionInfo]: ...
    def start_heartbeat(self, owner: str) -> None: ...
    def stop_heartbeat(self) -> None: ...
```

**`services/export_service.py`**
```python
class ExportService:
    def to_excel(self, excel_path: str, db_path: str) -> int:
        """Export SQLite → Excel Current List sheet."""
    
    def to_csv(self, units: list[Unit], path: str, columns: list[str]) -> None:
        """Export filtered units to CSV."""
    
    def to_pdf(self, units: list[Unit], path: str) -> None:
        """Export filtered view to PDF report."""
```

### New Package Structure

```
services/
├── __init__.py
├── unit_service.py          # Unit CRUD, identicals, fingerprints
├── import_service.py        # CSV + SSRS import pipeline
├── sync_service.py          # Multi-user lock + revision + session
├── export_service.py        # Excel, CSV, PDF export
├── config_service.py        # Config load/save with merge + validation
└── notification_service.py  # Cross-cutting: status bar, dialogs, logging
```

### ConfigService (extracted from MainWindow)

```python
class ConfigService:
    """Config.yaml loading, validation, persistence."""
    
    @staticmethod
    def load(path: str) -> dict: ...
    @staticmethod
    def validate(cfg: dict) -> list[str]: ...  # returns warnings
    @staticmethod
    def save(path: str, cfg: dict) -> None: ...
    def merge_ui_defaults(self, cfg: dict) -> dict: ...  # fill missing keys
    def get_detailer_schedules(self, cfg: dict) -> dict[str, list[int]]: ...
```

---

## Implementation Phases

### Phase 1: Extract ConfigService (3 days)
1. Create `services/config_service.py` — move config loading, validation, and save logic
2. Replace inline config handling in `main.py` and `MainWindow.__init__`
3. Add schema validation: mandatory keys, type checks, safe defaults
4. **Tests**: Test loading valid/invalid config files, merging defaults

### Phase 2: Extract UnitService (5 days)
1. Create `services/unit_service.py` — wrap `loader.load_units`, `writer.save_unit`, `db.row_to_unit`
2. Move fingerprint computation from `loader.py` into service
3. Move `_apply_identicals` logic into service
4. Move `_detect_due_date_changes` into service
5. **Tests**: Unit-test each method with in-memory SQLite fixtures

### Phase 3: Extract ImportService (3 days)
1. Create `services/import_service.py` — wrap CSV import and SSRS fetch
2. Move SSRS URL construction, fetch logic, fallback auth from `import_atomsvc.py`
3. **Tests**: Mock HTTP responses, test CSV-to-SQLite upsert

### Phase 4: Extract SyncService (5 days)
1. Create `services/sync_service.py` — wrap lock_manager, revision_store, session_registry, shared_cache
2. Provide `is_enabled()` guard so callers don't check config directly
3. **Tests**: Test lock acquisition, conflict detection, session heartbeat

### Phase 5: Extract ExportService (2 days)
1. Create `services/export_service.py` — wrap Excel export, add CSV export
2. **Tests**: Test export with temp files, verify SQLite → Excel row parity

### Phase 6: Thin MainWindow (5 days)
1. Replace all direct service calls in `MainWindow` with delegate methods
2. Inject services via constructor (or a simple `ServiceRegistry` singleton)
3. Remove unused imports, dead code paths
4. **Regression test**: Full manual walkthrough of all features

---

## Success Criteria

1. `MainWindow` is under 600 lines (currently 1378)
2. Every service is testable without `QApplication`; coverage > 85%
3. All existing tests pass without modification
4. A new CLI tool can import/export/query without importing GUI
5. `pylint --max-line-length=120` passes with score ≥ 9.0/10

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Regression during extraction | Medium | Phase 6 with full manual + automated regression |
| Service interface churn | Medium | Design interfaces before extraction; iterate fast |
| Circular imports | Low | Services import `data.*` and `sync.*` only; never import `gui.*` |
| Performance overhead of indirection | Low | Services are thin wrappers; cost is one function call |

---

## Effort Estimate

| Phase | Days | Dependencies |
|-------|------|-------------|
| Phase 1: ConfigService | 3 | None |
| Phase 2: UnitService | 5 | Phase 1 |
| Phase 3: ImportService | 3 | Phase 1 |
| Phase 4: SyncService | 5 | Phase 1 |
| Phase 5: ExportService | 2 | Phase 3 |
| Phase 6: Thin MainWindow | 5 | Phases 1-5 |
| **Total** | **23** | |