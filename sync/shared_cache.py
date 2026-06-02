# sync/shared_cache.py
"""Shared per-COM unit cache for conflict diffs and session presence.

Stored as ``UnitTracker/units.json``, updated atomically after every
successful commit alongside ``revisions.json``.  Provides the "remote"
values needed by the conflict dialog without re-reading Excel.
"""

from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from data.models import Unit
from sync.revision_store import UnitRevision

SHARED_CACHE_SCHEMA_VERSION = 1


@dataclass
class SharedUnitEntry:
    """The remote-side view of a single unit in the shared cache."""
    com_number: str
    job_name: str
    contract_number: str
    description: str
    detailer: str
    checking_status: str
    department_hours: float
    target_department_hours: float
    iec_internal_hours: float
    percent_complete: float
    actual_hours: float
    unit_detailing_start_date: str | None  # ISO format or null
    unit_moved_to_checking_date: str | None
    unit_detailing_completion_date: str | None
    dept_due_date_previous: str | None
    detailing_due_date: str | None
    build_date: str | None
    modified_by: str
    modified_at: str
    revision: int

    @classmethod
    def from_unit(
        cls, unit: Unit, revision: UnitRevision
    ) -> "SharedUnitEntry":
        """Build a cache entry from a Unit and the just-committed revision."""
        return cls(
            com_number=unit.com_number,
            job_name=unit.job_name,
            contract_number=unit.contract_number,
            description=unit.description,
            detailer=unit.detailer,
            checking_status=unit.checking_status,
            department_hours=unit.department_hours,
            target_department_hours=unit.target_department_hours,
            iec_internal_hours=unit.iec_internal_hours,
            percent_complete=unit.percent_complete,
            actual_hours=unit.actual_hours,
            unit_detailing_start_date=(
                unit.unit_detailing_start_date.isoformat()
                if unit.unit_detailing_start_date else None
            ),
            unit_moved_to_checking_date=(
                unit.unit_moved_to_checking_date.isoformat()
                if unit.unit_moved_to_checking_date else None
            ),
            unit_detailing_completion_date=(
                unit.unit_detailing_completion_date.isoformat()
                if unit.unit_detailing_completion_date else None
            ),
            dept_due_date_previous=(
                unit.dept_due_date_previous.isoformat()
                if unit.dept_due_date_previous else None
            ),
            detailing_due_date=(
                unit.detailing_due_date.isoformat()
                if unit.detailing_due_date else None
            ),
            build_date=(
                unit.build_date.isoformat()
                if unit.build_date else None
            ),
            modified_by=revision.modified_by,
            modified_at=revision.modified_at,
            revision=revision.revision,
        )

    def to_payload(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_payload(cls, d: dict) -> "SharedUnitEntry":
        return cls(**d)


class SharedCache:
    """Per-COM shared state, updated atomically on every commit.

    The cache lives at ``UnitTracker/units.json`` next to the workbook.
    """

    SCHEMA_KEY = "_schema_version"

    def __init__(self, excel_path: str):
        self.root_dir = Path(excel_path).parent / "UnitTracker"
        self.cache_file = self.root_dir / "units.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, com_number: str) -> dict | None:
        """Return the remote field values for *com_number*, or *None*."""
        entries = self._read_all()
        raw = entries.get(com_number)
        if raw is None:
            return None
        # Strip internal keys before returning
        return {k: v for k, v in raw.items() if not k.startswith("_")}

    def get_entry(self, com_number: str) -> SharedUnitEntry | None:
        """Return the full entry object, or *None*."""
        entries = self._read_all()
        raw = entries.get(com_number)
        if raw is None:
            return None
        return SharedUnitEntry.from_payload(raw)

    def update(
        self, com_number: str, unit: Unit, revision: UnitRevision
    ) -> None:
        """Atomically upsert the shared cache entry for one COM."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        entries = self._read_all()
        entry = SharedUnitEntry.from_unit(unit, revision)
        entries[com_number] = entry.to_payload()
        self._write_all(entries)

    def delete(self, com_number: str) -> None:
        """Remove a COM from the shared cache."""
        entries = self._read_all()
        entries.pop(com_number, None)
        self._write_all(entries)

    def all(self) -> dict[str, dict]:
        """Return all entries (used for session presence / admin views)."""
        raw = self._read_all()
        return {
            k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
            for k, v in raw.items()
        }

    def clear(self) -> None:
        """Wipe the entire cache (e.g. when workbook is replaced)."""
        self._write_all({})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_all(self) -> dict[str, dict[str, object]]:
        try:
            data: dict = json.loads(self.cache_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            # Strip schema key if present
            data.pop(self.SCHEMA_KEY, None)
            return data
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}

    def _write_all(self, entries: dict[str, dict[str, object]]) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        # Inject schema version
        payload = {self.SCHEMA_KEY: SHARED_CACHE_SCHEMA_VERSION, **entries}
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.root_dir,
            delete=False,
        ) as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            temp_name = f.name
        Path(temp_name).replace(self.cache_file)