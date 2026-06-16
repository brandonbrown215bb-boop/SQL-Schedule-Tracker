# services/migration_registry.py
"""SchemaMigrationRegistry — versioned, ordered, rollback-capable migrations.

Storage: SQLite table `_schema_migrations`:
    version INTEGER PRIMARY KEY,
    description TEXT,
    checksum TEXT,
    applied_at TEXT,
    duration_ms INTEGER
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    """A single schema migration."""

    version: int
    description: str
    up_sql: str
    down_sql: str | None = None  # rollback script
    checksum: str = field(init=False)
    custom_rollback: Callable[[sqlite3.Connection], None] | None = None

    def __post_init__(self):
        self.checksum = hashlib.sha256((self.up_sql + (self.down_sql or "")).encode()).hexdigest()[
            :16
        ]


class SchemaMigrationRegistry:
    """Versioned, ordered, rollback-capable schema migrations.

    Usage:
        registry = SchemaMigrationRegistry(conn)
        pending = registry.pending(MIGRATIONS)
        for m in pending:
            registry.apply(m)

    Args:
        conn: SQLite database connection.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._ensure_migrations_table()

    def _ensure_migrations_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS _schema_migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now')),
                duration_ms INTEGER
            )
        """)
        self._conn.commit()

    def current_version(self) -> int:
        """Return the highest applied migration version, or 0."""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM _schema_migrations"
        ).fetchone()
        return row[0] if row else 0

    def applied_versions(self) -> set[int]:
        """Return the set of applied migration versions."""
        return {
            r[0] for r in self._conn.execute("SELECT version FROM _schema_migrations").fetchall()
        }

    def pending(self, migrations: list[Migration]) -> list[Migration]:
        """Return migrations that have not yet been applied, in version order."""
        applied = self.applied_versions()
        return sorted(
            (m for m in migrations if m.version not in applied),
            key=lambda m: m.version,
        )

    def apply(self, migration: Migration) -> None:
        """Apply a single migration.

        Args:
            migration: The migration to apply.

        Raises:
            RuntimeError: If the migration fails (rolled back).
        """
        t0 = time.perf_counter()
        try:
            self._conn.executescript(migration.up_sql)
            elapsed = int((time.perf_counter() - t0) * 1000)
            self._conn.execute(
                "INSERT INTO _schema_migrations "
                "(version, description, checksum, applied_at, duration_ms) "
                "VALUES (?, ?, ?, datetime('now'), ?)",
                (migration.version, migration.description, migration.checksum, elapsed),
            )
            self._conn.commit()
            logger.info(
                "Applied migration v%d (%s) in %dms",
                migration.version,
                migration.description,
                elapsed,
            )
        except Exception as e:
            self._conn.rollback()
            raise RuntimeError(f"Migration v{migration.version} failed: {e}") from e

    def rollback(self, migration: Migration) -> None:
        """Roll back a single migration.

        Args:
            migration: The migration to roll back. Must have down_sql or custom_rollback.

        Raises:
            RuntimeError: If the migration has no rollback.
        """
        if migration.custom_rollback:
            migration.custom_rollback(self._conn)
        elif migration.down_sql:
            self._conn.executescript(migration.down_sql)
        else:
            raise RuntimeError(f"Migration v{migration.version} has no rollback script")
        self._conn.execute(
            "DELETE FROM _schema_migrations WHERE version = ?",
            (migration.version,),
        )
        self._conn.commit()
        logger.info("Rolled back migration v%d (%s)", migration.version, migration.description)

    def apply_all(self, migrations: list[Migration]) -> list[Migration]:
        """Apply all pending migrations in order.

        Returns:
            List of migrations that were applied.
        """
        applied: list[Migration] = []
        for m in self.pending(migrations):
            self.apply(m)
            applied.append(m)
        return applied
