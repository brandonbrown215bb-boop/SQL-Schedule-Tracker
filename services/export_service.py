"""ExportService — Excel, CSV, and PDF export.

Wraps automation/export_to_workbook.py to provide a clean interface
for exporting data from SQLite. Zero Qt dependencies.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ExportService:
    """Service for exporting SQLite data to various formats.

    Usage:
        svc = ExportService()
        rows = svc.to_excel("/path/to/workbook.xlsm", db_path)
    """

    def to_excel(self, excel_path: str, db_path: str) -> int:
        """Export SQLite data to the Excel workbook's 'Current List' sheet.

        Overwrites the 'Current List' sheet with current SQLite data.
        All other sheets in the workbook are preserved.

        Args:
            excel_path: Path to the Excel workbook (.xlsm or .xlsx).
            db_path: Path to the SQLite database.

        Returns:
            Number of rows exported.
        """
        from automation.export_to_workbook import export_to_workbook

        return export_to_workbook(db_path, excel_path)

    def to_csv(self, db_path: str, csv_path: str) -> int:
        """Export all units from SQLite to a CSV file.

        Args:
            db_path: Path to the SQLite database.
            csv_path: Path to the output CSV file.

        Returns:
            Number of rows exported.
        """
        import csv
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM units ORDER BY detailing_due_date").fetchall()
        conn.close()

        if not rows:
            return 0

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(rows[0].keys())
            for row in rows:
                writer.writerow(list(row))

        return len(rows)
