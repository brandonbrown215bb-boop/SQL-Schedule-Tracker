#!/usr/bin/env python3
"""CSV Import Pipeline — reads SSRS CSV and upserts into SQLite.

Usage:
    python -m automation.import_csv --source csv --csv-path PATH --db PATH
    python -m automation.import_csv --source auto --db PATH
"""
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# CSV columns → SQLite fields (only RAW IMPORT columns)
CSV_TO_DB = {
    "DeptDueDate":            "detailing_due_date",
    "COMNumber":              "com_number",
    "ManufacturingLocation":  "manufacturing_location",
    "JobName":                "job_name",
    "TopLevelNumber":         "top_level_number",
    "Description":            "description",
    "BuildDate":              "build_date",
    "AssyCycle":              "build_cycle",
    "DepartmentHours":        "department_hours",
    "PercentComplete":        "percent_complete",
    "WeekEndingFriday":       "week_ending_friday",
}

VALUE_COLUMNS = [v for v in CSV_TO_DB.values() if v != "com_number"]


def parse_date(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    return datetime.strptime(raw, "%m/%d/%Y").strftime("%Y-%m-%d")


def parse_percent(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    return float(raw.replace("%", "").strip()) / 100.0


def parse_week_ending(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    if ":" in raw:
        raw = raw.split(":", 1)[1].strip()
    return parse_date(raw)


def parse_number(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    return float(raw)


PARSE_FUNCS = {
    "detailing_due_date":     parse_date,
    "manufacturing_location": lambda v: v.strip() or None,
    "job_name":               lambda v: v.strip() or None,
    "top_level_number":       lambda v: v.strip() or None,
    "description":            lambda v: v.strip() or None,
    "build_date":             parse_date,
    "build_cycle":            lambda v: int(v.strip()) if v.strip() else None,
    "department_hours":       parse_number,
    "percent_complete":       parse_percent,
    "week_ending_friday":     parse_week_ending,
}


def upsert_row(cursor, row_data: dict, csv_line: int) -> str:
    """Upsert one row. Returns 'inserted', 'updated', or 'skipped'."""
    com = row_data.get("com_number")
    if not com:
        return "skipped"

    new_due_date = row_data.get("detailing_due_date")
    csv_pct = row_data.get("percent_complete") or 0.0

    # Check if row exists
    cursor.execute("SELECT detailing_due_date, percent_complete FROM units WHERE com_number = ?", (com,))
    existing = cursor.fetchone()

    # Compute remaining_hours
    dept_hrs = row_data.get("department_hours") or 0

    if existing:
        current_due_date = existing[0]
        current_pct = existing[1]

        # Column B: if due date changed, push old date to dept_due_date_previous
        if new_due_date and current_due_date and str(current_due_date) != str(new_due_date):
            cursor.execute(
                "UPDATE units SET dept_due_date_previous = ? WHERE com_number = ?",
                (current_due_date, com)
            )

        # Build UPDATE — SSRS fields only (NOT manual fields)
        update_cols = [c for c in VALUE_COLUMNS if c in row_data and c != "percent_complete"]

        # percent_complete: only set from CSV if currently NULL
        if current_pct is None:
            update_cols.append("percent_complete")

        # Compute remaining_hours from effective percent_complete
        effective_pct = current_pct if current_pct is not None else csv_pct
        row_data["remaining_hours"] = dept_hrs * (1 - effective_pct)
        if "remaining_hours" not in update_cols:
            update_cols.append("remaining_hours")

        set_parts = [f"{col} = ?" for col in update_cols]
        set_parts.append("updated_at = datetime('now')")
        values = [row_data.get(c) for c in update_cols]
        values.append(com)

        sql = f"UPDATE units SET {', '.join(set_parts)} WHERE com_number = ?"
        cursor.execute(sql, values)
        return "updated"
    else:
        # INSERT new row
        insert_cols = ["com_number"] + [c for c in VALUE_COLUMNS if c in row_data and c != "percent_complete"]
        insert_values = [row_data.get(c) for c in insert_cols]

        insert_cols.append("percent_complete")
        insert_values.append(csv_pct)

        remaining = (row_data.get("department_hours") or 0) * (1 - csv_pct)
        insert_cols.append("remaining_hours")
        insert_values.append(remaining)

        placeholders = ", ".join(["?"] * len(insert_cols))
        sql = f"INSERT INTO units ({', '.join(insert_cols)}) VALUES ({placeholders})"
        cursor.execute(sql, insert_values)
        return "inserted"


def run_import(csv_path: str, db_path: str) -> dict:
    """Execute the full import pipeline. Returns stats dict."""
    import sqlite3

    stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for line_num, csv_row in enumerate(reader, start=2):
            if all(v.strip() == "" for v in csv_row.values()):
                stats["skipped"] += 1
                continue
            try:
                row_data = {}
                for csv_col, db_col in CSV_TO_DB.items():
                    raw_val = csv_row.get(csv_col, "")
                    parser = PARSE_FUNCS.get(db_col, lambda v: v)
                    row_data[db_col] = parser(raw_val)
                result = upsert_row(cursor, row_data, line_num)
                stats[result] += 1
            except Exception as e:
                stats["errors"] += 1
                log.error(f"Line {line_num}: {e}")
        conn.commit()
    conn.close()
    return stats


def import_csv(db_path: str, csv_path: str) -> int:
    """Convenience wrapper for GUI import. Returns total rows affected."""
    stats = run_import(csv_path, db_path)
    return stats["inserted"] + stats["updated"]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Import SSRS CSV into SQLite")
    parser.add_argument("--source", choices=["auto", "csv", "url"], default="csv")
    parser.add_argument("--csv-path", default=None)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()

    csv_path = args.csv_path
    if not csv_path and args.source == "csv":
        print("ERROR: --csv-path required for --source csv", file=sys.stderr)
        sys.exit(1)

    t0 = time.perf_counter()
    stats = run_import(csv_path, args.db)
    elapsed = time.perf_counter() - t0

    print(f"Import complete in {elapsed:.3f}s")
    print(f"  Inserted: {stats['inserted']}")
    print(f"  Updated:  {stats['updated']}")
    print(f"  Skipped:  {stats['skipped']}")
    print(f"  Errors:   {stats['errors']}")


if __name__ == "__main__":
    main()
