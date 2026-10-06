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

        conn = sqlite3.connect(db_path, timeout=30.0)
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

    @staticmethod
    def export_reporting_feed(
        db_path: str, feed_dir_or_file: str | None = None
    ) -> tuple[int, str]:
        """Export a clean reporting feed from SQLite v_reporting_export view.

        Generates both .xlsx and .csv files atomically (.tmp -> os.replace)
        so concurrent Excel readers never encounter file lock errors.

        Args:
            db_path: Path to the SQLite database.
            feed_dir_or_file: Output directory or specific base filename.
                Defaults to the parent directory of db_path with name
                'Detailing_Reporting_Feed'.

        Returns:
            Tuple of (row_count, xlsx_path).
        """
        import csv
        from datetime import datetime
        import os
        from pathlib import Path
        import sqlite3
        import openpyxl

        # Determine target paths
        if feed_dir_or_file is None:
            out_dir = Path(db_path).parent
            base_name = "Detailing_Reporting_Feed"
        else:
            p = Path(feed_dir_or_file)
            if p.is_dir() or not p.suffix:
                out_dir = p
                base_name = "Detailing_Reporting_Feed"
            else:
                out_dir = p.parent
                base_name = p.stem

        out_dir.mkdir(parents=True, exist_ok=True)
        xlsx_path = str(out_dir / f"{base_name}.xlsx")
        csv_path = str(out_dir / f"{base_name}.csv")

        # Read from view
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM v_reporting_export ORDER BY detailing_due_date")
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Fallback if view not yet created on this connection
            from data.db import _migrate_schema
            _migrate_schema(conn)
            cur.execute("SELECT * FROM v_reporting_export ORDER BY detailing_due_date")
            rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            logger.warning("No rows found in v_reporting_export")
            return 0, xlsx_path

        columns = list(rows[0].keys())

        # 1. Atomic write CSV
        tmp_csv = csv_path + ".tmp"
        try:
            with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                for r in rows:
                    writer.writerow(list(r))
            os.replace(tmp_csv, csv_path)
            logger.info("Reporting feed CSV written to %s", csv_path)
        except Exception as e:
            logger.warning("Failed to write feed CSV: %s", e)
            if os.path.exists(tmp_csv):
                try:
                    os.remove(tmp_csv)
                except OSError:
                    pass

        # 2. Atomic write XLSX with typed values
        tmp_xlsx = xlsx_path + ".tmp"
        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "ReportingData"
            ws.append(columns)

            def _clean(k: str, v):
                if v is None:
                    return ""
                if k == "com_number":
                    if isinstance(v, str) and v.strip().isdigit():
                        return int(v.strip())
                    elif isinstance(v, (int, float)):
                        return int(v)
                    return str(v).strip()
                if "date" in k and isinstance(v, str) and len(v) == 10 and v[4] == "-" and v[7] == "-":
                    try:
                        return datetime.strptime(v, "%Y-%m-%d").date()
                    except ValueError:
                        return v
                return v

            for r in rows:
                ws.append([_clean(col, r[col]) for col in columns])

            for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=len(columns)):
                for cell, col_name in zip(row, columns):
                    if "date" in col_name:
                        cell.number_format = "yyyy-mm-dd"
                    elif col_name == "percent_complete":
                        cell.number_format = "0%"
                    elif "hours" in col_name and isinstance(cell.value, (int, float)):
                        cell.number_format = "0.00"

            # Set clean column widths for human readability
            for c_idx, col_name in enumerate(columns, 1):
                col_letter = openpyxl.utils.get_column_letter(c_idx)
                if "date" in col_name:
                    ws.column_dimensions[col_letter].width = 14
                elif "hours" in col_name or "percent" in col_name:
                    ws.column_dimensions[col_letter].width = 12
                elif "name" in col_name or "detailer" in col_name or "notes" in col_name:
                    ws.column_dimensions[col_letter].width = 24
                else:
                    ws.column_dimensions[col_letter].width = 14

            wb.save(tmp_xlsx)
            os.replace(tmp_xlsx, xlsx_path)
            logger.info("Reporting feed XLSX written to %s", xlsx_path)
        except Exception as e:
            logger.warning("Failed to write feed XLSX: %s", e)
            if os.path.exists(tmp_xlsx):
                try:
                    os.remove(tmp_xlsx)
                except OSError:
                    pass

        return len(rows), xlsx_path

