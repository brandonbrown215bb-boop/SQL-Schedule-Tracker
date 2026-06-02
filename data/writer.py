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
    conn.execute(f"""
        UPDATE units SET
            detailer = ?,
            checking_status = ?,
            department_hours = ?,
            percent_complete = ?,
            actual_hours = ?,
            target_dept_hours = ?,
            iec_internal_hours = ?,
            unit_detailing_start_date = ?,
            unit_moved_to_checking_date = ?,
            unit_detailing_completion_date = ?,
            updated_at = datetime('now')
        {where_clause}
    """, (
        unit.detailer,
        unit.checking_status,
        unit.department_hours,
        unit.percent_complete / 100,
        unit.actual_hours,
        unit.target_department_hours,
        unit.iec_internal_hours,
        unit.unit_detailing_start_date.isoformat() if unit.unit_detailing_start_date else None,
        unit.unit_moved_to_checking_date.isoformat() if unit.unit_moved_to_checking_date else None,
        unit.unit_detailing_completion_date.isoformat() if unit.unit_detailing_completion_date else None,
        *where_params,
    ))
    if conn.total_changes == 0:
        conn.rollback()
        raise ConcurrentEditError(
            f"COM {unit.com_number} was modified by another user after you loaded it. "
            "Your changes were not saved."
        )
    conn.commit()
    logger.info(f"Saved unit {unit.com_number} to SQLite")


class ConcurrentEditError(Exception):
    """Raised when optimistic locking detects a concurrent edit conflict."""
