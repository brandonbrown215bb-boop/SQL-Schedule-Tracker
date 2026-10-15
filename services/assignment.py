"""Detailer assignment rules used by the list's right-click menu.

Zero Qt dependencies.

Rules:
- Assigning a detailer sets the start date to today.
- A unit without a detailer has no start date.
- Moving a unit from one detailer to another (or unassigning it) is noted in
  the unit's notes, since it should be rare and visible.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from data.models import Unit

UNASSIGNED = ""
UNASSIGNED_LABELS = ("— Unassigned —", "Unassigned", "")


def _append_note(notes: str, line: str) -> str:
    notes = (notes or "").rstrip()
    return f"{notes}\n{line}" if notes else line


def assign_detailer(unit: Unit, detailer: str, today: date | None = None) -> Unit | None:
    """Return a copy of *unit* assigned to *detailer*, or None if nothing changes.

    *unit* itself is never modified, so a failed save leaves the on-screen data
    untouched. Pass an unassigned label (or "") to unassign.
    """
    today = today or date.today()
    new_detailer = UNASSIGNED if detailer.strip() in UNASSIGNED_LABELS else detailer.strip()
    old_detailer = UNASSIGNED if (unit.detailer or "").strip() in UNASSIGNED_LABELS else unit.detailer.strip()
    if new_detailer == old_detailer:
        return None

    updated = replace(unit)
    updated.detailer = new_detailer
    updated.unit_detailing_start_date = today if new_detailer else None

    if old_detailer:
        stamp = today.strftime("%m/%d/%Y")
        if new_detailer:
            line = f"{stamp}: reassigned from {old_detailer} to {new_detailer}"
        else:
            line = f"{stamp}: unassigned from {old_detailer}"
        updated.notes = _append_note(unit.notes, line)

    return updated


def mark_cancelled(unit: Unit) -> Unit | None:
    """Return a cancelled copy of *unit* (detailer Cancelled, 0 target hours), or None if already cancelled."""
    if unit.detailer == "Cancelled":
        return None
    updated = replace(unit)
    updated.detailer = "Cancelled"
    updated.target_department_hours = 0.0
    return updated
