# tests/test_audit_findings.py
"""
Unit tests reproducing identified bugs/pitfalls in the SQL-Schedule-Tracker project.
These tests demonstrate the bugs by asserting the correct, expected behavior, which
fails due to the bugs currently present in the codebase.
"""

from __future__ import annotations

from datetime import date

import pytest

from data.loader import unit_fingerprint
from data.models import Unit
from services.validation import FieldRule, ValidationError, validate_input


def test_fingerprint_caching_stale_value_bug():
    """
    1. Fingerprint Caching Stale Value Bug
    
    Test that computes unit_fingerprint(unit), modifies a field (e.g., job_name),
    and computes the fingerprint again. Assert that the two fingerprints are different.
    This assertion will fail because the module-level _fingerprint_cache caches and
    returns the stale fingerprint.
    """
    unit = Unit(
        com_number="COM-BUG-TEST-1",
        job_name="Original Job Name",
        contract_number="C-1001",
        description="Audit Testing Unit",
        detailer="Jackie H",
        checking_status="Unassigned",
    )

    # Compute initial fingerprint
    fp_initial = unit_fingerprint(unit)

    # Modify the job name
    unit.job_name = "Modified Job Name"

    # Compute the fingerprint again
    fp_after_mod = unit_fingerprint(unit)

    # Under correct behavior, the fingerprint should reflect the modification.
    # Currently, it returns the cached stale value, making this assertion fail.
    assert fp_initial != fp_after_mod, (
        f"Expected fingerprint to change after modifying unit, but got the same cached value: {fp_initial}"
    )


def test_capacity_due_today_bug():
    """
    2. Capacity Due-Today Bug
    
    Test that creates a unit due today (available working days = 0) with non-zero
    department hours and 0% complete. Assert that calculated_status_color evaluates
    to 'red' (since remaining hours > available capacity). Currently, it evaluates
    to 'gray', making the assertion fail.
    """
    unit = Unit(
        com_number="COM-BUG-TEST-2",
        job_name="Due Today Capacity Bug",
        contract_number="C-1002",
        description="Audit Testing Unit",
        detailer="Jackie H",
        checking_status="Unassigned",
        department_hours=40.0,
        percent_complete=0.0,
        detailing_due_date=date.today(),
        working_days=[0, 1, 2, 3],  # Monday-Thursday schedule
    )

    color = unit.calculated_status_color

    # With 0 working days left and 40 remaining hours, this is overdue/potential miss (red).
    # Currently, it skips capacity checks and returns 'gray', making this assertion fail.
    assert color == "red", (
        f"Expected calculated_status_color to be 'red' for a unit due today with 40 remaining hours, but got '{color}'"
    )


def test_decorator_validation_positional_arguments_bug():
    """
    3. Decorator Validation Positional Arguments Bug
    
    Test that invokes a method decorated with @validate_input by passing invalid
    arguments positionally. Assert that ValidationError is raised. Since the
    decorator currently only validates kwargs, no error is raised, making the
    assertion fail.
    """

    class MockService:
        @validate_input(test_hours=FieldRule(nullable=False, min_value=0.0, max_value=200.0))
        def set_hours(self, test_hours: float) -> float:
            return test_hours

    service = MockService()

    # Asserting that ValidationError is raised when invoking with invalid positional arguments.
    # Since the validation decorator currently ignores positional args, it will execute without
    # raising ValidationError, causing this test to fail.
    with pytest.raises(ValidationError):
        service.set_hours(-50.0)
