#!/usr/bin/env python3
"""Debug extract_name_from_segment step by step."""
import re
import sys
sys.path.insert(0, "/run/media/pigeon/890dd7cb-9753-4f6b-b8e6-58c98e531754/Downloads/Schedule-Viewer-App-v2")

# Import the exact functions
from automation.cleanup_detailers import (
    _NON_NAME_WORDS, _KNOWN_FIRST_NAMES, _normalize
)

def debug_extract(segment: str):
    segment = segment.strip()
    if not segment:
        return "", ""
    words = segment.split()
    if not words:
        return "", ""

    print(f"    words = {words}")
    
    # Check if entire segment is a known first name
    if len(words) <= 2:
        test = _normalize(segment)
        in_known = test in _KNOWN_FIRST_NAMES
        print(f"    _normalize('{segment}') = '{test}', in _KNOWN_FIRST_NAMES = {in_known}")
        if in_known:
            return segment.strip(), ""

    name_words = []
    for i, word in enumerate(words):
        clean = re.sub(r"[^a-zA-Z]", "", word).lower()
        if not clean:
            print(f"    word[{i}] '{word}' => clean='' => BREAK")
            break
        if clean in _NON_NAME_WORDS and len(name_words) > 0:
            print(f"    word[{i}] '{word}' => clean='{clean}' in _NON_NAME_WORDS and name_words={name_words} => BREAK")
            break
        is_known = clean in _KNOWN_FIRST_NAMES
        is_cap = word[0].isupper() and len(clean) > 1
        is_initial = len(clean) == 1
        has_apost = "'" in word
        accept = is_known or is_cap or is_initial or has_apost
        print(f"    word[{i}] '{word}' => clean='{clean}' known={is_known} cap={is_cap} initial={is_initial} apost={has_apost} => accept={accept}")
        if accept:
            name_words.append(word)
        else:
            break

    if name_words:
        name = " ".join(name_words)
        rest = segment[len(name):].strip()
        rest = re.sub(r"^[,\s]+", "", rest)
        print(f"    => name_words={name_words}, name='{name}', rest='{rest}'")
        return name, rest

    print(f"    => NO name_words, returning ('', '{segment}')")
    return "", segment

tests = ["Thomas", "Johnathan", "Ryan W.", "Melvin", "Stoney", "Daniel", "Brady", "Matt"]
for t in tests:
    print(f"\n=== '{t}' ===")
    name, notes = debug_extract(t)
    print(f"  RESULT: name={name!r}, notes={notes!r}")