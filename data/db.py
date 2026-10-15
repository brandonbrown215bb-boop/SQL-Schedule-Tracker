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
_audit_user = "local"


# SQL twin of data.loader._apply_identicals: true for every unit except the
# primary of a contract group (earliest due date, undated last, then lowest
# COM). Non-primary identicals aren't detailed again, so they report 0 target
# hours; the real value stays in units.target_dept_hours in case the primary
# changes.
NON_PRIMARY_IDENTICAL_SQL = """(
    TRIM(COALESCE(top_level_number, '')) <> ''
    AND ROW_NUMBER() OVER (
        PARTITION BY TRIM(top_level_number)
        ORDER BY date(detailing_due_date) IS NULL, date(detailing_due_date), com_number
    ) > 1
)"""

_REPORTING_VIEW_VERSION = "v_reporting_export:identicals-v1"
_REPORTING_VIEW_SQL = (
    f"""CREATE VIEW v_reporting_export AS
            -- {_REPORTING_VIEW_VERSION}
            SELECT
                u.com_number,
                u.job_name,
                u.top_level_number AS contract_number,
                u.detailer,
                u.notes,
                CASE
                    WHEN u.notes IS NOT NULL AND u.notes != '' AND u.detailer IS NOT NULL AND u.detailer != ''
                        THEN (CASE WHEN u.detailer = 'Matthew E' THEN 'Matt' WHEN u.detailer = 'Matthew S' THEN 'Matthew' ELSE u.detailer END) || ' / ' || u.notes
                    WHEN u.notes IS NOT NULL AND u.notes != '' THEN u.notes
                    ELSE (CASE WHEN u.detailer = 'Matthew E' THEN 'Matt' WHEN u.detailer = 'Matthew S' THEN 'Matthew' ELSE COALESCE(u.detailer, '') END)
                END AS detailer_display,
                u.percent_complete,
                u.remaining_hours,
                u.department_hours,
                CASE WHEN {NON_PRIMARY_IDENTICAL_SQL} THEN 0.0
                     ELSE COALESCE(u.target_dept_hours, u.department_hours)
                END AS target_dept_hours,
                u.checking_status,
                u.unit_detailing_start_date,
                u.unit_moved_to_checking_date,
                u.unit_detailing_completion_date,
                u.detailing_due_date,
                u.build_date,
                COALESCE(u.actual_hours_to_detail_unit, u.actual_hours, 0.0) AS actual_hours,
                COALESCE(u.iec_internal_hours, 0.0) AS iec_internal_hours,
                COALESCE(u.same_as, '') AS same_as,
                COALESCE(u.dr_checks, '') AS dr_checks,
                COALESCE(u.dvl_checks, '') AS dvl_checks,
                u.updated_at
            FROM units u
"""
)


def set_audit_user(name: str) -> None:
    """Set the name recorded in _audit_log.saved_by for saves from this process."""
    global _audit_user
    _audit_user = (name or "").strip() or "local"


def _safe_journal_mode(conn: sqlite3.Connection, db_path: str) -> None:
    """Set WAL mode only if the database is on a local filesystem and multi-user is disabled."""
    import os
    import sys

    import yaml

    # Set generous busy timeout to prevent immediate lock crashes on network shares
    conn.execute("PRAGMA busy_timeout = 30000")

    path = os.path.abspath(db_path)
    # UNC paths (\\server\share) or mapped drives on Windows network shares
    is_net = path.startswith("\\\\") or (os.name == "nt" and _is_network_drive(path))

    # Detect if multi-user is enabled in config.yaml
    multi_user_enabled = False
    if getattr(sys, "frozen", False):
        app_path = os.path.dirname(sys.executable)
    else:
        app_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(app_path, "config.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                multi_user_enabled = config.get("multi_user", {}).get("enabled", False)
        except Exception:
            pass

    if is_net or multi_user_enabled:
        conn.execute("PRAGMA journal_mode=DELETE")
    else:
        conn.execute("PRAGMA journal_mode=WAL")


def _is_network_drive(path: str) -> bool:
    """Check if a Windows drive letter maps to a network share."""
    import os
    try:
        import ctypes
        drive = os.path.splitdrive(path)[0] + "\\"
        return ctypes.windll.kernel32.GetDriveTypeW(drive) == 4  # DRIVE_REMOTE
    except Exception:
        return False


# Busy timeout for the UI thread. It only reads (saves and imports run on worker
# threads with the full 30 s), so while an import holds the write lock a click
# fails fast with DatabaseBusyError instead of freezing the window for 30 s.
UI_BUSY_TIMEOUT_MS = 5000


class DatabaseBusyError(RuntimeError):
    """The shared database is locked by another writer (usually an import)."""

    def __init__(self) -> None:
        super().__init__("The database is busy (an import or save is running). Try again in a moment.")


def is_busy_error(exc: BaseException) -> bool:
    """True if *exc* is SQLite's "database is locked/busy" error."""
    return isinstance(exc, DatabaseBusyError) or (
        isinstance(exc, sqlite3.OperationalError)
        and any(s in str(exc).lower() for s in ("database is locked", "database is busy"))
    )


def set_thread_busy_timeout(ms: int) -> None:
    """Use a busy timeout of *ms* for this thread's connection (now and if recreated)."""
    _local.busy_timeout_ms = int(ms)
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.execute(f"PRAGMA busy_timeout = {int(ms)}")


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
        conn = sqlite3.connect(_db_path, timeout=30.0)
        _safe_journal_mode(conn, _db_path)
        if getattr(_local, "busy_timeout_ms", None) is not None:
            conn.execute(f"PRAGMA busy_timeout = {_local.busy_timeout_ms}")
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

        if "week_ending_friday" not in cols:
            conn.execute("ALTER TABLE units ADD COLUMN week_ending_friday TEXT")
            logger.info("Migration: added week_ending_friday column")

        if "unit_state" not in cols:
            conn.execute("ALTER TABLE units ADD COLUMN unit_state TEXT")
            logger.info("Migration: added unit_state column")

        if "same_as" not in cols:
            conn.execute("ALTER TABLE units ADD COLUMN same_as TEXT")
            logger.info("Migration: added same_as column")

        # ── Database indexes for common query filters ────────────
        desired_indexes = {
            "idx_units_detailing_due_date": "detailing_due_date",
            "idx_units_detailer": "detailer",
            "idx_units_contract_number": "top_level_number",
            "idx_units_status_color": "status_color",
            "idx_units_unit_state": "unit_state",
        }
        existing_indexes = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
        for idx_name, col in desired_indexes.items():
            if idx_name not in existing_indexes:
                conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON units({col})")
                logger.info(f"Migration: created index {idx_name} on {col}")

        _ensure_audit_log(conn)

        # ── Dedicated view for Excel reporting export ───────────
        # Recreate when the stored definition predates the current version
        # (CREATE VIEW IF NOT EXISTS would keep an old definition forever).
        existing = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='view' AND name='v_reporting_export'"
        ).fetchone()
        if existing is None or _REPORTING_VIEW_VERSION not in (existing[0] or ""):
            conn.execute("DROP VIEW IF EXISTS v_reporting_export")
            conn.execute(_REPORTING_VIEW_SQL)
            logger.info("Migration: (re)created v_reporting_export (%s)", _REPORTING_VIEW_VERSION)

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


def log_field_changes(
    conn: sqlite3.Connection,
    com_number: str,
    old_row: sqlite3.Row | None,
    new_values: dict,
    *,
    saved_by: str | None = None,
    commit: bool = True,
) -> int:
    """Record field-level changes to the audit log.

    Compares *old_row* (the DB row before save) against *new_values*
    (the dict of field_name → new_value being written).  Inserts one
    row per changed field into _audit_log.

    *saved_by* defaults to the name set via set_audit_user(). Pass
    ``commit=False`` to keep the audit rows in the caller's transaction.

    Returns the number of changes recorded.
    """
    _ensure_audit_log(conn)
    if saved_by is None:
        saved_by = _audit_user

    def _normalize_for_comparison(val):
        """Normalize a value for audit log comparison, accounting for SQLite type affinity."""
        if val is None or val == "":
            return None
        if isinstance(val, float):
            # Normalize float to int if it's a whole number (SQLite stores 0.0 as 0)
            if val == int(val):
                return str(int(val))
            return str(val)
        return str(val)

    changes = 0
    if old_row is None:
        # New unit — log all initial field values as creation events
        for field, new_val in new_values.items():
            new_str = _normalize_for_comparison(new_val)
            if new_str is not None:
                conn.execute(
                    "INSERT INTO _audit_log (com_number, field_name, old_value, new_value, saved_by) "
                    "VALUES (?, ?, NULL, ?, ?)",
                    (com_number, field, new_str, saved_by),
                )
                changes += 1
        if changes > 0 and commit:
            conn.commit()
        return changes

    for field, new_val in new_values.items():
        # sqlite3.Row doesn't support `.get()` — use try/except
        try:
            old_val = old_row[field]
        except (IndexError, KeyError):
            old_val = None

        # Normalize for comparison: dates, None, etc.
        old_str = _normalize_for_comparison(old_val)
        new_str = _normalize_for_comparison(new_val)
        # NULL and 0 mean the same thing for numeric columns — don't log noise.
        if {old_str, new_str} == {None, "0"}:
            continue

        if old_str != new_str:
            conn.execute(
                "INSERT INTO _audit_log (com_number, field_name, old_value, new_value, saved_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (com_number, field, old_str, new_str, saved_by),
            )
            changes += 1

    if changes > 0:
        if commit:
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


def startup_backups_to_prune(
    paths: list[str], *, daily: int = 7, weekly: int = 4, monthly: int = 3
) -> list[str]:
    """Pick startup backups to delete, keeping a grandfather-father-son spread.

    Keeps the newest backup of each of the last *daily* days, the oldest backup
    of each of the last *weekly* ISO weeks and the oldest of each of the last
    *monthly* months, so history reaches back about *monthly* months instead of
    just the most recent files. Files whose name doesn't start with a
    ``YYYYmmdd_HHMMSS`` timestamp are never deleted.
    """
    import os
    from datetime import datetime

    stamped: list[tuple[datetime, str]] = []
    for p in paths:
        try:
            stamped.append((datetime.strptime(os.path.basename(p)[:15], "%Y%m%d_%H%M%S"), p))
        except ValueError:
            continue
    stamped.sort(reverse=True)  # newest first

    keep: set[str] = set()

    def _keep_per_bucket(key, limit: int, oldest: bool) -> None:
        chosen: dict = {}
        for ts, p in stamped:
            k = key(ts)
            if k not in chosen:
                if len(chosen) >= limit:
                    break
                chosen[k] = p
            elif oldest:
                chosen[k] = p  # later in newest-first order = older
        keep.update(chosen.values())

    _keep_per_bucket(lambda ts: ts.date(), daily, oldest=False)
    _keep_per_bucket(lambda ts: ts.isocalendar()[:2], weekly, oldest=True)
    _keep_per_bucket(lambda ts: (ts.year, ts.month), monthly, oldest=True)

    return [p for _, p in stamped if p not in keep]


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
        base_dir = os.path.dirname(db_path)
        if not base_dir:
            base_dir = "."
        backup_dir = os.path.join(base_dir, "backups")

    os.makedirs(backup_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_path = os.path.join(backup_dir, f"{ts}_pre_import_backup.db")

    # Use VACUUM INTO for a consistent atomic copy
    conn = get_db(db_path)
    try:
        conn.execute("VACUUM INTO ?", (export_path,))
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
    row_keys = set(row.keys())
    return Unit(
        com_number=row["com_number"] or "",
        job_name=row["job_name"] or "",
        contract_number=row["top_level_number"] or "",
        description=row["description"] or "",
        detailer=row["detailer"] or "",
        checking_status=row["checking_status"] or "",
        unit_state=(row["unit_state"] or "") if "unit_state" in row_keys else "",
        notes=row["notes"] or "",
        dr_checks=(row["dr_checks"] or "") if "dr_checks" in row_keys else "",
        dvl_checks=(row["dvl_checks"] or "") if "dvl_checks" in row_keys else "",
        status_color=row["status_color"] or "gray",  # persisted from last computed value
        department_hours=row["department_hours"] or 0.0,
        target_department_hours=(
            row["target_dept_hours"]
            if "target_dept_hours" in row_keys and row["target_dept_hours"] is not None
            else max(0.0, (row["department_hours"] or 0.0) - (row["iec_internal_hours"] or 0.0))
        ),
        iec_internal_hours=row["iec_internal_hours"] or 0.0,
        percent_complete=(row["percent_complete"] or 0.0) * 100,
        actual_hours=row["actual_hours"] or 0.0,
        actual_hours_to_detail_unit=row["actual_hours_to_detail_unit"]
        if "actual_hours_to_detail_unit" in row_keys and row["actual_hours_to_detail_unit"] is not None
        else 0.0,
        hour_variance=row["hour_variance"]
        if "hour_variance" in row_keys and row["hour_variance"] is not None
        else 0.0,
        remaining_demand=row["remaining_demand"]
        if "remaining_demand" in row_keys and row["remaining_demand"] is not None
        else 0.0,
        hours_checking=row["hours_checking"]
        if "hours_checking" in row_keys and row["hours_checking"] is not None
        else 0.0,
        working_days=None,  # set from config detailer_schedules after loading
        unit_detailing_start_date=_parse_date(row["unit_detailing_start_date"]),
        unit_moved_to_checking_date=_parse_date(row["unit_moved_to_checking_date"]),
        unit_detailing_completion_date=_parse_date(row["unit_detailing_completion_date"]),
        dept_due_date_previous=_parse_date(row["dept_due_date_previous"]),
        detailing_due_date=_parse_date(row["detailing_due_date"]),
        build_date=_parse_date(row["build_date"]),
        working_days_in_checking=row["working_days_in_checking"]
        if "working_days_in_checking" in row_keys and row["working_days_in_checking"] is not None
        else None,
        week_ending_friday=_parse_date(row["week_ending_friday"])
        if "week_ending_friday" in row_keys and row["week_ending_friday"] is not None
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
        try:
            schedules["default"] = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Malformed JSON in default_schedule.working_weekdays; using default (Mon-Thu)"
            )
            schedules["default"] = [0, 1, 2, 3]
    else:
        schedules["default"] = [0, 1, 2, 3]

    # Load detailers
    cur.execute("SELECT name, working_weekdays FROM detailers ORDER BY display_order")
    for row in cur.fetchall():
        try:
            schedules[row[0]] = json.loads(row[1])
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Malformed JSON in detailers.working_weekdays for '%s'; using default (Mon-Thu)",
                row[0],
            )
            schedules[row[0]] = [0, 1, 2, 3]

    return schedules
