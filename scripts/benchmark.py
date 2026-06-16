#!/usr/bin/env python3
"""Performance baseline benchmark — times major operations against the SQLite database.

Run before and after any performance optimization to measure impact.

Usage:
    python -m scripts.benchmark --db PATH
    python scripts/benchmark.py --db PATH

Produces a report like:
    Operation                    Time (ms)     Notes
    ──────────────────────────── ───────────── ─────────────────
    DB connection (cold)          12.3
    Load 2765 units              145.2
    Save 1 unit                   8.1
    CSV import (2765 rows)       890.4
    Query by detailer             2.1          idx_units_detailer
    Query by due_date             1.8          idx_units_detailing_due_date
    Fingerprint 100 units        15.3
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import statistics
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.models import Unit

# ── Helpers ──────────────────────────────────────────────────────────────────


class Timer:
    """Context-manager timer that collects multiple samples."""

    def __init__(self):
        self.samples: list[float] = []

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_):
        elapsed_ms = (time.perf_counter() - self._start) * 1000
        self.samples.append(elapsed_ms)

    @property
    def mean(self) -> float:
        return statistics.mean(self.samples) if self.samples else 0.0

    @property
    def median(self) -> float:
        return statistics.median(self.samples) if self.samples else 0.0

    @property
    def stdev(self) -> float:
        return statistics.stdev(self.samples) if len(self.samples) >= 2 else 0.0


# ── Benchmark cases ─────────────────────────────────────────────────────────


def bench_db_connection(db_path: str, runs: int = 5) -> Timer:
    """Time a fresh SQLite connection open (not reusing thread-local)."""
    import threading

    t = Timer()
    for _ in range(runs):
        # Use a unique thread to force a fresh connection
        container: list[sqlite3.Connection] = []

        def _open(_c: list[sqlite3.Connection] = container) -> None:
            # Import here to bypass thread-local cache
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            _c.append(conn)

        th = threading.Thread(target=_open)
        th.start()
        th.join()
        with t:
            if container:
                container[0].close()
    return t


def bench_load_units(db_path: str, runs: int = 3) -> Timer:
    """Time loading all units via data.loader.load_units."""
    from data.loader import load_units

    t = Timer()
    for _ in range(runs):
        with t:
            load_units(db_path)
    return t


def bench_save_unit(db_path: str, sample_unit: Unit, runs: int = 5) -> Timer:
    """Time saving a single unit."""
    from data.writer import save_unit

    t = Timer()
    for i in range(runs):
        sample_unit.percent_complete = float(i * 20)
        with t:
            save_unit(db_path, sample_unit)
    return t


def bench_query_by_detailer(db_path: str, runs: int = 5) -> Timer:
    """Time a filtered query by detailer."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    t = Timer()
    for _ in range(runs):
        with t:
            conn.execute(
                "SELECT * FROM units WHERE detailer = ?",
                ("Carl M",),
            ).fetchall()
    conn.close()
    return t


def bench_query_by_due_date(db_path: str, runs: int = 5) -> Timer:
    """Time a filtered query by detailing_due_date."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    t = Timer()
    for _ in range(runs):
        with t:
            conn.execute(
                "SELECT * FROM units WHERE detailing_due_date >= ? AND detailing_due_date <= ?",
                ("2025-01-01", "2025-12-31"),
            ).fetchall()
    conn.close()
    return t


def bench_fingerprint(db_path: str, runs: int = 3) -> Timer:
    """Time fingerprinting a batch of units."""
    from data.loader import load_units, unit_fingerprint

    units = load_units(db_path)
    t = Timer()
    for _ in range(runs):
        with t:
            for u in units[:100]:
                unit_fingerprint(u)
    return t


def bench_full_scan(db_path: str, runs: int = 3) -> Timer:
    """Time a full table scan with no WHERE clause."""
    conn = sqlite3.connect(db_path)
    t = Timer()
    for _ in range(runs):
        with t:
            conn.execute("SELECT COUNT(*) FROM units").fetchone()
    conn.close()
    return t


# ── Index audit ──────────────────────────────────────────────────────────────


def audit_indexes(db_path: str) -> None:
    """Print current indexes on the units table."""
    conn = sqlite3.connect(db_path)
    idxs = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='units'"
    ).fetchall()
    conn.close()

    print("\n  Indexes on 'units' table:")
    if not idxs:
        print("    (none)")
    for name, sql in idxs:
        print(f"    {name}: {sql}")


# ── Main ─────────────────────────────────────────────────────────────────────


def format_row(name: str, t: Timer, notes: str = "") -> str:
    mean = t.mean
    stdev = t.stdev
    timing = f"{mean:>8.1f} ± {stdev:.1f}" if stdev > 0 else f"{mean:>8.1f}"
    return f"  {name:<30} {timing:<16} {notes}"


def main():
    parser = argparse.ArgumentParser(description="Performance baseline benchmark")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    parser.add_argument("--runs", type=int, default=5, help="Samples per benchmark (default: 5)")
    args = parser.parse_args()

    db_path = args.db
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    print("=" * 72)
    print("  PERFORMANCE BASELINE BENCHMARK")
    print("=" * 72)
    print(f"  Database: {db_path}")
    print(f"  Samples per test: {args.runs}")
    print()

    # Get row count
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM units").fetchone()[0]
    conn.close()
    print(f"  Units in database: {count}")
    print()

    results: list[tuple[str, Timer, str]] = []

    print("  Running benchmarks...")
    results.append(("DB connection (cold)", bench_db_connection(db_path, args.runs), ""))
    results.append(
        ("Load all units", bench_load_units(db_path, min(args.runs, 3)), f"{count} rows")
    )
    results.append(
        ("Query by detailer", bench_query_by_detailer(db_path, args.runs), "idx_units_detailer")
    )
    results.append(
        (
            "Query by due_date",
            bench_query_by_due_date(db_path, args.runs),
            "idx_units_detailing_due_date",
        )
    )
    results.append(("Fingerprint 100 units", bench_fingerprint(db_path, min(args.runs, 3)), ""))
    results.append(("Full table scan", bench_full_scan(db_path, args.runs), ""))

    # Build a sample unit for save benchmark
    sample = Unit(
        com_number="BENCH-TEST",
        job_name="Benchmark",
        contract_number="BENCH-001",
        description="Benchmark test unit",
        detailer="Carl M",
        checking_status="",
        department_hours=40.0,
        percent_complete=50.0,
        actual_hours=20.0,
        target_department_hours=40.0,
        detailing_due_date=date(2026, 12, 31),
    )
    # Ensure test unit exists
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO units (com_number, job_name, detailer) VALUES (?, ?, ?)",
        ("BENCH-TEST", "Benchmark", "Carl M"),
    )
    conn.commit()
    conn.close()

    results.append(("Save 1 unit", bench_save_unit(db_path, sample, args.runs), ""))

    # Clean up test unit
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM units WHERE com_number = 'BENCH-TEST'")
    conn.commit()
    conn.close()

    # Print report
    print()
    print("=" * 72)
    print("  RESULTS")
    print("=" * 72)
    header = f"  {'Operation':<30} {'Time (ms)':<16} {'Notes'}"
    print(header)
    print("  " + "─" * 68)
    for name, timer, notes in results:
        print(format_row(name, timer, notes))

    print()
    print("=" * 72)
    audit_indexes(db_path)
    print()
    print("=" * 72)
    print("  SUGGESTED BASELINE THRESHOLDS (20% regression gate)")
    print("=" * 72)
    for name, timer, _ in results:
        threshold = timer.mean * 1.20
        print(f"  {name:<30} max {threshold:.1f} ms")
    print()


if __name__ == "__main__":
    main()
