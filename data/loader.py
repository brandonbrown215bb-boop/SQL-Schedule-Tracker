# data/loader.py
"""Data loader — reads units from SQLite database."""

import hashlib
import json
import logging
from collections import defaultdict
from datetime import date

from data.db import get_db, row_to_unit
from data.models import Unit

logger = logging.getLogger(__name__)

# Legacy COLUMN_MAP — kept for test compatibility only
COLUMN_MAP: dict[str, str] = {}

_fingerprint_cache: dict[str, str] = {}


def _date_to_str(val) -> str:
    """Convert date to string for fingerprinting."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    return val.isoformat()


def unit_fingerprint(unit: Unit) -> str:
    """Stable hash of editable unit fields for optimistic conflict checks."""
    uid = unit.com_number
    cached = _fingerprint_cache.get(uid)
    if cached is not None:
        return cached
    payload = {
        "com_number": unit.com_number,
        "job_name": unit.job_name,
        "contract_number": unit.contract_number,
        "description": unit.description,
        "detailer": unit.detailer,
        "checking_status": unit.checking_status,
        "notes": unit.notes,
        "department_hours": unit.department_hours,
        "actual_hours": unit.actual_hours,
        "target_department_hours": unit.target_department_hours,
        "iec_internal_hours": unit.iec_internal_hours,
        "percent_complete": unit.percent_complete,
        "unit_detailing_start_date": _date_to_str(unit.unit_detailing_start_date),
        "unit_moved_to_checking_date": _date_to_str(unit.unit_moved_to_checking_date),
        "unit_detailing_completion_date": _date_to_str(unit.unit_detailing_completion_date),
        "dept_due_date_previous": _date_to_str(unit.dept_due_date_previous),
        "detailing_due_date": _date_to_str(unit.detailing_due_date),
        "build_date": _date_to_str(unit.build_date),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    result = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    _fingerprint_cache[uid] = result
    return result


def _apply_identicals(units: list[Unit]) -> None:
    """Apply the "Identicals" rule to target_department_hours in-place.

    When multiple units share the same order number (contract_number /
    top_level_number), they are called "Identicals". The unit with the
    earliest detailing_due_date is the *primary* and keeps its normal
    target hour calculation. Every other identical gets
    target_department_hours forced to 0.0.

    Units with an empty contract_number or no due date are skipped.
    If two identicals have the same due date, the one appearing first
    (i.e. lowest COM number) wins — this ensures a deterministic primary.
    """
    groups: dict[str, list[Unit]] = defaultdict(list)
    for u in units:
        key = (u.contract_number or "").strip()
        if key:
            groups[key].append(u)

    for _order_number, group in groups.items():
        if len(group) < 2:
            continue  # not enough units to form identicals

        # Primary = earliest detailing_due_date.
        # Tie-break by com_number for determinism.
        def _sort_key(u: Unit) -> tuple:
            dd = u.detailing_due_date
            # Put units without a due date at the end so they aren't primary
            return (0 if dd is not None else 1, dd if dd is not None else date.min, u.com_number)

        primary = min(group, key=_sort_key)

        for u in group:
            if u is not primary:
                u.target_department_hours = 0.0
                u.is_non_primary_identical = True


def load_units(
    db_path: str,
    detailer_schedules: dict | None = None,
    force_reload: bool = False,
) -> list[Unit]:
    """Load all units from SQLite database.

    Args:
        db_path: Path to the SQLite database.
        detailer_schedules: Dict of detailer name → working weekdays.
        force_reload: Ignored for SQLite (always fast).

    Returns:
        List of Unit objects ordered by detailing_due_date, with the
        "Identicals" rule applied to target_department_hours.
    """
    conn = get_db(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM units ORDER BY detailing_due_date")
    rows = cur.fetchall()

    units = []
    for row in rows:
        unit = row_to_unit(row)
        # Set working days from config
        if detailer_schedules:
            if unit.detailer and unit.detailer in detailer_schedules:
                unit.working_days = detailer_schedules[unit.detailer]
            elif "default" in detailer_schedules:
                unit.working_days = detailer_schedules["default"]
        units.append(unit)

    # Apply the Identicals rule so non-primary identicals have zero target hours
    _apply_identicals(units)

    logger.info(f"Loaded {len(units)} units from SQLite")
    return units
