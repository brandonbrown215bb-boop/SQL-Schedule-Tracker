# tests/test_models.py
"""Tests for data/models.py — Unit dataclass, status colors, working days."""

from __future__ import annotations

from datetime import date, timedelta

from data.models import Unit, _working_days_between

# ── _working_days_between ─────────────────────────────────────────


class TestWorkingDaysBetween:
    def test_single_week(self):
        """Mon to Fri of the same week with Mon-Thu schedule = 3 working days (Tue-Thu, exclusive start)."""
        start = date(2025, 6, 16)  # Mon
        end = date(2025, 6, 20)  # Fri
        # Mon is exclusive, so counting from Tue. Mon-Thu schedule → Tue, Wed, Thu = 3
        assert _working_days_between(start, end, [0, 1, 2, 3]) == 3

    def test_mon_fri_schedule(self):
        """Tue to Thu = 2 days (Wed, Thu — start exclusive)."""
        start = date(2025, 6, 17)  # Tue
        end = date(2025, 6, 19)  # Thu
        # Tue exclusive → start at Wed(18, weekday 2). Mon-Thu schedule → Wed, Thu = 2
        assert _working_days_between(start, end, [0, 1, 2, 3]) == 2

    def test_weekend_excluded(self):
        """Thu to Mon: only Mon counts as working day (Fri is excluded for Mon-Thu schedule)."""
        start = date(2025, 6, 19)  # Thu
        end = date(2025, 6, 23)  # Mon
        assert _working_days_between(start, end, [0, 1, 2, 3]) == 1

    def test_tue_fri_schedule(self):
        """Chen works Tue-Fri. Mon-to-Thu span = 3 days (Tue, Wed, Thu)."""
        start = date(2025, 6, 16)  # Mon
        end = date(2025, 6, 19)  # Thu
        assert _working_days_between(start, end, [1, 2, 3, 4]) == 3

    def test_same_day(self):
        """Start date = end date, exclusive start → 0."""
        d = date(2025, 6, 18)  # Wed
        assert _working_days_between(d, d, [0, 1, 2, 3]) == 0

    def test_default_weekdays(self):
        """No weekdays specified → defaults to Mon-Thu [0,1,2,3]. Mon exclusive → Tue, Wed, Thu = 3."""
        start = date(2025, 6, 16)  # Mon
        end = date(2025, 6, 19)  # Thu
        assert _working_days_between(start, end) == 3

    def test_start_after_end(self):
        """Start date after end date → 0."""
        start = date(2025, 6, 20)
        end = date(2025, 6, 16)
        assert _working_days_between(start, end, [0, 1, 2, 3]) == 0


# ── Unit dataclass defaults ───────────────────────────────────────


class TestUnitDefaults:
    def test_default_status_color_is_gray(self):
        unit = Unit(
            com_number="X",
            job_name="Y",
            contract_number="Z",
            description="D",
            detailer="E",
            checking_status="F",
        )
        assert unit.status_color == "gray"

    def test_default_hours_are_zero(self):
        unit = Unit(
            com_number="X",
            job_name="Y",
            contract_number="Z",
            description="D",
            detailer="E",
            checking_status="F",
        )
        assert unit.department_hours == 0.0
        assert unit.percent_complete == 0.0
        assert unit.actual_hours == 0.0

    def test_default_dates_are_none(self):
        unit = Unit(
            com_number="X",
            job_name="Y",
            contract_number="Z",
            description="D",
            detailer="E",
            checking_status="F",
        )
        assert unit.detailing_due_date is None
        assert unit.build_date is None
        assert unit.unit_detailing_start_date is None


# ── Unit.milestones ───────────────────────────────────────────────


class TestMilestones:
    def test_milestones_order(self):
        unit = Unit(
            com_number="X",
            job_name="Y",
            contract_number="Z",
            description="D",
            detailer="E",
            checking_status="F",
            unit_detailing_start_date=date(2025, 1, 1),
            unit_moved_to_checking_date=date(2025, 2, 1),
            unit_detailing_completion_date=date(2025, 3, 1),
            dept_due_date_previous=date(2025, 2, 15),
            detailing_due_date=date(2025, 3, 15),
            build_date=date(2025, 4, 1),
        )
        names = [name for name, _ in unit.milestones]
        assert names == [
            "Detailing Start",
            "Moved to Checking",
            "Detailing Complete",
            "Dept Due (prev)",
            "Detailing Due",
            "Build Date",
        ]

    def test_milestones_include_none_dates(self):
        unit = Unit(
            com_number="X",
            job_name="Y",
            contract_number="Z",
            description="D",
            detailer="E",
            checking_status="F",
        )
        milestones = unit.milestones
        assert len(milestones) == 6
        for _, d in milestones:
            assert d is None


# ── Unit.status_label static method ──────────────────────────────


class TestStatusLabel:
    def test_all_colors(self):
        assert Unit.status_label("gray") == "Unassigned (0%)"
        assert Unit.status_label("yellow") == "In Progress (1-89%)"
        assert Unit.status_label("purple") == "Ready for Checking (90%)"
        assert Unit.status_label("orange") == "Checked & Returned (95%)"
        assert Unit.status_label("green") == "Released (100%)"
        assert Unit.status_label("red") == "Overdue"

    def test_unknown_color(self):
        assert Unit.status_label("chartreuse") == "Unknown"


# ── Unit.calculated_status_color ─────────────────────────────────


class TestCalculatedStatusColor:
    def test_100_percent_is_green(self, completed_unit):
        assert completed_unit.calculated_status_color == "green"

    def test_zero_percent_no_due_date_is_gray(self):
        unit = Unit(
            com_number="X",
            job_name="Y",
            contract_number="Z",
            description="D",
            detailer="E",
            checking_status="F",
            percent_complete=0.0,
            detailing_due_date=None,
        )
        assert unit.calculated_status_color == "gray"

    def test_nonzero_percent_no_due_date_is_yellow(self):
        unit = Unit(
            com_number="X",
            job_name="Y",
            contract_number="Z",
            description="D",
            detailer="E",
            checking_status="F",
            percent_complete=50.0,
            detailing_due_date=None,
        )
        assert unit.calculated_status_color == "yellow"

    def test_past_due_date_is_red(self):
        unit = Unit(
            com_number="X",
            job_name="Y",
            contract_number="Z",
            description="D",
            detailer="E",
            checking_status="F",
            percent_complete=50.0,
            working_days=[0, 1, 2, 3],
            detailing_due_date=date.today() - timedelta(days=1),
        )
        assert unit.calculated_status_color == "red"

    def test_behind_capacity_is_red(self):
        """Huge remaining hours but almost no working days left → red.
        Use a due date far enough ahead for working_days > 0 on any weekday."""
        unit = Unit(
            com_number="X",
            job_name="Y",
            contract_number="Z",
            description="D",
            detailer="E",
            checking_status="F",
            department_hours=100000.0,
            percent_complete=0.0,
            working_days=[0, 1, 2, 3, 4],
            detailing_due_date=date.today() + timedelta(days=7),
        )
        remaining = 100000.0  # essentially all remaining
        # Even with 5 working days in a week: 5 * 10 = 50 available hours
        assert remaining > 50  # sanity
        assert unit.calculated_status_color == "red"

    def test_on_track_is_yellow(self):
        """Remaining hours fit within available capacity → yellow."""
        unit = Unit(
            com_number="X",
            job_name="Y",
            contract_number="Z",
            description="D",
            detailer="E",
            checking_status="F",
            department_hours=20.0,
            percent_complete=50.0,
            working_days=[0, 1, 2, 3],
            detailing_due_date=date.today() + timedelta(days=30),
        )
        assert unit.calculated_status_color == "yellow"

    def test_today_not_overdue(self):
        """Due date is today → not overdue yet (due_today >= 0)."""
        unit = Unit(
            com_number="X",
            job_name="Y",
            contract_number="Z",
            description="D",
            detailer="E",
            checking_status="F",
            percent_complete=50.0,
            working_days=[0, 1, 2, 3],
            detailing_due_date=date.today(),
        )
        assert unit.calculated_status_color == "yellow"
