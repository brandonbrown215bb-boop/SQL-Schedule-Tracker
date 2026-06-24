# data/writer.py
"""Data writer — saves units to SQLite database.

Uses the validation layer (services.validation) for field validation
and supports pre-save hooks via PreSaveHookRegistry.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from data.db import _working_days_between, get_db, log_field_changes
from data.models import Unit

if TYPE_CHECKING:
    from services.pre_save_hooks import PreSaveHookRegistry

logger = logging.getLogger(__name__)


class ConcurrentEditError(Exception):
    """Raised when optimistic locking detects a concurrent edit conflict."""


def _validate_unit(unit: Unit) -> None:
    """Validate unit fields before saving using the validation layer.

    Raises:
        ValidationError: If any field value is out of valid range.
    """
    # Lazy import to avoid circular dependency:
    # data/writer -> services.validation -> services/__init__ -> services.unit_service -> data/writer
    from services.validation import ValidationError, validate_unit

    valid, errors = validate_unit(unit)
    if not valid:
        raise ValidationError(errors)


def save_unit(
    db_path: str,
    unit: Unit,
    hook_registry: PreSaveHookRegistry | None = None,
    context: dict | None = None,
) -> list[str]:
    """Write a unit's data to the SQLite database.

    Updates all operator-editable fields for the row matching unit.com_number.
    Uses optimistic locking: if the row's updated_at timestamp has changed since
    the unit was loaded, raises ConcurrentEditError to signal a conflict.

    Args:
        db_path: Path to the SQLite database.
        unit: The unit to write.
        hook_registry: Optional PreSaveHookRegistry for business rule hooks.
        context: Optional context dict passed to hooks (e.g., {"is_new": True}).

    Returns:
        List of warning strings from pre-save hooks (non-fatal issues).

    Raises:
        ValidationError: If any field value is out of valid range.
        ConcurrentEditError: If another user modified the row after it was loaded.
    """
    # Phase 1: Field-level validation
    _validate_unit(unit)

    # Phase 2: Pre-save hooks (business rules)
    warnings: list[str] = []
    if hook_registry is not None:
        warnings = hook_registry.run_all(unit, context or {})

    # Phase 3: Write to DB
    conn = get_db(db_path)
    old_row = conn.execute(
        "SELECT * FROM units WHERE com_number = ?",
        (unit.com_number,),
    ).fetchone()

    if unit.updated_at:  # Has a timestamp — match it exactly
        where_clause = "WHERE com_number = ? AND updated_at = ?"
        where_params: tuple = (unit.com_number, unit.updated_at)
    else:
        where_clause = "WHERE com_number = ? AND updated_at IS NULL"
        where_params = (unit.com_number,)

    # Calculate week_ending_friday dynamically if detailing_due_date is set
    from datetime import timedelta
    if unit.detailing_due_date:
        unit.week_ending_friday = unit.detailing_due_date + timedelta(days=(4 - unit.detailing_due_date.weekday()) % 7)
    else:
        unit.week_ending_friday = None

    cursor = conn.execute(
        f"""
        UPDATE units SET
            job_name = ?,
            top_level_number = ?,
            description = ?,
            detailer = ?,
            checking_status = ?,
            dr_checks = ?,
            dvl_checks = ?,
            department_hours = ?,
            percent_complete = ?,
            actual_hours = ?,
            target_dept_hours = MAX(0, ?),
            iec_internal_hours = ?,
            dept_due_date_previous = ?,
            detailing_due_date = ?,
            build_date = ?,
            unit_detailing_start_date = ?,
            unit_moved_to_checking_date = ?,
            unit_detailing_completion_date = ?,
            notes = ?,
            status_color = ?,
            working_days_in_checking = ?,
            remaining_hours = ?,
            week_ending_friday = ?,
            updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')
        {where_clause}
    """,
        (
            unit.job_name,
            unit.contract_number,
            unit.description,
            unit.detailer,
            unit.checking_status,
            unit.dr_checks,
            unit.dvl_checks,
            unit.department_hours,
            unit.percent_complete / 100,
            unit.actual_hours,
            # restore original target_dept_hours for non-primary identicals
            getattr(unit, '_original_target_department_hours', unit.target_department_hours),
            unit.iec_internal_hours,
            unit.dept_due_date_previous.isoformat() if unit.dept_due_date_previous else None,
            unit.detailing_due_date.isoformat() if unit.detailing_due_date else None,
            unit.build_date.isoformat() if unit.build_date else None,
            unit.unit_detailing_start_date.isoformat() if unit.unit_detailing_start_date else None,
            unit.unit_moved_to_checking_date.isoformat()
            if unit.unit_moved_to_checking_date
            else None,
            unit.unit_detailing_completion_date.isoformat()
            if unit.unit_detailing_completion_date
            else None,
            unit.notes,
            unit.calculated_status_color,
            _working_days_between(
                unit.unit_moved_to_checking_date.isoformat()
                if unit.unit_moved_to_checking_date
                else None,
                unit.unit_detailing_completion_date.isoformat()
                if unit.unit_detailing_completion_date
                else None,
            ),
            (unit.department_hours or 0.0) * (1.0 - (unit.percent_complete or 0.0) / 100.0),
            unit.week_ending_friday.isoformat() if unit.week_ending_friday else None,
            *where_params,
        ),
    )

    if cursor.rowcount == 0:
        conn.rollback()
        raise ConcurrentEditError(
            f"COM {unit.com_number} was modified by another user after you loaded it. "
            "Your changes were not saved."
        )

    # Audit trail
    new_values = {
        "job_name": unit.job_name,
        "top_level_number": unit.contract_number,
        "description": unit.description,
        "detailer": unit.detailer,
        "checking_status": unit.checking_status,
        "dr_checks": unit.dr_checks,
        "dvl_checks": unit.dvl_checks,
        "department_hours": unit.department_hours,
        "percent_complete": unit.percent_complete / 100,
        "actual_hours": unit.actual_hours,
        "target_dept_hours": unit.target_department_hours,
        "iec_internal_hours": unit.iec_internal_hours,
        "dept_due_date_previous": unit.dept_due_date_previous.isoformat()
        if unit.dept_due_date_previous
        else None,
        "detailing_due_date": unit.detailing_due_date.isoformat()
        if unit.detailing_due_date
        else None,
        "build_date": unit.build_date.isoformat() if unit.build_date else None,
        "unit_detailing_start_date": unit.unit_detailing_start_date.isoformat()
        if unit.unit_detailing_start_date
        else None,
        "unit_moved_to_checking_date": unit.unit_moved_to_checking_date.isoformat()
        if unit.unit_moved_to_checking_date
        else None,
        "unit_detailing_completion_date": unit.unit_detailing_completion_date.isoformat()
        if unit.unit_detailing_completion_date
        else None,
        "notes": unit.notes,
        "status_color": unit.calculated_status_color,
        "week_ending_friday": unit.week_ending_friday.isoformat()
        if unit.week_ending_friday
        else None,
    }
    log_field_changes(conn, unit.com_number, old_row, new_values)

    refreshed = conn.execute(
        "SELECT updated_at FROM units WHERE com_number = ?",
        (unit.com_number,),
    ).fetchone()
    if refreshed:
        unit.updated_at = refreshed["updated_at"] if hasattr(refreshed, "keys") else refreshed[0]

    conn.commit()
    logger.info(f"Saved unit {unit.com_number} to SQLite")

    return warnings
