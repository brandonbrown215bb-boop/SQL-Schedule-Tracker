# automation/import_preview.py
"""Import diff engine — compares CSV rows against current DB state.

Shows what will change before applying an import, preventing blind data corruption.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

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


def compute_diff(csv_path: str, db_path: str) -> ImportDiff:
    """Compute what an import would change without modifying any data.

    Uses the same parsing, validation and comparison as the real import
    (automation.import_csv), so the preview matches what will be written.
    A row that fails to parse or validate is listed under ``errors`` and the
    rest of the file is still previewed — the real import skips such rows too.

    Args:
        csv_path: Path to the CSV file to import.
        db_path: Path to the SQLite database.

    Returns:
        ImportDiff with new, updated, unchanged, and error rows.
    """
    from automation.import_csv import csv_dict_reader, parse_row, require_com_column, validate_row

    diff = ImportDiff(csv_path=csv_path)
    reader = csv_dict_reader(csv_path)
    require_com_column(reader, csv_path)

    # Load existing units keyed by com_number
    # Use a separate connection to avoid mutating the app's shared connection
    import sqlite3 as _sqlite3
    conn = _sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = _sqlite3.Row
    try:
        existing = {row["com_number"]: row for row in conn.execute("SELECT * FROM units").fetchall()}
    finally:
        conn.close()

    for line_num, csv_row in enumerate(reader, start=2):
        if all((v or "").strip() == "" for v in csv_row.values()):
            continue
        raw_com = (csv_row.get("COMNumber") or "").strip()
        label = raw_com or f"? (line {line_num})"
        try:
            row_data = parse_row(csv_row)
        except Exception as e:
            diff.errors.append(_error_row(label, line_num, str(e)))
            continue

        com = row_data.get("com_number")
        if not com:
            diff.errors.append(_error_row(label, line_num, "missing COM number"))
            continue
        val_errors = validate_row(row_data)
        if val_errors:
            diff.errors.append(_error_row(com, line_num, "; ".join(val_errors)))
            continue

        old_row = existing.get(com)
        changes = _csv_row_to_changes(old_row, row_data)
        if old_row is None:
            diff.new_rows.append(RowDiff(com_number=com, status="new", changes=changes))
        elif changes:
            diff.updated_rows.append(RowDiff(com_number=com, status="updated", changes=changes))
        else:
            diff.unchanged_rows.append(RowDiff(com_number=com, status="unchanged"))

    return diff


def _error_row(com_number: str, line_num: int, message: str) -> RowDiff:
    return RowDiff(
        com_number=com_number,
        status="error",
        changes=[{"field": f"line {line_num}", "old": None, "new": message}],
    )


def _csv_row_to_changes(old_row, new_data: dict) -> list[dict]:
    """Compare an old DB row against new CSV data, returning field-level changes.

    Mirrors the column rules in ``automation.import_csv.upsert_row``.
    """
    from automation.import_csv import VALUE_COLUMNS, _same_value

    changes = []
    for field_name in VALUE_COLUMNS:
        if field_name not in new_data:
            continue
        new_val = new_data.get(field_name)

        if old_row is None:
            # New row — every non-empty value is a change
            if new_val not in (None, ""):
                changes.append({"field": field_name, "old": None, "new": new_val})
            continue

        try:
            old_val = old_row[field_name]
        except (IndexError, KeyError):
            old_val = None

        if field_name == "percent_complete" and old_val is not None:
            # The import only sets percent_complete when it is currently NULL
            continue
        if field_name == "unit_state" and not new_val:
            # The import never clears unit_state
            continue

        if not _same_value(old_val, new_val):
            changes.append({"field": field_name, "old": old_val, "new": new_val})

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
