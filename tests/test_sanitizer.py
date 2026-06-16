# tests/test_sanitizer.py
"""Tests for the InputSanitizer (services.sanitizer)."""

import pytest

from services.sanitizer import InputSanitizer


class TestCleanDate:
    def test_us_format(self):
        assert InputSanitizer.clean_date("01/15/2026") == "2026-01-15"

    def test_iso_format(self):
        assert InputSanitizer.clean_date("2026-01-15") == "2026-01-15"

    def test_short_year(self):
        assert InputSanitizer.clean_date("01/15/26") == "2026-01-15"

    def test_compact_format(self):
        assert InputSanitizer.clean_date("20260115") == "2026-01-15"

    def test_empty_returns_none(self):
        assert InputSanitizer.clean_date("") is None

    def test_none_returns_none(self):
        assert InputSanitizer.clean_date(None) is None

    def test_whitespace_returns_none(self):
        assert InputSanitizer.clean_date("   ") is None

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Could not parse date"):
            InputSanitizer.clean_date("not-a-date")

    def test_european_format(self):
        assert InputSanitizer.clean_date("15-01-2026") == "2026-01-15"


class TestCleanPercent:
    def test_with_percent_sign(self):
        assert InputSanitizer.clean_percent("65%") == 65.0

    def test_without_percent_sign(self):
        assert InputSanitizer.clean_percent("65") == 65.0

    def test_decimal(self):
        assert InputSanitizer.clean_percent("65.5") == 65.5

    def test_comma_decimal(self):
        assert InputSanitizer.clean_percent("65,5") == 65.5

    def test_zero(self):
        assert InputSanitizer.clean_percent("0%") == 0.0

    def test_hundred(self):
        assert InputSanitizer.clean_percent("100%") == 100.0

    def test_empty_returns_zero(self):
        assert InputSanitizer.clean_percent("") == 0.0

    def test_none_returns_zero(self):
        assert InputSanitizer.clean_percent(None) == 0.0

    def test_over_100_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            InputSanitizer.clean_percent("101")

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            InputSanitizer.clean_percent("-5")


class TestCleanNumber:
    def test_integer(self):
        assert InputSanitizer.clean_number("42") == 42.0

    def test_float(self):
        assert InputSanitizer.clean_number("3.14") == 3.14

    def test_comma_separated(self):
        assert InputSanitizer.clean_number("1,234") == 1234.0

    def test_empty_returns_none(self):
        assert InputSanitizer.clean_number("") is None

    def test_none_returns_none(self):
        assert InputSanitizer.clean_number(None) is None


class TestCleanComNumber:
    def test_digits_only(self):
        assert InputSanitizer.clean_com_number("123456") == "123456"

    def test_strips_prefix(self):
        assert InputSanitizer.clean_com_number("COM123456") == "123456"

    def test_uppercase(self):
        assert InputSanitizer.clean_com_number("abc123") == "123"


class TestCleanString:
    def test_trims_whitespace(self):
        assert InputSanitizer.clean_string("  hello  ") == "hello"

    def test_collapses_spaces(self):
        assert InputSanitizer.clean_string("a   b") == "a b"

    def test_empty_returns_none(self):
        assert InputSanitizer.clean_string("") is None

    def test_none_returns_none(self):
        assert InputSanitizer.clean_string(None) is None

    def test_max_length(self):
        result = InputSanitizer.clean_string("hello world", max_length=5)
        assert result == "hello"
        assert len(result) == 5

    def test_max_length_no_truncate(self):
        result = InputSanitizer.clean_string("hi", max_length=10)
        assert result == "hi"
