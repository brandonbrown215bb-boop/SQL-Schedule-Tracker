# QA-004: Performance Benchmark & Regression Suite

| **Field**       | **Details**                                      |
|-----------------|--------------------------------------------------|
| **Status**      | Draft                                            |
| **Priority**    | Medium                                           |
| **Effort**      | S (5 days)                                       |
| **Dependencies**| None                                             |
| **Phases**      | 3                                                |

---

## 1. Problem

The project currently has:

- **No performance benchmarks.** There is no way to quantitatively measure whether a change improves or degrades runtime performance.
- **No regression gates.** Pull requests can introduce significant slowdowns without any automated signal, making performance regressions invisible until users notice.
- **No historical tracking.** Without persisted benchmark results, performance trends across commits cannot be analyzed, making it impossible to identify when a regression was introduced.

---

## 2. Solution

Introduce a `pytest-benchmark`-based performance test suite. Each benchmark defines a baseline threshold. If a change exceeds that threshold by more than 20%, the CI pipeline flags it.

### 2.1 Benchmark Scenarios & Baselines

| # | Benchmark Scenario | Code Trigger | Baseline (ms) | Notes |
|---|-------------------|-------------|---------------|-------|
| 1 | Load 1000 units from SQLite | `load_units(1000)` | <100 | — |
| 2 | Load 10000 units from SQLite | `load_units(10000)` | <500 | Stress test |
| 3 | Save 1 unit | `save_unit(unit)` | <50 | — |
| 4 | Render list panel with 1000 rows | `render_list(1000)` | <200 | PyQt rendering |
| 5 | Tag parse 2765 descriptions | `parse_tags(descriptions)` | <500 | Production data |
| 6 | CSV import 1000 rows | `csv_import("1000_rows.csv")` | <1000 | — |
| 7 | `_apply_identicals` on 1000 units | `apply_identicals(units_1000)` | <50 | — |
| 8 | `full_suite()` | combined benchmark | N/A | Aggregate runner |

### 2.2 Benchmark Code

All benchmarks live under `tests/benchmarks/`. Below is the implementation for each file.

#### `tests/benchmarks/conftest.py`

```python
"""Shared fixtures for benchmark tests."""

import pytest
import sqlite3
import tempfile
import csv
import os

from src.data_model import Unit, ScheduleStore
from src.parser import TagParser
from src.list_panel import ListPanel


@pytest.fixture(scope="module")
def temp_db():
    """Create a temporary SQLite database and return the path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS units (id TEXT PRIMARY KEY, data TEXT)")
    conn.commit()
    conn.close()
    yield db_path
    os.unlink(db_path)


@pytest.fixture
def store(temp_db):
    """Return a ScheduleStore backed by a temp DB."""
    return ScheduleStore(db_path=temp_db)


def _populate_db(db_path: str, count: int):
    """Insert *count* dummy units into the database."""
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM units")
    data = []
    for i in range(count):
        data.append((f"U{i:06d}", f'{{"name": "Unit {i}", "value": {i}}}'))
    conn.executemany("INSERT INTO units (id, data) VALUES (?, ?)", data)
    conn.commit()
    conn.close()


@pytest.fixture
def db_1000(temp_db):
    """Populate DB with 1000 units."""
    _populate_db(temp_db, 1000)
    return temp_db


@pytest.fixture
def db_10000(temp_db):
    """Populate DB with 10000 units."""
    _populate_db(temp_db, 10000)
    return temp_db


@pytest.fixture
def sample_unit():
    """Return a single Unit instance."""
    return Unit(id="bench-unit", name="Benchmark Unit", value=42)


@pytest.fixture
def units_1000():
    """Return a list of 1000 Unit instances."""
    return [Unit(id=f"U{i:06d}", name=f"Unit {i}", value=i) for i in range(1000)]


@pytest.fixture
def production_descriptions():
    """Return a list of 2765 tag-parseable descriptions (synthetic production data)."""
    descriptions = []
    for i in range(2765):
        descriptions.append(
            f"[{'critical' if i % 3 == 0 else 'normal'}] "
            f"Task #{i}: {('fix' if i % 2 == 0 else 'update')} "
            f"component_{i % 50} — assigned to {'alice' if i % 2 == 0 else 'bob'}"
        )
    return descriptions


@pytest.fixture
def csv_1000_rows(temp_db):
    """Create a CSV file with 1000 rows for import benchmarks."""
    csv_path = temp_db.replace(".db", ".csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "value"])
        for i in range(1000):
            writer.writerow([f"CSV{i:06d}", f"CSV Row {i}", i])
    yield csv_path
    os.unlink(csv_path)


@pytest.fixture
def list_panel(qapp, units_1000):
    """Return a ListPanel instance populated with 1000 units."""
    panel = ListPanel()
    panel.load(units_1000)
    return panel
```

#### `tests/benchmarks/test_benchmarks.py`

```python
"""Performance benchmark tests for core operations."""

import pytest
from src.data_model import ScheduleStore
from src.parser import TagParser
from src.list_panel import ListPanel
from src.csv_handler import CsvHandler
from src.tag_matcher import TagMatcher  # contains _apply_identicals


# ── 1. Load 1000 units from SQLite ──────────────────────────────────────

def test_load_1000_units(benchmark, store, db_1000):
    """Benchmark loading 1000 units from SQLite."""
    benchmark.group = "db_load"
    result = benchmark(store.load_all, db_1000)
    assert len(result) == 1000


# ── 2. Load 10000 units from SQLite ─────────────────────────────────────

def test_load_10000_units(benchmark, store, db_10000):
    """Benchmark loading 10000 units from SQLite (stress test)."""
    benchmark.group = "db_load"
    store.db_path = db_10000
    result = benchmark(store.load_all)
    assert len(result) == 10000


# ── 3. Save 1 unit ──────────────────────────────────────────────────────

def test_save_1_unit(benchmark, store, sample_unit):
    """Benchmark saving a single unit."""
    benchmark.group = "db_write"
    benchmark(store.save, sample_unit)


# ── 4. Render list panel with 1000 rows ─────────────────────────────────

def test_render_list_1000(benchmark, list_panel):
    """Benchmark rendering a list panel with 1000 rows."""
    benchmark.group = "rendering"
    benchmark(list_panel.render)


# ── 5. Tag parse 2765 descriptions from production data ─────────────────

def test_tag_parse_2765(benchmark, production_descriptions):
    """Benchmark tag parsing on 2765 descriptions (production-scale data)."""
    benchmark.group = "parsing"
    parser = TagParser()
    benchmark(parser.parse_batch, production_descriptions)


# ── 6. CSV import 1000 rows ─────────────────────────────────────────────

def test_csv_import_1000(benchmark, csv_1000_rows, store):
    """Benchmark CSV import of 1000 rows."""
    benchmark.group = "csv"
    handler = CsvHandler(store)
    benchmark(handler.import_csv, csv_1000_rows)


# ── 7. _apply_identicals on 1000 units ──────────────────────────────────

def test_apply_identicals_1000(benchmark, units_1000):
    """Benchmark _apply_identicals with 1000 units."""
    benchmark.group = "matching"
    matcher = TagMatcher()
    benchmark(matcher.apply_identicals, units_1000)


# ── 8. full_suite() — combined benchmark ────────────────────────────────

def test_full_suite(benchmark, store, db_1000, sample_unit,
                    list_panel, production_descriptions,
                    csv_1000_rows, units_1000):
    """Benchmark the full pipeline end-to-end."""
    benchmark.group = "full_suite"

    def full_suite():
        store.load_all(db_1000)
        store.save(sample_unit)
        list_panel.render()
        TagParser().parse_batch(production_descriptions)
        CsvHandler(store).import_csv(csv_1000_rows)
        TagMatcher().apply_identicals(units_1000)

    benchmark(full_suite)
```

#### `tests/benchmarks/__init__.py`

```python
"""Performance benchmark package."""
```

### 2.3 Running Benchmarks Locally

```bash
# Run all benchmarks
pytest tests/benchmarks/ --benchmark-only

# Run benchmarks and compare against stored historical data
pytest tests/benchmarks/ --benchmark-only --benchmark-compare

# Run benchmarks and save results to a JSON file
pytest tests/benchmarks/ --benchmark-only --benchmark-json=benchmarks.json

# Run a specific benchmark group
pytest tests/benchmarks/ -k "db_load" --benchmark-only

# Run with calibration disabled (for faster iteration)
pytest tests/benchmarks/ --benchmark-only --benchmark-disable-calibration
```

### 2.4 Baseline Reference Table

| Benchmark | Baseline (ms) | Method |
|-----------|---------------|--------|
| `test_load_1000_units` | < 100 | `benchmark(store.load_all, db_1000)` |
| `test_load_10000_units` | < 500 | `benchmark(store.load_all, db_10000)` |
| `test_save_1_unit` | < 50 | `benchmark(store.save, sample_unit)` |
| `test_render_list_1000` | < 200 | `benchmark(list_panel.render)` |
| `test_tag_parse_2765` | < 500 | `benchmark(parser.parse_batch, descriptions)` |
| `test_csv_import_1000` | < 1000 | `benchmark(handler.import_csv, csv_path)` |
| `test_apply_identicals_1000` | < 50 | `benchmark(matcher.apply_identicals, units_1000)` |
| `test_full_suite` | N/A (aggregate) | `benchmark(full_suite)` |

---

## 3. Architecture

```
tests/
├── benchmarks/
│   ├── __init__.py              # Package marker
│   ├── conftest.py              # Shared fixtures (DB, units, CSV, etc.)
│   └── test_benchmarks.py       # Benchmark test functions
├── benchmarks.json              # Historical benchmark results (committed)
└── .benchmarks/                 # pytest-benchmark local cache (git-ignored)
```

Key design decisions:

- **`conftest.py`** contains all test fixtures, keeping the benchmark file focused on test logic.
- **`scope="module"`** on the `temp_db` fixture avoids recreating the database for every test.
- **`benchmark.group`** enables grouping in output reports.
- **`benchmarks.json`** is the single source of truth for historical comparison.
- **`.benchmarks/`** (local cache) is excluded from version control.

---

## 4. CI Gates

### 4.1 GitHub Actions Workflow

```yaml
# .github/workflows/benchmark.yml

name: Performance Benchmarks

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

jobs:
  benchmark:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # fetch all history for comparison

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install system dependencies (PyQt)
        run: |
          sudo apt-get update
          sudo apt-get install -y libxcb-xinerama0 libegl1 libgl1-mesa-glx xvfb

      - name: Install project dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pytest pytest-benchmark
          pip install -e .

      - name: Pull historical benchmarks
        run: |
          # If a benchmarks.json exists in the base branch, copy it
          git show origin/${{ github.base_ref }}:tests/benchmarks.json 2>/dev/null \
            > tests/benchmarks.json || true

      - name: Run benchmarks with comparison
        run: |
          xvfb-run pytest tests/benchmarks/ \
            --benchmark-only \
            --benchmark-json=tests/benchmarks.json \
            --benchmark-compare \
            --benchmark-compare-fail=min:20% \
            --benchmark-histogram=benchmark-histograms
        env:
          QT_QPA_PLATFORM: offscreen

      - name: Upload benchmark results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: |
            tests/benchmarks.json
            benchmark-histograms/

      - name: Commit updated benchmarks.json (main only)
        if: github.ref == 'refs/heads/main'
        run: |
          git config user.name "benchmark-bot"
          git config user.email "bot@example.com"
          git add tests/benchmarks.json
          git commit -m "Update benchmarks.json [skip ci]" || echo "No changes to commit"
          git push
```

### 4.2 Regression Gate Configuration

The `--benchmark-compare-fail=min:20%` flag is the regression gate. It means:

> If **any** benchmark is slower than the stored baseline by **20% or more**, the CI step exits with a non-zero status, causing the job to fail.

This prevents performance regressions from passing unnoticed.

**Monitoring and escalation:**

- **Flagged PRs:** The CI failure message includes a link to the benchmark histogram artifacts.
- **Manual override:** A maintainer can add the label `perf-regression-ack` to bypass the gate in urgent cases.
- **Baseline updates:** When a change intentionally improves performance, the `benchmarks.json` is updated so the new faster time becomes the baseline.

---

## 5. Historical Tracking

### 5.1 Storage Format (`tests/benchmarks.json`)

```json
{
  "commit": "7ad0fbf3a476f032ea8e60f418c7a399a27a9378",
  "timestamp": "2024-01-15T14:30:00Z",
  "machine": "ci-linux-x86_64",
  "benchmarks": {
    "test_load_1000_units": {
      "min": 45.2,
      "max": 62.1,
      "mean": 50.3,
      "median": 49.8,
      "stddev": 4.1,
      "rounds": 10,
      "baseline_ms": 100
    },
    "test_load_10000_units": {
      "min": 320.0,
      "max": 410.5,
      "mean": 368.2,
      "median": 365.0,
      "stddev": 25.3,
      "rounds": 5,
      "baseline_ms": 500
    },
    "test_save_1_unit": {
      "min": 12.3,
      "max": 18.7,
      "mean": 15.1,
      "median": 14.9,
      "stddev": 1.9,
      "rounds": 20,
      "baseline_ms": 50
    },
    "test_render_list_1000": {
      "min": 110.2,
      "max": 145.8,
      "mean": 128.5,
      "median": 126.0,
      "stddev": 10.2,
      "rounds": 10,
      "baseline_ms": 200
    },
    "test_tag_parse_2765": {
      "min": 280.0,
      "max": 350.0,
      "mean": 315.0,
      "median": 312.0,
      "stddev": 20.0,
      "rounds": 5,
      "baseline_ms": 500
    },
    "test_csv_import_1000": {
      "min": 550.0,
      "max": 700.0,
      "mean": 625.0,
      "median": 620.0,
      "stddev": 40.0,
      "rounds": 5,
      "baseline_ms": 1000
    },
    "test_apply_identicals_1000": {
      "min": 18.5,
      "max": 25.3,
      "mean": 21.2,
      "median": 20.8,
      "stddev": 2.1,
      "rounds": 20,
      "baseline_ms": 50
    },
    "test_full_suite": {
      "min": 1350.0,
      "max": 1700.0,
      "mean": 1520.0,
      "median": 1500.0,
      "stddev": 100.0,
      "rounds": 5,
      "baseline_ms": null
    }
  }
}
```

### 5.2 Historical Analysis Dashboard

A lightweight dashboard script can be run locally to visualize trends:

```python
#!/usr/bin/env python3
# tools/benchmark_trend.py — Display benchmark history from benchmarks.json

import json
import sys
from pathlib import Path
from datetime import datetime


def load_history(benchmark_json: Path):
    """Load a single benchmarks.json snapshot."""
    with open(benchmark_json) as f:
        return json.load(f)


def load_all_history(repo_root: Path):
    """Gather all benchmarks.json commits from git history."""
    import subprocess
    result = subprocess.run(
        ["git", "log", "--pretty=format:%H", "--", "tests/benchmarks.json"],
        capture_output=True, text=True, cwd=repo_root
    )
    commits = result.stdout.strip().split("\n")
    history = []
    for commit in commits:
        if not commit:
            continue
        blob = subprocess.run(
            ["git", "show", f"{commit}:tests/benchmarks.json"],
            capture_output=True, text=True, cwd=repo_root
        )
        if blob.returncode == 0:
            data = json.loads(blob.stdout)
            history.append(data)
    return history


def format_trend(history):
    """Print a simple ASCII trend table."""
    header = f"{'Commit':<12} {'Date':<20} {'Load1k':<10} {'Load10k':<10} {'Save':<10} {'Render':<10} {'Tags':<10} {'CSV':<10} {'Identical':<10}"
    print(header)
    print("-" * len(header))
    for entry in history:
        short = entry["commit"][:8]
        dt = entry["timestamp"][:10]
        b = entry["benchmarks"]
        print(
            f"{short:<12} {dt:<20} "
            f"{b['test_load_1000_units']['median']:<10.1f} "
            f"{b['test_load_10000_units']['median']:<10.1f} "
            f"{b['test_save_1_unit']['median']:<10.1f} "
            f"{b['test_render_list_1000']['median']:<10.1f} "
            f"{b['test_tag_parse_2765']['median']:<10.1f} "
            f"{b['test_csv_import_1000']['median']:<10.1f} "
            f"{b['test_apply_identicals_1000']['median']:<10.1f}"
        )


if __name__ == "__main__":
    repo = Path(__file__).resolve().parent.parent
    snapshot = repo / "tests" / "benchmarks.json"
    if snapshot.exists():
        print("== Current Snapshot ==")
        data = load_history(snapshot)
        print(f"Commit: {data['commit'][:8]}  Timestamp: {data['timestamp']}")
        for name, metrics in data["benchmarks"].items():
            print(f"  {name}: median={metrics['median']:.1f}ms  "
                  f"(baseline={metrics['baseline_ms']}ms)")
    print("\n== Historical Trend ==")
    full = load_all_history(repo)
    if full:
        format_trend(full)
    else:
        print("No historical benchmarks.json entries found in git history.")
```

### 5.3 Trend Visualization

When run with `--benchmark-histogram=benchmark-histograms`, `pytest-benchmark` generates HTML histogram plots comparing each benchmark run against historical runs. These are uploaded as CI artifacts and linked from the PR check.

---

## 6. Phases

### Phase 1 — pytest-benchmark Setup + Baseline Tests (2 days)

| Day | Tasks |
|-----|-------|
| 1 | Install pytest-benchmark, create `tests/benchmarks/` package, write `conftest.py` with all fixtures |
| 2 | Write all 8 benchmark tests, run locally to establish initial baselines, commit `benchmarks.json` |

**Deliverables:**
- `tests/benchmarks/__init__.py`
- `tests/benchmarks/conftest.py`
- `tests/benchmarks/test_benchmarks.py`
- Initial `tests/benchmarks.json`

### Phase 2 — CI Integration + Gates (1 day)

| Day | Tasks |
|-----|-------|
| 3 | Create `.github/workflows/benchmark.yml`, configure regression gate with 20% threshold, test PR workflow |

**Deliverables:**
- `.github/workflows/benchmark.yml`
- CI passes with baseline benchmarks
- PR that degrades performance by >20% is flagged

### Phase 3 — Historical Tracking Dashboard (2 days)

| Day | Tasks |
|-----|-------|
| 4 | Write `tools/benchmark_trend.py`, add auto-commit of `benchmarks.json` on main branch pushes |
| 5 | Test full pipeline: merge → benchmark run → JSON update → trend script renders history correctly |

**Deliverables:**
- `tools/benchmark_trend.py`
- Verified historical trend output format

---

## 7. Effort Breakdown

| Phase | Days | Description |
|-------|------|-------------|
| 1 | 2 | pytest-benchmark setup + baseline tests |
| 2 | 1 | CI integration + regression gates |
| 3 | 2 | Historical tracking + trend dashboard |
| **Total** | **5** | **Effort: S** |

---

## 8. Dependencies

- **None.** All work is self-contained within the test infrastructure.
- Required packages: `pytest-benchmark` (added to `dev-requirements.txt` or equivalent).
- System dependency for headless rendering: `xvfb-run` (CI only).

---

## 9. Output Format Specification

### 9.1 CLI Output (`pytest --benchmark-only`)

```
-------------------------------------------------------------------------------------------------- benchmark: 8 tests --------------------------------------------------------------------------------------------------
Name (time in ms)                          Min                 Max                Mean            StdDev              Median               IQR            Outliers     OPS            Rounds  Iterations
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
test_load_1000_units                     45.2000 (1.0)       62.1000 (1.0)       50.3000 (1.0)      4.1000 (1.0)       49.8000 (1.0)      4.5000 (1.0)          2;2   19.8807 (1.0)          10           1
test_load_10000_units                   320.0000 (7.08)     410.5000 (6.61)     368.2000 (7.32)    25.3000 (6.17)     365.0000 (7.33)    20.1000 (4.47)         1;1    2.7159 (0.14)          5           1
test_save_1_unit                         12.3000 (0.27)      18.7000 (0.30)      15.1000 (0.30)     1.9000 (0.46)      14.9000 (0.30)     2.2000 (0.49)         3;3   66.2252 (3.33)         20           1
test_render_list_1000                   110.2000 (2.44)     145.8000 (2.35)     128.5000 (2.55)    10.2000 (2.49)     126.0000 (2.53)    12.1000 (2.69)         2;2    7.7821 (0.39)         10           1
test_tag_parse_2765                     280.0000 (6.19)     350.0000 (5.64)     315.0000 (6.26)    20.0000 (4.88)     312.0000 (6.27)    18.0000 (4.00)         1;0    3.1746 (0.16)          5           1
test_csv_import_1000                    550.0000 (12.17)    700.0000 (11.27)    625.0000 (12.42)   40.0000 (9.76)     620.0000 (12.45)   35.0000 (7.78)         1;0    1.6000 (0.08)          5           1
test_apply_identicals_1000               18.5000 (0.41)      25.3000 (0.41)      21.2000 (0.42)     2.1000 (0.51)      20.8000 (0.42)     2.5000 (0.56)         2;2   47.1698 (2.37)         20           1
test_full_suite                       1,350.0000 (29.87)  1,700.0000 (27.38)  1,520.0000 (30.22)  100.0000 (24.39)  1,500.0000 (30.12)  80.0000 (17.78)        0;0    0.6579 (0.03)          5           1
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Legend:
  Outliers: 1 Standard Deviation from Mean; 1.5 IQR (InterQuartile Range) from 1st Quartile.
  OPS: Operations Per Second, computed as 1 / Mean
```

### 9.2 CI Gate Failure Message

```
❌ PERFORMANCE REGRESSION DETECTED

The following benchmarks degraded by more than 20% compared to the baseline:

  test_load_10000_units:  365.0ms (baseline: 280.0ms, +30.4%)  FAIL
  test_tag_parse_2765:    412.0ms (baseline: 312.0ms, +32.1%)  FAIL

To bypass (emergency only), add the label `perf-regression-ack` to this PR.
Please review the benchmark histogram artifacts for detailed breakdowns.
```

### 9.3 Historical Trend Output

```
== Current Snapshot ==
Commit: 7ad0fbf3  Timestamp: 2024-01-15T14:30:00Z
  test_load_1000_units: median=49.8ms  (baseline=100ms)
  test_load_10000_units: median=365.0ms  (baseline=500ms)
  test_save_1_unit: median=14.9ms  (baseline=50ms)
  test_render_list_1000: median=126.0ms  (baseline=200ms)
  test_tag_parse_2765: median=312.0ms  (baseline=500ms)
  test_csv_import_1000: median=620.0ms  (baseline=1000ms)
  test_apply_identicals_1000: median=20.8ms  (baseline=50ms)

== Historical Trend ==
Commit       Date                 Load1k     Load10k    Save       Render     Tags       CSV        Identical
--------------------------------------------------------------------------------------------------------------------------
7ad0fbf3     2024-01-15          49.8       365.0      14.9       126.0      312.0      620.0      20.8
a1b2c3d4     2024-01-10          52.1       380.2      15.3       130.5      325.0      640.0      21.5
e5f6g7h8     2024-01-05          55.0       395.0      16.1       135.0      340.0      670.0      22.3
i9j0k1l2     2023-12-28          60.0       420.0      17.0       142.0      360.0      710.0      24.0
```

---

## 10. Adoption Checklist

- [ ] Phase 1: Add `pytest-benchmark` to dev dependencies
- [ ] Phase 1: Create `tests/benchmarks/` package with `__init__.py`, `conftest.py`, `test_benchmarks.py`
- [ ] Phase 1: Run benchmarks locally and record initial `benchmarks.json`
- [ ] Phase 2: Create `.github/workflows/benchmark.yml`
- [ ] Phase 2: Verify CI fails when a >20% regression is introduced
- [ ] Phase 3: Implement `tools/benchmark_trend.py`
- [ ] Phase 3: Enable auto-commit of `benchmarks.json` on main branch
- [ ] Document: Add PR template checkbox for performance impact
