# tests/test_validation.py
"""Tests for the validation layer (services.validation)."""

import pytest

from data.models import Unit
from services.validation import (
    UNIT_FIELD_RULES,
    FieldRule,
    ValidationError,
    validate_unit,
)


@pytest.fixture
def valid_unit():
    return Unit(
        com_number="123456",
        job_name="Test Job",
        contract_number="CONT-001",
        description="Test description",
        detailer="— Unassigned —",
        checking_status="In Progress",
        notes="Some notes",
        department_hours=100.0,
        target_department_hours=80.0,
        iec_internal_hours=20.0,
        percent_complete=50.0,
        actual_hours=25.0,
    )


class TestValidateUnit:
    def test_valid_unit_passes(self, valid_unit):
        valid, errors = validate_unit(valid_unit)
        assert valid is True
        assert errors == []

    def test_com_number_required(self, valid_unit):
        valid_unit.com_number = ""
        valid, errors = validate_unit(valid_unit)
        assert valid is False
        assert any("com_number" in e for e in errors)

    def test_com_number_pattern(self, valid_unit):
        valid_unit.com_number = "ABC"
        valid, errors = validate_unit(valid_unit)
        assert valid is False
        assert any("com_number" in e for e in errors)

    def test_com_number_too_short(self, valid_unit):
        valid_unit.com_number = "123"
        valid, _errors = validate_unit(valid_unit)
        assert valid is False

    def test_com_number_too_long(self, valid_unit):
        valid_unit.com_number = "123456789012345678901"
        valid, _errors = validate_unit(valid_unit)
        assert valid is False

    def test_percent_complete_min_boundary(self, valid_unit):
        valid_unit.percent_complete = 0.0
        valid, _errors = validate_unit(valid_unit)
        assert valid is True

    def test_percent_complete_max_boundary(self, valid_unit):
        valid_unit.percent_complete = 100.0
        valid, _errors = validate_unit(valid_unit)
        assert valid is True

    def test_percent_complete_over_100(self, valid_unit):
        valid_unit.percent_complete = 101.0
        valid, errors = validate_unit(valid_unit)
        assert valid is False
        assert any("percent_complete" in e for e in errors)

    def test_percent_complete_negative(self, valid_unit):
        valid_unit.percent_complete = -1.0
        valid, _errors = validate_unit(valid_unit)
        assert valid is False

    def test_department_hours_negative(self, valid_unit):
        valid_unit.department_hours = -1.0
        valid, errors = validate_unit(valid_unit)
        assert valid is False
        assert any("department_hours" in e for e in errors)

    def test_actual_hours_negative(self, valid_unit):
        valid_unit.actual_hours = -5.0
        valid, errors = validate_unit(valid_unit)
        assert valid is False
        assert any("actual_hours" in e for e in errors)

    def test_invalid_detailer(self, valid_unit):
        valid_unit.detailer = "Not A Real Detailer"
        valid, errors = validate_unit(valid_unit)
        assert valid is False
        assert any("detailer" in e for e in errors)

    def test_valid_detailer(self, valid_unit):
        valid_unit.detailer = "Brandon B"
        valid, _errors = validate_unit(valid_unit)
        assert valid is True

    def test_invalid_status_color(self, valid_unit):
        valid_unit.status_color = "neon"
        valid, errors = validate_unit(valid_unit)
        assert valid is False
        assert any("status_color" in e for e in errors)

    def test_valid_status_color(self, valid_unit):
        for color in ["gray", "yellow", "purple", "orange", "green", "red"]:
            valid_unit.status_color = color
            valid, _errors = validate_unit(valid_unit)
            assert valid is True, f"Color '{color}' should be valid"

    def test_notes_max_length(self, valid_unit):
        valid_unit.notes = "x" * 2001
        valid, errors = validate_unit(valid_unit)
        assert valid is False
        assert any("notes" in e for e in errors)

    def test_notes_nullable(self, valid_unit):
        valid_unit.notes = None
        valid, _errors = validate_unit(valid_unit)
        assert valid is True

    def test_description_nullable(self, valid_unit):
        valid_unit.description = None
        valid, _errors = validate_unit(valid_unit)
        assert valid is True

    def test_checking_status_nullable(self, valid_unit):
        valid_unit.checking_status = None
        valid, _errors = validate_unit(valid_unit)
        assert valid is True

    def test_multiple_errors(self, valid_unit):
        valid_unit.com_number = ""
        valid_unit.percent_complete = 200.0
        valid_unit.department_hours = -10.0
        valid, errors = validate_unit(valid_unit)
        assert valid is False
        assert len(errors) >= 3

    def test_integer_percent_passes(self, valid_unit):
        valid_unit.percent_complete = 50
        valid, _errors = validate_unit(valid_unit)
        assert valid is True

    def test_integer_hours_pass(self, valid_unit):
        valid_unit.department_hours = 100
        valid_unit.actual_hours = 25
        valid, _errors = validate_unit(valid_unit)
        assert valid is True


class TestFieldRule:
    def test_custom_validator(self):
        rule = FieldRule(
            type_check=str,
            custom_validator=lambda v: None if len(v) >= 3 else "too short",
        )
        errors = []
        value = "ab"
        if rule.custom_validator:
            result = rule.custom_validator(value)
            if result:
                errors.append(result)
        assert errors == ["too short"]

    def test_custom_validator_passes(self):
        rule = FieldRule(
            type_check=str,
            custom_validator=lambda v: None if len(v) >= 3 else "too short",
        )
        errors = []
        value = "abc"
        if rule.custom_validator:
            result = rule.custom_validator(value)
            if result:
                errors.append(result)
        assert errors == []


class TestValidationError:
    def test_single_error(self):
        err = ValidationError(["field: error"])
        assert str(err) == "field: error"
        assert err.errors == ["field: error"]

    def test_multiple_errors(self):
        err = ValidationError(["a: 1", "b: 2"])
        assert str(err) == "a: 1; b: 2"
        assert len(err.errors) == 2


class TestValidateUnitCustomRules:
    def test_with_custom_rules(self, valid_unit):
        custom_rules = {
            "percent_complete": FieldRule(
                type_check=(int, float),
                min_value=0,
                max_value=50,  # stricter than default
            ),
        }
        valid_unit.percent_complete = 75.0
        valid, _errors = validate_unit(valid_unit, custom_rules)
        assert valid is False

    def test_with_override_rules(self, valid_unit):
        # Override to allow None for notes (even though default already allows it)
        rules = dict(UNIT_FIELD_RULES)
        rules["notes"] = FieldRule(type_check=str, nullable=True, max_length=5000)
        valid_unit.notes = "x" * 3000
        valid, _errors = validate_unit(valid_unit, rules)
        assert valid is True
