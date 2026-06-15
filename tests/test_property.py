# tests/test_property.py
"""Property-based tests using Hypothesis.

5 properties tested:
1. calculated_status_color always returns a valid status color string
2. alert_level always returns a valid level string
3. percent_complete validation rejects out-of-range values
4. calculated_status_color is deterministic (same input → same output)
5. unit_fingerprint is stable across Unit instances with same fields
"""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from data.models import Unit
from data.writer import ValidationError, _validate_unit

# ── Strategies ───────────────────────────────────────────────────────────────

VALID_STATUS_COLORS = {"gray", "yellow", "purple", "orange", "green", "red"}
VALID_ALERT_LEVELS = {"COMPLETE", "UNSET", "OVERDUE", "URGENT", "APPROACHING", "ON_TRACK"}


def _any_unit() -> st.SearchStrategy[Unit]:
    """Build a Unit with arbitrary but valid inputs."""
    return st.builds(
        Unit,
        com_number=st.from_regex(r"[0-9A-Za-z]{1,20}", fullmatch=True),
        job_name=st.text(min_size=0, max_size=50),
        contract_number=st.text(min_size=0, max_size=20),
        description=st.text(min_size=0, max_size=100),
        detailer=st.text(min_size=0, max_size=30),
        checking_status=st.text(min_size=0, max_size=30),
        notes=st.text(min_size=0, max_size=200),
        status_color=st.sampled_from(sorted(VALID_STATUS_COLORS)),
        department_hours=st.floats(min_value=-100, max_value=10000, allow_nan=False),
        target_department_hours=st.floats(min_value=-100, max_value=10000, allow_nan=False),
        iec_internal_hours=st.floats(min_value=0, max_value=5000, allow_nan=False),
        percent_complete=st.floats(
            min_value=0, max_value=100, allow_nan=False, allow_infinity=False
        ),
        actual_hours=st.floats(min_value=0, max_value=5000, allow_nan=False),
        working_days=st.none()
        | st.lists(st.integers(min_value=0, max_value=4), min_size=0, max_size=5),
        unit_detailing_start_date=st.none()
        | st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
        unit_moved_to_checking_date=st.none()
        | st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
        unit_detailing_completion_date=st.none()
        | st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
        dept_due_date_previous=st.none()
        | st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
        detailing_due_date=st.none()
        | st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
        build_date=st.none() | st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
    )


# ── Property 1: calculated_status_color always valid ─────────────────────────


@given(unit=_any_unit())
@settings(max_examples=200)
def test_calculated_status_color_returns_valid_string(unit: Unit):
    """calculated_status_color must always return a member of valid StatusColor."""
    result = unit.calculated_status_color
    assert result in VALID_STATUS_COLORS, f"Invalid status color: {result!r}"


# ── Property 2: alert_level always valid ─────────────────────────────────────


@given(unit=_any_unit())
@settings(max_examples=200)
def test_alert_level_returns_valid_string(unit: Unit):
    """alert_level must always return a member of valid alert levels."""
    result = unit.alert_level
    assert result in VALID_ALERT_LEVELS, f"Invalid alert level: {result!r}"


# ── Property 3: percent_complete validation ──────────────────────────────────


@given(pct=st.floats(min_value=-10, max_value=110, allow_nan=False, allow_infinity=False))
@settings(max_examples=200)
def test_validate_percent_complete_boundaries(pct: float):
    """Unit with percent_complete in [0,100] must pass validation.
    Values outside must raise ValidationError."""
    unit = Unit(
        com_number="TEST",
        job_name="",
        contract_number="",
        description="",
        detailer="",
        checking_status="",
        percent_complete=pct,
        department_hours=40.0,
        actual_hours=0.0,
    )
    if pct < 0 or pct > 100:
        with pytest.raises(ValidationError, match="percent_complete"):
            _validate_unit(unit)
    else:
        # Should pass without error (other fields may warn but we check pct only)
        _validate_unit(unit)


# ── Property 4: calculated_status_color is deterministic ─────────────────────


@given(unit=_any_unit())
@settings(max_examples=200)
def test_calculated_status_color_deterministic(unit: Unit):
    """Same Unit object must return the same status color across calls."""
    first = unit.calculated_status_color
    second = unit.calculated_status_color
    assert first == second, f"Status color not deterministic: {first!r} vs {second!r}"


# ── Property 5: fingerprint stability ────────────────────────────────────────


@given(
    com=st.from_regex(r"[0-9]{5}", fullmatch=True),
    pct=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
    hrs=st.floats(min_value=0, max_value=1000, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200)
def test_fingerprint_stable_for_same_fields(com: str, pct: float, hrs: float):
    """Two Unit objects with identical fields must produce the same fingerprint."""
    from data.loader import unit_fingerprint

    u1 = Unit(
        com_number=com,
        job_name="Job",
        contract_number="CN-001",
        description="Desc",
        detailer="Carl M",
        checking_status="",
        department_hours=hrs,
        percent_complete=pct,
        actual_hours=hrs * 0.5,
        target_department_hours=40.0,
    )
    u2 = Unit(
        com_number=com,
        job_name="Job",
        contract_number="CN-001",
        description="Desc",
        detailer="Carl M",
        checking_status="",
        department_hours=hrs,
        percent_complete=pct,
        actual_hours=hrs * 0.5,
        target_department_hours=40.0,
    )
    assert unit_fingerprint(u1) == unit_fingerprint(u2), (
        f"Fingerprint differs for identical units: {unit_fingerprint(u1)} vs {unit_fingerprint(u2)}"
    )
