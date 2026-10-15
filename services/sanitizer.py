# services/sanitizer.py
"""InputSanitizer — cleaning pipeline for external data (CSV, SSRS).

Normalizes and validates raw input strings before they enter the system.
Zero Qt dependencies.
"""

from __future__ import annotations

import re
from datetime import datetime


class InputSanitizer:
    """Cleaning pipeline for external data (CSV, SSRS, API)."""

    # Accepted date formats (tried in order)
    DATE_FORMATS: list[str] = [
        "%m/%d/%Y",  # 01/15/2026
        "%Y-%m-%d",  # 2026-01-15
        "%m/%d/%y",  # 01/15/26
        "%d-%b-%Y",  # 15-Jan-2026
        "%Y%m%d",  # 20260115
        "%B %d, %Y",  # January 15, 2026
        "%d-%m-%Y",  # 15-01-2026 (European)
    ]

    # Trailing time-of-day that SSRS/Excel may append to a date, e.g.
    # "1/15/2026 12:00:00 AM" or "2026-01-15T00:00:00.000"
    _TIME_SUFFIX = re.compile(r"[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:\s*[AaPp][Mm])?$")

    @staticmethod
    def clean_date(raw: str | None) -> str | None:
        """Parse and normalize a date string to ISO format YYYY-MM-DD.

        A trailing time of day is ignored.

        Args:
            raw: Raw date string from CSV/SSRS.

        Returns:
            ISO-formatted date string, or None if empty.

        Raises:
            ValueError: If the date cannot be parsed by any known format.
        """
        if not raw or not raw.strip():
            return None
        raw = InputSanitizer._TIME_SUFFIX.sub("", raw.strip()).strip()
        for fmt in InputSanitizer.DATE_FORMATS:
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        raise ValueError(f"Could not parse date: {raw!r}")

    @staticmethod
    def clean_percent(raw: str | None) -> float:
        """Parse percentage string to 0-100 float.

        Args:
            raw: Raw percentage string (e.g., "65%", "65.5").

        Returns:
            Float value 0-100.

        Raises:
            ValueError: If out of range or unparseable.
        """
        if not raw or not raw.strip():
            return 0.0
        cleaned = raw.strip().replace("%", "").replace(",", ".").strip()
        value = float(cleaned)
        if value < 0 or value > 100:
            raise ValueError(f"Percent out of range [0-100]: {value}")
        return value

    @staticmethod
    def clean_number(raw: str | None) -> float | None:
        """Parse a number string, returning None for empty.

        Args:
            Raw number string (e.g., "1,234.56").

        Returns:
            Float value, or None if empty.
        """
        if not raw or not raw.strip():
            return None
        return float(raw.strip().replace(",", ""))

    @staticmethod
    def clean_int(raw: str | None) -> int | None:
        """Parse a whole number, accepting "3", "3.0" and "1,200"; None for empty.

        Raises:
            ValueError: If unparseable or not a whole number (e.g. "3.5").
        """
        if not raw or not raw.strip():
            return None
        value = float(raw.strip().replace(",", ""))
        if not value.is_integer():
            raise ValueError(f"Not a whole number: {raw.strip()!r}")
        return int(value)

    @staticmethod
    def clean_com_number(raw: str) -> str:
        """Normalize COM number: strip leading non-digits, uppercase.

        Args:
            raw: Raw COM number string.

        Returns:
            Normalized COM number.
        """
        cleaned = raw.strip().upper()
        # Remove any non-digit prefix characters
        while cleaned and not cleaned[0].isdigit():
            cleaned = cleaned[1:]
        return cleaned

    @staticmethod
    def clean_string(raw: str | None, max_length: int | None = None) -> str | None:
        """Trim whitespace, collapse multiple spaces, None for empty.

        Args:
            raw: Raw string.
            max_length: Optional max length to truncate to.

        Returns:
            Cleaned string, or None if empty.
        """
        if not raw or not raw.strip():
            return None
        cleaned = re.sub(r"\s+", " ", raw.strip())
        if max_length and len(cleaned) > max_length:
            cleaned = cleaned[:max_length]
        return cleaned
