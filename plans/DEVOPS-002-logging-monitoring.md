# DEVOPS-002: Structured Logging & Error Monitoring

**Status**: Draft  
**Priority**: Medium  
**Effort**: S (5 days)  
**Depends on**: None  

---

## Problem Statement

Current logging is ad-hoc and unstructured:

| Issue | Location | Impact |
|-------|----------|--------|
| `print()` statements | `main.py`, `import_atomsvc.py` | No timestamps, no levels, can't filter |
| Raw `logger.info/error` | Every file | Inconsistent format, no structured data |
| No error tracking | N/A | Silent failures in background threads |
| No log rotation | `faulthandler` writes to `error.log` | Single file grows unbounded |
| No correlation IDs | N/A | Can't trace a save operation across modules |

---

## Solution

Three-layer logging architecture:
1. **Structured logging** via `structlog` — JSON output with correlation IDs
2. **Error monitoring** via Sentry — crash reporting with context
3. **Performance metrics** — operation timing with statsd-compatible output

### Log Format

```json
{
  "event": "Unit saved",
  "timestamp": "2026-06-14T10:30:00.123Z",
  "level": "info",
  "logger": "services.unit_service",
  "correlation_id": "req-abc123",
  "com_number": "252994",
  "duration_ms": 45.2,
  "detailer": "Brandon B",
  "thread": "MainThread"
}
```

### Implementation

```python
# services/logging.py

import json
import logging
import os
import sys
import time
import uuid
from logging.handlers import RotatingFileHandler

import structlog

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer() if sys.stderr and sys.stderr.isatty()
        else structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)


def setup_logging(config: dict) -> None:
    """Configure logging for the entire application.
    
    Config structure:
        logging:
            level: info|debug|warning|error
            file: ~/.unit_tracker/app.log
            max_size_mb: 10
            backup_count: 5
            sentry_dsn: ""
    """
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    
    # File handler (rotating)
    log_file = log_config.get("file", os.path.join(
        os.path.expanduser("~"), ".unit_tracker", "app.log"
    ))
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    max_bytes = log_config.get("max_size_mb", 10) * 1024 * 1024
    backup_count = log_config.get("backup_count", 5)
    
    file_handler = RotatingFileHandler(
        log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setLevel(level)
    
    # Wrap with structlog
    structlog_handler = structlog.stdlib.ProcessorFormatter.wrap_for_formatter(
        file_handler
    )
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # Sentry
    sentry_dsn = log_config.get("sentry_dsn", "")
    if sentry_dsn:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
        sentry_sdk.init(
            dsn=sentry_dsn,
            integrations=[LoggingIntegration(level=level, event_level=logging.ERROR)],
            traces_sample_rate=0.1,
        )
    
    logging.info(f"Logging configured: level={level}, file={log_file}")


class CorrelationIDFilter(logging.Filter):
    """Add correlation_id to every log record."""
    
    _local = threading.local()
    
    @classmethod
    def get_correlation_id(cls) -> str:
        if not hasattr(cls._local, "correlation_id"):
            cls._local.correlation_id = uuid.uuid4().hex[:12]
        return cls._local.correlation_id
    
    @classmethod
    def set_correlation_id(cls, cid: str) -> None:
        cls._local.correlation_id = cid
    
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = self.get_correlation_id()
        return True


# Usage throughout services:
from structlog import get_logger
logger = get_logger(__name__)

def save_unit(db_path, unit):
    logger.info("unit.save.start", com_number=unit.com_number)
    t0 = time.monotonic()
    # ... save logic ...
    elapsed = (time.monotonic() - t0) * 1000
    logger.info("unit.save.complete", com_number=unit.com_number, duration_ms=elapsed)
```

### Config

```yaml
# config.yaml additions
logging:
  level: info                    # debug | info | warning | error
  file: ~/.unit_tracker/app.log  # log file path
  max_size_mb: 10                # max size per file
  backup_count: 5                # number of rotated files to keep
  sentry_dsn: ""                 # Sentry DSN (empty = disabled)
```

---

## Implementation Phases

### Phase 1: Structured Logging with structlog (2 days)
1. Create `services/logging.py` with structlog configuration
2. Replace all `print()` calls with `logger.info/warning/error`
3. Add CorrelationIDFilter to all handlers
4. Add timing decorator for service methods
5. **Tests**: Verify JSON output, correlation IDs, log levels

### Phase 2: Error Monitoring with Sentry (2 days)
1. Add Sentry SDK initialization
2. Configure error event capture (ERROR+ level)
3. Add context (user, version, config) to Sentry events
4. **Tests**: Test DSN configuration, verify error capture

### Phase 3: Performance Metrics (1 day)
1. Add statsd client for operation timing
2. Emit timing metrics for: load, save, import, export, render
3. Add metric configuration to config.yaml
4. **Tests**: Verify metrics emitted to statsd socket

---

## Success Criteria

1. All log output is structured JSON (file) or pretty-printed (console)
2. Every log record has correlation_id
3. Sentry captures all ERROR-level exceptions with full context
4. Log rotation works (verified with large log generation)
5. Performance metrics emitted for all major operations

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Structured Logging | 2 |
| Phase 2: Error Monitoring | 2 |
| Phase 3: Performance Metrics | 1 |
| **Total** | **5** |