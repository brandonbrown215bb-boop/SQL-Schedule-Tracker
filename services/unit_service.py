"""UnitService — CRUD operations for Unit objects.

Wraps data/loader.py, data/writer.py, and data/db.py to provide a clean
interface for loading, saving, and querying units. Zero Qt dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from data.db import get_audit_trail, row_to_unit
from data.loader import _apply_identicals, load_units, unit_fingerprint
from data.models import Unit
from data.writer import save_unit

logger = logging.getLogger(__name__)


@dataclass
class DueDateChange:
    """Represents a detected due date change for a unit."""
    unit: Unit
    previous_due_date: date | None


class UnitService:
    """High-level service for unit CRUD operations.

    All methods are pure business logic — no Qt, no GUI.
    The service owns the db_path and detailer_schedules configuration.

    Usage:
        svc = UnitService(db_path, detailer_schedules)
        units = svc.load_all()
        svc.save(unit)
        single = svc.get_by_com("14201")
    """

    def __init__(self, db_path: str, detailer_schedules: dict | None = None):
        self._db_path = db_path
        self._detailer_schedules = detailer_schedules or {}

    @property
    def db_path(self) -> str:
        return self._db_path

    # ── Load ──────────────────────────────────────────────────────────

    def load_all(self, force: bool = False) -> list[Unit]:
        """Load all units from SQLite, apply identicals rule, return ordered list.

        Args:
            force: Ignored for SQLite (always fast), kept for interface compat.

        Returns:
            List of Unit objects ordered by detailing_due_date.
        """
        units = load_units(
            self._db_path,
            detailer_schedules=self._detailer_schedules,
            force_reload=force,
        )
        return units

    def get_by_com(self, com_number: str) -> Unit | None:
        """Fetch a single unit by COM number.

        Returns None if not found. Used by conflict dialog to reload
        the remote version of a unit after an optimistic lock failure.
        """
        import sqlite3

        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM units WHERE com_number = ?", (com_number,)
        ).fetchone()
        if row is None:
            return None
        return row_to_unit(row)

    # ── Save ──────────────────────────────────────────────────────────

    def save(self, unit: Unit) -> Unit:
        """Save a unit to SQLite with optimistic locking.

        On success, updates the unit's updated_at from the DB.
        Raises ConcurrentEditError if the row was modified by another user.

        Args:
            unit: The unit to save. Must have updated_at set from load time.

        Returns:
            The saved Unit with updated_at refreshed from DB.
        """
        save_unit(self._db_path, unit)
        return unit

    # ── Fingerprint ──────────────────────────────────────────────────

    @staticmethod
    def compute_fingerprint(unit: Unit) -> str:
        """Stable hash of editable unit fields for conflict detection."""
        return unit_fingerprint(unit)

    # ── Identicals ────────────────────────────────────────────────────

    @staticmethod
    def apply_identicals(units: list[Unit]) -> None:
        """In-place identicals rule application.

        When multiple units share the same contract_number, the one with
        the earliest detailing_due_date is the primary. All others get
        target_department_hours forced to 0.0 and is_non_primary_identical set.
        """
        _apply_identicals(units)

    # ── Due date change detection ─────────────────────────────────────

    @staticmethod
    def detect_changed_due_dates(
        old_units: list[Unit], new_units: list[Unit]
    ) -> list[DueDateChange]:
        """Compare old vs new units, return list of due date changes.

        For each unit whose detailing_due_date changed, returns a
        DueDateChange with the new unit and the previous due date.
        Also sets unit.due_date_changed and unit.previous_detailing_due_date
        on the changed units in-place.
        """
        old_by_com = {u.com_number: u for u in old_units}
        changed: list[DueDateChange] = []
        for unit in new_units:
            old_unit = old_by_com.get(unit.com_number)
            if old_unit is None:
                continue  # brand new unit — not a change
            old_due = old_unit.detailing_due_date
            new_due = unit.detailing_due_date
            if old_due != new_due:
                unit.due_date_changed = True
                unit.previous_detailing_due_date = old_due
                changed.append(DueDateChange(unit=unit, previous_due_date=old_due))
        return changed

    # ── Audit ─────────────────────────────────────────────────────────

    def get_audit_trail(
        self, com_number: str | None = None, limit: int = 100
    ) -> list[dict]:
        """Retrieve audit log entries.

        Args:
            com_number: If provided, filter to this COM only.
            limit: Max entries to return.

        Returns:
            List of dicts with keys: id, com_number, field_name,
            old_value, new_value, saved_by, saved_at.
        """
        return get_audit_trail(self._db_path, com_number=com_number, limit=limit)

    # ── Internal ──────────────────────────────────────────────────────

    def _get_conn(self):
        """Get a raw SQLite connection (for internal queries only)."""
        import sqlite3

        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
