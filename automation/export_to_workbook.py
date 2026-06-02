#!/usr/bin/env python3
"""Export SQLite data to the Excel workbook's Current List sheet.

Writes ALL columns (A through AG, skipping computed R/S/T) so the
workbook's pivot table and formulas have the full dataset.

Strategy: overwrite existing rows in place, then add or trim rows to match.
This preserves the pivot table's data source range and any external links
that reference specific row positions.
"""

import logging
import sqlite3
import sys
import time

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CURRENT_LIST_SHEET = "Current List"

# Column layout: (excel_column_letter, db_field_name, value_formatter)
# Covers A through AG, skipping R/S/T (computed by workbook formulas).
EXPORT_COLUMNS = [
    ("A",  "detailing_due_date",            "date"),
    ("B",  "dept_due_date_previous",        "str"),
    ("C",  "com_number",                    "str"),
    ("D",  "manufacturing_location",        "str"),
    ("E",  "detailer",                      "str"),
    ("F",  "job_name",                      "str"),
    ("G",  "top_level_number",              "str"),
    ("H",  "description",                   "str"),
    ("I",  "build_date",                    "date"),
    ("J",  "build_cycle",                   "int"),
    ("K",  "department_hours",              "float"),
    ("L",  "percent_complete",              "percent"),
    ("M",  "remaining_hours",               "float"),
    ("N",  "actual_hours",                  "float"),
    ("O",  "week_ending_friday",            "date"),
    ("P",  "notes",                         "str"),
    ("Q",  "late",                          "int"),
    # R, S, T are COMPUTED — workbook formulas, skip
    ("U",  "checking_status",               "str"),
    ("V",  "target_dept_hours",             "float"),
    ("W",  "iec_internal_hours",            "float"),
    ("X",  "unit_detailing_start_date",     "date"),
    ("Y",  "unit_moved_to_checking_date",   "date"),
    ("Z",  "unit_detailing_completion_date","date"),
    ("AA", "actual_hours_to_detail_unit",   "float"),
    ("AB", "hour_variance",                 "float"),
    ("AC", "remaining_demand",              "float"),
    ("AD", "same_as",                       "str"),
    ("AE", "dr_checks",                     "str"),
    ("AF", "dvl_checks",                    "str"),
    ("AG", "hours_checking",                "float"),
]


def _format_value(val, fmt: str):
    """Convert a Python value to the appropriate Excel cell value."""
    if val is None:
        return None
    if fmt == "date":
        if isinstance(val, str):
            from datetime import datetime
            try:
                return datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                return val
        return val
    if fmt == "percent":
        return val
    if fmt == "float":
        return float(val) if val is not None else None
    if fmt == "int":
        return int(val) if val is not None else None
    return str(val) if val else None


def export_to_workbook(db_path: str, excel_path: str) -> int:
    """Export all units from SQLite to the workbook's Current List sheet.

    Overwrites existing data rows in place to preserve pivot table ranges
    and external workbook links. Adds or trims rows as needed.

    Returns the number of rows exported.
    """
    # Read all columns from SQLite
    db_fields = [col[1] for col in EXPORT_COLUMNS]
    select_cols = ", ".join(db_fields)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT {select_cols} FROM units ORDER BY detailing_due_date")
    rows = cur.fetchall()
    conn.close()

    log.info(f"Read {len(rows)} rows from SQLite")

    # Open workbook
    wb = load_workbook(excel_path, data_only=False, keep_vba=True)

    if CURRENT_LIST_SHEET not in wb.sheetnames:
        available = ", ".join(wb.sheetnames)
        raise ValueError(
            f"Sheet '{CURRENT_LIST_SHEET}' not found. Available: {available}"
        )
    ws = wb[CURRENT_LIST_SHEET]

    # Build column index map from column letters
    col_map = []
    for col_letter, db_field, fmt in EXPORT_COLUMNS:
        col_idx = column_index_from_string(col_letter)
        col_map.append((col_idx, db_field, fmt))

    # Determine existing data row count (excluding header)
    existing_rows = ws.max_row - 1 if ws.max_row else 0
    new_count = len(rows)

    # Overwrite existing rows in place
    for row_idx, db_row in enumerate(rows, start=2):
        for col_idx, db_field, fmt in col_map:
            raw_val = db_row[db_field]
            cell_value = _format_value(raw_val, fmt)
            ws.cell(row=row_idx, column=col_idx, value=cell_value)

    # If we have more rows than before, the extra rows are already written above
    # If we have fewer rows than before, clear the leftover rows
    if existing_rows > new_count:
        for row_idx in range(new_count + 2, existing_rows + 2):
            for col_idx, _, _ in col_map:
                ws.cell(row=row_idx, column=col_idx, value=None)

    wb.save(excel_path)
    log.info(
        f"Exported {new_count} rows to {excel_path} ({CURRENT_LIST_SHEET} sheet)"
    )
    return new_count


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export SQLite to Excel Current List")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--excel-path", required=True, help="Path to Excel workbook")
    args = parser.parse_args()

    t0 = time.perf_counter()
    count = export_to_workbook(args.db, args.excel_path)
    elapsed = time.perf_counter() - t0
    print(f"Exported {count} rows in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
