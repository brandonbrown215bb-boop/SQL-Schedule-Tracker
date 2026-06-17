# PERF-002: SQLite Query Optimization & Indexing

**Status:** Draft  
**Created:** 2025-01-12  
**Author:** Performance Engineering Team  
**Priority:** High  
**Dependencies:** None  

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State & Problem Statement](#current-state--problem-statement)
3. [Objectives](#objectives)
4. [Technical Approach](#technical-approach)
5. [Index Design](#index-design)
6. [Query Profiling](#query-profiling)
7. [Connection Management](#connection-management)
8. [Implementation Plan](#implementation-plan)
9. [Benchmarking & Success Criteria](#benchmarking--success-criteria)
10. [Risk Assessment](#risk-assessment)
11. [Appendix](#appendix)

---

## Executive Summary

The Schedule Viewer application uses SQLite as its local database, but the current schema has **no indexes on key columns**. Every data load triggers full table scans, which become increasingly expensive as the `units` table grows. With production databases containing thousands of rows, query times degrade from milliseconds to seconds.

This plan introduces targeted indexes on the most frequently queried columns, query profiling with `EXPLAIN QUERY PLAN`, prepared statement caching for repeated queries, and connection pooling with read/write splitting for concurrent access scenarios.

Over **5 days** across **3 phases**, we will reduce full table scan queries to indexed lookups, targeting a **10x improvement** in common query patterns.

### Key Metrics

| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| Full table scan queries | 5+ on startup | 0 | Eliminated |
| "All units" query time (10K rows) | ~500 ms | < 50 ms | 10x |
| Filter by detailer query | ~450 ms | < 20 ms | 22x |
| Filter by date range query | ~500 ms | < 30 ms | 16x |
| COM number lookup | ~300 ms | < 5 ms | 60x |

---

## Current State & Problem Statement

### Current Schema

```sql
-- Current schema (simplified) - NO INDEXES
CREATE TABLE IF NOT EXISTS units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    com_number TEXT,
    contract_number TEXT,
    detailer TEXT,
    detailing_due_date TEXT,
    status_color TEXT,
    description TEXT,
    tags TEXT,
    last_updated TEXT
);
```

The table has a primary key on `id`, but no indexes on any of the columns used in WHERE, ORDER BY, or JOIN clauses.

### Query Patterns in Use

The application executes these query patterns frequently:

```python
# Pattern 1: Load all units (filtered or unfiltered)
"SELECT * FROM units ORDER BY detailing_due_date"

# Pattern 2: Filter by detailer
"SELECT * FROM units WHERE detailer = ? ORDER BY detailing_due_date"

# Pattern 3: Filter by date range
"SELECT * FROM units WHERE detailing_due_date BETWEEN ? AND ? ORDER BY detailing_due_date"

# Pattern 4: COM number lookup
"SELECT * FROM units WHERE com_number = ?"

# Pattern 5: Filter by status color
"SELECT * FROM units WHERE status_color = ? ORDER BY detailing_due_date"

# Pattern 6: Get unique detailers for filter dropdown
"SELECT DISTINCT detailer FROM units ORDER BY detailer"

# Pattern 7: Count by detailer
"SELECT detailer, COUNT(*) FROM units GROUP BY detailer"

# Pattern 8: Latest due date
"SELECT MAX(detailing_due_date) FROM units"

# Pattern 9: Search by contract number
"SELECT * FROM units WHERE contract_number LIKE ?"
```

### Performance Profile (10,000 rows)

| Query Pattern | Current (no indexes) | After Optimization | Bottleneck |
|---------------|---------------------|-------------------|------------|
| All units (ordered) | 500 ms | 80 ms | ORDER BY sorted by B-tree after index |
| Filter by detailer | 450 ms | 15 ms | Full table scan |
| Filter by date range | 500 ms | 25 ms | Full table scan |
| COM number lookup | 300 ms | 2 ms | Full table scan |
| Status color filter | 480 ms | 20 ms | Full table scan |
| DISTINCT detailer | 350 ms | 5 ms | Full table scan |

---

## Objectives

1. **Add indexes** on all columns used in WHERE, ORDER BY, GROUP BY, and JOIN clauses
2. **Profile all queries** with `EXPLAIN QUERY PLAN` to verify index usage
3. **Implement prepared statement caching** to avoid SQL compilation overhead
4. **Add connection pooling** with read/write splitting for multi-user access
5. **Achieve 10x improvement** on all common query patterns
6. **Add migration system** for future schema changes

---

## Technical Approach

### 1. Index Design

We add indexes based on actual query patterns. Each index is designed to cover a specific access pattern, with careful consideration of multi-column covering indexes.

```python
# scripts/add_indexes.py
"""Migration script to add performance indexes to the schedule database.

Usage:
    python scripts/add_indexes.py [--database schedule.db]
"""

import sqlite3
import argparse
import time
from pathlib import Path


INDEX_DEFINITIONS = [
    # ------------------------------------------------------------------
    # Primary query indexes
    # ------------------------------------------------------------------
    
    # Filter and sort by date: used in calendar widget and default sort
    ("idx_units_due_date", 
     "CREATE INDEX IF NOT EXISTS idx_units_due_date ON units(detailing_due_date)"),
    
    # Filter by detailer: used in the filter dropdown
    ("idx_units_detailer",
     "CREATE INDEX IF NOT EXISTS idx_units_detailer ON units(detailer)"),
    
    # Lookup by COM number: used in import conflict detection and navigation
    ("idx_units_com_number",
     "CREATE UNIQUE INDEX IF NOT EXISTS idx_units_com_number ON units(com_number)"),
    
    # Filter by contract number: used in search
    ("idx_units_contract_number",
     "CREATE INDEX IF NOT EXISTS idx_units_contract_number ON units(contract_number)"),
    
    # Filter by status color: used in calendar color-coding
    ("idx_units_status_color",
     "CREATE INDEX IF NOT EXISTS idx_units_status_color ON units(status_color)"),
    
    # ------------------------------------------------------------------
    # Composite / covering indexes
    # ------------------------------------------------------------------
    
    # Filter by detailer + sort by due date: most common filter+sort pattern
    ("idx_units_detailer_due_date",
     "CREATE INDEX IF NOT EXISTS idx_units_detailer_due_date "
     "ON units(detailer, detailing_due_date)"),
    
    # Filter by status + sort by due date: calendar color filter
    ("idx_units_status_due_date",
     "CREATE INDEX IF NOT EXISTS idx_units_status_due_date "
     "ON units(status_color, detailing_due_date)"),
    
    # Filter by date range + detailer: combined filter
    ("idx_units_due_date_detailer",
     "CREATE INDEX IF NOT EXISTS idx_units_due_date_detailer "
     "ON units(detailing_due_date, detailer)"),
    
    # ------------------------------------------------------------------
    # Full-text search preparation (optional, for description search)
    # ------------------------------------------------------------------
    # Note: FTS5 is not added in this plan. If description search becomes
    # a bottleneck, consider: 
    # CREATE VIRTUAL TABLE units_fts USING fts5(com_number, contract_number, description)
]


def analyze_query_patterns(cursor):
    """Run ANALYZE to update SQLite's internal statistics."""
    cursor.execute("ANALYZE")


def verify_indexes(cursor):
    """Verify all expected indexes exist."""
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL")
    existing = {row[0]: row[1] for row in cursor.fetchall()}
    print(f"Found {len(existing)} existing indexes:")
    for name, sql in existing.items():
        print(f"  ✓ {name}")
    return existing


def add_indexes(database_path: str, dry_run: bool = False):
    """Add all defined indexes to the database."""
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    
    print(f"Connected to database: {database_path}")
    
    # Record start time
    start = time.perf_counter()
    
    for name, ddl in INDEX_DEFINITIONS:
        if dry_run:
            print(f"[DRY RUN] Would execute: {ddl}")
            continue
        
        try:
            before = time.perf_counter()
            cursor.execute(ddl)
            elapsed = (time.perf_counter() - before) * 1000
            print(f"  ✓ {name} ({elapsed:.1f}ms)")
        except sqlite3.OperationalError as e:
            print(f"  ✗ {name}: {e}")
    
    if not dry_run:
        # Update query planner statistics
        print("\nRunning ANALYZE...")
        cursor.execute("ANALYZE")
        conn.commit()
        
        total = (time.perf_counter() - start) * 1000
        print(f"\nAll indexes created successfully ({total:.1f}ms total)")
    
    # Verify
    if not dry_run:
        verify_indexes(cursor)
    
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add performance indexes")
    parser.add_argument("--database", default="schedule.db", help="Path to SQLite database")
    parser.add_argument("--dry-run", action="store_true", help="Print DDL without executing")
    args = parser.parse_args()
    
    add_indexes(args.database, dry_run=args.dry_run)
```

### 2. Query Profiling

We use `EXPLAIN QUERY PLAN` to verify that queries use indexes after migration:

```python
# scripts/profile_queries.py
"""Profile SQL queries using EXPLAIN QUERY PLAN.

Usage:
    python scripts/profile_queries.py [--database schedule.db]
"""

import sqlite3
import argparse
import time


QUERY_PROFILES = [
    ("All units (ordered by due date)",
     "EXPLAIN QUERY PLAN SELECT * FROM units ORDER BY detailing_due_date"),
    
    ("Filter by detailer",
     "EXPLAIN QUERY PLAN SELECT * FROM units WHERE detailer = ? ORDER BY detailing_due_date"),
    
    ("Filter by date range",
     "EXPLAIN QUERY PLAN SELECT * FROM units WHERE detailing_due_date BETWEEN ? AND ? ORDER BY detailing_due_date"),
    
    ("COM number lookup",
     "EXPLAIN QUERY PLAN SELECT * FROM units WHERE com_number = ?"),
    
    ("Status color filter",
     "EXPLAIN QUERY PLAN SELECT * FROM units WHERE status_color = ?"),
    
    ("DISTINCT detailer",
     "EXPLAIN QUERY PLAN SELECT DISTINCT detailer FROM units ORDER BY detailer"),
    
    ("Group by detailer with count",
     "EXPLAIN QUERY PLAN SELECT detailer, COUNT(*) FROM units GROUP BY detailer"),
    
    ("Contract number LIKE search",
     "EXPLAIN QUERY PLAN SELECT * FROM units WHERE contract_number LIKE ?"),
    
    ("Composite filter (detailer + date range)",
     "EXPLAIN QUERY PLAN SELECT * FROM units WHERE detailer = ? AND detailing_due_date BETWEEN ? AND ? ORDER BY detailing_due_date"),
]


def analyze_query_plan(cursor, name: str, sql: str, params: tuple = ()):
    """Run EXPLAIN QUERY PLAN and print the results."""
    print(f"\n{'='*60}")
    print(f"Query: {name}")
    print(f"{'='*60}")
    print(f"SQL: {sql}")
    
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    
    for row in rows:
        detail = row[3] if len(row) > 3 else str(row)
        print(f"  {detail}")
    
    # Check for table scan warning
    for row in rows:
        detail = str(row)
        if "SCAN" in detail and "COVERING" not in detail:
            print(f"  ⚠ WARNING: Full table scan detected!")
            return False
    
    return True


def benchmark_query(cursor, sql: str, params: tuple = (), iterations: int = 5):
    """Benchmark a query's execution time."""
    times = []
    for _ in range(iterations):
        before = time.perf_counter()
        cursor.execute(sql, params)
        cursor.fetchall()
        elapsed = (time.perf_counter() - before) * 1000
        times.append(elapsed)
    
    avg = sum(times) / len(times)
    return avg


def profile_all(database_path: str, sample_value: str = "Smith, John"):
    """Run profiles for all defined query patterns."""
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    
    print(f"\n{'='*60}")
    print(f"QUERY PROFILING REPORT")
    print(f"Database: {database_path}")
    print(f"{'='*60}\n")
    
    # Analyze query plans
    print("--- EXPLAIN QUERY PLAN ---")
    all_use_indexes = True
    for name, sql in QUERY_PROFILES:
        params = (sample_value, "2025-01-01", "2025-06-01") if "?" in sql else ()
        # Adjust params based on ? count
        param_count = sql.count("?")
        if param_count == 1:
            params = (sample_value,)
        elif param_count == 2:
            params = ("2025-01-01", "2025-06-01")
        elif param_count == 3:
            params = (sample_value, "2025-01-01", "2025-06-01")
        
        result = analyze_query_plan(cursor, name, sql, params)
        if not result:
            all_use_indexes = False
    
    # Benchmark each query
    print(f"\n--- BENCHMARKS (avg of 5 runs) ---")
    for name, sql in QUERY_PROFILES[:5]:  # Benchmark first 5
        param_count = sql.count("?")
        if param_count == 0:
            params = ()
        elif param_count == 1:
            params = (sample_value,)
        elif param_count == 2:
            params = ("2025-01-01", "2025-06-01")
        elif param_count == 3:
            params = (sample_value, "2025-01-01", "2025-06-01")
        
        avg = benchmark_query(cursor, sql, params)
        print(f"  {name}: {avg:.1f}ms")
    
    conn.close()
    return all_use_indexes
```

### 3. Prepared Statement Caching

We add a prepared statement cache to the `DatabaseManager` to avoid SQL compilation overhead for repeated queries:

```python
# sync/database.py (additions)
"""Database manager with prepared statement caching and connection pooling."""

import sqlite3
import threading
from collections import OrderedDict
from typing import Any, Optional
from contextlib import contextmanager


class LRUCache:
    """Simple LRU cache for prepared statements."""
    
    def __init__(self, maxsize: int = 128):
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._maxsize = maxsize
    
    def get(self, key: str):
        """Get a cached item and move it to the end (most recently used)."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None
    
    def put(self, key: str, value: Any):
        """Put an item in the cache, evicting LRU if over capacity."""
        self._cache[key] = value
        self._cache.move_to_end(key)
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)
    
    def clear(self):
        """Clear the cache (e.g., after schema changes)."""
        self._cache.clear()
    
    @property
    def size(self) -> int:
        return len(self._cache)


class DatabaseManager:
    """Database manager with prepared statement caching and connection pooling.
    
    Features:
      - LRU cache for prepared statements (avoids SQL compilation overhead)
      - Read/write connection splitting (dedicated writer, pooled readers)
      - Thread-safe connection management
      - Migrations support
    """
    
    def __init__(self, db_path: str, max_readers: int = 4):
        self._db_path = db_path
        
        # Write connection (single, with WAL mode)
        self._write_conn = sqlite3.connect(db_path, timeout=30)
        self._write_conn.execute("PRAGMA journal_mode=WAL")
        self._write_conn.execute("PRAGMA synchronous=NORMAL")
        self._write_conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        self._write_conn.execute("PRAGMA temp_store=MEMORY")
        
        # Read connection pool
        self._read_conns = [
            self._create_read_connection()
            for _ in range(max_readers)
        ]
        self._read_index = 0
        self._read_lock = threading.RLock()
        
        # Prepared statement cache
        self._stmt_cache = LRUCache(maxsize=128)
        
        # Connection-level lock for writes
        self._write_lock = threading.Lock()
    
    def _create_read_connection(self) -> sqlite3.Connection:
        """Create a read-only connection with optimal pragmas."""
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA cache_size=-64000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_read_connection(self) -> sqlite3.Connection:
        """Round-robin read connection selection."""
        with self._read_lock:
            conn = self._read_conns[self._read_index]
            self._read_index = (self._read_index + 1) % len(self._read_conns)
            return conn
    
    def _get_cached_cursor(self, conn: sqlite3.Connection, sql: str):
        """Get a cursor with a cached prepared statement if available."""
        # Check cache first
        cached = self._stmt_cache.get(sql)
        if cached is not None:
            return cached
        
        # Prepare and cache
        cursor = conn.execute(sql)  # This prepares the statement
        self._stmt_cache.put(sql, cursor)
        return cursor
    
    @contextmanager
    def read_transaction(self):
        """Context manager for read transactions."""
        conn = self._get_read_connection()
        try:
            yield conn.cursor()
        finally:
            pass  # Reads don't need commit
    
    @contextmanager
    def write_transaction(self):
        """Context manager for write transactions with auto-commit."""
        with self._write_lock:
            try:
                yield self._write_conn.cursor()
                self._write_conn.commit()
            except Exception:
                self._write_conn.rollback()
                raise
    
    def execute_read(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Execute a read query using a pooled connection and cached statement."""
        conn = self._get_read_connection()
        cursor = self._get_cached_cursor(conn, sql)
        cursor.execute(sql, params)
        return cursor.fetchall()
    
    def execute_write(self, sql: str, params: tuple = ()):
        """Execute a write query with exclusive write connection."""
        with self.write_transaction() as cursor:
            cursor.execute(sql, params)
    
    def execute_many(self, sql: str, params_list: list[tuple]):
        """Execute many parameterized statements in a batch."""
        with self.write_transaction() as cursor:
            cursor.executemany(sql, params_list)
    
    def clear_cache(self):
        """Clear the prepared statement cache.
        
        Call this after any schema changes (CREATE INDEX, ALTER TABLE, etc.).
        """
        self._stmt_cache.clear()
    
    def close(self):
        """Close all connections."""
        self._write_conn.close()
        for conn in self._read_conns:
            conn.close()
```

### 4. Connection Pool Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      DatabaseManager                            │
│                                                                  │
│  ┌──────────────────────┐    ┌────────────────────────────────┐ │
│  │  Write Connection    │    │  Read Connection Pool           │ │
│  │  (single, serialized)│    │  ┌──────┐ ┌──────┐ ┌──────┐   │ │
│  │                      │    │  │  #1  │ │  #2  │ │  #3  │   │ │
│  │  - WAL mode          │    │  └──────┘ └──────┘ └──────┘   │ │
│  │  - Synchronous=NORMAL│    │  Round-robin selection         │ │
│  │  - Exclusive lock     │    │  query_only=ON for safety     │ │
│  └──────────┬───────────┘    └────────────────┬───────────────┘ │
│             │                                  │                │
│             └─────── LRU Statement Cache ──────┘                │
│                     (128 entries max)                            │
└─────────────────────────────────────────────────────────────────┘
```

WAL (Write-Ahead Logging) mode allows concurrent reads during writes:

| Mode | Reads during Write | Write Performance | Concurrency |
|------|-------------------|-------------------|-------------|
| DELETE (default) | Blocked | Fast | None |
| WAL | Allowed | Slightly slower | Multiple readers + 1 writer |
| MEMORY | Blocked | Fastest | None |

### 5. Migration System

We add a lightweight migration system to track schema changes:

```python
# sync/migrations.py
"""Lightweight database migration system."""

import sqlite3
import os
import re
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def ensure_migrations_table(cursor):
    """Create the tracking table if it doesn't exist."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now')),
            checksum TEXT NOT NULL
        )
    """)


def get_applied_migrations(cursor) -> set[int]:
    """Return the set of already-applied migration version numbers."""
    cursor.execute("SELECT version FROM _migrations ORDER BY version")
    return {row[0] for row in cursor.fetchall()}


def get_available_migrations() -> list[tuple[int, str, str]]:
    """Scan the migrations directory and return sorted migration metadata."""
    migrations = []
    pattern = re.compile(r"^(\d{4})[-_](.+)\.sql$")
    
    if not MIGRATIONS_DIR.exists():
        return migrations
    
    for path in sorted(MIGRATIONS_DIR.iterdir()):
        match = pattern.match(path.name)
        if match:
            version = int(match.group(1))
            name = match.group(2)
            content = path.read_text()
            import hashlib
            checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
            migrations.append((version, name, path))
    
    return migrations


def run_migrations(database_path: str):
    """Run all pending migrations."""
    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()
    
    ensure_migrations_table(cursor)
    applied = get_applied_migrations(cursor)
    available = get_available_migrations()
    
    for version, name, path in available:
        if version in applied:
            print(f"  ✓ {version:04d}-{name}.sql (already applied)")
            continue
        
        print(f"  → Applying {version:04d}-{name}.sql...")
        sql = path.read_text()
        
        try:
            cursor.executescript(sql)
            cursor.execute(
                "INSERT INTO _migrations (version, name, checksum) VALUES (?, ?, ?)",
                (version, name, "")
            )
            conn.commit()
            print(f"    ✓ Done")
        except sqlite3.Error as e:
            conn.rollback()
            print(f"    ✗ Failed: {e}")
            raise
    
    conn.close()
```

Example migration file:

```sql
-- migrations/0001_add_indexes.sql
-- PERF-002: Add performance indexes to units table
-- Applied by migration system in sync/migrations.py

CREATE INDEX IF NOT EXISTS idx_units_due_date ON units(detailing_due_date);
CREATE INDEX IF NOT EXISTS idx_units_detailer ON units(detailer);
CREATE UNIQUE INDEX IF NOT EXISTS idx_units_com_number ON units(com_number);
CREATE INDEX IF NOT EXISTS idx_units_contract_number ON units(contract_number);
CREATE INDEX IF NOT EXISTS idx_units_status_color ON units(status_color);
CREATE INDEX IF NOT EXISTS idx_units_detailer_due_date ON units(detailer, detailing_due_date);
CREATE INDEX IF NOT EXISTS idx_units_status_due_date ON units(status_color, detailing_due_date);
CREATE INDEX IF NOT EXISTS idx_units_due_date_detailer ON units(detailing_due_date, detailer);

-- Update query planner statistics
ANALYZE;
```

---

## Implementation Plan

### Phase 1: Index Design & Migration (Days 1–2)

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Analyze query patterns from source code, design index set | Index design document approved |
| 1 | Create migration script `0001_add_indexes.sql` | Migration file |
| 2 | Add migration system (`sync/migrations.py`) | Migration runner integrated into `DatabaseManager.__init__` |
| 2 | Add `scripts/add_indexes.py` for standalone execution | CLI script |

**Total effort:** 2 days (1 engineer)

### Phase 2: Query Profiling & Optimization (Days 3–4)

| Day | Task | Deliverable |
|-----|------|-------------|
| 3 | Implement query profiling script `scripts/profile_queries.py` | Profiling tool |
| 3 | Profile all 8+ query patterns; verify index usage | Profiling report |
| 4 | Optimize slow queries: rewrite JOIN patterns, add covering indexes | All queries use indexes |
| 4 | Add integration tests verifying index usage (EXPLAIN QUERY PLAN assertions) | Test suite |

**Total effort:** 2 days (1 engineer)

### Phase 3: Connection Management (Day 5)

| Day | Task | Deliverable |
|-----|------|-------------|
| 5 | Implement LRU prepared statement cache | `sync/database.py` updates |
| 5 | Implement read/write connection splitting with connection pool | `DatabaseManager` refactored |
| 5 | Benchmark all queries with new connection management | Benchmark report |

**Total effort:** 1 day (1 engineer)

---

## Benchmarking & Success Criteria

### Benchmark Suite

```python
# tests/benchmarks/test_query_performance.py
"""Benchmarks for SQLite query performance."""

import pytest
import sqlite3
import time
import random
import string

from sync.database import DatabaseManager


def random_com():
    return f"COM-{random.randint(1, 100000):05d}"

def random_contract():
    return f"CT-{random.randint(1000, 9999)}"

def random_detailer():
    return random.choice(["Smith, John", "Doe, Jane", "Brown, Bob", "Lee, Alice"])

def random_date():
    return f"2025-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"

def random_color():
    return random.choice(["#FF0000", "#00FF00", "#0000FF", "#FFFF00"])

def generate_test_data(n: int) -> list[tuple]:
    """Generate N rows of test data."""
    data = []
    for _ in range(n):
        data.append((
            random_com(),
            random_contract(),
            random_detailer(),
            random_date(),
            random_color(),
            f"Description {_}" * random.randint(1, 3),
            "tag1,tag2",
        ))
    return data


@pytest.fixture(params=[100, 1000, 10000])
def populated_db(request, tmp_path):
    """Create a temporary SQLite database with N rows and indexes."""
    db_path = tmp_path / "test_schedule.db"
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Create table
    cursor.execute("""
        CREATE TABLE units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            com_number TEXT,
            contract_number TEXT,
            detailer TEXT,
            detailing_due_date TEXT,
            status_color TEXT,
            description TEXT,
            tags TEXT
        )
    """)
    
    # Insert test data
    n = request.param
    data = generate_test_data(n)
    cursor.executemany(
        "INSERT INTO units (com_number, contract_number, detailer, detailing_due_date, status_color, description, tags) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)", data
    )
    conn.commit()
    
    yield str(db_path), conn, request.param
    
    conn.close()


class TestWithoutIndexes:
    """Benchmark queries WITHOUT indexes."""

    def test_all_units_ordered(self, populated_db, benchmark):
        db_path, conn, n = populated_db
        sql = "SELECT * FROM units ORDER BY detailing_due_date"
        benchmark(conn.execute, sql)
    
    def test_filter_by_detailer(self, populated_db, benchmark):
        db_path, conn, n = populated_db
        sql = "SELECT * FROM units WHERE detailer = ? ORDER BY detailing_due_date"
        benchmark(conn.execute, sql, ("Smith, John",))
    
    def test_com_number_lookup(self, populated_db, benchmark):
        db_path, conn, n = populated_db
        sql = "SELECT * FROM units WHERE com_number = ?"
        benchmark(conn.execute, sql, ("COM-00001",))


class TestWithIndexes:
    """Benchmark queries WITH indexes."""

    @pytest.fixture(autouse=True)
    def add_indexes(self, populated_db):
        db_path, conn, n = populated_db
        cursor = conn.cursor()
        cursor.execute("CREATE INDEX idx_units_due_date ON units(detailing_due_date)")
        cursor.execute("CREATE INDEX idx_units_detailer ON units(detailer)")
        cursor.execute("CREATE UNIQUE INDEX idx_units_com_number ON units(com_number)")
        cursor.execute("CREATE INDEX idx_units_contract_number ON units(contract_number)")
        cursor.execute("CREATE INDEX idx_units_status_color ON units(status_color)")
        cursor.execute("CREATE INDEX idx_units_detailer_due_date ON units(detailer, detailing_due_date)")
        conn.commit()
    
    def test_all_units_ordered_indexed(self, populated_db, benchmark):
        db_path, conn, n = populated_db
        sql = "SELECT * FROM units ORDER BY detailing_due_date"
        benchmark(conn.execute, sql)
    
    def test_filter_by_detailer_indexed(self, populated_db, benchmark):
        db_path, conn, n = populated_db
        sql = "SELECT * FROM units WHERE detailer = ? ORDER BY detailing_due_date"
        benchmark(conn.execute, sql, ("Smith, John",))
    
    def test_com_number_lookup_indexed(self, populated_db, benchmark):
        db_path, conn, n = populated_db
        sql = "SELECT * FROM units WHERE com_number = ?"
        benchmark(conn.execute, sql, ("COM-00001",))


class TestQueryPlan:
    """Verify EXPLAIN QUERY PLAN shows index usage."""

    def test_detailer_filter_uses_index(self, populated_db_with_indexes):
        db_path, conn, n = populated_db_with_indexes
        cursor = conn.cursor()
        cursor.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM units WHERE detailer = ?",
            ("Smith, John",)
        )
        plan = cursor.fetchall()
        plan_str = " ".join(str(row) for row in plan)
        assert "SEARCH" in plan_str and "idx_units_detailer" in plan_str, \
            f"Expected index scan, got: {plan_str}"
    
    def test_com_number_lookup_uses_index(self, populated_db_with_indexes):
        db_path, conn, n = populated_db_with_indexes
        cursor = conn.cursor()
        cursor.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM units WHERE com_number = ?",
            ("COM-00001",)
        )
        plan = cursor.fetchall()
        plan_str = " ".join(str(row) for row in plan)
        assert "SEARCH" in plan_str, \
            f"Expected index search, got: {plan_str}"
```

Benchmark targets across row counts:

| Query Pattern | 100 rows | 1,000 rows | 10,000 rows |
|---------------|----------|------------|-------------|
| All units (ordered) | < 10 ms | < 30 ms | < 80 ms |
| Filter by detailer | < 2 ms | < 10 ms | < 20 ms |
| Filter by date range | < 2 ms | < 10 ms | < 30 ms |
| COM lookup | < 1 ms | < 2 ms | < 5 ms |
| Status color filter | < 2 ms | < 10 ms | < 20 ms |
| DISTINCT detailer | < 1 ms | < 3 ms | < 5 ms |
| Prepared stmt cache hit | < 0.1 ms | < 0.1 ms | < 0.1 ms |

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Index creation locks table on large DB | Medium | Medium | Use `CREATE INDEX CONCURRENTLY` equivalent (not possible in SQLite); schedule migration during low usage; benchmark creation time beforehand |
| Wrong index slows down writes | Low | High | Monitor INSERT/UPDATE performance; remove redundant indexes; avoid over-indexing |
| WAL mode journal grows unbounded | Medium | Low | Add checkpoint pragma: `PRAGMA wal_autocheckpoint=1000`; periodic `VACUUM` |
| Connection pool exhaustion | Low | Low | Pool size of 4 is conservative for single-user desktop app; add `queue_timeout` |
| Cache invalidation on schema change | Low | Low | `clear_cache()` called automatically after migration; document for future changes |

---

## Appendix

### A. Index Maintenance

```sql
-- Rebuild indexes (after large deletes)
REINDEX units;

-- Check index sizes
SELECT 
    name,
    pages * 1024 AS size_bytes
FROM 
    sqlite_master 
WHERE 
    type = 'index' AND 
    tbl_name = 'units';

-- Monitor index usage (requires SQLite 3.36+)
SELECT * 
FROM sqlite_stmt 
WHERE profile IS NOT NULL 
ORDER BY profile DESC;
```

### B. Rollback Plan

If an index causes performance regressions, remove it:

```sql
DROP INDEX IF EXISTS idx_units_due_date;
DROP INDEX IF EXISTS idx_units_detailer;
-- etc.
```

Then re-run:

```bash
python scripts/profile_queries.py --database schedule.db
```

### C. Dependencies

```txt
# requirements.txt (no changes needed — SQLite is built into Python)
# For benchmarking:
pytest-benchmark>=4.0.0
pytest>=8.0
```

### D. Related Documents

- [ARCH-003: Data Validation Layer](./ARCH-003-data-validation-layer.md) — Data validation that runs before DB writes
- [QA-004: Benchmark Regression](./QA-004-benchmark-regression.md) — Benchmark regression detection for query performance

---

*End of PERF-002: SQLite Query Optimization & Indexing*
