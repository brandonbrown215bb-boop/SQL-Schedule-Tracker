# data/db.py
"""SQLite connection management and row-to-Unit conversion."""
import json
import logging
import sqlite3
from datetime import date

from data.models import Unit

logger = logging.getLogger(__name__)

import threading

_db_path: str | None = None
_local = threading.local()


def get_db(db_path: str | None = None) -> sqlite3.Connection:
    """Get a per-thread SQLite connection.

    Stores db_path globally on first call, then creates one connection
    per thread via threading.local(). If called with a different path,
    the connection is recreated.
    """
    global _db_path
    if db_path is not None:
        _db_path = db_path
    if _db_path is None:
        raise RuntimeError("Database path not provided. Call get_db(path) first.")
    conn = getattr(_local, "conn", None)
    # Recreate connection if path changed or doesn't exist
    if conn is None or getattr(_local, "db_path", None) != _db_path:
        conn = sqlite3.connect(_db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
        _local.db_path = _db_path
        logger.info(f"SQLite connection opened for thread {threading.current_thread().name}: {_db_path}")
    return conn


def close_db() -> None:
    """Close the SQLite connection for the current thread."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
        logger.info("SQLite connection closed")


def row_to_unit(row: sqlite3.Row) -> Unit:
    """Convert a SQLite row to a Unit dataclass."""
    return Unit(
        com_number=row["com_number"] or "",
        job_name=row["job_name"] or "",
        contract_number=row["top_level_number"] or "",
        description=row["description"] or "",
        detailer=row["detailer"] or "",
        checking_status=row["checking_status"] or "",
        status_color="gray",  # calculated in models.py
        department_hours=row["department_hours"] or 0.0,
        target_department_hours=row["target_dept_hours"] if "target_dept_hours" in row.keys() and row["target_dept_hours"] is not None else 0.0,
        iec_internal_hours=row["iec_internal_hours"] or 0.0,
        percent_complete=(row["percent_complete"] or 0.0) * 100,
        actual_hours=row["actual_hours"] or 0.0,
        working_days=None,  # set from config detailer_schedules after loading
        unit_detailing_start_date=_parse_date(row["unit_detailing_start_date"]),
        unit_moved_to_checking_date=_parse_date(row["unit_moved_to_checking_date"]),
        unit_detailing_completion_date=_parse_date(row["unit_detailing_completion_date"]),
        dept_due_date_previous=_parse_date(row["dept_due_date_previous"]),
        detailing_due_date=_parse_date(row["detailing_due_date"]),
        build_date=_parse_date(row["build_date"]),
        updated_at=row["updated_at"] or "",
    )


def _parse_date(val) -> date | None:
    """Parse ISO date string to date object."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        s = str(val).split(" ")[0]  # strip " 00:00:00" from datetime strings
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Detailer schedule helpers
# ---------------------------------------------------------------------------

def get_detailer_schedules(db_path: str) -> dict[str, list[int]]:
    """Load all detailer schedules from the detailers table.
    
    Returns dict of detailer_name -> [weekday_numbers].
    Always includes a 'default' key.
    """
    conn = get_db(db_path)
    cur = conn.cursor()
    
    schedules = {}
    
    # Load default
    cur.execute("SELECT working_weekdays FROM default_schedule WHERE id = 1")
    row = cur.fetchone()
    if row:
        schedules["default"] = json.loads(row[0])
    else:
        schedules["default"] = [0, 1, 2, 3]
    
    # Load detailers
    cur.execute("SELECT name, working_weekdays FROM detailers ORDER BY display_order")
    for row in cur.fetchall():
        schedules[row[0]] = json.loads(row[1])
    
    return schedules


def working_days_between(start: date, end: date, working_weekdays: list[int]) -> int:
    """Count working days from start (exclusive) to end (inclusive).
    
    working_weekdays: list of weekday numbers (0=Mon … 6=Sun).
    Returns 0 if end <= start.
    """
    if end <= start:
        return 0
    count = 0
    current = start
    from datetime import timedelta
    while current < end:
        current += timedelta(days=1)
        if current.weekday() in working_weekdays:
            count += 1
    return count
