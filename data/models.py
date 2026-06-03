# data/models.py
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal


def _working_days_between(start: date, end: date, working_weekdays: list[int] | None = None) -> int:
    """Count working days from start (exclusive) to end (inclusive).

    Args:
        start: Start date (exclusive).
        end: End date (inclusive).
        working_weekdays: List of weekday numbers (0=Mon … 4=Fri).
            Defaults to Mon-Thu [0,1,2,3].
    """
    if working_weekdays is None:
        working_weekdays = [0, 1, 2, 3]
    count = 0
    current = start + timedelta(days=1)
    while current <= end:
        if current.weekday() in working_weekdays:
            count += 1
        current += timedelta(days=1)
    return count


StatusColor = Literal["gray", "yellow", "purple", "orange", "green", "red"]


@dataclass
class Unit:
    com_number: str
    job_name: str
    contract_number: str
    description: str
    detailer: str
    checking_status: str

    # Computed status color (not stored in Excel)
    #
    # ``calculated_status_color`` returns a status based on completion percentage
    # and due date logic. It can now return all color values:
    #   gray(0%) → yellow(1-89%) → purple(90-94%) → orange(95-99%) → green(100%)
    #   red when overdue or behind schedule.
    # The "purple" and "orange" status colors can also be MANUALLY ASSIGNED.
    status_color: StatusColor = "gray"

    # Numeric fields
    department_hours: float = 0.0
    target_department_hours: float = 0.0
    iec_internal_hours: float = 0.0
    percent_complete: float = 0.0
    actual_hours: float = 0.0
    working_days: list[int] | None = None

    # Date fields — all Optional since some may be blank
    unit_detailing_start_date: date | None = None
    unit_moved_to_checking_date: date | None = None
    unit_detailing_completion_date: date | None = None
    dept_due_date_previous: date | None = None
    detailing_due_date: date | None = None
    build_date: date | None = None

    # Optimistic locking — set by db.py from SQLite updated_at column.
    # Compared in writer.py before saving to detect concurrent edits.
    updated_at: str = field(default="", compare=False, repr=False)

    # Internal cache/sync metadata. Not persisted as Unit fields in Excel.
    excel_row: int | None = field(default=None, compare=False, repr=False)
    fingerprint: str = field(default="", compare=False, repr=False)
    base_revision: int = field(default=0, compare=False, repr=False)

    # Transient: due date changed detection (set on reload, cleared on selection).
    # Not persisted to DB — purely an in-memory flag for visual indicators.
    due_date_changed: bool = field(default=False, compare=False, repr=False)
    previous_detailing_due_date: date | None = field(default=None, compare=False, repr=False)

    # Transient: set to True by _apply_identicals when this unit is a non-primary
    # identical (shares contract_number with other units and has a later due date).
    # When True, the edit form should NOT auto-calculate target_department_hours.
    is_non_primary_identical: bool = field(default=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        """Clear computed caches after construction."""
        self._clear_caches()

    def _clear_caches(self) -> None:
        """Reset any computed caches."""
        self._milestones_cache: list[tuple[str, date | None]] | None = None

    @property
    def milestones(self) -> list[tuple[str, date | None]]:
        """Ordered timeline of milestone dates (cached after first call).

        Detailing Due is the upper limit — Build Date is excluded.
        """
        if not hasattr(self, "_milestones_cache") or self._milestones_cache is None:
            self._milestones_cache = [
                ("Detailing Start", self.unit_detailing_start_date),
                ("Moved to Checking", self.unit_moved_to_checking_date),
                ("Detailing Complete", self.unit_detailing_completion_date),
                ("Dept Due (prev)", self.dept_due_date_previous),
                ("Detailing Due", self.detailing_due_date),
            ]
        return self._milestones_cache

    @staticmethod
    def status_label(color: str) -> str:
        labels = {
            "gray": "Unassigned (0%)",
            "yellow": "In Progress (1-89%)",
            "purple": "Ready for Checking (90-94%)",
            "orange": "Checked & Returned (95-99%)",
            "green": "Released (100%)",
            "red": "Overdue/Potential Miss",
        }
        return labels.get(color, "Unknown")

    @property
    def calculated_status_color(self) -> StatusColor:
        today = date.today()
        HOURS_PER_DAY = 10.0  # 40 dept hours / 4 working days per week
        pct = self.percent_complete

        # Percentage-based gates — 100% complete always green regardless of due date
        if pct >= 100.0:
            return "green"

        # Overdue / behind-schedule checks only apply to incomplete units
        if self.detailing_due_date is not None:
            days_until_due = (self.detailing_due_date - today).days

            # Past due — red
            if days_until_due < 0:
                return "red"

            # Capacity-based rules (using working days, not calendar days)
            working_days = _working_days_between(today, self.detailing_due_date, self.working_days)
            if working_days > 0 and self.department_hours > 0:
                remaining_hours = self.department_hours * (1.0 - pct / 100.0)
                available_hours = working_days * HOURS_PER_DAY

                # Behind schedule: remaining work exceeds available capacity
                if remaining_hours > available_hours:
                    return "red"
        if pct >= 95.0:
            return "orange"
        if pct >= 90.0:
            return "purple"
        if pct > 0.0:
            return "yellow"

        return "gray"
