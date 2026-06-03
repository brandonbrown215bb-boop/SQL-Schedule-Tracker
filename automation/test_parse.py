#!/usr/bin/env python3
"""Quick test of parse_detailer_field output."""
import sys
sys.path.insert(0, "/run/media/pigeon/890dd7cb-9753-4f6b-b8e6-58c98e531754/Downloads/Schedule-Viewer-App-v2")
from automation.cleanup_detailers import parse_detailer_field, load_canonical_detailers
import sqlite3

conn = sqlite3.connect("schedule.db")
canonical = load_canonical_detailers(conn)

tests = [
    "Thomas", "Johnathan", "Ryan W.", "Ryan M.", "Melvin",
    "Stoney", "Matthew", "Brady", "Daniel",
    "Brandon / IEC Internals complete", "Jonhathan", "Matt",
    "Ryan Same-as 18712", "Katie ISG", "Tanner same as 18683",
    "CANCELED IN MOM", "— Unassigned —", "Same as 18557 copied by Mark H., released by RT",
    "e", "katie", "IEC Internals New 55", "Jackie",
]
for t in tests:
    result = parse_detailer_field(t, canonical)
    d, n = result
    print(f"  {t!r:50s} => detailer={d!r:20s} notes={n!r}")