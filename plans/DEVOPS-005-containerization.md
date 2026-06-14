# DEVOPS-005: Containerization Strategy

**Status**: Draft  
**Priority**: Low  
**Effort**: S (5 days)  
**Depends on**: FEAT-020 (REST API for headless mode)  

---

## Problem Statement

The application runs only as a native desktop app. No containerized deployment exists:

| Scenario | Current | Desired |
|----------|---------|---------|
| API server deployment | N/A | Docker container running FastAPI |
| Sync server deployment | N/A | Docker container running WebSocket server |
| Development environment | Manual venv + PyQt5 | Docker Compose with all services |
| CI build artifacts | PyInstaller binary | Docker images in registry |

---

## Solution

Docker images for three components, orchestrated with Docker Compose.

### Images

```
┌─────────────────────┐     ┌─────────────────────┐
│   unit-tracker-app  │     │  unit-tracker-api   │
│   (PyQt5 GUI)       │     │  (FastAPI, headless) │
│   Port: X11/Wayland │     │  Port: 8420         │
│   Base: python:3.11 │     │  Base: python:3.11  │
│   Slim variant      │     │  Slim variant       │
└─────────────────────┘     └──────────┬──────────┘
                                       │
                              ┌────────▼─────────┐
                              │  unit-tracker-db  │
                              │  (SQLite + volume) │
                              └───────────────────┘
```

### Dockerfile (API)

```dockerfile
# api/Dockerfile
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt fastapi uvicorn

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY api/ ./api/
COPY services/ ./services/
COPY data/ ./data/
COPY sync/ ./sync/

ENV PATH=/root/.local/bin:$PATH
ENV UNIT_TRACKER_DB=/data/schedule.db

EXPOSE 8420

CMD ["uvicorn", "api:create_app", "--host", "0.0.0.0", "--port", "8420"]
```

### Docker Compose

```yaml
# docker-compose.yml
version: "3.9"

services:
  api:
    build:
      context: .
      dockerfile: api/Dockerfile
    ports:
      - "8420:8420"
    volumes:
      - ./data:/data
      - ./config.yaml:/app/config.yaml:ro
    environment:
      - UNIT_TRACKER_DB=/data/schedule.db
    restart: unless-stopped

  sync:
    build:
      context: .
      dockerfile: sync/Dockerfile
    ports:
      - "8421:8421"
    volumes:
      - ./data:/data
      - ./config.yaml:/app/config.yaml:ro
    environment:
      - UNIT_TRACKER_DB=/data/schedule.db
      - SYNC_PORT=8421
    restart: unless-stopped

  app:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ./data:/data
      - ./config.yaml:/app/config.yaml:ro
      - /tmp/.X11-unix:/tmp/.X11-unix:ro  # X11 passthrough
    environment:
      - DISPLAY=${DISPLAY}
      - UNIT_TRACKER_DB=/data/schedule.db
      - QT_QPA_PLATFORM=xcb
    network_mode: host  # X11 requires host network
    profiles:
      - gui  # Only start with: docker compose --profile gui up

  db-backup:
    image: alpine:latest
    volumes:
      - ./data:/data
      - ./backups:/backups
    entrypoint: |
      sh -c "
      while true; do
        cp /data/schedule.db /backups/schedule_\$$(date +%Y%m%d_%H%M%S).db
        find /backups -name '*.db' -mtime +7 -delete
        sleep 86400
      done
      "
    restart: unless-stopped
```

---

## Implementation Phases

### Phase 1: API + Sync Dockerfiles (2 days)
1. Create `api/Dockerfile` with FastAPI + uvicorn
2. Create `sync/Dockerfile` with WebSocket server
3. Build and test API container: `docker compose up api`
4. **Tests**: API responds to curl requests from container

### Phase 2: App Dockerfile (2 days)
1. Create `Dockerfile` for GUI app (base: `python:3.11`, X11 passthrough)
2. Test with `docker compose --profile gui up`
3. **Tests**: App launches with X11 forwarding

### Phase 3: Docker Compose + Production (1 day)
1. Create `docker-compose.yml` with all services
2. Add backup sidecar container
3. Configure GitHub Actions to build and push images to ghcr.io
4. Document deployment in README

---

## Success Criteria

1. `docker compose up api` starts the API server on port 8420
2. `docker compose --profile gui up` starts the GUI app with X11
3. API container runs without GUI dependencies
4. Images published to GitHub Container Registry
5. Development setup: `docker compose up` = full environment

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: API + Sync Dockerfiles | 2 |
| Phase 2: App Dockerfile | 2 |
| Phase 3: Compose + Production | 1 |
| **Total** | **5** |