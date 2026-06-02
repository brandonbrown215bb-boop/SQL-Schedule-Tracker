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
    # NOTE: ``calculated_status_color`` only returns "gray", "yellow", "green", or "red".
    # The "purple" and "orange" status colors are MANUALLY ASSIGNED ONLY — they are never
    # returned by the calculation logic. Do not waste time debugging why
    # ``calculated_status_color`` never returns "purple" or "orange"; those values
    # must be set directly on the field (e.g., from Excel data or user input).
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

    # Internal cache/sync metadata. Not persisted as Unit fields in Excel.
    excel_row: int | None = field(default=None, compare=False, repr=False)
    fingerprint: str = field(default="", compare=False, repr=False)
    base_revision: int = field(default=0, compare=False, repr=False)

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
            "purple": "Ready for Checking (90%)",
            "orange": "Checked & Returned (95%)",
            "green": "Released (100%)",
            "red": "Overdue",
        }
        return labels.get(color, "Unknown")

    @property
    def calculated_status_color(self) -> StatusColor:
        today = date.today()
        HOURS_PER_DAY = 10.0  # 40 dept hours / 4 working days per week

        # 100% complete is always green (released)
        if self.percent_complete >= 100.0:
            return "green"

        # No due date: use percentage alone
        if self.detailing_due_date is None:
            if self.percent_complete <= 0:
                return "gray"
            return "yellow"

        days_until_due = (self.detailing_due_date - today).days

        # Overdue — red
        if days_until_due < 0:
            return "red"

        # Capacity-based rules (using working days, not calendar days)
        working_days = _working_days_between(today, self.detailing_due_date, self.working_days)
        if working_days > 0 and self.department_hours > 0:
            remaining_hours = self.department_hours * (1.0 - self.percent_complete / 100.0)
            available_hours = working_days * HOURS_PER_DAY

            # Behind schedule: remaining work exceeds available capacity
            if remaining_hours > available_hours:
                return "red"

        # On track or close
        return "yellow"