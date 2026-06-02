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
    
    Args:
        db_path: Path to the SQLite database.
        unit: The unit to write.
    """
    conn = get_db(db_path)
    conn.execute("""
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
        WHERE com_number = ?
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
        unit.com_number,
    ))
    conn.commit()
    logger.info(f"Saved unit {unit.com_number} to SQLite")
