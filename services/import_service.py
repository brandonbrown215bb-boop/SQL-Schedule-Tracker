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
        self,
        url: str,
        ssrs_summary_url: str | None = None,
        lookback_days: int = 30,
        lookahead_days: int = 365,
    ) -> ImportResult:
        """Fetch CSV from SSRS ReportServer and import into SQLite.

        Backs up the database before import. Returns ImportResult with stats.

        Args:
            url: SSRS ReportServer endpoint URL.
            ssrs_summary_url: Optional secondary summary report URL for LineItemStateDesc.
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
            ssrs_summary_url=ssrs_summary_url,
            lookback_days=lookback_days,
            lookahead_days=lookahead_days,
        )
        return ImportResult(
            inserted=stats.get("inserted", 0),
            updated=stats.get("updated", 0),
            skipped=stats.get("skipped", 0),
            errors=stats.get("errors", 0),
        )

    def download_ssrs(
        self,
        url: str,
        ssrs_summary_url: str | None = None,
        lookback_days: int = 30,
        lookahead_days: int = 365,
    ) -> str:
        """Fetch CSV from SSRS ReportServer to a temporary file.

        Args:
            url: SSRS ReportServer endpoint URL.
            ssrs_summary_url: Optional secondary summary report URL for LineItemStateDesc.
            lookback_days: Number of days to look back in the report.
            lookahead_days: Number of days to look forward in the report.

        Returns:
            The path to the downloaded temporary CSV file.
        """
        import os
        from automation.import_atomsvc import (
            build_date_params,
            build_ssrs_url,
            fetch_csv_from_ssrs,
            merge_summary_states_into_csv,
        )

        start_date, end_date = build_date_params(lookback_days, lookahead_days)
        full_url = build_ssrs_url(url, start_date, end_date)
        csv_path = fetch_csv_from_ssrs(full_url, filename_prefix="_ssrs_detailing_pull")

        if ssrs_summary_url:
            try:
                summary_full_url = build_ssrs_url(ssrs_summary_url, start_date, end_date)
                summary_csv_path = fetch_csv_from_ssrs(summary_full_url, filename_prefix="_ssrs_summary_pull")
                if summary_csv_path and os.path.exists(summary_csv_path):
                    merge_summary_states_into_csv(csv_path, summary_csv_path)
                    try:
                        os.remove(summary_csv_path)
                    except OSError:
                        pass
            except Exception as e:
                logger.warning("Summary report merge failed: %s", e)

        return csv_path

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
