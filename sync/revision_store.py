from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from data.models import Unit
    from sync.shared_cache import SharedCache


@dataclass
class UnitRevision:
    com_number: str
    revision: int
    fingerprint: str
    modified_by: str
    modified_at: str


class RevisionConflictError(Exception):
    """Raised when a local edit is based on a stale shared revision."""

    def __init__(
        self,
        latest: UnitRevision,
        remote_values: dict | None = None,
    ):
        self.latest = latest
        self.remote_values = remote_values or {}
        super().__init__(
            f"COM {latest.com_number} was modified by {latest.modified_by} "
            f"at {latest.modified_at}"
        )


class RevisionStore:
    """Shared per-COM revision metadata for cache-first conflict checks."""

    def __init__(self, excel_path: str):
        self.root_dir = Path(excel_path).parent / "UnitTracker"
        self.revision_file = self.root_dir / "revisions.json"
        self._shared_cache: SharedCache | None = None

    def get(self, com_number: str) -> UnitRevision | None:
        raw = self._read_all().get(com_number)
        return UnitRevision(**raw) if raw else None

    def baseline(self, com_number: str) -> int:
        revision = self.get(com_number)
        return revision.revision if revision else 0

    def set_shared_cache(self, cache: "SharedCache | None") -> None:
        """Attach a shared cache that will be updated on every commit."""
        self._shared_cache = cache

    def commit(
        self,
        com_number: str,
        base_revision: int,
        fingerprint: str,
        modified_by: str,
        unit: "Unit | None" = None,
    ) -> UnitRevision:
        revisions = self._read_all()
        latest_raw = revisions.get(com_number)
        if latest_raw:
            latest = UnitRevision(**latest_raw)
            if latest.revision != base_revision:
                # Look up remote values from shared cache for conflict dialog
                remote_values: dict | None = None
                if self._shared_cache is not None:
                    remote_values = self._shared_cache.get(com_number)
                raise RevisionConflictError(latest, remote_values=remote_values)
            next_revision = latest.revision + 1
        else:
            if base_revision != 0:
                remote_values = None
                if self._shared_cache is not None:
                    remote_values = self._shared_cache.get(com_number)
                raise RevisionConflictError(
                    UnitRevision(
                        com_number=com_number,
                        revision=0,
                        fingerprint="",
                        modified_by="unknown",
                        modified_at="unknown",
                    ),
                    remote_values=remote_values,
                )
            next_revision = 1

        revision = UnitRevision(
            com_number=com_number,
            revision=next_revision,
            fingerprint=fingerprint,
            modified_by=modified_by,
            modified_at=datetime.now().isoformat(timespec="seconds"),
        )
        revisions[com_number] = asdict(revision)
        self._write_all(revisions)

        # Update shared cache if attached
        if self._shared_cache is not None and unit is not None:
            self._shared_cache.update(com_number, unit, revision)

        return revision

    def _read_all(self) -> dict[str, dict[str, object]]:
        try:
            return json.loads(self.revision_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}

    def _write_all(self, revisions: dict[str, dict[str, object]]) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.root_dir,
            delete=False,
        ) as f:
            json.dump(revisions, f, indent=2, sort_keys=True)
            temp_name = f.name
        Path(temp_name).replace(self.revision_file)
