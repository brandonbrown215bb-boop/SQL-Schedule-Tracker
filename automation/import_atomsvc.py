#!/usr/bin/env python3
"""SSRS auto-pull — fetches CSV from SSRS ReportServer and imports into SQLite.

Usage:
    python -m automation.import_atomsvc --db PATH
    python -m automation.import_atomsvc --db PATH --ssrs-url URL
    python -m automation.import_atomsvc --db PATH --lookback-days 30 --lookahead-days 365

The script builds a date-range URL (default: 1 month back, 12 months forward),
fetches the SSRS report as CSV, and upserts into SQLite via import_csv.

Config.yaml keys used:
    ssrs_url          — base report URL (without date parameters)
    ssrs_date_format  — strftime format for date params (default: %m/%d/%Y)
    lookback_days     — days before today for start date (default: 30)
    lookahead_days    — days after today for end date (default: 365)
"""

import argparse
import logging
import os
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Date range builder ──────────────────────────────────────────────


def build_date_params(
    lookback_days: int = 30,
    lookahead_days: int = 365,
    date_format: str = "%m/%d/%Y",
) -> tuple[str, str]:
    """Return (start_date, end_date) strings for SSRS URL parameters."""
    today = datetime.now()
    start = today - timedelta(days=lookback_days)
    end = today + timedelta(days=lookahead_days)
    return start.strftime(date_format), end.strftime(date_format)


def build_ssrs_url(
    base_url: str,
    start_date: str,
    end_date: str,
) -> str:
    """Construct the full SSRS CSV render URL with date parameters.

    The base_url should be the report path URL, e.g.:
        http://server/ReportServer?/path/to/report&rs:Format=CSV

    We append SHIP_DATE_START and SHIP_DATE_END if not already present.
    """
    url = base_url
    # Ensure we're requesting CSV format
    if "rs:Format=" not in url:
        url += "&rs:Format=CSV"
    elif "rs:Format=ATOM" in url or "rs:Format=XML" in url:
        url = url.replace("rs:Format=ATOM", "rs:Format=CSV")
        url = url.replace("rs:Format=XML", "rs:Format=CSV")

    # Add date parameters if not already in URL
    if "SHIP_DATE_START" not in url:
        url += f"&SHIP_DATE_START={urllib.parse.quote(start_date)}"
    if "SHIP_DATE_END" not in url:
        url += f"&SHIP_DATE_END={urllib.parse.quote(end_date)}"

    return url


# ── Fetch + import pipeline ──────────────────────────────────────────


def fetch_csv_from_ssrs(url: str, timeout: int = 60) -> str:
    """Fetch CSV from SSRS URL, return path to temp file."""
    log.info(f"Fetching SSRS CSV: {url[:120]}...")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = resp.read()
    except Exception as e:
        log.error(f"SSRS fetch failed: {e}")
        raise

    # Write to temp file
    tmp_path = os.path.join(tempfile.gettempdir(), "_ssrs_pull.csv")
    with open(tmp_path, "wb") as tmp:
        tmp.write(data)
    log.info(f"Downloaded {len(data)} bytes to {tmp_path}")
    return tmp_path


def run_ssrs_import(
    db_path: str,
    ssrs_url: str | None = None,
    lookback_days: int = 30,
    lookahead_days: int = 365,
    date_format: str = "%m/%d/%Y",
) -> dict:
    """Full pipeline: build URL → fetch CSV → import into SQLite.

    Returns stats dict from import_csv.
    """
    import urllib.parse

    # Build date range
    start_date, end_date = build_date_params(lookback_days, lookahead_days, date_format)
    log.info(f"Date range: {start_date} → {end_date}")

    # Build full URL
    full_url = build_ssrs_url(ssrs_url, start_date, end_date)
    log.info(f"SSRS URL: {full_url[:150]}...")

    # Fetch CSV
    csv_path = fetch_csv_from_ssrs(full_url)

    try:
        # Delegate to existing CSV import
        from automation.import_csv import run_import

        log.info(f"Importing into {db_path}")
        stats = run_import(csv_path, db_path)
        return stats
    finally:
        # Clean up temp file
        if os.path.exists(csv_path):
            os.remove(csv_path)


# ── CLI ──────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Auto-pull SSRS report into SQLite")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--ssrs-url", default=None,
                        help="SSRS report URL (without date params)")
    parser.add_argument("--lookback-days", type=int, default=30,
                        help="Days before today for start date (default: 30)")
    parser.add_argument("--lookahead-days", type=int, default=365,
                        help="Days after today for end date (default: 365)")
    parser.add_argument("--date-format", default="%m/%d/%Y",
                        help="strftime format for date params (default: %%m/%%d/%%Y)")
    args = parser.parse_args()

    url = args.ssrs_url or "http://j030m1p3/ReportServer?/Custom/Production%20Control/SCHDetailingReport&rs:Format=CSV"

    t0 = time.perf_counter()
    stats = run_ssrs_import(
        db_path=args.db,
        ssrs_url=url,
        lookback_days=args.lookback_days,
        lookahead_days=args.lookahead_days,
        date_format=args.date_format,
    )
    elapsed = time.perf_counter() - t0

    log.info("")
    log.info("=" * 60)
    log.info("SSRS IMPORT COMPLETE")
    log.info("=" * 60)
    log.info(f"Elapsed:               {elapsed:.3f}s")
    log.info(f"Inserted:              {stats['inserted']}")
    log.info(f"Updated:               {stats['updated']}")
    log.info(f"Skipped:               {stats['skipped']}")
    log.info(f"Errors:                {stats['errors']}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
