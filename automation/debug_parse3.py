#!/usr/bin/env python3
"""Debug the full parse pipeline."""
import sys
sys.path.insert(0, "/run/media/pigeon/890dd7cb-9753-4f6b-b8e6-58c98e531754/Downloads/Schedule-Viewer-App-v2")

# Force reimport
import importlib
import automation.cleanup_detailers as cd
importlib.reload(cd)

from automation.cleanup_detailers import (
    extract_name_from_segment, match_name_to_detailer,
    load_canonical_detailers, parse_detailer_field,
)
import sqlite3

conn = sqlite3.connect("schedule.db")
canonical = load_canonical_detailers(conn)

tests = ["Thomas", "Johnathan", "Ryan W.", "Melvin", "Stoney", "Daniel", "Brady", "Matt"]
for t in tests:
    name, notes = extract_name_from_segment(t)
    matched = match_name_to_detailer(name, canonical)
    final_d, final_n = parse_detailer_field(t, canonical)
    print(f"  '{t}'")
    print(f"    extract: name={name!r}, notes={notes!r}")
    print(f"    match:   matched={matched!r}")
    print(f"    final:   detailer={final_d!r}, notes={final_n!r}")
    print()