"""ImportService — CSV and SSRS import pipeline.

Wraps automation/import_csv.py and automation/import_atomsvc.py to provide
a clean interface for importing data into SQLite. Zero Qt dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from automation.import_preview import ImportDiff
from data.db import backup_db

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Result of an import operation."""

    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0

    @property
    def total_affected(self) -> int:
        return self.inserted + self.updated


class ImportService:
    """Service for importing CSV and SSRS data into SQLite.

    Usage:
        svc = ImportService(db_path)
        result = svc.from_csv("/path/to/report.csv")
        result = svc.from_ssrs(url, lookback=30, lookahead=365)
    """

    def __init__(self, db_path: str):
        self._db_path = db_path

    def from_csv(self, csv_path: str) -> ImportResult:
        """Import a CSV file into SQLite.

        Backs up the database before import. Returns ImportResult with stats.

        Args:
            csv_path: Path to the CSV file (SSRS export format).

        Returns:
            ImportResult with inserted/updated/skipped/error counts.
        """
        from automation.import_csv import run_import

        backup_db(self._db_path)
        stats = run_import(csv_path, self._db_path)
        return ImportResult(
            inserted=stats.get("inserted", 0),
            updated=stats.get("updated", 0),
            skipped=stats.get("skipped", 0),
            errors=stats.get("errors", 0),
        )

    def from_ssrs(
        self, url: str, lookback_days: int = 30, lookahead_days: int = 365
    ) -> ImportResult:
        """Fetch CSV from SSRS ReportServer and import into SQLite.

        Backs up the database before import. Returns ImportResult with stats.

        Args:
            url: SSRS ReportServer endpoint URL.
            lookback_days: Number of days to look back in the report.
            lookahead_days: Number of days to look forward in the report.

        Returns:
            ImportResult with inserted/updated/skipped/error counts.
        """
        from automation.import_atomsvc import run_ssrs_import

        backup_db(self._db_path)
        stats = run_ssrs_import(
            db_path=self._db_path,
            ssrs_url=url,
            lookback_days=lookback_days,
            lookahead_days=lookahead_days,
        )
        return ImportResult(
            inserted=stats.get("inserted", 0),
            updated=stats.get("updated", 0),
            skipped=stats.get("skipped", 0),
            errors=stats.get("errors", 0),
        )

    def diff_before_import(self, csv_path: str) -> ImportDiff:
        """Preview what would change during an import without applying changes.

        Args:
            csv_path: Path to the CSV file to preview.

        Returns:
            ImportDiff with lists of rows to insert and update.

        Raises:
            NotImplementedError: The diff preview module is not yet implemented
                (FEAT-019 is still in the roadmap). The UI handles this gracefully.
        """
        from automation.import_preview import compute_diff

        diff = compute_diff(csv_path, self._db_path)
        return diff
