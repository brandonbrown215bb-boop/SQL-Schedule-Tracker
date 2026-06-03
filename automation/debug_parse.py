#!/usr/bin/env python3
import sys
sys.path.insert(0, "/run/media/pigeon/890dd7cb-9753-4f6b-b8e6-58c98e531754/Downloads/Schedule-Viewer-App-v2")
from automation.cleanup_detailers import extract_name_from_segment, match_name_to_detailer, load_canonical_detailers
import sqlite3

conn = sqlite3.connect("schedule.db")
canonical = load_canonical_detailers(conn)

tests = ["Thomas", "Johnathan", "Ryan W.", "Melvin", "Stoney", "Daniel", "Brady", "Matt"]
for t in tests:
    name, notes = extract_name_from_segment(t)
    matched = match_name_to_detailer(name, canonical)
    print(f"  {t!r:30s} => extract_name={name!r:20s} notes={notes!r:20s} matched={matched!r}")