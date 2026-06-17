# QA-003: Fuzz Testing for Data Pipelines

**Status:** Draft  
**Created:** 2025-01-12  
**Author:** Quality Assurance Team  
**Priority:** Medium  
**Dependencies:** [ARCH-003](./ARCH-003-data-validation-layer.md)  

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State & Problem Statement](#current-state--problem-statement)
3. [Objectives](#objectives)
4. [Technical Approach](#technical-approach)
5. [Fuzz Targets](#fuzz-targets)
6. [Seed Corpus](#seed-corpus)
7. [Implementation Plan](#implementation-plan)
8. [CI Integration](#ci-integration)
9. [Success Criteria](#success-criteria)
10. [Risk Assessment](#risk-assessment)
11. [Appendix](#appendix)

---

## Executive Summary

The Schedule Viewer application processes external data from CSV imports, user-entered tags, and date strings. These data pipelines currently lack robustness testing against malformed, unexpected, or adversarial inputs. This plan introduces **fuzz testing** to systematically discover crashes, hangs, and data corruption bugs in three critical data processing paths.

We will use **Hypothesis** for Python-level fuzzing (CSV import, tag parser, date parser) and **atheris** for native/C-level fuzzing if any C extensions are part of the data pipeline. The fuzz targets will be seeded with a corpus derived from **2,765 production descriptions** and real CSV files from the deployed system.

Over **7 days** across **4 phases**, we will deliver a suite of fuzz targets that run for **60 seconds per target** in CI, providing continuous regression coverage against input-handling bugs.

### Key Metrics

| Metric | Target |
|--------|--------|
| Fuzz targets | 3 (CSV, tags, dates) |
| CI fuzz duration | 60 seconds per target |
| Seed corpus size | 2,765 descriptions + 50+ CSV files |
| Code coverage (data pipeline) | > 80% |
| Critical bugs found (Phase 2) | 0 (target: zero after fixes) |

---

## Current State & Problem Statement

### Current Pain Points

1. **CSV import silently accepts malformed rows** — Missing fields, wrong delimiters, and encoding errors can produce corrupt data without user notification
2. **Tag parser has no formal specification** — Edge cases (empty tags, special characters, extremely long tags) are undefined
3. **Date parser accepts ambiguous formats** — "02/03/04" could be interpreted differently, leading to subtle scheduling errors
4. **No adversarial input testing** — All test data is hand-crafted and "nice" — no coverage of malicious or pathological inputs

### Root Causes

- Data validation was added incrementally without a formal validation layer (now addressed by ARCH-003)
- Input parsers evolved organically without a grammar/specification
- No automated test infrastructure existed for generating edge-case inputs
- Team lacked awareness of fuzz testing tools and techniques

---

## Objectives

1. **Formalize input specifications** for CSV, tags, and dates via the data validation layer
2. **Implement Hypothesis-based fuzz targets** for all three data pipelines
3. **Build a seed corpus** from production data to guide fuzzing
4. **Integrate fuzz testing into CI** with a 60-second-per-target budget
5. **Eliminate all crash/hang bugs** in the data pipelines

---

## Technical Approach

### 1. Tooling & Framework

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **Hypothesis** | Python-level property-based fuzzing | All pure Python data pipelines (CSV, tags, dates) |
| **atheris** | Native/C-level fuzzing (libFuzzer wrapper) | Only if C extensions are added to parsing |
| **coverage.py** | Measure code coverage during fuzzing | Track fuzz effectiveness |
| **python-afl** | American Fuzzy Lop for Python (optional) | Alternative if atheris doesn't work on target platform |

### 2. Fuzzing Strategy

Each fuzz target follows a standard pattern:

```python
# tests/fuzz/test_csv_import.py
from hypothesis import given, assume, settings, HealthCheck
from hypothesis import strategies as st
import pytest
import io
import csv

from sync.importer import parse_csv_row, ImportError
from sync.models import UnitRow

# ---------------------------------------------------------------------------
# Strategy: generate CSV rows that look like real data
# ---------------------------------------------------------------------------

@st.composite
def csv_row_strategy(draw):
    """Generate a CSV row that conforms to the expected schema, plus mutations.
    
    This strategy generates valid rows, then applies random mutations
    (missing fields, extra fields, encoding errors) to test robustness.
    """
    # Generate a valid base row
    com_number = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('L', 'N', 'P'))))
    contract_number = draw(st.text(min_size=1, max_size=20))
    detailer = draw(st.text(min_size=0, max_size=50))
    due_date = draw(st.text(min_size=0, max_size=30))
    status_color = draw(st.text(min_size=0, max_size=10))
    description = draw(st.text(min_size=0, max_size=200))
    tags = draw(st.text(min_size=0, max_size=100))

    # Apply mutation: randomly drop fields
    mutation = draw(st.sampled_from(["none", "missing_com", "missing_contract", "extra_field", "empty_row"]))
    
    if mutation == "missing_com":
        com_number = ""
    elif mutation == "missing_contract":
        contract_number = ""
    elif mutation == "extra_field":
        return f"{com_number},{contract_number},{detailer},{due_date},{status_color},{description},{tags},EXTRA\n"
    elif mutation == "empty_row":
        return "\n"
    
    return f"{com_number},{contract_number},{detailer},{due_date},{status_color},{description},{tags}\n"


# ---------------------------------------------------------------------------
# Fuzz target: CSV import
# ---------------------------------------------------------------------------

@given(csv_row_strategy())
@settings(max_examples=1000, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_csv_import(csv_line: str):
    """Fuzz the CSV row parser. Must never crash."""
    try:
        reader = csv.DictReader(io.StringIO(csv_line))
        for row in reader:
            result = parse_csv_row(row)
            # If it parsed, validate the result structure
            if result is not None:
                assert isinstance(result, UnitRow)
                assert isinstance(result.com_number, str)
                # com_number should be non-empty if present
                if result.com_number:
                    assert len(result.com_number) <= 20
    except (ImportError, csv.Error, UnicodeDecodeError):
        # Acceptable failure modes
        pass
    except Exception as e:
        # Unexpected exceptions are bugs
        pytest.fail(f"Unexpected exception: {e!r}")
```

### 3. Hypothesis Strategies

We define a set of composable strategies in `tests/fuzz/strategies.py`:

```python
"""Hypothesis strategies for generating fuzz inputs."""
from hypothesis import strategies as st
import string
import datetime


# ---------------------------------------------------------------------------
# Tag parser strategies
# ---------------------------------------------------------------------------

def tag_strings():
    """Generate tag strings that test the tag parser.
    
    Focus on edge cases: empty, single character, very long, special chars,
    unicode, repeated delimiters, and whitespace-heavy strings.
    """
    return st.one_of(
        # Normal tags
        st.text(
            alphabet=string.ascii_letters + string.digits + "_-",
            min_size=1,
            max_size=50,
        ).map(lambda s: s.replace(" ", "_")),
        # Tags with special characters
        st.text(
            alphabet=string.printable,
            min_size=0,
            max_size=100,
        ),
        # Unicode tags (including emoji)
        st.text(
            min_size=0,
            max_size=50,
        ),
        # Tags with repeated delimiters
        st.just("tag1,,tag2"),
        st.just("tag1,tag2,"),
        st.just(",tag1,tag2"),
        st.just(","),
        st.just(""),
        # Very long tag
        st.text(min_size=1000, max_size=10000),
    )


# ---------------------------------------------------------------------------
# Date parser strategies
# ---------------------------------------------------------------------------

def date_strings():
    """Generate date strings that test the date parser.
    
    Covers: ISO 8601, US format, EU format, relative dates, invalid dates,
    Unix timestamps, natural language, and SQL date formats.
    """
    formats = [
        # ISO 8601 variants
        st.just(datetime.date.today().isoformat()),
        st.just((datetime.date.today() - datetime.timedelta(days=1)).isoformat()),
        st.just("2025-01-01"),
        st.just("2025-12-31"),
        # US format
        st.just("01/15/2025"),
        st.just("12/25/2025"),
        # EU format
        st.just("15/01/2025"),
        st.just("25/12/2025"),
        # Two-digit year
        st.just("01/15/25"),
        st.just("15/01/25"),
        # Compact formats
        st.just("20250101"),
        st.just("250101"),
        # Relative
        st.just("today"),
        st.just("yesterday"),
        st.just("tomorrow"),
        # Invalid dates
        st.just("02/30/2025"),   # Feb 30
        st.just("13/01/2025"),   # Month 13
        st.just("00/01/2025"),   # Month 0
        st.just("2025-13-01"),   # Month 13 (ISO)
        st.just("2025-00-01"),   # Month 0 (ISO)
        # SQL format
        st.just("2025-01-01 00:00:00"),
        st.just("2025-01-01T00:00:00"),
        # Unix timestamp
        st.just("1735689600"),
        st.just("0"),
        st.just("-1"),
        # Gibberish
        st.just("not a date"),
        st.just(""),
        st.just("   "),
        st.just(None),
    ]
    # Also generate random date-like strings
    random_dates = st.text(
        alphabet=string.digits + "/-.: T",
        min_size=6,
        max_size=30,
    )
    return st.one_of(st.one_of(formats), random_dates)


# ---------------------------------------------------------------------------
# CSV file strategies
# ---------------------------------------------------------------------------

def csv_content():
    """Generate full CSV file contents for fuzzing the import pipeline.
    
    Includes: valid CSVs, empty files, binary content, extremely large rows,
    mismatched columns, BOM markers, and different line endings.
    """
    return st.one_of(
        # Valid CSV with random data
        st.lists(
            st.lists(
                st.text(alphabet=string.printable, min_size=0, max_size=100),
                min_size=5,
                max_size=10,
            ),
            min_size=1,
            max_size=100,
        ).map(lambda rows: "\n".join([",".join(row) for row in rows])),
        # Empty
        st.just(""),
        st.just("\n"),
        st.just("\r\n"),
        # Binary-like
        st.binary(min_size=1, max_size=1024).map(lambda b: b.decode("latin-1")),
        # BOM prefixed
        st.just("\ufeffcom_number,contract_number\nCOM-001,CT-1001\n"),
        # Unix vs Windows line endings
        st.text(alphabet=string.printable, min_size=1, max_size=500).map(
            lambda s: s.replace("\n", "\r\n")
        ),
    )
```

### 4. Fuzz Test Templates

#### Target 1: CSV Import Fuzzing

```python
# tests/fuzz/test_csv_fuzz.py
"""Fuzz tests for the CSV import pipeline."""

from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st
import pytest
import io
import csv
import os
import tempfile

from sync.importer import ImportPipeline, ImportResult, parse_csv_row
from sync.models import UnitRow


@given(st.text(alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z', 'S')), min_size=0, max_size=5000))
@settings(max_examples=2000, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
def test_fuzz_csv_content(csv_content):
    """Fuzz the full CSV import with arbitrary text content.
    
    Must not:
      - Crash with any exception
      - Enter an infinite loop
      - Consume excessive memory
    """
    assume(len(csv_content) < 10000)  # Limit input size for CI
    pipeline = ImportPipeline()
    try:
        result = pipeline.import_from_string(csv_content, format="csv")
        # If import succeeded, verify invariants
        if result.success:
            assert isinstance(result.units, list)
            for unit in result.units:
                assert isinstance(unit, UnitRow)
                # Unit IDs should be unique
                ids = [u.com_number for u in result.units if u.com_number]
                assert len(ids) == len(set(ids)), "Duplicate COM numbers after import"
    except (csv.Error, UnicodeDecodeError, ValueError):
        # Acceptable parser failures
        pass
    except MemoryError:
        pytest.skip("Input caused memory exhaustion (acceptable for fuzz)")
    except Exception as e:
        pytest.fail(f"Unexpected exception: {e!r}")
```

#### Target 2: Tag Parser Fuzzing

```python
# tests/fuzz/test_tag_fuzz.py
"""Fuzz tests for the tag parser."""

from hypothesis import given, settings, HealthCheck
import pytest

from gui.tag_parser import parse_tags, Tag, TagError


@given(st.text(min_size=0, max_size=1000))
@settings(max_examples=2000, suppress_health_check=[HealthCheck.too_slow])
def test_fuzz_tag_parser(tag_string):
    """Fuzz the tag parser with arbitrary strings.
    
    Invariants:
      - parse_tags() always returns a list (possibly empty)
      - Each tag has a non-empty name
      - No exception is raised (TagError is acceptable)
    """
    try:
        tags = parse_tags(tag_string)
        assert isinstance(tags, list), "parse_tags must return a list"
        for tag in tags:
            assert isinstance(tag, Tag), "Each item must be a Tag object"
            assert isinstance(tag.name, str), "Tag name must be a string"
            assert tag.name, "Tag name must not be empty"
    except TagError:
        # Acceptable — the parser may reject invalid input
        pass
    except Exception as e:
        pytest.fail(f"Unexpected exception: {e!r}")
```

#### Target 3: Date Parser Fuzzing

```python
# tests/fuzz/test_date_fuzz.py
"""Fuzz tests for the date parser."""

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
import pytest
import datetime

from gui.date_parser import parse_date, DateParseError


@given(st.text(min_size=0, max_size=200))
@settings(max_examples=2000, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
def test_fuzz_date_parser(date_string):
    """Fuzz the date parser with arbitrary strings.
    
    Invariants:
      - parse_date() either returns a datetime.date or raises DateParseError
      - If it returns a date, the date is within reasonable bounds
    """
    # Skip extremely long strings to keep CI fast
    assume(len(date_string) < 100)
    
    try:
        result = parse_date(date_string)
        if result is not None:
            assert isinstance(result, (datetime.date, datetime.datetime)), \
                f"Expected date/datetime, got {type(result)}"
            # Sanity check: year should be reasonable
            if hasattr(result, 'year'):
                assert 1900 <= result.year <= 2100, \
                    f"Year {result.year} out of reasonable range"
    except (DateParseError, ValueError, OverflowError):
        # Acceptable failure modes
        pass
    except Exception as e:
        pytest.fail(f"Unexpected exception: {e!r}")


@given(st.floats(allow_nan=False, allow_infinity=False, min_value=-1e12, max_value=1e12))
@settings(max_examples=1000)
def test_fuzz_date_numeric(timestamp):
    """Fuzz the date parser with numeric timestamps."""
    try:
        result = parse_date(str(timestamp))
        # No crash is the primary assertion
    except (DateParseError, ValueError, OverflowError):
        pass
```

---

## Seed Corpus

### Source Data

The seed corpus is derived from **2,765 production descriptions** and real CSV files from the deployed system. These are stored in `tests/fuzz/corpus/` and used to seed Hypothesis's internal database.

### Corpus Structure

```
tests/fuzz/
  corpus/
    csv/
      production_export_2025-01-01.csv
      production_export_2025-01-02.csv
      ...
      edge_case_empty.csv
      edge_case_single_column.csv
      edge_case_unicode_bom.csv
    tags/
      descriptions.txt          # 2,765 lines, one description per line
      tags_from_production.txt  # Extracted tag strings
    dates/
      dates_from_production.txt # All due dates from production DB
```

### Corpus Generation Script

```python
# scripts/generate_fuzz_corpus.py
"""Generate a seed corpus from production data for fuzz testing.

Usage:
    python scripts/generate_fuzz_corpus.py --input data/production_export.csv --output tests/fuzz/corpus/
"""

import csv
import argparse
import os
import random
from pathlib import Path


def extract_descriptions(csv_path: str, output_dir: str, sample_size: int = 2765):
    """Extract unique descriptions from a production CSV export."""
    descriptions = set()
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            desc = row.get("description", "").strip()
            if desc:
                descriptions.add(desc)
    
    # Take a sample (or all if fewer)
    sampled = random.sample(list(descriptions), min(sample_size, len(descriptions)))
    
    output_path = Path(output_dir) / "tags" / "descriptions.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sampled))
    
    print(f"Wrote {len(sampled)} descriptions to {output_path}")
    return sampled


def extract_tags(descriptions: list[str], output_dir: str):
    """Extract individual tags from tag-formatted descriptions."""
    all_tags = set()
    for desc in descriptions:
        # Assume tags are comma-separated or space-separated
        for sep in [",", ";", "|", " "]:
            if sep in desc:
                parts = desc.split(sep)
                for part in parts:
                    part = part.strip().lower()
                    if 1 < len(part) < 50:
                        all_tags.add(part)
    
    output_path = Path(output_dir) / "tags" / "tags_from_production.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(all_tags)))
    
    print(f"Extracted {len(all_tags)} unique tags to {output_path}")


def extract_dates(csv_path: str, output_dir: str):
    """Extract all date strings from a production CSV export."""
    dates = set()
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for key in ["detailing_due_date", "due_date", "date", "created_at", "updated_at"]:
                val = row.get(key, "").strip()
                if val:
                    dates.add(val)
    
    output_path = Path(output_dir) / "dates" / "dates_from_production.txt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(dates)))
    
    print(f"Extracted {len(dates)} unique dates to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate fuzz seed corpus")
    parser.add_argument("--input", required=True, help="Path to production CSV export")
    parser.add_argument("--output", default="tests/fuzz/corpus", help="Output directory")
    parser.add_argument("--sample-size", type=int, default=2765, help="Number of descriptions to sample")
    args = parser.parse_args()
    
    descriptions = extract_descriptions(args.input, args.output, args.sample_size)
    extract_tags(descriptions, args.output)
    extract_dates(args.input, args.output)
```

### Using the Corpus with Hypothesis

Hypothesis automatically writes examples to a `.hypothesis/examples` database. To seed it with our corpus:

```python
# conftest.py or test file
from hypothesis import settings

# Point Hypothesis to load from the seed corpus
settings.register_profile("ci", database=".hypothesis-examples")
settings.register_profile("corpus", database="tests/fuzz/corpus")
settings.load_profile("ci")

# Or use the --hypothesis-database flag:
# pytest --hypothesis-database=tests/fuzz/corpus tests/fuzz/
```

---

## Implementation Plan

### Phase 1: Infrastructure Setup (Days 1–2)

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Install Hypothesis, configure project structure in `tests/fuzz/` | Working test environment |
| 1 | Create `strategies.py` with composable strategies for CSV, tags, dates | Reusable strategy module |
| 2 | Build seed corpus from production data (run corpus generation script) | Seed corpus in `tests/fuzz/corpus/` |
| 2 | Set up coverage reporting for fuzz targets | Baseline coverage metrics |

**Total effort:** 2 days (1 engineer)

### Phase 2: Fuzz Target Implementation (Days 3–5)

| Day | Task | Deliverable |
|-----|------|-------------|
| 3 | CSV import fuzz target with Hypothesis @given + strategies | `test_csv_fuzz.py` |
| 3 | Run 10,000 examples, collect failures, fix bugs | Bug fixes + hardened CSV parser |
| 4 | Tag parser fuzz target | `test_tag_fuzz.py` |
| 4 | Run 10,000 examples, collect failures, fix bugs | Bug fixes + hardened tag parser |
| 5 | Date parser fuzz target | `test_date_fuzz.py` |
| 5 | Run 10,000 examples, collect failures, fix bugs | Bug fixes + hardened date parser |

**Total effort:** 3 days (1 engineer)

### Phase 3: CI Integration (Days 6)

| Day | Task | Deliverable |
|-----|------|-------------|
| 6 | Add GitHub Actions workflow for fuzz tests with 60s per target | `fuzz-tests.yml` |
| 6 | Configure parallel fuzzing with pytest-xdist | CI pipeline running 3 targets in parallel |
| 6 | Add dashboard/notification for fuzz failures | Slack/email alerting |

**Total effort:** 1 day (1 engineer)

### Phase 4: Hardening & Continuous Fuzzing (Day 7)

| Day | Task | Deliverable |
|-----|------|-------------|
| 7 | Add regression tests for all bugs found during Phase 2 | `tests/regression/` test cases |
| 7 | Document fuzz testing process in CONTRIBUTING.md | Developer guide |
| 7 | Set up weekly long-duration fuzz runs (10 min per target) | Cron job or scheduled CI |

**Total effort:** 1 day (1 engineer)

---

## CI Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/fuzz-tests.yml
name: Fuzz Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1"  # Every Monday at 6 AM UTC

jobs:
  fuzz:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        target: [csv, tags, dates]
      fail-fast: false

    steps:
    - uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: "3.11"

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install hypothesis pytest pytest-xdist coverage
        pip install -r requirements.txt

    - name: Run fuzz test (${{ matrix.target }})
      run: |
        timeout 120 pytest tests/fuzz/test_${target}_fuzz.py \
          --verbose \
          --hypothesis-profile=ci \
          --hypothesis-max-examples=0 \
          -x \
          --timeout=90 \
          2>&1 | tee fuzz_${target}_output.txt
      env:
        target: ${{ matrix.target }}

    - name: Collect coverage
      run: |
        coverage run --include="sync/*,gui/*" -m pytest tests/fuzz/test_${target}_fuzz.py \
          --hypothesis-profile=ci \
          --hypothesis-max-examples=0 \
          --timeout=90
        coverage report
      env:
        target: ${{ matrix.target }}

    - name: Upload fuzz artifacts
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: fuzz-results-${{ matrix.target }}
        path: |
          fuzz_${{ matrix.target }}_output.txt
          .hypothesis/
```

### Time Budget Management

Each CI run allocates **60 seconds per target** (3 targets = 3 minutes total). The `--hypothesis-max-examples=0` flag tells Hypothesis to run until the time budget expires.

```python
# profiles.py
from hypothesis import settings

# CI profile: 60 seconds per target
settings.register_profile("ci", max_examples=0, deadline=60000, database=".hypothesis-examples")

# Development profile: quick sanity check
settings.register_profile("dev", max_examples=500, deadline=5000)

# Nightly profile: deep fuzzing
settings.register_profile("nightly", max_examples=0, deadline=600000, database=".hypothesis-examples")

# Coverage profile: maximize coverage
settings.register_profile("coverage", max_examples=2000, deadline=10000, database=None)
```

### Long-Running Fuzz Schedule

```yaml
# .github/workflows/fuzz-nightly.yml
name: Nightly Deep Fuzz

on:
  schedule:
    - cron: "0 2 * * *"  # Every night at 2 AM UTC

jobs:
  deep-fuzz:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - name: Install dependencies
      run: |
        pip install hypothesis pytest coverage
        pip install -r requirements.txt
    - name: Run deep fuzz (10 min per target)
      run: |
        for target in csv tags dates; do
          echo "=== Fuzzing $target for 10 minutes ==="
          timeout 620 pytest tests/fuzz/test_${target}_fuzz.py \
            --hypothesis-profile=nightly \
            --verbose \
            -x 2>&1 | tee fuzz_${target}_nightly.txt
        done
    - name: Archive results
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: nightly-fuzz-logs
        path: fuzz_*_nightly.txt
```

---

## Success Criteria

| Criterion | Measurement | Pass/Fail |
|-----------|-------------|-----------|
| All 3 fuzz targets implemented | CI pipeline has 3 fuzz jobs | |
| Zero crash/hang bugs in data pipelines | 7 days of CI fuzzing with no failures | |
| Coverage > 80% on data pipeline code | `coverage report` shows > 80% | |
| Seed corpus loaded and used | Hypothesis database contains > 1000 entries | |
| CI fuzz run completes in < 3 min | Workflow duration < 180s | |
| All Phase 2 discovered bugs have regression tests | `tests/regression/` contains test cases | |

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Hypothesis generates too many invalid inputs | Low | Medium | Use `assume()` judiciously; tune strategies to skew toward valid-like inputs |
| Fuzz tests take too long in CI | Medium | Medium | Set 60s time budget; parallelize across 3 jobs; use `--timeout` |
| Seed corpus becomes stale | Low | High | Regenerate corpus weekly from production data via cron |
| False positives from Hypothesis flakiness | Low | Low | Pin Hypothesis version; use deterministic seed (`--hypothesis-seed`) |
| atheris not available on Linux | Medium | Low | Fall back to Hypothesis-only; atheris is optional |

---

## Appendix

### A. Dependencies

```txt
# requirements-fuzz.txt
hypothesis>=6.100.0
pytest>=8.0
pytest-xdist>=3.5.0
pytest-timeout>=2.2.0
coverage>=7.4.0

# Optional: atheris for native/C-level fuzzing
# atheris>=2.0.12
```

### B. Installation

```bash
# Install fuzz-specific dependencies
pip install -r requirements-fuzz.txt

# Verify Hypothesis installation
python -c "from hypothesis import strategies; print('Hypothesis ready')"

# Generate seed corpus from production data
python scripts/generate_fuzz_corpus.py \
  --input data/production_export.csv \
  --output tests/fuzz/corpus

# Run all fuzz tests locally (60s per target)
pytest tests/fuzz/ --hypothesis-profile=ci --verbose
```

### C. Running Fuzz Tests Locally

```bash
# Quick check (500 examples per test)
pytest tests/fuzz/ --hypothesis-profile=dev --verbose

# Full fuzz run (60s per target)
pytest tests/fuzz/ --hypothesis-profile=ci --verbose --timeout=90

# Run a specific target
pytest tests/fuzz/test_csv_fuzz.py --verbose

# Run with coverage
coverage run -m pytest tests/fuzz/ --hypothesis-profile=dev
coverage report -m

# Reproduce a specific failure
pytest tests/fuzz/test_date_fuzz.py \
  --hypothesis-seed=12345 \
  --verbose \
  --hypothesis-show-statistics
```

### D. Related Documents

- [ARCH-003: Data Validation Layer](./ARCH-003-data-validation-layer.md) — Formal data validation that fuzz targets exercise
- [QA-001: Property-Based Testing](./QA-001-property-based-testing.md) — Complementary property-based tests for data invariants
- [QA-002: UI Integration Tests](./QA-002-ui-integration-tests.md) — Higher-level UI tests that exercise these pipelines
- [QA-004: Benchmark Regression](./QA-004-benchmark-regression.md) — Performance benchmarks for these same pipelines

---

*End of QA-003: Fuzz Testing for Data Pipelines*
