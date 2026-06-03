#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect("schedule.db")
cur = conn.cursor()

print("=== After cleanup ===")
cur.execute('SELECT COUNT(DISTINCT detailer) FROM units WHERE detailer IS NOT NULL AND detailer != ""')
print(f"Unique detailer values: {cur.fetchone()[0]}")

print()
print("=== Distinct detailer values (count >= 2) ===")
cur.execute('''SELECT detailer, COUNT(*) as cnt FROM units 
    WHERE detailer IS NOT NULL AND detailer != ""
    GROUP BY detailer ORDER BY cnt DESC''')
for r in cur.fetchall():
    if r[1] >= 2:
        print(f"  {r[0]!r:30s}: {r[1]} units")

print()
cur.execute('SELECT COUNT(*) FROM units WHERE notes IS NOT NULL AND notes != ""')
print(f"Units with notes: {cur.fetchone()[0]}")

cur.execute('SELECT COUNT(*) FROM units WHERE detailer IS NULL OR detailer = ""')
print(f"Units with no detailer: {cur.fetchone()[0]}")