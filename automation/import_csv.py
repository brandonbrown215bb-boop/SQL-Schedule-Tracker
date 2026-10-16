#!/usr/bin/env python3
"""CSV Import Pipeline — reads SSRS CSV and upserts into SQLite.

Uses InputSanitizer for parsing and validate_unit for row-level validation
before any data touches the database.

Usage:
    python -m automation.import_csv --source csv --csv-path PATH --db PATH
    python -m automation.import_csv --source auto --db PATH
"""

import csv
import io
import logging
import sys
import time

from data.models import Unit
from services.sanitizer import InputSanitizer
from services.validation import validate_unit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# CSV columns → SQLite fields (only RAW IMPORT columns)
CSV_TO_DB = {
    "DeptDueDate": "detailing_due_date",
    "COMNumber": "com_number",
    "ManufacturingLocation": "manufacturing_location",
    "JobName": "job_name",
    "TopLevelNumber": "top_level_number",
    "Description": "description",
    "BuildDate": "build_date",
    "AssyCycle": "build_cycle",
    "DepartmentHours": "department_hours",
    "PercentComplete": "percent_complete",
    "WeekEndingFriday": "week_ending_friday",
    "LineItemState": "unit_state",
    "LineItemStateDesc": "unit_state",
    "UnitState": "unit_state",
}

VALUE_COLUMNS = list(dict.fromkeys(v for v in CSV_TO_DB.values() if v != "com_number"))

def _parse_week_ending(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    try:
        return InputSanitizer.clean_date(raw)
    except ValueError:
        if ":" not in raw:
            raise
    # Labelled value such as "Week Ending: 1/16/2026"
    return InputSanitizer.clean_date(raw.split(":", 1)[1])


# Map DB field names to InputSanitizer methods
SANITIZE_FUNCS = {
    "detailing_due_date": InputSanitizer.clean_date,
    "manufacturing_location": lambda v: InputSanitizer.clean_string(v),
    "job_name": lambda v: InputSanitizer.clean_string(v, max_length=255),
    "top_level_number": lambda v: InputSanitizer.clean_string(v, max_length=50),
    "description": lambda v: InputSanitizer.clean_string(v, max_length=500),
    "build_date": InputSanitizer.clean_date,
    "build_cycle": InputSanitizer.clean_int,
    "department_hours": InputSanitizer.clean_number,
    "percent_complete": lambda v: InputSanitizer.clean_percent(v) / 100.0,
    "week_ending_friday": _parse_week_ending,
    "com_number": InputSanitizer.clean_com_number,
    "unit_state": lambda v: InputSanitizer.clean_string(v, max_length=50),
}


def read_csv_text(csv_path: str) -> str:
    """Read a CSV export as text whatever its encoding.

    Handles UTF-16 (Excel "Unicode Text"), UTF-8 with or without BOM, and
    falls back to cp1252 (Excel's plain "CSV" on Windows).
    """
    with open(csv_path, "rb") as fh:
        data = fh.read()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def csv_dict_reader(csv_path: str) -> csv.DictReader:
    """DictReader over *csv_path*, decoded with ``read_csv_text``.

    Tab-separated files (Excel "Unicode Text") are detected from the header line.
    """
    text = read_csv_text(csv_path)
    header = text.split("\n", 1)[0]
    delimiter = "\t" if "\t" in header and "," not in header else ","
    return csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)


def parse_row(csv_row: dict) -> dict:
    """Sanitize one CSV row into DB field values. Raises ValueError on bad data."""
    row_data: dict = {}
    for csv_col, db_col in CSV_TO_DB.items():
        if csv_col in csv_row:
            raw_val = csv_row.get(csv_col) or ""
            if raw_val or db_col not in row_data or not row_data[db_col]:
                sanitizer = SANITIZE_FUNCS.get(db_col, lambda v: v)
                try:
                    row_data[db_col] = sanitizer(raw_val)
                except ValueError as e:
                    raise ValueError(f"{csv_col}: {e}") from e
    return row_data


def validate_row(row_data: dict) -> list[str]:
    """Row-level validation of parsed import data. Returns error messages."""
    unit_for_validation = Unit(
        com_number=row_data.get("com_number", ""),
        job_name=row_data.get("job_name", ""),
        contract_number=row_data.get("top_level_number", ""),
        description=row_data.get("description", ""),
        detailer="— Unassigned —",
        checking_status="",
        department_hours=row_data.get("department_hours", 0) or 0,
        target_department_hours=0,
        iec_internal_hours=0,
        percent_complete=((row_data.get("percent_complete", 0) or 0) * 100),
        actual_hours=0,
    )
    valid, val_errors = validate_unit(unit_for_validation)
    return [] if valid else list(val_errors)


def _same_value(old, new) -> bool:
    """Compare a DB value with an incoming CSV value, ignoring type/float noise."""
    if old in (None, "") and new in (None, ""):
        return True
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        return abs(old - new) <= 1e-9
    return str(old) == str(new)


def upsert_row(cursor, row_data: dict, csv_line: int) -> str:
    """Upsert one row. Returns 'inserted', 'updated', 'unchanged', or 'skipped'."""
    from data.db import _working_days_between

    com = row_data.get("com_number")
    if not com:
        return "skipped"

    new_due_date = row_data.get("detailing_due_date")
    csv_pct = row_data.get("percent_complete") or 0.0
    # Compute working_days_in_checking from the two date fields
    wd_checking = _working_days_between(
        row_data.get("unit_moved_to_checking_date"),
        row_data.get("unit_detailing_completion_date"),
    )

    # Check if row exists
    cursor.execute(
        "SELECT detailing_due_date, percent_complete, iec_internal_hours, target_adjustment_hours"
        " FROM units WHERE com_number = ?",
        (com,),
    )
    existing = cursor.fetchone()

    # Compute remaining_hours
    dept_hrs = row_data.get("department_hours") or 0

    if existing:
        current_due_date, current_pct, current_iec, current_adj = existing

        # Column B: if due date changed, push old date to dept_due_date_previous
        if new_due_date and current_due_date and str(current_due_date) != str(new_due_date):
            cursor.execute(
                "UPDATE units SET dept_due_date_previous = ? WHERE com_number = ?",
                (current_due_date, com),
            )

        # Build UPDATE — SSRS fields only (NOT manual fields)
        update_cols = [
            c
            for c in VALUE_COLUMNS
            if c in row_data
            and c != "percent_complete"
            and (c != "unit_state" or row_data.get("unit_state"))
        ]

        # percent_complete: only set from CSV if currently NULL
        if current_pct is None:
            update_cols.append("percent_complete")

        # target_dept_hours is derived: Dept - IEC + the scheduler's adjustment.
        # IEC and the adjustment are manual fields, so new Dept Hours flow through
        # without losing either. Cancelled/identicals are applied when read.
        row_data["target_dept_hours"] = max(0.0, dept_hrs - (current_iec or 0.0) + (current_adj or 0.0))
        update_cols.append("target_dept_hours")

        # Compute remaining_hours from effective percent_complete
        effective_pct = current_pct if current_pct is not None else csv_pct
        row_data["remaining_hours"] = dept_hrs * (1 - effective_pct)
        if "remaining_hours" not in update_cols:
            update_cols.append("remaining_hours")

        # Always update working_days_in_checking when dates are available
        if wd_checking is not None:
            update_cols.append("working_days_in_checking")
            row_data["working_days_in_checking"] = wd_checking

        # Skip rows whose SSRS values are identical to the DB. Bumping updated_at
        # on unchanged rows would make every open edit in other sessions fail
        # the optimistic-lock check after each import.
        due_changed = bool(
            new_due_date and current_due_date and str(current_due_date) != str(new_due_date)
        )
        if not due_changed:
            cursor.execute(
                f"SELECT {', '.join(update_cols)} FROM units WHERE com_number = ?", (com,)
            )
            current_values = cursor.fetchone()
            if current_values is not None and all(
                _same_value(old, row_data.get(col))
                for col, old in zip(update_cols, current_values, strict=True)
            ):
                return "unchanged"

        set_parts = [f"{col} = ?" for col in update_cols]
        set_parts.append("updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')")
        values = [row_data.get(c) for c in update_cols]
        values.append(com)

        sql = f"UPDATE units SET {', '.join(set_parts)} WHERE com_number = ?"
        cursor.execute(sql, values)
        return "updated"
    else:
        # INSERT new row
        insert_cols = ["com_number"] + [
            c for c in VALUE_COLUMNS if c in row_data and c != "percent_complete"
        ]
        insert_values = [row_data.get(c) for c in insert_cols]

        insert_cols.append("percent_complete")
        insert_values.append(csv_pct)

        insert_cols.append("target_dept_hours")
        insert_values.append(max(0.0, dept_hrs))

        remaining = (row_data.get("department_hours") or 0) * (1 - csv_pct)
        insert_cols.append("remaining_hours")
        insert_values.append(remaining)

        if wd_checking is not None:
            insert_cols.append("working_days_in_checking")
            insert_values.append(wd_checking)

        placeholders = ", ".join(["?"] * len(insert_cols))
        sql = f"INSERT INTO units ({', '.join(insert_cols)}) VALUES ({placeholders})"
        cursor.execute(sql, insert_values)
        return "inserted"


def run_import(csv_path: str, db_path: str) -> dict:
    """Execute the full import pipeline. Returns stats dict."""
    import sqlite3

    from data.db import backup_db

    # Pre-import backup for safety
    backup_db(db_path)

    stats = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0, "errors": 0}

    conn = sqlite3.connect(db_path, timeout=30.0)
    from data.db import _migrate_schema, _safe_journal_mode
    _safe_journal_mode(conn, db_path)
    _migrate_schema(conn)  # the import reads target_adjustment_hours
    cursor = conn.cursor()

    try:
        _import_rows(csv_path, cursor, stats)
        conn.commit()
    except BaseException:
        # Never leave a half-applied import or a held write lock on the shared DB.
        conn.rollback()
        raise
    finally:
        conn.close()
    return stats


def _import_rows(csv_path: str, cursor, stats: dict) -> None:
    """Parse, validate and upsert every CSV row using *cursor* (no commit)."""
    import sqlite3

    reader = csv_dict_reader(csv_path)
    require_com_column(reader, csv_path)
    for line_num, csv_row in enumerate(reader, start=2):
        if all((v or "").strip() == "" for v in csv_row.values()):
            stats["skipped"] += 1
            continue
        try:
            row_data = parse_row(csv_row)
            val_errors = validate_row(row_data)
            if val_errors:
                stats["errors"] += 1
                log.error(
                    "Line %d: validation failed: %s",
                    line_num,
                    "; ".join(val_errors),
                )
                continue

            result = upsert_row(cursor, row_data, line_num)
            stats[result] += 1
        except sqlite3.OperationalError:
            # "database is locked" etc. — abort the whole import instead of
            # waiting out the busy timeout once per row.
            raise
        except Exception as e:
            stats["errors"] += 1
            log.error(f"Line {line_num}: {e}")


def require_com_column(reader: csv.DictReader, csv_path: str) -> None:
    """Reject files that are not SSRS detailing exports (e.g. a saved error page)."""
    if "COMNumber" not in (reader.fieldnames or []):
        raise ValueError(
            f"{csv_path} has no COMNumber column — not an SSRS detailing export "
            "(the report server may have returned an error page)."
        )


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
