#!/usr/bin/env python3
"""Migrate units.detailer from scratch-pad format to clean canonical names.

Parses each unit's detailer field, extracts the person's name,
maps it to a canonical detailer from the detailers table, and moves
any scratch-pad notes into the existing (but unused) notes column.

For former employees not in the canonical list, normalizes the name
to clean Title Case format (e.g. "JAMES" → "James", "matt" → "Matt").

Usage:
    python -m automation.cleanup_detailers --db schedule.db --dry-run
    python -m automation.cleanup_detailers --db schedule.db --apply
"""
import re
import sqlite3
import sys
from collections import defaultdict


def load_canonical_detailers(conn: sqlite3.Connection) -> dict[str, str]:
    """Load canonical detailer names from the detailers table.

    Returns mapping of lowercase base name → canonical name.
    e.g. {"brandon": "Brandon B", "matthew e": "Matthew E", ...}
    """
    cur = conn.cursor()
    cur.execute("SELECT name FROM detailers ORDER BY display_order")
    canonical = {}
    for row in cur.fetchall():
        name = row[0].strip()
        # "Brandon B" → base = "brandon"
        base = name.rsplit(" ", 1)[0].lower() if " " in name else name.lower()
        canonical[base] = name
        # Also map the full name (lowercase) for direct matches
        canonical[name.lower()] = name
    return canonical


# ── Name extraction ────────────────────────────────────────────────────

# Pattern: split on "/" with optional surrounding whitespace.
_SLASH_RE = re.compile(r"\s*/\s*")

# Words that indicate notes/description rather than a person's name.
_NON_NAME_WORDS = frozenset({
    "iec", "internals", "new", "complete", "wip", "as",
    "mirror", "obo", "cad", "only", "base", "moved", "canceled",
    "not", "mom", "deflection", "test", "will", "need", "bracing",
    "pre-eng", "hot", "helping", "and", "fiberglass", "platform",
    "unassigned", "isg", "he", "just", "do", "bottom", "top",
    "stacked", "stack", "partial", "tier", "alum", "steel",
    "floor", "penetration", "raised", "drain", "pan", "funky",
    "chopped", "housing", "embassy", "waiting", "product", "eng",
    "info", "fan", "pe", "issues", "approved", "add", "splits",
    "prc", "revised", "drawings", "swap", "service",
    "order", "won't", "generate", "surfaces", "done", "except",
    "training", "next", "first", "second", "complicated",
})

# Common first names that appear in the data (not necessarily canonical).
_KNOWN_FIRST_NAMES = frozenset({
    "amarjeet", "amol", "brady", "brandon", "carl", "daniel",
    "david", "derrick", "emilio", "evan", "jd", "jackie", "james",
    "jeremy", "johnathan", "jonathan", "jonhathan", "josh", "joshua",
    "katie", "ken", "kenneth", "kevin", "kris", "kyle",
    "mahantesh", "matt", "matthew", "melvin", "morgan", "paul",
    "ricky", "ryan", "stewart", "stoney", "tanner", "thomas",
    "tim", "timothy", "tommy", "tracy", "mark", "john",
    "bryan", "jake", "sam", "tom", "todd", "dan", "mike",
    "chris", "joe", "steve", "jeff", "greg", "keith",
    "austin", "amol",
})

# Known typos → correct spelling
_NAME_TYPOS = {
    "jonhathan": "Johnathan",
    "jonathan": "Johnathan",
    "joshua": "Joshua",  # same, but ensure consistent casing
}

# Suffixes that should be stripped from names (scratch-pad markers)
_STRIP_SUFFIXES = [
    r"\s+same-as.*",           # "Johnathan Same-as 18821" → "Johnathan"
    r"\s*\(same.*",            # "Johnathan(same" → "Johnathan"
    r"\s+hsb.*",              # "Johnathan HSB" → "Johnathan"
    r"\s+special.*",          # "Johnathan Special" → "Johnathan"
    r"\.stewart.*",           # "Matthew E.Stewart" → "Matthew E"
    r"\s+moved.*",            # "Moved ..." → notes
]

# Entire values that are notes-only (not a person's name at all)
_NOTES_ONLY_VALUES = {
    "iec", "base", "deflection", "same", "same-as", "moved",
}


def _normalize(name: str) -> str:
    """Normalize a name for comparison."""
    return re.sub(r"[.\s]+", " ", name).strip().lower()


def _clean_name(name: str) -> str:
    """Clean and normalize a person's name to Title Case.

    Handles: "JAMES" → "James", "matt" → "Matt", "ryan w." → "Ryan W."
    Preserves: "JD" → "JD" (2-letter initialisms stay uppercase)
    """
    # Handle known typos first
    lower = name.lower().strip()
    if lower in _NAME_TYPOS:
        return _NAME_TYPOS[lower]

    parts = name.strip().split()
    cleaned = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Single letter (initial) → uppercase
        alpha_only = re.sub(r"[^a-zA-Z]", "", part)
        if len(alpha_only) == 1:
            cleaned.append(alpha_only.upper())
        # 2-letter all-uppercase (like "JD") → keep uppercase (initialism)
        elif len(alpha_only) == 2 and part.upper() == part and part.isalpha():
            cleaned.append(part.upper())
        else:
            cleaned.append(part.capitalize())
    return " ".join(cleaned)


def _strip_suffixes(raw: str) -> tuple[str, str]:
    """Strip scratch-pad suffixes from a name string.

    Returns (cleaned_name, stripped_suffix_as_notes).
    """
    name = raw.strip()
    notes = ""

    for pattern in _STRIP_SUFFIXES:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            notes = name[match.start():].strip()
            name = name[:match.start()].strip()
            break

    return name, notes


def extract_name_from_segment(segment: str) -> tuple[str, str]:
    """Extract a person's name from a text segment.

    Returns (name, notes).  name may be "" if no name found.
    """
    segment = segment.strip()
    if not segment:
        return "", ""

    # Check if entire segment is notes-only
    if segment.lower() in _NOTES_ONLY_VALUES:
        return "", segment

    # Strip suffixes first
    segment, suffix_notes = _strip_suffixes(segment)

    words = segment.split()
    if not words:
        return "", suffix_notes

    # Check if the entire segment is a known first name (case-insensitive)
    if len(words) <= 2:
        test = _normalize(segment)
        if test in _KNOWN_FIRST_NAMES:
            cleaned = _clean_name(segment)
            return cleaned, suffix_notes

    # Find the longest prefix that consists of name-like words
    name_words = []
    for i, word in enumerate(words):
        clean = re.sub(r"[^a-zA-Z]", "", word).lower()
        if not clean:
            break
        # Single lowercase letters are likely stray marks, not initials
        if len(clean) == 1 and word.islower():
            break
        # Stop if this is clearly a non-name word (but allow short words
        # that might be initials or name parts)
        if clean in _NON_NAME_WORDS and len(name_words) > 0:
            break
        # Allow: capitalized words, known names, single letters (initials),
        # words with apostrophes
        if (clean in _KNOWN_FIRST_NAMES
                or (word[0].isupper() and len(clean) > 1)
                or len(clean) == 1  # Initial like "E" in "Matthew E"
                or "'" in word):
            name_words.append(word)
        else:
            break

    if name_words:
        name = " ".join(name_words)
        rest = segment[len(name):].strip()
        # Strip leading punctuation from rest
        rest = re.sub(r"^[,\s]+", "", rest)
        # Combine suffix notes with rest
        notes = " — ".join(filter(None, [suffix_notes, rest])) or ""
        return _clean_name(name), notes

    return "", suffix_notes or segment


def match_name_to_detailer(
    name: str,
    canonical: dict[str, str],
) -> str | None:
    """Match an extracted name to a canonical detailer.

    Tries exact match, last-initial match, and fuzzy match.
    Returns canonical name or None.
    """
    if not name:
        return None

    norm = _normalize(name)

    # Direct match (full canonical key)
    if norm in canonical:
        return canonical[norm]

    # Try "firstname" → "firstname X" matching
    # e.g., "Brandon" matches "Brandon B"
    # But reject ambiguous cases: "Matthew" has both "Matthew E" and "Matthew S"
    prefix_matches = []
    for base, canon in canonical.items():
        if base == norm:
            return canon
        if norm.startswith(base) or base.startswith(norm):
            prefix_matches.append(canon)
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    # If multiple prefix matches, it's ambiguous — return None
    # But: if the name itself is a canonical first name (exact match on first part),
    # AND all matches share the same first name, pick the most common one
    if prefix_matches and len(norm.split()) == 1:
        # All matches are "FirstName X" for the same first name
        # Return None to keep the raw name (can't disambiguate)
        pass

    # Last-initial matching: "Matthew E." or "Matthew E" → "Matthew E"
    parts = norm.rstrip(". ").split()
    if len(parts) == 2 and len(parts[1]) == 1:
        # parts[1] is an initial
        initial = parts[1]
        for base, canon in canonical.items():
            canon_parts = canon.lower().rstrip(". ").split()
            if (len(canon_parts) == 2
                    and canon_parts[0] == parts[0]
                    and len(canon_parts[1]) == 1
                    and canon_parts[1] == initial):
                return canon

    # Typos / fuzzy: require first 4+ chars to match (not just 3)
    # to avoid false matches like "brady" → "brandon"
    if len(norm) >= 5:
        for base, canon in canonical.items():
            if (len(base) >= 5
                    and abs(len(norm) - len(base)) <= 2
                    and norm[:4] == base[:4]):
                return canon

    return None


def parse_detailer_field(
    raw: str,
    canonical: dict[str, str],
) -> tuple[str, str]:
    """Parse a raw detailer field value into (clean_name, notes).

    For entries matching a canonical detailer, returns the canonical name.
    For entries with a recognizable person name but no canonical match,
    returns the cleaned-up name (e.g. "Johnathan Same-as 18821" → "Johnathan").
    For pure notes, returns ("", notes).

    Handles:
    - Simple names: "Brandon" → ("Brandon B", "")
    - Name + notes: "Brandon / IEC Internals..." → ("Brandon B", "IEC Internals...")
    - Multi-person: "Johnathan/Brady" → ("Johnathan", "also: Brady")
    - Non-canonical name: "Thomas" → ("Thomas", "")
    - Notes only: "Same as 18557..." → ("", "Same as 18557...")
    - Empty/NULL → ("", "")
    - Case normalization: "JAMES" → ("James", "")
    - Typos: "Jonhathan" → ("Johnathan", "")
    - Suffix stripping: "Johnathan Same-as 18821" → ("Johnathan", "same-as 18821")
    - Malformed: "Johnathan(same" → ("Johnathan", "")
    """
    if not raw or not raw.strip():
        return "", ""

    raw = raw.strip()

    # Special known non-name entries
    _NOTES_ONLY = {
        "— unassigned —", "not in mom", "canceled in mom",
        "pre-eng 5/29",
    }
    if raw.lower() in _NOTES_ONLY:
        return "", raw

    # Check if entire value is notes-only
    if raw.lower() in _NOTES_ONLY_VALUES:
        return "", raw

    # Split on "/"
    parts = [p.strip() for p in _SLASH_RE.split(raw) if p.strip()]

    if len(parts) == 1:
        # No slash — single segment
        name, notes = extract_name_from_segment(parts[0])
        matched = match_name_to_detailer(name, canonical)
        if matched:
            return matched, notes
        if name:
            # Recognizable name but not canonical — keep it clean
            return name, notes
        # No name found — entire value is notes
        return "", raw

    # Has slash — check if second part is a known name
    first_name, first_notes = extract_name_from_segment(parts[0])
    first_matched = match_name_to_detailer(first_name, canonical)

    # Check if any subsequent parts are also names
    also_names = []
    note_parts = []
    for part in parts[1:]:
        pname, pnotes = extract_name_from_segment(part)
        pmatched = match_name_to_detailer(pname, canonical)
        if pmatched and not pnotes:
            # This is a standalone name — it's a co-detailer
            also_names.append(pmatched)
        elif pmatched and pnotes:
            # Name + notes — co-detailer with notes
            also_names.append(pmatched)
            if pnotes:
                note_parts.append(pnotes)
        else:
            # Not a name — it's a note
            note_parts.append(part)

    if first_matched:
        notes = " / ".join(note_parts) if note_parts else first_notes
        if also_names:
            notes = f"also: {', '.join(also_names)}" + (
                f" — {notes}" if notes else ""
            )
        return first_matched, notes

    if first_name:
        # First part is a recognizable name but not canonical — keep it clean
        notes = " / ".join(note_parts) if note_parts else first_notes
        if also_names:
            notes = f"also: {', '.join(also_names)}" + (
                f" — {notes}" if notes else ""
            )
        return first_name, notes

    if also_names:
        # First part wasn't a name but second part was
        notes_parts = [parts[0]] + note_parts
        notes = " / ".join(notes_parts)
        if len(also_names) == 1:
            return also_names[0], notes
        return also_names[0], f"also: {', '.join(also_names[1:])} — {notes}"

    # Nothing matched — everything is notes
    return "", raw


def cleanup_detailers(
    db_path: str,
    apply: bool = False,
    dry_run: bool = True,
) -> dict:
    """Clean up the detailer field for all units.

    Args:
        db_path: Path to SQLite database.
        apply: If True, write changes to database.
        dry_run: If True, only report what would change.

    Returns:
        Stats dict with counts.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    canonical = load_canonical_detailers(conn)

    print(f"Loaded {len(canonical)} canonical detailer mappings:")
    for base, canon in sorted(canonical.items()):
        if base == canon.lower():
            print(f"  {base} → {canon}")
    print()

    cur = conn.cursor()
    cur.execute(
        "SELECT com_number, detailer, notes FROM units "
        "WHERE detailer IS NOT NULL AND detailer != ''"
    )
    rows = cur.fetchall()

    stats = defaultdict(int)
    changes = []

    for row in rows:
        com = row["com_number"]
        raw = row["detailer"]
        existing_notes = row["notes"] or ""

        matched, notes = parse_detailer_field(raw, canonical)
        stats["total"] += 1

        if matched == raw:
            # No change needed
            stats["unchanged"] += 1
            continue

        if matched:
            stats["matched"] += 1
        else:
            stats["unmatched"] += 1

        # Merge notes if unit already has notes
        if existing_notes and notes:
            notes = f"{notes} — {existing_notes}"
        elif existing_notes:
            notes = existing_notes

        changes.append({
            "com_number": com,
            "old_detailer": raw,
            "new_detailer": matched,
            "notes": notes,
        })

    # Report
    print(f"Total units with detailer: {stats['total']}")
    print(f"Unchanged (already clean): {stats['unchanged']}")
    print(f"Matched to canonical: {stats['matched']}")
    print(f"No match found (cleaned/notes): {stats['unmatched']}")
    print(f"Total changes: {len(changes)}")
    print()

    # Show sample changes
    if changes:
        print("=== Sample changes (first 40) ===")
        for c in changes[:40]:
            old = c["old_detailer"]
            new = c["new_detailer"] or "(no match)"
            notes = c["notes"][:80] if c["notes"] else ""
            print(f"  COM {c['com_number']}: {old!r} → {new!r}"
                  + (f"  notes={notes!r}" if notes else ""))

        # Show unmatched entries
        unmatched = [c for c in changes if not c["new_detailer"]]
        if unmatched:
            print(f"\n=== Unmatched entries ({len(unmatched)}) ===")
            for c in unmatched[:50]:
                print(f"  COM {c['com_number']}: {c['old_detailer']!r}")

    # Apply changes
    if apply and changes:
        print(f"\nApplying {len(changes)} changes...")
        for c in changes:
            cur.execute(
                "UPDATE units SET detailer = ?, notes = ? WHERE com_number = ?",
                (c["new_detailer"], c["notes"] or None, c["com_number"]),
            )
        conn.commit()
        print("Done.")
    elif dry_run:
        print("\n[DRY RUN] No changes written. Use --apply to write changes.")

    conn.close()
    return dict(stats)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Clean up units.detailer scratch-pad data"
    )
    parser.add_argument("--db", default="schedule.db", help="SQLite database path")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true",
                       help="Report changes without writing")
    group.add_argument("--apply", action="store_true",
                       help="Write changes to database")
    args = parser.parse_args()

    cleanup_detailers(args.db, apply=args.apply, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
