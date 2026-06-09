#!/usr/bin/env python3
"""Create the SQLite database schema and seed detailers.

Usage:
    python -m automation.create_db --db PATH
"""
import argparse
import logging
import sqlite3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    com_number TEXT UNIQUE NOT NULL,
    detailing_due_date TEXT,
    manufacturing_location TEXT,
    job_name TEXT,
    top_level_number TEXT,
    description TEXT,
    build_date TEXT,
    build_cycle INTEGER,
    department_hours REAL DEFAULT 0.0,
    week_ending_friday TEXT,
    dept_due_date_previous TEXT,
    remaining_hours REAL DEFAULT 0.0,
    detailer TEXT,
    percent_complete REAL DEFAULT 0.0,
    actual_hours REAL DEFAULT 0.0,
    notes TEXT,
    late INTEGER DEFAULT 0,
    checking_status TEXT,
    target_dept_hours REAL DEFAULT 0.0,
    iec_internal_hours REAL DEFAULT 0.0,
    unit_detailing_start_date TEXT,
    unit_moved_to_checking_date TEXT,
    unit_detailing_completion_date TEXT,
    actual_hours_to_detail_unit REAL DEFAULT 0.0,
    hour_variance REAL DEFAULT 0.0,
    remaining_demand REAL DEFAULT 0.0,
    same_as TEXT,
    dr_checks TEXT,
    dvl_checks TEXT,
    hours_checking REAL DEFAULT 0.0,
    working_days_in_checking INTEGER,
    working_days_until_due INTEGER,
    calendar_days_until_due INTEGER,
    days_diff_due_to_build INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    status_color TEXT DEFAULT 'gray'
);


CREATE TABLE IF NOT EXISTS detailers (
    name TEXT PRIMARY KEY,
    working_weekdays TEXT NOT NULL,
    display_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS default_schedule (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    working_weekdays TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_units_com ON units(com_number);
CREATE INDEX IF NOT EXISTS idx_units_build_date ON units(build_date);
CREATE INDEX IF NOT EXISTS idx_units_week_ending ON units(week_ending_friday);
CREATE INDEX IF NOT EXISTS idx_units_detailer ON units(detailer);
CREATE INDEX IF NOT EXISTS idx_units_pct_complete ON units(percent_complete);
CREATE INDEX IF NOT EXISTS idx_units_manufacturing_location ON units(manufacturing_location);
CREATE INDEX IF NOT EXISTS idx_units_working_days ON units(working_days_until_due);
CREATE INDEX IF NOT EXISTS idx_units_due_date ON units(detailing_due_date);
"""

SEED_SQL = """
INSERT OR IGNORE INTO default_schedule (id, working_weekdays) VALUES (1, '[0,1,2,3]');

INSERT OR IGNORE INTO detailers (name, working_weekdays, display_order) VALUES
    ('Jackie H',  '[0,1,2,3]', 1),
    ('Tommy N',   '[1,2,3,4]', 2),
    ('Matthew S', '[1,2,3,4]', 3),
    ('Matthew E', '[1,2,3,4]', 4),
    ('Carl M',    '[0,1,2,3]', 5),
    ('Stewart D', '[1,2,3,4]', 6),
    ('David K',   '[0,1,2,3]', 7),
    ('Katie D',   '[0,1,2,3]', 8),
    ('Kris L',    '[0,1,2,3]', 9),
    ('Emilio P',  '[0,1,2,3]', 10),
    ('Timothy B', '[1,2,3,4]', 11),
    ('Jeremy B',  '[0,1,2,3]', 12),
    ('Brandon B', '[1,2,3,4]', 13),
    ('Tracy V',   '[0,1,2,3]', 14),
    ('Tanner D',  '[0,1,2,3]', 15);
"""


def create_database(db_path: str) -> None:
    """Create the SQLite database with schema and seed data."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA_SQL)
    conn.executescript(SEED_SQL)
    conn.commit()

    # Verify
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM detailers")
    detailer_count = cur.fetchone()[0]
    cur.execute("SELECT working_weekdays FROM default_schedule WHERE id = 1")
    default = cur.fetchone()

    conn.close()
    log.info(f"Created database at {db_path}")
    log.info(f"  Detailers seeded: {detailer_count}")
    log.info(f"  Default schedule: {default[0] if default else 'NOT SET'}")


def main():
    parser = argparse.ArgumentParser(description="Create SQLite database")
    parser.add_argument("--db", required=True, help="Path to SQLite database")
    args = parser.parse_args()
    create_database(args.db)
    print(f"Database created at {args.db}")


if __name__ == "__main__":
    main()
