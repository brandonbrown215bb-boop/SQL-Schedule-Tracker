# FEAT-020: REST API Layer

**Status**: Draft  
**Priority**: Medium  
**Effort**: L (12 days)  
**Depends on**: ARCH-001, ARCH-002, FEAT-017  
**Enables**: Mobile companion, PowerBI integration, Slack bot, CI/CD integration  

---

## Problem Statement

The application has no programmatic API. All data access goes through the PyQt5 GUI:

| Integration | Status | Pain Point |
|------------|--------|------------|
| PowerBI dashboard | Impossible | No REST endpoint to query data |
| Slack bot (due dates, alerts) | Impossible | No API to trigger or query |
| Mobile companion app | Impossible | No API backend |
| CI/CD pipeline (auto-import) | Impossible | Import requires human clicking buttons |
| External script ingestion | Impossible | Must parse SQLite directly, fragile |
| Automated testing | Manual only | No HTTP-level test harness |

---

## Proposed Solution

A FastAPI-based REST API layer that reuses the service layer (ARCH-001) and exposes all core functionality via HTTP and WebSocket.

### Architecture

```
┌──────────────┐     HTTP/WS      ┌────────────────────┐
│  External     │ ────────────────→ │  FastAPI App       │
│  Clients      │ ←──────────────── │  (api/)            │
│  (PowerBI,    │                  │                    │
│   mobile,     │                  │  ┌──────────────┐  │
│   Slack, ...) │                  │  │AuthMiddleware │  │
└──────────────┘                  │  └──────┬───────┘  │
                                   │         │          │
                                   │  ┌──────▼───────┐  │
                                   │  │ Pydantic     │  │
                                   │  │ Models       │  │
                                   │  └──────┬───────┘  │
                                   │         │          │
                                   │  ┌──────▼───────┐  │
                                   │  │ Routers      │  │
                                   │  │  /api/units  │  │
                                   │  │  /api/import │  │
                                   │  │  /api/analyt │  │
                                   │  │  /api/sync   │  │
                                   │  └──────┬───────┘  │
                                   │         │          │
                                   │  ┌──────▼───────┐  │
                                   │  │ Service Layer │  │
                                   │  │ (ARCH-001)   │  │
                                   │  └──────────────┘  │
                                   └────────────────────┘
```

### Package Structure

```
api/
├── __init__.py              # FastAPI app factory
├── config.py                # API config (host, port, auth)
├── auth.py                  # API key + JWT authentication
├── deps.py                  # Dependency injection for services
├── routers/
│   ├── __init__.py
│   ├── units.py             # GET/PUT /api/units
│   ├── import_routes.py     # POST /api/import
│   ├── analytics.py         # GET /api/analytics/*
│   ├── sync.py              # GET /api/sync/*
│   └── ws.py                # WebSocket /ws/live
├── models/
│   ├── __init__.py
│   ├── unit.py              # Pydantic models for Unit
│   ├── import_models.py     # Import request/response
│   └── analytics.py         # Analytics response models
└── middleware/
    ├── __init__.py
    ├── auth_middleware.py    # API key validation on every request
    ├── error_handler.py     # Structured error responses
    └── request_logger.py    # Request/response logging
```

### Pydantic Models

```python
# api/models/unit.py

from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator


class UnitResponse(BaseModel):
    """Full unit representation returned by API."""
    com_number: str = Field(..., pattern=r"^\d{4,6}$")
    job_name: str | None = None
    contract_number: str | None = None
    description: str | None = None
    detailer: str | None = None
    checking_status: str | None = None
    notes: str | None = None
    
    department_hours: float = 0.0
    target_department_hours: float = 0.0
    iec_internal_hours: float = 0.0
    percent_complete: float = Field(..., ge=0, le=100)
    actual_hours: float = 0.0
    
    status_color: str = "gray"
    alert_level: str = "UNSET"
    
    unit_detailing_start_date: date | None = None
    unit_moved_to_checking_date: date | None = None
    unit_detailing_completion_date: date | None = None
    detailing_due_date: date | None = None
    dept_due_date_previous: date | None = None
    build_date: date | None = None
    
    updated_at: str = ""
    version_stamp: str = ""
    
    class Config:
        from_attributes = True


class UnitUpdateRequest(BaseModel):
    """Fields that can be updated via API."""
    job_name: str | None = None
    contract_number: str | None = None
    description: str | None = None
    detailer: str | None = None
    checking_status: str | None = None
    notes: str | None = None
    department_hours: float | None = Field(None, ge=0)
    iec_internal_hours: float | None = Field(None, ge=0)
    percent_complete: float | None = Field(None, ge=0, le=100)
    actual_hours: float | None = Field(None, ge=0)
    unit_detailing_start_date: date | None = None
    unit_moved_to_checking_date: date | None = None
    unit_detailing_completion_date: date | None = None
    detailing_due_date: date | None = None
    build_date: date | None = None
    version_stamp: str | None = None  # optimistic lock token


class UnitListParams(BaseModel):
    """Query parameters for listing units."""
    detailer: str | None = None
    status: str | None = None  # gray/yellow/purple/orange/green/red
    alert: str | None = None  # OVERDUE/URGENT/APPROACHING/ON_TRACK
    date_from: date | None = None
    date_to: date | None = None
    search: str | None = None
    sort_by: str = "detailing_due_date"
    sort_asc: bool = True
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=1000)


class PaginatedResponse(BaseModel):
    data: list[UnitResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
```

### Endpoint Specifications

```python
# api/routers/units.py

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/api/units", tags=["units"])


@router.get("", response_model=PaginatedResponse)
async def list_units(
    params: UnitListParams = Depends(),
    service: UnitService = Depends(get_unit_service),
):
    """List all units with filtering, sorting, and pagination.
    
    Query parameters:
    - detailer: Filter by detailer name
    - status: Filter by status color
    - alert: Filter by alert level
    - date_from/date_to: Filter by due date range
    - search: Search COM number, job name, description
    - sort_by/sort_asc: Sort column and direction
    - page/page_size: Pagination
    
    Returns paginated unit list with total count.
    """
    units = service.load_all()
    # Apply filters
    if params.detailer:
        units = [u for u in units if u.detailer == params.detailer]
    if params.status:
        units = [u for u in units if u.calculated_status_color == params.status]
    if params.search:
        q = params.search.lower()
        units = [u for u in units if q in u.com_number.lower() or q in (u.job_name or "").lower()]
    
    total = len(units)
    start = (params.page - 1) * params.page_size
    end = start + params.page_size
    page_units = units[start:end]
    
    return PaginatedResponse(
        data=[UnitResponse.from_unit(u) for u in page_units],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=(total + params.page_size - 1) // params.page_size,
    )


@router.get("/{com_number}", response_model=UnitResponse)
async def get_unit(
    com_number: str,
    service: UnitService = Depends(get_unit_service),
):
    """Get a single unit by COM number."""
    unit = service.get_by_com(com_number)
    if unit is None:
        raise HTTPException(status_code=404, detail=f"Unit {com_number} not found")
    return UnitResponse.from_unit(unit)


@router.put("/{com_number}", response_model=UnitResponse)
async def update_unit(
    com_number: str,
    update: UnitUpdateRequest,
    service: UnitService = Depends(get_unit_service),
):
    """Update a unit with optimistic locking.
    
    Requires `version_stamp` (updated_at) for conflict detection.
    Returns the updated unit on success, 409 Conflict on version mismatch.
    """
    unit = service.get_by_com(com_number)
    if unit is None:
        raise HTTPException(status_code=404, detail=f"Unit {com_number} not found")
    
    # Apply updates
    update_data = update.model_dump(exclude_none=True, exclude={"version_stamp"})
    for field, value in update_data.items():
        setattr(unit, field, value)
    
    try:
        saved = service.save(unit, update.version_stamp or unit.updated_at)
        return UnitResponse.from_unit(saved)
    except ConcurrentEditError as e:
        raise HTTPException(
            status_code=409,
            detail=f"Conflict: unit was modified by another user. {e}",
        )


# api/routers/import_routes.py

@router.post("/api/import", response_model=ImportResponse)
async def trigger_import(
    request: ImportRequest,
    service: ImportService = Depends(get_import_service),
):
    """Trigger a CSV or SSRS import.
    
    For CSV imports, provide `csv_path`. For SSRS, provide `ssrs_url`.
    Returns immediately with a `job_id` for polling.
    """
    job_id = str(uuid.uuid4())[:8]
    # Launch import in background thread
    thread = threading.Thread(
        target=_run_import,
        args=(job_id, request, service),
        daemon=True,
    )
    thread.start()
    return ImportResponse(job_id=job_id, status="started")


# WebSocket for live updates
# api/routers/ws.py

@router.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time unit updates.
    
    Messages:
    - {"type": "subscribe", "com": "12345"} — subscribe to unit changes
    - {"type": "unsubscribe", "com": "12345"} — unsubscribe
    - Server push: {"type": "unit_updated", "com": "12345", "data": {...}}
    - Server push: {"type": "import_complete", "job_id": "...", "stats": {...}}
    - Server push: {"type": "presence", "users": ["user1", "user2"]}
    """
    await websocket.accept()
    # Register with event bus
    ...
```

### Authentication

```python
# api/auth.py

from fastapi import Header, HTTPException
from pydantic import BaseModel


API_KEYS: dict[str, str] = {}  # key → role, loaded from config or env


async def verify_api_key(x_api_key: str = Header(None)) -> str:
    """Verify API key from header. 
    
    API keys are loaded from:
    1. config.yaml: api.keys
    2. Environment variable: UNIT_TRACKER_API_KEYS
    3. Auto-generated on first run (printed to logs)
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    role = API_KEYS.get(x_api_key)
    if role is None:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return role


# Config.yaml additions:
# api:
#   enabled: true
#   host: "127.0.0.1"
#   port: 8420
#   keys:
#     "sk-abc123": "readonly"
#     "sk-def456": "readwrite"
```

### OpenAPI Specification (auto-generated by FastAPI)

The API will be self-documenting via OpenAPI at `/docs` (Swagger UI) and `/redoc` (ReDoc):

```yaml
openapi: 3.1.0
info:
  title: Unit Tracker API
  version: 2.0.0
paths:
  /api/units:
    get:
      summary: List all units
      parameters:
        - name: detailer
          in: query
          schema: { type: string }
        - name: page
          in: query
          schema: { type: integer, default: 1 }
      responses:
        "200":
          description: Paginated unit list
  /api/units/{com_number}:
    get:
      summary: Get single unit
    put:
      summary: Update unit
      requestBody:
        content:
          application/json:
            schema: UnitUpdateRequest
  /api/import:
    post:
      summary: Trigger CSV/SSRS import
  /ws/live:
    get:
      summary: WebSocket for live updates
```

### Running the API

```python
# api/__init__.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import units, import_routes, analytics, sync, ws
from api.middleware import error_handler, request_logger


def create_app() -> FastAPI:
    app = FastAPI(
        title="Unit Tracker API",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(units.router)
    app.include_router(import_routes.router)
    app.include_router(analytics.router)
    app.include_router(sync.router)
    app.include_router(ws.router)
    
    app.add_exception_handler(Exception, error_handler.handler)
    app.middleware("http")(request_logger.log_middleware)
    
    return app
```

---

## Implementation Phases

### Phase 1: FastAPI Foundation + Unit Endpoints (4 days)
1. Create `api/` package with app factory, config, deps
2. Implement Pydantic models: `UnitResponse`, `UnitUpdateRequest`, `UnitListParams`, `PaginatedResponse`
3. Implement `GET /api/units`, `GET /api/units/{com}`, `PUT /api/units/{com}`
4. Implement dependency injection for `UnitService`
5. **Tests**: HTTPX-based integration tests against test database

### Phase 2: Import + Analytics Endpoints (3 days)
1. Implement `POST /api/import` with background job processing
2. Implement `GET /api/analytics/risk` and `GET /api/analytics/workload`
3. Implement `GET /api/sync/sessions`
4. **Tests**: Test import endpoint with mock CSV files, test analytics aggregation

### Phase 3: WebSocket Live Updates (3 days)
1. Implement WebSocket endpoint at `/ws/live`
2. Wire into `ApplicationStore` event bus for live push
3. Implement subscribe/unsubscribe pattern per COM number
4. **Tests**: WebSocket connection test, verify message delivery on unit update

### Phase 4: Auth + Documentation (2 days)
1. Implement API key authentication middleware
2. Implement JWT-based auth for session tokens
3. Add rate limiting middleware
4. Configure auto-generated OpenAPI docs
5. Write README with curl examples
6. **Tests**: Auth tests with valid/invalid/missing keys

---

## Success Criteria

1. All endpoints return correct data and handle errors gracefully
2. API can be started as standalone process: `python -m api --port 8420`
3. Swagger UI at `/docs` shows complete, accurate API documentation
4. Authentication blocks unauthorized requests with 401/403
5. WebSocket delivers live updates within 100ms of state change
6. API server handles 100+ concurrent requests without degradation

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Service layer not thread-safe | Medium | Use thread-local DB connections (already exists in db.py) |
| WebSocket performance with 1000+ units | Low | Only subscribe to changed units; batch updates |
| Auth key leakage | Medium | Generate keys on first run; log warning on first request |
| API versioning breaks clients | Low | Use `/api/v2/` prefix for future breaking changes |

---

## Effort Estimate

| Phase | Days | Dependencies |
|-------|------|-------------|
| Phase 1: Foundation + Units | 4 | ARCH-001 |
| Phase 2: Import + Analytics | 3 | Phase 1, FEAT-017 |
| Phase 3: WebSocket | 3 | Phase 1, ARCH-002 |
| Phase 4: Auth + Docs | 2 | Phase 1 |
| **Total** | **12** | |