# services/pre_save_hooks.py
"""PreSaveHookRegistry — business rule hooks executed before every save.

Hooks can:
- Modify the unit (e.g., recalculate derived fields)
- Return warnings (non-fatal issues logged but save proceeds)
- Raise ValidationError (fatal issues, blocks save)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from data.models import Unit
from services.validation import ValidationError

logger = logging.getLogger(__name__)

# Type: (unit, context) -> list of warning strings
PreSaveHook = Callable[[Unit, dict], list[str]]


@dataclass
class _HookEntry:
    name: str
    hook: PreSaveHook
    priority: int  # lower = runs first


class PreSaveHookRegistry:
    """Registry of business rule hooks executed before every save.

    Usage:
        registry = PreSaveHookRegistry()
        registry.register("date_order", date_order_hook, priority=10)
        registry.register("auto_target", auto_target_hook, priority=20)

        warnings = registry.run_all(unit, {"is_new": False})
    """

    def __init__(self):
        self._hooks: list[_HookEntry] = []

    def register(
        self,
        name: str,
        hook: PreSaveHook,
        priority: int = 100,
    ) -> None:
        """Register a pre-save hook.

        Args:
            name: Unique hook name (for logging/debugging).
            hook: Callable that receives (unit, context) and returns warning strings.
            priority: Lower values run first. Default 100.
        """
        self._hooks.append(_HookEntry(name=name, hook=hook, priority=priority))
        self._hooks.sort(key=lambda e: e.priority)
        logger.debug("Registered pre-save hook '%s' (priority=%d)", name, priority)

    def unregister(self, name: str) -> None:
        """Remove a hook by name."""
        self._hooks = [e for e in self._hooks if e.name != name]

    def run_all(
        self,
        unit: Unit,
        context: dict | None = None,
    ) -> list[str]:
        """Execute all hooks. Returns list of warning messages.

        Raises:
            ValidationError: If any hook raises it (fatal, blocks save).
        """
        warnings: list[str] = []
        ctx = context or {}
        for entry in self._hooks:
            try:
                result = entry.hook(unit, ctx)
                if result:
                    warnings.extend(result)
                    for w in result:
                        logger.warning("Pre-save hook '%s': %s", entry.name, w)
            except ValidationError:
                raise
            except Exception as e:
                logger.error("Pre-save hook '%s' raised unexpected error: %s", entry.name, e)
                warnings.append(f"Internal validation error in hook '{entry.name}': {e}")
        return warnings


# ---------------------------------------------------------------------------
# Built-in hooks
# ---------------------------------------------------------------------------


def date_order_hook(unit: Unit, context: dict) -> list[str]:
    """Warn if milestone dates are out of order."""
    warnings: list[str] = []
    dates = [
        ("Detailing Start", unit.unit_detailing_start_date),
        ("Moved to Checking", unit.unit_moved_to_checking_date),
        ("Detailing Complete", unit.unit_detailing_completion_date),
    ]
    set_dates = [(name, d) for name, d in dates if d is not None]
    if len(set_dates) >= 2:
        for i in range(len(set_dates) - 1):
            name_a, date_a = set_dates[i]
            name_b, date_b = set_dates[i + 1]
            if date_a > date_b:
                warnings.append(f"Date order: {name_a} ({date_a}) is after {name_b} ({date_b})")
    return warnings


def non_primary_identical_hook(unit: Unit, context: dict) -> list[str]:
    """Enforce non-primary identical rules: counted target hours must be 0."""
    if unit.is_non_primary_identical:
        unit.target_department_hours = 0.0
    return []


def target_hours_hook(unit: Unit, context: dict) -> list[str]:
    """Derive target_department_hours: Dept - IEC + adjustment, 0 for cancelled units and non-primary identicals.

    Target hours are never typed directly; a correction goes in target_adjustment_hours.
    """
    unit.target_department_hours = unit.counted_target_hours
    return []


def target_adjustment_reason_hook(unit: Unit, context: dict) -> list[str]:
    """A target adjustment must say why (fatal if not)."""
    if abs(unit.target_adjustment_hours or 0.0) > 1e-9 and not (unit.target_adjustment_reason or "").strip():
        raise ValidationError(["target_adjustment_reason: required when Target Adjustment is not 0"])
    return []


def percent_complete_range_hook(unit: Unit, context: dict) -> list[str]:
    """Validate percent_complete is in valid range (fatal if not)."""
    if not (0.0 <= unit.percent_complete <= 100.0):
        raise ValidationError([f"percent_complete must be 0-100, got {unit.percent_complete}"])
    return []


def non_negative_hours_hook(unit: Unit, context: dict) -> list[str]:
    """Validate numeric hour fields are non-negative (fatal if not)."""
    errors: list[str] = []
    if unit.department_hours < 0:
        errors.append(f"department_hours must be >= 0, got {unit.department_hours}")
    if unit.actual_hours < 0:
        errors.append(f"actual_hours must be >= 0, got {unit.actual_hours}")
    if unit.target_department_hours < 0:
        errors.append(f"target_department_hours must be >= 0, got {unit.target_department_hours}")
    if errors:
        raise ValidationError(errors)
    return []
