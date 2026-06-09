#!/usr/bin/env python3
"""
Ensure the detailers table exists in schedule.db and is seeded.
Safe to run multiple times — uses IF NOT EXISTS / INSERT OR IGNORE.

Usage:
    python ensure_detailers.py [--db PATH]
"""
import argparse
import sqlite3
import sys
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS detailers (
    name TEXT PRIMARY KEY,
    working_weekdays TEXT NOT NULL,
    display_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS default_schedule (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    working_weekdays TEXT NOT NULL
);
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


def main():
    parser = argparse.ArgumentParser(description="Ensure detailers table exists")
    parser.add_argument("--db", default=None, help="Path to schedule.db")
    args = parser.parse_args()

    db_path = args.db or str(Path(__file__).resolve().parent.parent / "schedule.db")

    if not Path(db_path).exists():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    print(f"Database: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.executescript(SEED_SQL)
    conn.commit()

    # Verify
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM detailers")
    count = cur.fetchone()[0]
    print(f"Detailers table: {count} rows")

    cur.execute("SELECT COUNT(*) FROM default_schedule")
    def_count = cur.fetchone()[0]
    print(f"Default schedule: {def_count} row(s)")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
