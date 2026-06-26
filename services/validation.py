# services/validation.py
"""Validation layer — field rules, validators, and schema enforcement.

Provides:
- FieldRule / UNIT_FIELD_RULES: declarative field validation rules for Unit
- validate_unit(): validate a Unit against field rules
- ValidationError: exception raised on validation failures
- @validate_input / @validate_output: decorators for service methods

Zero Qt dependencies.
"""

from __future__ import annotations

import logging
import re
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from functools import wraps
from typing import Any

from data.models import Unit

logger = logging.getLogger(__name__)

# Type alias: (is_valid, list_of_error_strings)
ValidationResult = tuple[bool, list[str]]

# ---------------------------------------------------------------------------
# Field rules
# ---------------------------------------------------------------------------


@dataclass
class FieldRule:
    """Declarative validation rule for a single Unit field."""

    type_check: type | tuple[type, ...] | None = None
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    enum_values: list[str] | None = None
    pattern: str | None = None  # regex
    nullable: bool = False
    custom_validator: Callable[[Any], str | None] | None = None
    description: str = ""


# Canonical detailer names (matches config.yaml default_detailers)
_DEFAULT_DETAILERS: list[str] = [
    "— Unassigned —",
    "Jackie H",
    "Tommy N",
    "Matthew S",
    "Matthew E",
    "Carl M",
    "Stewart D",
    "David K",
    "Katie D",
    "Kris L",
    "Emilio P",
    "Timothy B",
    "Jeremy B",
    "Brandon B",
    "Tracy V",
    "Tanner D",
]

# Status color values
_STATUS_COLORS: list[str] = ["gray", "yellow", "purple", "orange", "green", "red"]

# Unit field rule definitions — single source of truth
UNIT_FIELD_RULES: dict[str, FieldRule] = {
    "com_number": FieldRule(
        type_check=str,
        min_length=1,
        max_length=20,
        pattern=r"^\d{4,6}$",
        description="Unique COM identifier, 4-6 digits",
    ),
    "job_name": FieldRule(
        type_check=str,
        max_length=255,
        nullable=True,
        description="Job name, max 255 chars",
    ),
    "contract_number": FieldRule(
        type_check=str,
        max_length=50,
        nullable=True,
        description="Top-level contract number",
    ),
    "description": FieldRule(
        type_check=str,
        max_length=500,
        nullable=True,
        description="Unit description",
    ),
    "detailer": FieldRule(
        type_check=str,
        max_length=100,
        enum_values=_DEFAULT_DETAILERS,
        description="Assigned detailer name",
    ),
    "department_hours": FieldRule(
        type_check=(int, float),
        min_value=0,
        max_value=99999,
        description="Department hours, 0-99999",
    ),
    "target_department_hours": FieldRule(
        type_check=(int, float),
        min_value=0,
        max_value=99999,
        description="Target hours, auto-calculated, 0 for non-primary identicals",
    ),
    "iec_internal_hours": FieldRule(
        type_check=(int, float),
        min_value=0,
        max_value=99999,
        description="IEC internal hours",
    ),
    "percent_complete": FieldRule(
        type_check=(int, float),
        min_value=0,
        max_value=100,
        description="Percent complete (0-100 scale, NOT 0-1)",
    ),
    "actual_hours": FieldRule(
        type_check=(int, float),
        min_value=0,
        max_value=99999,
        description="Actual hours logged",
    ),
    "checking_status": FieldRule(
        type_check=str,
        nullable=True,
        max_length=100,
        description="Checking pipeline status",
    ),
    "dr_checks": FieldRule(
        type_check=str,
        nullable=True,
        max_length=100,
        description="DR check status",
    ),
    "dvl_checks": FieldRule(
        type_check=str,
        nullable=True,
        max_length=100,
        description="DVL check status",
    ),
    "actual_hours_to_detail_unit": FieldRule(
        type_check=(int, float),
        min_value=0,
        max_value=99999,
        description="Actual hours to detail unit",
    ),
    "hour_variance": FieldRule(
        type_check=(int, float),
        description="Hour variance",
    ),
    "remaining_demand": FieldRule(
        type_check=(int, float),
        min_value=0,
        max_value=99999,
        description="Remaining demand",
    ),
    "hours_checking": FieldRule(
        type_check=(int, float),
        min_value=0,
        max_value=99999,
        description="Hours checking",
    ),
    "notes": FieldRule(
        type_check=str,
        nullable=True,
        max_length=2000,
        description="Free-text notes",
    ),
    "status_color": FieldRule(
        type_check=str,
        enum_values=_STATUS_COLORS,
        nullable=True,
        description="Computed or manually-assigned status color",
    ),
    "unit_detailing_start_date": FieldRule(nullable=True),
    "unit_moved_to_checking_date": FieldRule(nullable=True),
    "unit_detailing_completion_date": FieldRule(nullable=True),
    "dept_due_date_previous": FieldRule(nullable=True),
    "detailing_due_date": FieldRule(nullable=True),
    "build_date": FieldRule(nullable=True),
}


# ---------------------------------------------------------------------------
# Validation error
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    """Raised when a unit fails validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


# ---------------------------------------------------------------------------
# Field validator
# ---------------------------------------------------------------------------


def validate_unit(
    unit: Unit,
    rules: dict[str, FieldRule] | None = None,
) -> ValidationResult:
    """Validate a Unit against field rules.

    Returns:
        (is_valid, errors) tuple.
    """
    errors: list[str] = []
    rules = rules or UNIT_FIELD_RULES

    DATE_FIELDS = {
        "unit_detailing_start_date",
        "unit_moved_to_checking_date",
        "unit_detailing_completion_date",
        "dept_due_date_previous",
        "detailing_due_date",
        "build_date",
    }
    for field in DATE_FIELDS:
        val = getattr(unit, field, None)
        if val is not None and not isinstance(val, date):
            errors.append(f"{field}: must be a date or None, got {type(val).__name__}")

    for field_name, rule in rules.items():
        value = getattr(unit, field_name, None)

        # Null check
        if value is None:
            if not rule.nullable:
                errors.append(f"{field_name}: is required (cannot be None)")
            continue

        # Type check
        if rule.type_check is not None and not isinstance(value, rule.type_check):
            expected = (
                rule.type_check.__name__
                if isinstance(rule.type_check, type)
                else " | ".join(t.__name__ for t in rule.type_check)
            )
            errors.append(f"{field_name}: expected {expected}, got {type(value).__name__}")
            continue

        # Min/max for numeric
        if (
            rule.min_value is not None
            and isinstance(value, (int, float))
            and value < rule.min_value
        ):
            errors.append(f"{field_name}: minimum {rule.min_value}, got {value}")
        if (
            rule.max_value is not None
            and isinstance(value, (int, float))
            and value > rule.max_value
        ):
            errors.append(f"{field_name}: maximum {rule.max_value}, got {value}")

        # String length
        if isinstance(value, str):
            if rule.min_length is not None and len(value) < rule.min_length:
                errors.append(f"{field_name}: minimum length {rule.min_length}, got {len(value)}")
            if rule.max_length is not None and len(value) > rule.max_length:
                errors.append(f"{field_name}: maximum length {rule.max_length}, got {len(value)}")

        # Enum
        if (
            rule.enum_values is not None
            and isinstance(value, str)
            and value not in rule.enum_values
        ):
            errors.append(f"{field_name}: must be one of {rule.enum_values}, got '{value}'")

        # Pattern
        if (
            rule.pattern is not None
            and isinstance(value, str)
            and not re.match(rule.pattern, value)
        ):
            errors.append(f"{field_name}: must match pattern {rule.pattern}, got '{value}'")

        # Custom validator
        if rule.custom_validator is not None:
            try:
                result = rule.custom_validator(value)
                if result:
                    errors.append(f"{field_name}: {result}")
            except Exception as e:
                errors.append(f"{field_name}: custom validation failed: {e}")

    return (len(errors) == 0, errors)


# ---------------------------------------------------------------------------
# Validation decorators
# ---------------------------------------------------------------------------


def validate_input(**field_rules: FieldRule):
    """Decorator: validate named keyword arguments against field rules.

    Usage:
        @validate_input(department_hours=UNIT_FIELD_RULES["department_hours"])
        def set_hours(self, department_hours: float) -> None: ...
    """

    def decorator(func):
        sig = inspect.signature(func)
        @wraps(func)
        def wrapper(*args, **kwargs):
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            all_args = bound.arguments
            errors = []
            for field_name, rule in field_rules.items():
                if field_name not in all_args:
                    continue
                value = all_args[field_name]
                if value is None and not rule.nullable:
                    errors.append(f"{field_name}: is required")
                    continue
                if value is None:
                    continue
                if (
                    rule.min_value is not None
                    and isinstance(value, (int, float))
                    and value < rule.min_value
                ):
                    errors.append(f"{field_name}: minimum {rule.min_value}")
                if (
                    rule.max_value is not None
                    and isinstance(value, (int, float))
                    and value > rule.max_value
                ):
                    errors.append(f"{field_name}: maximum {rule.max_value}")
            if errors:
                raise ValidationError(errors)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def validate_output(rules: dict[str, FieldRule] | None = None):
    """Decorator: validate the return value of a function against Unit rules.

    Usage:
        @validate_output(UNIT_FIELD_RULES)
        def load_all(self) -> list[Unit]: ...
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
