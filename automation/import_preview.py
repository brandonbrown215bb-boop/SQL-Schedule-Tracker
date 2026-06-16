# automation/import_preview.py
"""Import diff engine — compares CSV rows against current DB state.

Shows what will change before applying an import, preventing blind data corruption.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field

from data.db import get_db
from automation.import_csv import CSV_TO_DB, SANITIZE_FUNCS as PARSE_FUNCS

logger = logging.getLogger(__name__)


@dataclass
class RowDiff:
    """Diff for a single row."""
    com_number: str
    status: str  # "new", "updated", "unchanged", "error"
    changes: list[dict] = field(default_factory=list)  # [{field, old, new}]

    @property
    def change_count(self) -> int:
        return len(self.changes)


@dataclass
class ImportDiff:
    """Complete diff for an import operation."""
    csv_path: str
    new_rows: list[RowDiff] = field(default_factory=list)
    updated_rows: list[RowDiff] = field(default_factory=list)
    unchanged_rows: list[RowDiff] = field(default_factory=list)
    errors: list[RowDiff] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return (
            sum(r.change_count for r in self.new_rows)
            + sum(r.change_count for r in self.updated_rows)
        )

    @property
    def summary(self) -> str:
        parts = []
        if self.new_rows:
            parts.append(f"{len(self.new_rows)} new units")
        if self.updated_rows:
            total = sum(r.change_count for r in self.updated_rows)
            parts.append(f"{len(self.updated_rows)} updated ({total} field changes)")
        if self.unchanged_rows:
            parts.append(f"{len(self.unchanged_rows)} unchanged")
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        return ", ".join(parts) if parts else "No changes"


def parse_csv_rows(csv_path: str) -> list[dict]:
    """Parse a CSV file and return a list of row_data dicts."""
    rows = []
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for csv_row in reader:
            if all((v or "").strip() == "" for v in csv_row.values()):
                continue
            row_data = {}
            for csv_col, db_col in CSV_TO_DB.items():
                raw_val = csv_row.get(csv_col, "")
                parser = PARSE_FUNCS.get(db_col, lambda v: v)
                row_data[db_col] = parser(raw_val)
            rows.append(row_data)
    return rows


def compute_diff(csv_path: str, db_path: str) -> ImportDiff:
    """Compute what an import would change without modifying any data.

    Args:
        csv_path: Path to the CSV file to import.
        db_path: Path to the SQLite database.

    Returns:
        ImportDiff with new, updated, unchanged, and error rows.
    """
    csv_rows = parse_csv_rows(csv_path)
    diff = ImportDiff(csv_path=csv_path)

    # Load existing units keyed by com_number
    conn = get_db(db_path)
    conn.row_factory = None  # Use tuples for raw access
    existing = {}
    for row in conn.execute("SELECT * FROM units").fetchall():
        # row is a sqlite3.Row when using Row factory from get_db
        com = row["com_number"] if hasattr(row, "keys") else row[1]  # com_number is column 2
        existing[com] = row

    # Reset row factory
    conn.row_factory = None

    for csv_row_data in csv_rows:
        com = csv_row_data.get("com_number")
        if not com:
            diff.errors.append(RowDiff(com_number="?", status="error", changes=[{"field": "com_number", "old": None, "new": "missing"}]))
            continue

        old_row = existing.get(com)
        if old_row is None:
            # New row
            changes = _csv_row_to_changes(None, csv_row_data)
            diff.new_rows.append(RowDiff(com_number=com, status="new", changes=changes))
        else:
            # Existing row — compare fields
            changes = _csv_row_to_changes(old_row, csv_row_data)
            if changes:
                diff.updated_rows.append(RowDiff(com_number=com, status="updated", changes=changes))
            else:
                diff.unchanged_rows.append(RowDiff(com_number=com, status="unchanged"))

    return diff


def _csv_row_to_changes(old_row, new_data: dict) -> list[dict]:
    """Compare an old DB row against new CSV data, returning field-level changes."""
    changes = []

    # Fields imported from CSV (non-com_number)
    import_fields = [
        "detailing_due_date", "job_name", "top_level_number", "description",
        "build_date", "department_hours", "percent_complete",
    ]

    for field_name in import_fields:
        new_val = new_data.get(field_name)
        if new_val is None:
            continue

        if old_row is None:
            # New row — all non-None values are changes
            changes.append({
                "field": field_name,
                "old": None,
                "new": new_val,
            })
        else:
            # Compare against old value
            try:
                old_val = old_row[field_name]
            except (IndexError, KeyError):
                old_val = None

            old_str = str(old_val) if old_val is not None else None
            new_str = str(new_val) if new_val is not None else None

            if old_str != new_str:
                changes.append({
                    "field": field_name,
                    "old": old_val,
                    "new": new_val,
                })

    return changes


def format_change_summary(change: dict) -> str:
    """Human-readable summary of a single field change."""
    field = change["field"]
    old = change["old"]
    new = change["new"]
    if old is None or (isinstance(old, str) and old.strip() == ""):
        return f"{field}: (empty) → {new}"
    elif new is None or (isinstance(new, str) and new.strip() == ""):
        return f"{field}: {old} → (empty)"
    return f"{field}: {old} → {new}"