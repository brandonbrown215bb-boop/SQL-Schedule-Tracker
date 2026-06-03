#!/usr/bin/env python3
"""Analyze the detailer column to understand data patterns before cleanup."""
import sqlite3
import sys


def analyze(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Total units
    cur.execute("SELECT COUNT(*) FROM units")
    total = cur.fetchone()[0]
    print(f"Total units: {total}")

    # Units with notes already
    cur.execute('SELECT COUNT(*) FROM units WHERE notes IS NOT NULL AND notes != ""')
    print(f"Units with notes already: {cur.fetchone()[0]}")

    # Distinct detailer count
    cur.execute('SELECT COUNT(DISTINCT detailer) FROM units WHERE detailer IS NOT NULL AND detailer != ""')
    print(f"Distinct detailer values: {cur.fetchone()[0]}")

    print("\n=== Short entries WITHOUT slash (likely just names) ===")
    cur.execute("""SELECT com_number, detailer FROM units 
        WHERE detailer IS NOT NULL AND detailer != '' 
        AND detailer NOT LIKE '%/%'
        AND length(detailer) < 25
        ORDER BY detailer""")
    for r in cur.fetchall():
        print(f"  COM {r[0]}: {repr(r[1])}")

    print("\n=== Entries WITHOUT slash that look like notes (no clear name) ===")
    cur.execute("""SELECT com_number, detailer FROM units 
        WHERE detailer IS NOT NULL AND detailer != '' 
        AND detailer NOT LIKE '%/%'
        AND length(detailer) >= 25
        ORDER BY detailer LIMIT 20""")
    for r in cur.fetchall():
        print(f"  COM {r[0]}: {repr(r[1])}")

    print("\n=== Entries with slash — first segment only ===")
    cur.execute("""SELECT com_number, detailer FROM units 
        WHERE detailer LIKE '%/%'
        ORDER BY detailer LIMIT 30""")
    for r in cur.fetchall():
        first = r[1].split("/")[0].strip()
        print(f"  COM {r[0]}: full={repr(r[1])} => first_seg={repr(first)}")

    conn.close()


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "schedule.db"
    analyze(db)