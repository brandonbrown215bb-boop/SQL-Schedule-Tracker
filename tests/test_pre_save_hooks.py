# tests/test_pre_save_hooks.py
"""Tests for PreSaveHookRegistry (services.pre_save_hooks)."""

import pytest

from data.models import Unit
from services.pre_save_hooks import (
    PreSaveHookRegistry,
    date_order_hook,
    non_negative_hours_hook,
    non_primary_identical_hook,
    percent_complete_range_hook,
    target_hours_hook,
)
from services.validation import ValidationError


@pytest.fixture
def base_unit():
    return Unit(
        com_number="123456",
        job_name="Test",
        contract_number="CONT-001",
        description="Test",
        detailer="— Unassigned —",
        checking_status="",
        department_hours=100.0,
        target_department_hours=80.0,
        iec_internal_hours=20.0,
        percent_complete=50.0,
        actual_hours=25.0,
    )


class TestPreSaveHookRegistry:
    def test_register_and_run(self, base_unit):
        registry = PreSaveHookRegistry()

        def _hook(u, ctx):
            return ["warning1"]

        registry.register("test", _hook)
        warnings = registry.run_all(base_unit)
        assert warnings == ["warning1"]

    def test_multiple_hooks(self, base_unit):
        registry = PreSaveHookRegistry()

        def _hook_a(u, ctx):
            return ["w1"]

        def _hook_b(u, ctx):
            return ["w2"]

        registry.register("a", _hook_a)
        registry.register("b", _hook_b)
        warnings = registry.run_all(base_unit)
        assert len(warnings) == 2

    def test_priority_ordering(self, base_unit):
        registry = PreSaveHookRegistry()
        order = []

        def _hook_b_priority(u, ctx):
            order.append("b")
            return []

        def _hook_a_priority(u, ctx):
            order.append("a")
            return []

        registry.register("b", _hook_b_priority, priority=200)
        registry.register("a", _hook_a_priority, priority=10)
        registry.run_all(base_unit)
        assert order == ["a", "b"]

    def test_unregister(self, base_unit):
        registry = PreSaveHookRegistry()

        def _hook_unregister(u, ctx):
            return ["warning"]

        registry.register("test", _hook_unregister)
        registry.unregister("test")
        warnings = registry.run_all(base_unit)
        assert warnings == []

    def test_validation_error_propagates(self, base_unit):
        registry = PreSaveHookRegistry()

        def _hook_validation_error(u, ctx):
            raise ValidationError(["fatal"])

        registry.register("bad", _hook_validation_error)
        with pytest.raises(ValidationError):
            registry.run_all(base_unit)

    def test_exception_becomes_warning(self, base_unit):
        registry = PreSaveHookRegistry()

        def _hook_buggy(u, ctx):
            raise RuntimeError("oops")

        registry.register("buggy", _hook_buggy)
        warnings = registry.run_all(base_unit)
        assert len(warnings) == 1
        assert "Internal validation error" in warnings[0]


class TestDateOrderHook:
    def test_no_dates_no_warning(self, base_unit):
        warnings = date_order_hook(base_unit, {})
        assert warnings == []

    def test_single_date_no_warning(self, base_unit):
        base_unit.unit_detailing_start_date = "2026-01-01"
        warnings = date_order_hook(base_unit, {})
        assert warnings == []

    def test_correct_order_no_warning(self, base_unit):
        base_unit.unit_detailing_start_date = "2026-01-01"
        base_unit.unit_moved_to_checking_date = "2026-01-15"
        warnings = date_order_hook(base_unit, {})
        assert warnings == []

    def test_reversed_order_warns(self, base_unit):
        base_unit.unit_detailing_start_date = "2026-01-15"
        base_unit.unit_moved_to_checking_date = "2026-01-01"
        warnings = date_order_hook(base_unit, {})
        assert len(warnings) == 1
        assert "Date order" in warnings[0]

    def test_all_three_dates_reversed(self, base_unit):
        base_unit.unit_detailing_start_date = "2026-02-01"
        base_unit.unit_moved_to_checking_date = "2026-01-15"
        base_unit.unit_detailing_completion_date = "2026-01-30"
        warnings = date_order_hook(base_unit, {})
        assert len(warnings) == 1  # only start > checking


class TestNonPrimaryIdenticalHook:
    def test_non_primary_clears_target(self, base_unit):
        base_unit.is_non_primary_identical = True
        base_unit.target_department_hours = 50.0
        warnings = non_primary_identical_hook(base_unit, {})
        assert base_unit.target_department_hours == 0.0
        assert warnings == []

    def test_primary_unchanged(self, base_unit):
        base_unit.is_non_primary_identical = False
        base_unit.target_department_hours = 50.0
        non_primary_identical_hook(base_unit, {})
        assert base_unit.target_department_hours == 50.0


class TestTargetHoursHook:
    def test_auto_calculates(self, base_unit):
        base_unit.department_hours = 100.0
        base_unit.iec_internal_hours = 30.0
        base_unit.target_department_hours = 0.0
        target_hours_hook(base_unit, {})
        assert base_unit.target_department_hours == 70.0

    def test_non_primary_unchanged(self, base_unit):
        base_unit.is_non_primary_identical = True
        base_unit.target_department_hours = 0.0
        target_hours_hook(base_unit, {})
        assert base_unit.target_department_hours == 0.0

    def test_non_negative(self, base_unit):
        base_unit.department_hours = 10.0
        base_unit.iec_internal_hours = 50.0
        base_unit.target_department_hours = 5.0
        target_hours_hook(base_unit, {})
        assert base_unit.target_department_hours == 0.0


class TestPercentCompleteRangeHook:
    def test_valid_passes(self, base_unit):
        assert percent_complete_range_hook(base_unit, {}) == []

    def test_negative_raises(self, base_unit):
        base_unit.percent_complete = -1.0
        with pytest.raises(ValidationError):
            percent_complete_range_hook(base_unit, {})

    def test_over_100_raises(self, base_unit):
        base_unit.percent_complete = 101.0
        with pytest.raises(ValidationError):
            percent_complete_range_hook(base_unit, {})

    def test_zero_passes(self, base_unit):
        base_unit.percent_complete = 0.0
        assert percent_complete_range_hook(base_unit, {}) == []

    def test_hundred_passes(self, base_unit):
        base_unit.percent_complete = 100.0
        assert percent_complete_range_hook(base_unit, {}) == []


class TestNonNegativeHoursHook:
    def test_valid_passes(self, base_unit):
        assert non_negative_hours_hook(base_unit, {}) == []

    def test_negative_dept_raises(self, base_unit):
        base_unit.department_hours = -1.0
        with pytest.raises(ValidationError):
            non_negative_hours_hook(base_unit, {})

    def test_negative_actual_raises(self, base_unit):
        base_unit.actual_hours = -1.0
        with pytest.raises(ValidationError):
            non_negative_hours_hook(base_unit, {})

    def test_multiple_errors(self, base_unit):
        base_unit.department_hours = -1.0
        base_unit.actual_hours = -2.0
        with pytest.raises(ValidationError) as exc_info:
            non_negative_hours_hook(base_unit, {})
        assert len(exc_info.value.errors) == 2
