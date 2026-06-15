# data/db.py
"""SQLite connection management and row-to-Unit conversion."""

import json
import logging
import sqlite3
import threading
from datetime import date

from data.models import Unit

logger = logging.getLogger(__name__)

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
        _migrate_schema(conn)
        logger.info(
            f"SQLite connection opened for thread {threading.current_thread().name}: {_db_path}"
        )
    return conn


def _working_days_between(start_str: str | None, end_str: str | None) -> int | None:
    """Count working days (Mon-Fri, all 5 days) between two ISO date strings.

    Both start and end are inclusive. Returns None if either date is missing/invalid.
    """
    from datetime import date as _date
    from datetime import timedelta

    if not start_str or not end_str:
        return None
    try:
        s = _date.fromisoformat(str(start_str).split(" ")[0])
        e = _date.fromisoformat(str(end_str).split(" ")[0])
    except (ValueError, TypeError):
        return None
    if e < s:
        return None
    count = 0
    d = s
    while d <= e:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add columns to existing databases that were created before these migrations."""
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(units)")}

        if "status_color" not in cols:
            conn.execute("ALTER TABLE units ADD COLUMN status_color TEXT DEFAULT 'gray'")
            logger.info("Migration: added status_color column")

        if "working_days_in_checking" not in cols:
            conn.execute("ALTER TABLE units ADD COLUMN working_days_in_checking INTEGER")
            logger.info("Migration: added working_days_in_checking column")
            # Backfill existing rows that have both dates
            rows = conn.execute(
                "SELECT com_number, unit_moved_to_checking_date, unit_detailing_completion_date "
                "FROM units WHERE unit_moved_to_checking_date IS NOT NULL "
                "AND unit_detailing_completion_date IS NOT NULL"
            ).fetchall()
            updated = 0
            for com, start, end in rows:
                wd = _working_days_between(start, end)
                if wd is not None:
                    conn.execute(
                        "UPDATE units SET working_days_in_checking = ? WHERE com_number = ?",
                        (wd, com),
                    )
                    updated += 1
            logger.info(f"Migration: backfilled working_days_in_checking for {updated} rows")

        # ── Sprint 1: Database indexes for common query filters ────────────
        desired_indexes = {
            "idx_units_detailing_due_date": "detailing_due_date",
            "idx_units_detailer": "detailer",
            "idx_units_contract_number": "top_level_number",
            "idx_units_status_color": "status_color",
        }
        existing_indexes = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        for idx_name, col in desired_indexes.items():
            if idx_name not in existing_indexes:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON units({col})")
                logger.info(f"Migration: created index {idx_name} on {col}")

    except Exception as e:
        logger.warning("Migration check failed: %s", e)
    finally:
        conn.commit()


def close_db() -> None:
    """Close the SQLite connection for the current thread."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
        logger.info("SQLite connection closed")


# ── Audit log ────────────────────────────────────────────────────────────────


def _ensure_audit_log(conn: sqlite3.Connection) -> None:
    """Create the _audit_log table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            com_number  TEXT    NOT NULL,
            field_name  TEXT    NOT NULL,
            old_value   TEXT,
            new_value   TEXT,
            saved_by    TEXT    DEFAULT 'local',
            saved_at    TEXT    DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
        )
    """)
    # Index for fast lookups by COM number
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_com ON _audit_log(com_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_saved_at ON _audit_log(saved_at)")
    conn.commit()


def log_field_changes(
    conn: sqlite3.Connection,
    com_number: str,
    old_row: sqlite3.Row | None,
    new_values: dict,
    *,
    saved_by: str = "local",
) -> int:
    """Record field-level changes to the audit log.

    Compares *old_row* (the DB row before save) against *new_values*
    (the dict of field_name → new_value being written).  Inserts one
    row per changed field into _audit_log.

    Returns the number of changes recorded.
    """
    _ensure_audit_log(conn)

    if old_row is None:
        return 0

    changes = 0
    for field, new_val in new_values.items():
        # sqlite3.Row doesn't support `.get()` — use try/except
        try:
            old_val = old_row[field]
        except (IndexError, KeyError):
            old_val = None

        # Normalize for comparison: dates, None, etc.
        old_str = str(old_val) if old_val is not None else None
        new_str = str(new_val) if new_val is not None else None

        if old_str != new_str:
            conn.execute(
                "INSERT INTO _audit_log (com_number, field_name, old_value, new_value, saved_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (com_number, field, old_str, new_str, saved_by),
            )
            changes += 1

    if changes > 0:
        conn.commit()
        logger.info(
            "Audit: %d field(s) changed for COM %s by %s",
            changes,
            com_number,
            saved_by,
        )
    return changes


def get_audit_trail(
    db_path: str,
    com_number: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Retrieve recent audit log entries.

    Args:
        db_path: Path to the SQLite database.
        com_number: If provided, filter to this COM only.
        limit: Max number of entries to return (default 100).

    Returns:
        List of dicts with keys: id, com_number, field_name, old_value,
        new_value, saved_by, saved_at.
    """
    conn = get_db(db_path)
    _ensure_audit_log(conn)

    if com_number:
        rows = conn.execute(
            "SELECT * FROM _audit_log WHERE com_number = ? ORDER BY saved_at DESC LIMIT ?",
            (com_number, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM _audit_log ORDER BY saved_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def backup_db(db_path: str, backup_dir: str | None = None, *, keep_count: int = 30) -> str:
    """Create a pre-import SQLite backup using VACUUM INTO.

    Creates a copy of the database at ``<timestamp>_backup.db`` in the same
    directory (or *backup_dir* if provided).  Keeps at most *keep_count*
    backups, deleting the oldest ones.

    Returns:
        Path to the created backup file.
    """
    import glob
    import os
    from datetime import datetime

    if backup_dir is None:
        backup_dir = os.path.dirname(db_path)
        if not backup_dir:
            backup_dir = "."

    os.makedirs(backup_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_path = os.path.join(backup_dir, f"{ts}_pre_import_backup.db")

    # Use VACUUM INTO for a consistent atomic copy
    conn = get_db(db_path)
    try:
        conn.execute(f"VACUUM INTO '{export_path}'")
    except Exception:
        # Some SQLite builds don't support VACUUM INTO — fall back to backup API
        try:
            backup_conn = sqlite3.connect(export_path)
            conn.backup(backup_conn)
            backup_conn.close()
        except Exception as e:
            logger.warning("Backup failed: %s", e)
            return ""

    logger.info("Pre-import backup saved to %s", export_path)

    # Prune old backups, keeping the most recent *keep_count*
    pattern = os.path.join(backup_dir, "*_pre_import_backup.db")
    backups = sorted(glob.glob(pattern))
    while len(backups) > keep_count:
        oldest = backups.pop(0)
        try:
            os.remove(oldest)
            logger.debug("Pruned old backup: %s", oldest)
        except OSError:
            pass

    return export_path


def row_to_unit(row: sqlite3.Row) -> Unit:
    """Convert a SQLite row to a Unit dataclass."""
    return Unit(
        com_number=row["com_number"] or "",
        job_name=row["job_name"] or "",
        contract_number=row["top_level_number"] or "",
        description=row["description"] or "",
        detailer=row["detailer"] or "",
        checking_status=row["checking_status"] or "",
        notes=row["notes"] or "",
        status_color=row["status_color"] or "gray",  # persisted from last computed value
        department_hours=row["department_hours"] or 0.0,
        target_department_hours=row["target_dept_hours"]
        if "target_dept_hours" in row and row["target_dept_hours"] is not None
        else 0.0,
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
        working_days_in_checking=row["working_days_in_checking"]
        if "working_days_in_checking" in row and row["working_days_in_checking"] is not None
        else None,
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
