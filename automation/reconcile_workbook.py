#!/usr/bin/env python3
"""One last reconciliation of schedule.db against the frozen workbook.

Three fixes, each written to its own CSV report:

1. detailers.csv: re-map Matt / Matthew units from the workbook's raw
   Detailer column with the fixed matcher ("Matt" = Matt E, "Matthew" =
   Matthew S). Units whose detailer was changed in the app are left alone.
2. targets.csv: FY26+ units (due on or after 2025-10-01) whose workbook
   Target Dept Hours differ from Dept - IEC get the difference as a
   target adjustment. Same-as units, workbook targets of 0 and non-primary
   identicals are left to the identicals rule.
3. checkers.csv: free-text checking statuses like "Tracy checked" become
   Checker = Tracy V and Checking Status = Checked. Text that is not a
   status moves to Notes, so nothing is lost.

Every change goes to the audit log as "workbook-reconcile". --apply backs up
the database first; without it nothing is written.

Usage:
    python -m automation.reconcile_workbook --workbook MASTER.xlsm --db schedule.db
    python -m automation.reconcile_workbook --workbook MASTER.xlsm --db schedule.db --apply
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from datetime import date, datetime

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from automation.cleanup_detailers import load_canonical_detailers, parse_detailer_field
from data.db import (
    NON_PRIMARY_IDENTICAL_SQL,
    UNIT_TARGET_SQL,
    backup_db,
    close_db,
    get_db,
    log_field_changes,
)
from services.config_service import DEFAULTS

SAVED_BY = "workbook-reconcile"
SHEET = "Current List"
FY26_START = date(2025, 10, 1)

# Current List columns (0-based)
COL_COM, COL_DETAILER, COL_DEPT, COL_TARGET, COL_IEC, COL_SAME_AS = 2, 4, 10, 21, 22, 29

# Units the matcher may move between Matt E and Matthew S.
_MATT_VARIANTS = {"matt", "matt e", "matthew", "matthew e", "matthew s"}
_RECONCILED = ("Matt E", "Matthew S")

# "<Name> checked" / "<Name> checking", anywhere in the status
_CHECKED_RE = re.compile(
    r"\b(?P<name>[A-Za-z]+(?:\s+[A-Za-z]\b\.?)?)\s+(?P<verb>checked|checking)\b",
    re.IGNORECASE,
)
_DONE_STATUSES = {"checking complete", "re-check done", "recheck done", "checked"}


def _com(val) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and val.is_integer():
        val = int(val)
    return str(val).strip()


def _num(val) -> float | None:
    return float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None


def read_workbook(path: str) -> dict[str, dict]:
    """COM → {detailer, target, formula, same_as} from the Current List sheet."""
    from openpyxl import load_workbook

    values = load_workbook(path, read_only=True, data_only=True)
    formulas = load_workbook(path, read_only=True, data_only=False)
    rows: dict[str, dict] = {}
    try:
        pairs = zip(
            values[SHEET].iter_rows(min_row=2, values_only=True),
            formulas[SHEET].iter_rows(min_row=2, values_only=True),
            strict=False,
        )
        for v, f in pairs:
            com = _com(v[COL_COM] if len(v) > COL_COM else None)
            if not com:
                continue
            formula = f[COL_TARGET] if len(f) > COL_TARGET else None
            rows[com] = {
                "detailer": str(v[COL_DETAILER] or "").strip(),
                "target": _num(v[COL_TARGET]) if len(v) > COL_TARGET else None,
                "dept": _num(v[COL_DEPT]) or 0.0,
                "iec": (_num(v[COL_IEC]) if len(v) > COL_IEC else None) or 0.0,
                "formula": formula if isinstance(formula, str) and formula.startswith("=") else "",
                "same_as": str(v[COL_SAME_AS] or "").strip() if len(v) > COL_SAME_AS else "",
            }
    finally:
        values.close()
        formulas.close()
    return rows


def plan_detailers(conn, wb: dict[str, dict]) -> list[dict]:
    canonical = load_canonical_detailers(conn)
    edited_in_app = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT com_number FROM _audit_log WHERE field_name = 'detailer' AND saved_by <> ?",
            (SAVED_BY,),
        )
    }
    changes = []
    for com, detailer in conn.execute("SELECT com_number, COALESCE(detailer, '') FROM units"):
        row = wb.get(com)
        if row is None or detailer.strip().lower() not in _MATT_VARIANTS:
            continue
        mapped, _notes = parse_detailer_field(row["detailer"], canonical)
        if mapped not in _RECONCILED or mapped == detailer:
            continue
        changes.append(
            {
                "com_number": com,
                "workbook_detailer": row["detailer"],
                "old": detailer,
                "new": mapped,
                "action": "skip: changed in app" if com in edited_in_app else "update",
            }
        )
    return changes


def plan_targets(conn, wb: dict[str, dict]) -> list[dict]:
    changes = []
    query = f"""
        SELECT com_number, detailing_due_date, COALESCE(department_hours, 0),
               COALESCE(iec_internal_hours, 0), COALESCE(target_adjustment_hours, 0),
               {UNIT_TARGET_SQL} - COALESCE(target_adjustment_hours, 0),
               {NON_PRIMARY_IDENTICAL_SQL}
        FROM units WHERE TRIM(COALESCE(detailer, '')) <> 'Cancelled'
    """
    for com, due, dept, iec, current_adj, base, non_primary in conn.execute(query):
        row = wb.get(com)
        if row is None or not due or date.fromisoformat(due[:10]) < FY26_START:
            continue
        target = row["target"]
        if target is None or row["same_as"].lower().startswith("same"):
            continue  # same-as units: the identicals rule covers them
        # The hand edit is measured against the workbook's own Dept - IEC, so a
        # Dept Hours change from SSRS since then is not mistaken for one.
        adj = round(target - max(0.0, row["dept"] - row["iec"]), 2)
        if abs(adj - current_adj) <= 0.01:
            continue
        if target == 0:
            action = "skip: workbook target 0 (identical)"
        elif non_primary:
            action = "skip: non-primary identical"
        elif current_adj:
            action = "skip: adjustment already set in app"
        else:
            action = "update"
        changes.append(
            {
                "com_number": com,
                "due": due[:10],
                "dept": dept,
                "iec": iec,
                "formula": row["formula"] or "typed value",
                "workbook_target": target,
                "workbook_dept": row["dept"],
                "app_target": round(max(0.0, base + current_adj), 2),
                "adjustment": adj,
                "new_app_target": round(max(0.0, base + adj), 2),
                "action": action,
            }
        )
    return changes


def _checker_name(raw: str, canonical: dict[str, str]) -> str:
    name, _notes = parse_detailer_field(raw, canonical)
    return name


def plan_checkers(conn, statuses: list[str]) -> list[dict]:
    canonical = load_canonical_detailers(conn)
    known = {s.lower(): s for s in statuses if s}
    changes = []
    rows = conn.execute(
        "SELECT com_number, checking_status, COALESCE(checker, '') FROM units "
        "WHERE TRIM(COALESCE(checking_status, '')) <> ''"
    )
    for com, status, checker in rows:
        text = status.strip()
        lower = text.lower()
        new_status, new_checker, note = text, checker, ""
        m = _CHECKED_RE.search(text)
        if lower in known:
            if known[lower] == text:
                continue
            new_status = known[lower]
        elif lower in _DONE_STATUSES:
            new_status = "Checked"
        elif m and _checker_name(m["name"], canonical):
            new_status = "Checked" if m["verb"].lower() == "checked" else "In checking"
            new_checker = checker or _checker_name(m["name"], canonical)
            # Anything beyond "<Name> checked" keeps the whole original text.
            if f"{text[: m.start()]}{text[m.end() :]}".strip(" ,.;:-"):
                note = text
        else:
            new_status, note = "", text
        changes.append(
            {
                "com_number": com,
                "old_status": status,
                "new_status": new_status,
                "old_checker": checker,
                "new_checker": new_checker,
                "note_added": f"Checking: {note}" if note else "",
            }
        )
    return changes


def _apply_unit_changes(conn, com: str, new_values: dict) -> None:
    old_row = conn.execute("SELECT * FROM units WHERE com_number = ?", (com,)).fetchone()
    sets = ", ".join(f"{k} = ?" for k in new_values)
    conn.execute(
        f"UPDATE units SET {sets}, updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') "
        "WHERE com_number = ?",
        (*new_values.values(), com),
    )
    log_field_changes(conn, com, old_row, new_values, saved_by=SAVED_BY, commit=False)


def apply(conn, detailers, targets, checkers) -> None:
    for c in detailers:
        if c["action"] == "update":
            _apply_unit_changes(conn, c["com_number"], {"detailer": c["new"]})
    for c in targets:
        if c["action"] == "update":
            reason = f"From workbook target ({c['formula']})"
            _apply_unit_changes(
                conn,
                c["com_number"],
                {
                    "target_adjustment_hours": c["adjustment"],
                    "target_adjustment_reason": reason,
                    "target_dept_hours": c["new_app_target"],
                },
            )
    for c in checkers:
        values = {"checking_status": c["new_status"], "checker": c["new_checker"]}
        if c["note_added"]:
            notes = conn.execute(
                "SELECT COALESCE(notes, '') FROM units WHERE com_number = ?", (c["com_number"],)
            ).fetchone()[0]
            values["notes"] = f"{notes} — {c['note_added']}" if notes.strip() else c["note_added"]
        _apply_unit_changes(conn, c["com_number"], values)
    conn.commit()


def _write_report(path: str, rows: list[dict]) -> None:
    if not rows:
        open(path, "w").close()
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _count(rows: list[dict], key: str = "action") -> str:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r[key]] = counts.get(r[key], 0) + 1
    return ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "none"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workbook", required=True, help="Frozen copy of the MASTER workbook")
    parser.add_argument("--db", required=True, help="Path to schedule.db")
    parser.add_argument("--report-dir", default=None, help="Where to write the CSV reports")
    parser.add_argument("--apply", action="store_true", help="Write the changes (backs up first)")
    args = parser.parse_args()

    report_dir = args.report_dir or os.path.join(
        os.path.dirname(os.path.abspath(args.db)),
        "reconcile_reports",
        datetime.now().strftime("%Y%m%d_%H%M%S"),
    )
    os.makedirs(report_dir, exist_ok=True)

    print(f"Reading workbook {args.workbook} ...")
    wb = read_workbook(args.workbook)
    print(f"  {len(wb)} COM rows")

    import yaml

    statuses = DEFAULTS["checking_statuses"]
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            statuses = (yaml.safe_load(f) or {}).get("checking_statuses") or statuses

    conn = get_db(args.db)  # runs schema migrations (checker column, Matt E rename)
    try:
        detailers = plan_detailers(conn, wb)
        targets = plan_targets(conn, wb)
        checkers = plan_checkers(conn, statuses)

        _write_report(os.path.join(report_dir, "detailers.csv"), detailers)
        _write_report(os.path.join(report_dir, "targets.csv"), targets)
        _write_report(os.path.join(report_dir, "checkers.csv"), checkers)

        print(f"Detailers: {_count(detailers)}")
        print(f"Targets (FY26+; older units keep Dept - IEC): {_count(targets)}")
        print(f"Checkers: {len(checkers)} status change(s)")
        print(f"Reports: {report_dir}")

        if args.apply:
            backup = backup_db(args.db)
            if not backup:
                print("Backup failed; nothing written.")
                return 1
            print(f"Backup: {backup}")
            apply(conn, detailers, targets, checkers)
            print("Applied.")
        else:
            print("Dry run: nothing written. Re-run with --apply to write the changes.")
    finally:
        close_db()
    return 0


if __name__ == "__main__":
    sys.exit(main())
