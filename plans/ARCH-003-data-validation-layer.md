# ARCH-003: Data Validation & Schema Enforcement Layer

**Status**: Draft  
**Priority**: High  
**Effort**: M (10 days)  
**Depends on**: ARCH-001  
**Required by**: QA-001, QA-003, DEVOPS-003  

---

## Problem Statement

The codebase has no centralized validation layer. Data integrity is maintained by convention and luck:

| Issue | Location | Impact |
|-------|----------|--------|
| `percent_complete` scale mismatch (DB 0-1 vs model 0-100) | `data/db.py:126`, `writer.py:67` | Any code path that writes directly to DB gets it wrong |
| No field-level validation | All `Unit` fields accept any value | `department_hours=-5000` would be accepted |
| CSV import has no sanitization | `automation/import_csv.py` | Malformed dates crash; garbage strings pass through |
| No schema version tracking | `data/db.py:_migrate_schema()` | Runs on every connection; can't detect incompatible versions |
| No business rule enforcement | `data/writer.py` | Can save `percent_complete > 100`, `detailer=""`, inconsistent date orders |
| No pre-save hooks | `data/writer.py` | No extensibility point for cross-field validation or derived field computation |

---

## Proposed Solution

A dedicated validation layer with four components:

1. **FieldValidator** — declarative field rules for `Unit` dataclass
2. **Validation decorators** — `@validate_input` / `@validate_output` for service methods
3. **InputSanitizer** — cleaning pipeline for external data (CSV, SSRS)
4. **SchemaMigrationRegistry** — versioned, ordered, rollback-capable migrations
5. **PreSaveHookRegistry** — business rule hooks executed before every save

### Architecture

```
External Data (CSV, SSRS, API)
         │
         ▼
  ┌─────────────┐
  │Sanitizer    │  ← cleans, normalizes, type-coerces
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │Validator    │  ← @validate_input decorator: type, range, enum, pattern checks
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │Service Layer│  ← UnitService, ImportService (ARCH-001)
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │PreSaveHooks │  ← business rules: date order, capacity limits, identicals enforcement
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │DB Writer    │  ← writes to SQLite (existing writer.py)
  └─────────────┘
```

### FieldValidator

```python
# services/validation.py
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Literal

ValidationResult = tuple[bool, list[str]]  # (is_valid, errors)


@dataclass
class FieldRule:
    type_check: type | None = None
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    enum_values: list[str] | None = None
    pattern: str | None = None          # regex
    nullable: bool = False
    custom_validator: Callable | None = None
    description: str = ""


# Field rule definitions for Unit dataclass
UNIT_FIELD_RULES: dict[str, FieldRule] = {
    "com_number": FieldRule(
        type_check=str, min_length=1, max_length=20,
        pattern=r"^\d{4,6}$",  # COM numbers are 4-6 digits
        description="Unique COM identifier, 4-6 digits"
    ),
    "job_name": FieldRule(
        type_check=str, max_length=255, nullable=True,
        description="Job name, max 255 chars"
    ),
    "contract_number": FieldRule(
        type_check=str, max_length=50, nullable=True,
        description="Top-level contract number"
    ),
    "description": FieldRule(
        type_check=str, max_length=500, nullable=True,
        description="Unit description"
    ),
    "detailer": FieldRule(
        type_check=str, max_length=100,
        enum_values=[
            "— Unassigned —", "Jackie H", "Tommy N", "Matthew S",
            "Matthew E", "Carl M", "Stewart D", "David K", "Katie D",
            "Kris L", "Emilio P", "Timothy B", "Jeremy B", "Brandon B",
            "Tracy V", "Tanner D",
        ],
        description="Assigned detailer name"
    ),
    "department_hours": FieldRule(
        type_check=(int, float), min_value=0, max_value=99999,
        description="Department hours, 0-99999"
    ),
    "target_department_hours": FieldRule(
        type_check=(int, float), min_value=0, max_value=99999,
        description="Target hours, auto-calculated, 0 for non-primary identicals"
    ),
    "iec_internal_hours": FieldRule(
        type_check=(int, float), min_value=0, max_value=99999,
        description="IEC internal hours"
    ),
    "percent_complete": FieldRule(
        type_check=(int, float), min_value=0, max_value=100,
        description="Percent complete (0-100 scale, NOT 0-1)"
    ),
    "actual_hours": FieldRule(
        type_check=(int, float), min_value=0, max_value=99999,
        description="Actual hours logged"
    ),
    "checking_status": FieldRule(
        type_check=str, nullable=True, max_length=100,
        description="Checking pipeline status"
    ),
    "notes": FieldRule(
        type_check=str, nullable=True, max_length=2000,
        description="Free-text notes"
    ),
    "status_color": FieldRule(
        type_check=str,
        enum_values=["gray", "yellow", "purple", "orange", "green", "red"],
        description="Computed or manually-assigned status color"
    ),
}


def validate_unit(unit: "Unit", rules: dict[str, FieldRule] | None = None) -> ValidationResult:
    """Validate a Unit against field rules. Returns (is_valid, errors)."""
    errors: list[str] = []
    rules = rules or UNIT_FIELD_RULES
    
    for field_name, rule in rules.items():
        value = getattr(unit, field_name, None)
        
        # Null check
        if value is None and not rule.nullable:
            errors.append(f"{field_name}: is required (cannot be None)")
            continue
        if value is None:
            continue
        
        # Type check
        if rule.type_check is not None:
            if not isinstance(value, rule.type_check):
                errors.append(f"{field_name}: expected {rule.type_check.__name__}, got {type(value).__name__}")
                continue
        
        # Min/max
        if rule.min_value is not None and isinstance(value, (int, float)):
            if value < rule.min_value:
                errors.append(f"{field_name}: minimum {rule.min_value}, got {value}")
        if rule.max_value is not None and isinstance(value, (int, float)):
            if value > rule.max_value:
                errors.append(f"{field_name}: maximum {rule.max_value}, got {value}")
        
        # String length
        if isinstance(value, str):
            if rule.min_length is not None and len(value) < rule.min_length:
                errors.append(f"{field_name}: minimum length {rule.min_length}, got {len(value)}")
            if rule.max_length is not None and len(value) > rule.max_length:
                errors.append(f"{field_name}: maximum length {rule.max_length}, got {len(value)}")
        
        # Enum
        if rule.enum_values is not None and isinstance(value, str):
            if value not in rule.enum_values:
                errors.append(f"{field_name}: must be one of {rule.enum_values}, got '{value}'")
        
        # Pattern
        if rule.pattern is not None and isinstance(value, str):
            import re
            if not re.match(rule.pattern, value):
                errors.append(f"{field_name}: must match pattern {rule.pattern}, got '{value}'")
        
        # Custom validator
        if rule.custom_validator is not None:
            try:
                result = rule.custom_validator(value)
                if isinstance(result, str):
                    errors.append(result)
            except Exception as e:
                errors.append(f"{field_name}: custom validation failed: {e}")
    
    return (len(errors) == 0, errors)
```

### Validation Decorators

```python
# services/validation.py

from functools import wraps


def validate_input(*field_rules: tuple[str, FieldRule]):
    """Decorator: validate method arguments against field rules.
    
    Usage:
        @validate_input(("department_hours", UNIT_FIELD_RULES["department_hours"]))
        def set_hours(self, department_hours: float) -> None:
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            errors = []
            for field_name, rule in field_rules:
                # Look up the argument by name
                if field_name in kwargs:
                    value = kwargs[field_name]
                else:
                    # Try positional — requires binding
                    continue
                # Validate single value
                if value is None and not rule.nullable:
                    errors.append(f"{field_name}: is required")
                    continue
                if rule.min_value is not None and isinstance(value, (int, float)):
                    if value < rule.min_value:
                        errors.append(f"{field_name}: minimum {rule.min_value}")
                if rule.max_value is not None and isinstance(value, (int, float)):
                    if value > rule.max_value:
                        errors.append(f"{field_name}: maximum {rule.max_value}")
            if errors:
                raise ValidationError(errors)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def validate_output(rules: dict[str, FieldRule] | None = None):
    """Decorator: validate the return value of a function.
    
    Usage:
        @validate_output(UNIT_FIELD_RULES)
        def load_all(self) -> list[Unit]:
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if isinstance(result, list):
                for item in result:
                    valid, errs = validate_unit(item, rules)
                    if not valid:
                        raise ValidationError(errs)
            elif result is not None:
                valid, errs = validate_unit(result, rules)
                if not valid:
                    raise ValidationError(errs)
            return result
        return wrapper
    return decorator


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))
```

### InputSanitizer

```python
# services/sanitizer.py

from datetime import datetime


class InputSanitizer:
    """Cleaning pipeline for external data (CSV, SSRS, API)."""
    
    # Accepted date formats (tried in order)
    DATE_FORMATS = [
        "%m/%d/%Y",        # 01/15/2026
        "%Y-%m-%d",        # 2026-01-15
        "%m/%d/%y",        # 01/15/26
        "%d-%b-%Y",        # 15-Jan-2026
        "%Y%m%d",          # 20260115
        "%B %d, %Y",       # January 15, 2026
        "%d-%m-%Y",        # 15-01-2026 (European)
    ]
    
    @staticmethod
    def clean_date(raw: str) -> str | None:
        """Parse and normalize a date string to ISO format YYYY-MM-DD."""
        if not raw or not raw.strip():
            return None
        raw = raw.strip()
        for fmt in InputSanitizer.DATE_FORMATS:
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        raise ValueError(f"Could not parse date: {raw!r}")
    
    @staticmethod
    def clean_percent(raw: str) -> float:
        """Parse percentage string to 0-100 float."""
        if not raw or not raw.strip():
            return 0.0
        cleaned = raw.strip().replace("%", "").replace(",", ".").strip()
        value = float(cleaned)
        if value < 0 or value > 100:
            raise ValueError(f"Percent out of range [0-100]: {value}")
        return value
    
    @staticmethod
    def clean_number(raw: str) -> float | None:
        """Parse a number string, returning None for empty."""
        if not raw or not raw.strip():
            return None
        return float(raw.strip().replace(",", ""))
    
    @staticmethod
    def clean_com_number(raw: str) -> str:
        """Normalize COM number: strip leading zeros, uppercase."""
        cleaned = raw.strip().upper()
        # Remove any non-alphanumeric prefix
        while cleaned and not cleaned[0].isdigit():
            cleaned = cleaned[1:]
        return cleaned
    
    @staticmethod
    def clean_string(raw: str, max_length: int | None = None) -> str | None:
        """Trim whitespace, collapse multiple spaces, None for empty."""
        if not raw or not raw.strip():
            return None
        import re
        cleaned = re.sub(r'\s+', ' ', raw.strip())
        if max_length and len(cleaned) > max_length:
            cleaned = cleaned[:max_length]
        return cleaned
```

### SchemaMigrationRegistry

```python
# services/migration_registry.py

from dataclasses import dataclass, field
from datetime import datetime
import hashlib


@dataclass
class Migration:
    version: int
    description: str
    up_sql: str
    down_sql: str | None = None  # rollback script
    checksum: str = field(init=False)
    applied_at: str | None = None
    
    def __post_init__(self):
        self.checksum = hashlib.sha256(
            (self.up_sql + (self.down_sql or "")).encode()
        ).hexdigest()[:16]


class SchemaMigrationRegistry:
    """Versioned, ordered, rollback-capable schema migrations.
    
    Storage: SQLite table `_schema_migrations`:
        version INTEGER PRIMARY KEY,
        description TEXT,
        checksum TEXT,
        applied_at TEXT,
        duration_ms INTEGER
    """
    
    def __init__(self, conn):
        self._conn = conn
        self._ensure_migrations_table()
    
    def _ensure_migrations_table(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS _schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now')),
                duration_ms INTEGER
            )
        """)
        self._conn.commit()
    
    def current_version(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM _schema_migrations"
        ).fetchone()
        return row[0] if row else 0
    
    def pending(self, migrations: list[Migration]) -> list[Migration]:
        applied = {
            r[0] for r in self._conn.execute(
                "SELECT version FROM _schema_migrations"
            ).fetchall()
        }
        return [m for m in migrations if m.version not in applied]
    
    def apply(self, migration: Migration) -> None:
        import time
        t0 = time.perf_counter()
        try:
            self._conn.executescript(migration.up_sql)
            elapsed = int((time.perf_counter() - t0) * 1000)
            self._conn.execute(
                "INSERT INTO _schema_migrations "
                "(version, description, checksum, applied_at, duration_ms) "
                "VALUES (?, ?, ?, datetime('now'), ?)",
                (migration.version, migration.description, migration.checksum, elapsed)
            )
            self._conn.commit()
        except Exception as e:
            self._conn.rollback()
            raise RuntimeError(f"Migration v{migration.version} failed: {e}")
    
    def rollback(self, migration: Migration) -> None:
        if not migration.down_sql:
            raise RuntimeError(f"Migration v{migration.version} has no rollback")
        self._conn.executescript(migration.down_sql)
        self._conn.execute(
            "DELETE FROM _schema_migrations WHERE version = ?",
            (migration.version,)
        )
        self._conn.commit()
```

### PreSaveHookRegistry

```python
# services/pre_save_hooks.py

from dataclasses import dataclass, field
from typing import Callable


PreSaveHook = Callable[["Unit", dict], list[str]]  # (unit, context) -> warnings


class PreSaveHookRegistry:
    """Registry of business rule hooks executed before every save.
    
    Hooks can:
    - Modify the unit (e.g., recalculate derived fields)
    - Return warnings (non-fatal issues)
    - Raise ValidationError (fatal issues, blocks save)
    """
    
    def __init__(self):
        self._hooks: list[tuple[str, PreSaveHook, int]] = []  # (name, hook, priority)
    
    def register(self, name: str, hook: PreSaveHook, priority: int = 100) -> None:
        self._hooks.append((name, hook, priority))
        self._hooks.sort(key=lambda x: x[2])  # lower priority runs first
    
    def run_all(self, unit: "Unit", context: dict | None = None) -> list[str]:
        """Execute all hooks. Returns list of warning messages.
        Raises ValidationError if any hook raises it."""
        warnings: list[str] = []
        ctx = context or {}
        for name, hook, priority in self._hooks:
            try:
                result = hook(unit, ctx)
                if result:
                    warnings.extend(result)
            except ValidationError:
                raise
            except Exception as e:
                warnings.append(f"Hook '{name}': {e}")
        return warnings


# Default hooks
def _check_percent_complete_range(unit, ctx):
    if unit.percent_complete < 0 or unit.percent_complete > 100:
        raise ValidationError([f"percent_complete must be 0-100, got {unit.percent_complete}"])
    return []

def _check_date_order(unit, ctx):
    """Ensure milestone dates are in chronological order."""
    dates = [
        ("unit_detailing_start_date", unit.unit_detailing_start_date),
        ("unit_moved_to_checking_date", unit.unit_moved_to_checking_date),
        ("unit_detailing_completion_date", unit.unit_detailing_completion_date),
        ("detailing_due_date", unit.detailing_due_date),
    ]
    valid_dates = [(n, d) for n, d in dates if d is not None]
    warnings = []
    for i in range(len(valid_dates) - 1):
        if valid_dates[i][1] > valid_dates[i + 1][1]:
            warnings.append(
                f"{valid_dates[i][0]} ({valid_dates[i][1]}) is after "
                f"{valid_dates[i+1][0]} ({valid_dates[i+1][1]})"
            )
    return warnings


# Register defaults
DEFAULT_HOOK_REGISTRY = PreSaveHookRegistry()
DEFAULT_HOOK_REGISTRY.register("percent_complete_range", _check_percent_complete_range, priority=10)
DEFAULT_HOOK_REGISTRY.register("date_order", _check_date_order, priority=20)
```

---

## Implementation Phases

### Phase 1: Field Validators (3 days)
1. Implement `FieldRule` dataclass and `UNIT_FIELD_RULES` dict
2. Implement `validate_unit()` function
3. Write `@validate_input` / `@validate_output` decorators
4. **Tests**: Test each field rule type (type, range, enum, pattern, custom), test edge cases

### Phase 2: Schema Migration System (3 days)
1. Implement `Migration` and `SchemaMigrationRegistry`
2. Add `_schema_migrations` table to initial schema creation
3. Move existing ad-hoc migrations (`_migrate_schema` in `db.py`) into registry
4. **Tests**: Test apply, rollback, pending detection, checksum verification

### Phase 3: Input Sanitization Pipeline (2 days)
1. Implement `InputSanitizer` with all date/number/string cleaners
2. Wire sanitizer into CSV import before upsert
3. Wire sanitizer into SSRS import
4. **Tests**: Test all date formats, edge cases (nulls, malformed, UTF-8 BOM)

### Phase 4: Pre-Save Hooks + Integration (2 days)
1. Implement `PreSaveHookRegistry` with default hooks
2. Wire hooks into `save_unit()` in writer.py (via UnitService)
3. **Tests**: Test hooks block/fail correctly, verify `_check_date_order` catches violations

---

## Success Criteria

1. 100% of `Unit` dataclass instantiations go through `validate_unit()`
2. 100% of `save_unit()` calls run through pre-save hooks
3. 0 `percent_complete` scale bugs (measured by monitoring)
4. All CSV imports pass through `InputSanitizer`
5. `SchemaMigrationRegistry` tracks every schema change with checksum verification
6. Test coverage > 90% for validation layer

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Validation too strict, breaks existing data | Medium | Run validator in "warn only" mode first; collect errors without blocking |
| Migration system conflicts with existing `_migrate_schema` | Medium | Phase 2 replaces `_migrate_schema` entirely; verify parity |
| Performance overhead of validation on every save | Low | Sub-millisecond per field; negligible compared to SQLite write |

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Field Validators | 3 |
| Phase 2: Schema Migration | 3 |
| Phase 3: Input Sanitizer | 2 |
| Phase 4: Pre-Save Hooks | 2 |
| **Total** | **10** |