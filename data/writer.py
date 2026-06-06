# data/writer.py
"""Data writer — saves units to SQLite database."""
import logging

from data.db import get_db
from data.models import Unit

logger = logging.getLogger(__name__)


def save_unit(
    db_path: str,
    unit: Unit,
) -> None:
    """Write a unit's data to the SQLite database.
    
    Updates all operator-editable fields for the row matching unit.com_number.
    Uses optimistic locking: if the row's updated_at timestamp has changed since
    the unit was loaded, raises ConcurrentEditError to signal a conflict.
    
    Args:
        db_path: Path to the SQLite database.
        unit: The unit to write.
    
    Raises:
        ConcurrentEditError: If another user modified the row after it was loaded.
    """
    conn = get_db(db_path)
    # Optimistic lock: only update if updated_at hasn't changed since we loaded it
    if unit.updated_at:
        where_clause = "WHERE com_number = ? AND updated_at = ?"
        where_params: tuple = (unit.com_number, unit.updated_at)
    else:
        # Row has no updated_at yet (legacy/seeded data) — fall back to unlocked
        where_clause = "WHERE com_number = ?"
        where_params = (unit.com_number,)
    cursor = conn.execute(f"""
        UPDATE units SET
            job_name = ?,
            top_level_number = ?,
            description = ?,
            detailer = ?,
            checking_status = ?,
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
            updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')
        {where_clause}
    """, (
        unit.job_name,
        unit.contract_number,
        unit.description,
        unit.detailer,
        unit.checking_status,
        unit.department_hours,
        unit.percent_complete / 100,
        unit.actual_hours,
        unit.target_department_hours,  # Use the unit's value (may be 0 for non-primary identicals)
        unit.iec_internal_hours,
        unit.dept_due_date_previous.isoformat() if unit.dept_due_date_previous else None,
        unit.detailing_due_date.isoformat() if unit.detailing_due_date else None,
        unit.build_date.isoformat() if unit.build_date else None,
        unit.unit_detailing_start_date.isoformat() if unit.unit_detailing_start_date else None,
        unit.unit_moved_to_checking_date.isoformat() if unit.unit_moved_to_checking_date else None,
        unit.unit_detailing_completion_date.isoformat() if unit.unit_detailing_completion_date else None,
        unit.notes,
        unit.calculated_status_color,
        *where_params,
    ))
    if cursor.rowcount == 0:
        conn.rollback()
        raise ConcurrentEditError(
            f"COM {unit.com_number} was modified by another user after you loaded it. "
            "Your changes were not saved."
        )
    refreshed = conn.execute(
        "SELECT updated_at FROM units WHERE com_number = ?",
        (unit.com_number,),
    ).fetchone()
    if refreshed:
        unit.updated_at = refreshed["updated_at"] if hasattr(refreshed, "keys") else refreshed[0]
    conn.commit()
    logger.info(f"Saved unit {unit.com_number} to SQLite")


class ConcurrentEditError(Exception):
    """Raised when optimistic locking detects a concurrent edit conflict."""
