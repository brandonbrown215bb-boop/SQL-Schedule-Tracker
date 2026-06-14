# FEAT-019: Advanced Import Pipeline — Diff, Review, Rollback, Schedule

## 1. Problem

Current import applies changes immediately with no preview, no rollback, and no scheduling. Users discover issues only after data has already been corrupted or incorrectly merged, forcing manual database repairs and lost time.

## 2. Solution

A multi-stage import pipeline that gives users full visibility and control over every import operation before, during, and after execution.

### 2.1 Pre-Import Diff Viewer

Show users exactly what will change before any write occurs:

| Diff Category | Description |
|---------------|-------------|
| **New rows**   | Records that exist in the incoming data but not in the current table |
| **Updated rows** | Records whose key matches but field values differ |
| **Removed rows** | Records present in the current table but absent from the incoming data (optional, configurable) |

A side-by-side or unified diff view highlights every field-level change using GViz-style colour coding (green for additions, red for deletions, yellow for modifications).

### 2.2 Import Staging Area

All incoming data is first loaded into a temporary staging table. Users can inspect it, run validation queries, and only then initiate a merge into the live table. The merge uses a configurable strategy (upsert, append-only, replace).

```
┌──────────┐    ┌──────────┐    ┌─────────┐
│  Source   │ -> │  Staging │ -> │  Live   │
│  (CSV/XLS)│    │ (temp)   │    │ (prod)  │
└──────────┘    └──────────┘    └─────────┘
                    │   ▲
                    ▼   │
              ┌─────────────┐
              │ Diff Viewer │
              └─────────────┘
```

### 2.3 Rollback Capability

Each committed import records a reverse-SQL script (e.g., `DELETE` for inserted rows, `UPDATE` for changed rows) that can be replayed to undo the operation. The rollback log is stored alongside the import history.

**Key interface:**
```python
class RollbackRecord:
    import_id: UUID
    reverse_sql: str
    affected_tables: list[str]
    row_count: int
    created_at: datetime

def rollback(import_id: UUID) -> RollbackResult:
    """Execute the stored reverse SQL for a given import."""
```

### 2.4 Scheduled Auto-Imports

A lightweight, in-process scheduler (QTimer-based) allows users to define recurring import jobs:

- **Frequency:** Every N minutes, hourly, daily, weekly, or custom cron expression.
- **Source:** SSRS report export URL, local file path, or shared network drive.
- **Notification:** Emit a system tray notification or webhook on success/failure.
- **Auto-revert:** Optionally auto-rollback if validation checks fail after merge.

```python
class ImportSchedule:
    id: UUID
    name: str
    source_url: str
    cron_expression: str           # e.g. "0 */6 * * *" = every 6 hours
    merge_strategy: MergeStrategy
    auto_rollback_on_failure: bool
    enabled: bool
    last_run: datetime | None
    next_run: datetime | None
```

### 2.5 Webhook Triggers

A lightweight HTTP endpoint (optional, Flask or FastAPI) accepts a POST request to trigger an import programmatically:

```
POST /api/v1/import/trigger
Authorization: Bearer <api_key>
Body: {
  "source_url": "https://ssrs-server/report?format=CSV&parameter=123",
  "merge_strategy": "upsert"
}
```

**Use cases:**
- CI/CD pipeline fires a webhook after an ETL job completes.
- SSRS report subscription pushes data via a webhook target.
- External cron service (e.g., AWS EventBridge, cron-job.org) hits the endpoint.

### 2.6 Import History Log

A persistent log stored in the application database records every import event:

| Field        | Type     | Description |
|--------------|----------|-------------|
| `id`         | UUID     | Primary key |
| `timestamp`  | datetime | When the import occurred |
| `user`       | str      | Who triggered it (local user or "scheduler" / "webhook") |
| `source`     | str      | File name or URL |
| `rows_added` | int      | Count of new rows |
| `rows_updated` | int    | Count of modified rows |
| `rows_removed` | int    | Count of deleted rows |
| `status`     | enum     | success / failed / rolled_back |
| `rollback_id`| UUID?    | Link to the rollback record, if applicable |

## 3. Architecture

### 3.1 Service Layer

```
services/
├── import_service.py     # Extended with diff + staging logic
├── import_scheduler.py   # QTimer-based scheduling engine
└── import_webhook.py     # Optional HTTP endpoint (Flask/FastAPI)
```

#### `services/import_service.py` (extensions)

```python
class ImportService:
    def stage_data(self, source: DataSource) -> StagingResult:
        """Load source data into staging table and return diff summary."""

    def compute_diff(self, staging_id: UUID) -> ImportDiff:
        """Compare staging data against live table and produce a diff."""

    def merge_staged(self, staging_id: UUID, strategy: MergeStrategy) -> MergeResult:
        """Apply staged changes to the live table and record rollback SQL."""

    def rollback_import(self, import_id: UUID) -> RollbackResult:
        """Undo the last import using stored reverse SQL."""

    def get_history(self, filters: HistoryFilter) -> list[ImportRecord]:
        """Query the import history log."""
```

#### `services/import_scheduler.py`

```python
class ImportScheduler(QObject):
    """Manages scheduled import jobs using QTimer."""

    def __init__(self, import_service: ImportService):
        self.jobs: dict[UUID, ScheduledJob] = {}
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)

    def add_job(self, schedule: ImportSchedule):
        ...

    def remove_job(self, job_id: UUID):
        ...

    def enable_job(self, job_id: UUID, enabled: bool):
        ...

    def start(self):
        self.timer.start(60_000)  # tick every minute

    def _tick(self):
        for job in self.jobs.values():
            if job.due and job.enabled:
                self._execute_job(job)
```

#### `services/import_webhook.py`

```python
# Optional — can be a standalone process or embedded thread
from fastapi import FastAPI, HTTPException, Security

app = FastAPI()

@app.post("/api/v1/import/trigger")
async def trigger_import(
    request: ImportRequest,
    api_key: str = Security(validate_api_key),
):
    try:
        result = import_service.stage_and_merge(
            source=request.source_url,
            strategy=request.merge_strategy,
        )
        return {"status": "ok", "import_id": str(result.import_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 3.2 Database Schema Additions

```sql
-- Staging tables are created dynamically per import:
CREATE TEMPORARY TABLE _staging_{import_id} AS
  SELECT * FROM live_table WITH NO DATA;

-- Import history
CREATE TABLE import_history (
    id              UUID PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_or_source  TEXT NOT NULL,
    file_name       TEXT,
    rows_added      INT DEFAULT 0,
    rows_updated    INT DEFAULT 0,
    rows_removed    INT DEFAULT 0,
    status          TEXT NOT NULL CHECK (status IN ('success', 'failed', 'rolled_back')),
    error_message   TEXT
);

-- Rollback records
CREATE TABLE import_rollbacks (
    id              UUID PRIMARY KEY,
    import_id       UUID NOT NULL REFERENCES import_history(id),
    reverse_sql     TEXT NOT NULL,
    affected_tables TEXT[] NOT NULL,
    row_count       INT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## 4. Phases

| Phase | Description | Tasks | Effort |
|-------|-------------|-------|--------|
| **1** | **Diff viewer + staging** | Extend `import_service.py` with `stage_data()`, `compute_diff()`, and `merge_staged()`. Build the diff UI (table comparison, colour-coded rows). Write staging table management logic. | 4 days |
| **2** | **Rollback** | Implement `rollback_import()` in `import_service.py`. Store reverse SQL on merge. Add rollback UI button in import history view. Write rollback tests. | 2 days |
| **3** | **Scheduler** | Create `import_scheduler.py`. Build CRUD UI for scheduled jobs (add/edit/delete schedule). Wire QTimer tick logic. Add system tray notifications on job completion. | 3 days |
| **4** | **Webhook** | Create `import_webhook.py` (Flask/FastAPI). Implement API key validation. Add webhook configuration UI. Decide on in-process thread vs. standalone process. | 3 days |
| **5** | **History UI** | Build the import history table view with search/filter. Show diff summary per import. Hook up rollback button. Add visual indicators (success / failed / rolled_back). | 2 days |
| | **Total** | | **14 days** |

## 5. Effort

**Level:** L (Large) — Estimated **14 person-days** total.

### Risk Factors

- **Database locking:** Staging → live merges on large tables may cause row locks. Mitigate with batch-commit and off-peak scheduling.
- **Concurrent imports:** Simultaneous manual and scheduled imports could conflict. Use an import-in-progress mutex / lock file.
- **SSRS export reliability:** Network timeouts or format changes in the SSRS export could break scheduled jobs. Add retry logic with exponential backoff.

## 6. Dependencies

| Dependency | Description |
|------------|-------------|
| [**ARCH-001**](../ARCH-001.md) | Core database abstraction layer — provides the `DatabaseService` used by import staging/merge operations. |
| [**ARCH-003**](../ARCH-003.md) | Plugin / service registry — allows the webhook endpoint and scheduler to be registered as optional plugins without bloating the core app. |

## 7. Appendix: UI Mockups (Text)

### 7.1 Import Diff Dialog

```
┌────────────────────────────────────────────────────────────┐
│  Pre-Import Preview — "sales_report_2025-03-21.csv"       │
├────────────────────────────────────────────────────────────┤
│  ┌─────────┬────────────┬────────────┬──────────────────┐ │
│  │ Action  │ Key (ID)   │ Field      │ Old → New        │ │
│  ├─────────┼────────────┼────────────┼──────────────────┤ │
│  │ + added │ 104        │            │                  │ │
│  │ ~ mod   │ 102        │ amount     │ 150.00 → 175.00  │ │
│  │ ~ mod   │ 102        │ region     │ East → West      │ │
│  │ - del   │ 101        │            │                  │ │
│  └─────────┴────────────┴────────────┴──────────────────┘ │
│                                                            │
│  Summary: +3 added, ~2 modified, -1 removed               │
│                                                            │
│      [ Cancel ]                    [ Import & Merge ]      │
└────────────────────────────────────────────────────────────┘
```

### 7.2 Import History View

```
┌──────────────────────────────────────────────────────────────────┐
│  Import History                                   [ Filter... ] │
├──────┬──────────┬──────────┬──────┬──────┬──────┬──────┬────────┤
│ Date │ Source   │ User     │ +    │ ~    │ -    │Status│ Roll-  │
│      │          │          │      │      │      │      │ back   │
├──────┼──────────┼──────────┼──────┼──────┼──────┼──────┼────────┤
│ 3/21 │ sales..  │ scheduler│ 12   │ 3    │ 1    │ ✅   │ [↩️]   │
│ 3/20 │ inven..  │ admin    │ 8    │ 0    │ 0    │ ✅   │ [↩️]   │
│ 3/19 │ emplo..  │ webhook  │ 0    │ 0    │ 0    │ ❌   │ —      │
│ 3/18 │ sales..  │ admin    │ 45   │ 12   │ 7    │ 🔄   │ [↩️]   │
└──────┴──────────┴──────────┴──────┴──────┴──────┴──────┴────────┘
```
