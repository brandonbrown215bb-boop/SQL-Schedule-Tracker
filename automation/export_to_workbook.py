#!/usr/bin/env python3
"""Export SQLite data to the Excel workbook's Unedited Report sheet.

Usage:
    python -m automation.export_to_workbook --db PATH --excel-path PATH
"""
import logging
import sqlite3
import sys
import time

from openpyxl import load_workbook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

UNEDITED_SHEET = "Unedited Report"


def export_to_workbook(db_path: str, excel_path: str) -> int:
    """Export all units from SQLite to the workbook's Unedited Report sheet.
    
    Returns the number of rows exported.
    """
    # Read from SQLite
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT com_number, detailing_due_date, manufacturing_location, job_name,
               top_level_number, description, build_date, build_cycle,
               department_hours, percent_complete, week_ending_friday
        FROM units
        ORDER BY detailing_due_date
    """)
    rows = cur.fetchall()
    conn.close()

    log.info(f"Read {len(rows)} rows from SQLite")

    # Write to workbook
    wb = load_workbook(excel_path, data_only=False, keep_vba=True)
    ws = wb[UNEDITED_SHEET]

    # Clear old data (keep header row)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row or 1):
        for cell in row:
            cell.value = None

    # Write header
    headers = [
        "DeptDueDate", "COMNumber", "ManufacturingLocation", "JobName",
        "TopLevelNumber", "Description", "BuildDate", "AssyCycle",
        "DepartmentHours", "PercentComplete", "WeekEndingFriday"
    ]
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=1, column=col_idx, value=header)

    # Write data
    for row_idx, row in enumerate(rows, start=2):
        ws.cell(row=row_idx, column=1, value=row["detailing_due_date"])
        ws.cell(row=row_idx, column=2, value=row["com_number"])
        ws.cell(row=row_idx, column=3, value=row["manufacturing_location"])
        ws.cell(row=row_idx, column=4, value=row["job_name"])
        ws.cell(row=row_idx, column=5, value=row["top_level_number"])
        ws.cell(row=row_idx, column=6, value=row["description"])
        ws.cell(row=row_idx, column=7, value=row["build_date"])
        ws.cell(row=row_idx, column=8, value=row["build_cycle"])
        ws.cell(row=row_idx, column=9, value=row["department_hours"])
        ws.cell(row=row_idx, column=10, value=row["percent_complete"])
        ws.cell(row=row_idx, column=11, value=row["week_ending_friday"])

    wb.save(excel_path)
    log.info(f"Exported {len(rows)} rows to {excel_path}")
    return len(rows)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export SQLite to Excel workbook")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--excel-path", required=True, help="Path to Excel workbook")
    args = parser.parse_args()

    t0 = time.perf_counter()
    count = export_to_workbook(args.db, args.excel_path)
    elapsed = time.perf_counter() - t0
    print(f"Exported {count} rows in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
