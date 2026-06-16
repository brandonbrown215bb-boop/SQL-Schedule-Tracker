# tests/test_migration_registry.py
"""Tests for SchemaMigrationRegistry (services.migration_registry)."""

import sqlite3

import pytest

from services.migration_registry import Migration, SchemaMigrationRegistry


@pytest.fixture
def db():
    """In-memory SQLite database."""
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def registry(db):
    return SchemaMigrationRegistry(db)


class TestSchemaMigrationRegistry:
    def test_initial_version_is_zero(self, registry):
        assert registry.current_version() == 0

    def test_apply_migration(self, registry, db):
        m = Migration(
            version=1,
            description="Create units table",
            up_sql="CREATE TABLE test (id INTEGER PRIMARY KEY)",
            down_sql="DROP TABLE test",
        )
        registry.apply(m)
        assert registry.current_version() == 1

    def test_applied_versions(self, registry):
        m = Migration(
            version=1,
            description="test",
            up_sql="CREATE TABLE t1 (id INTEGER PRIMARY KEY)",
        )
        registry.apply(m)
        assert 1 in registry.applied_versions()

    def test_pending_returns_unapplied(self, registry):
        migrations = [
            Migration(
                version=1, description="m1", up_sql="CREATE TABLE t1 (id INTEGER PRIMARY KEY)"
            ),
            Migration(
                version=2, description="m2", up_sql="CREATE TABLE t2 (id INTEGER PRIMARY KEY)"
            ),
        ]
        registry.apply(migrations[0])
        pending = registry.pending(migrations)
        assert len(pending) == 1
        assert pending[0].version == 2

    def test_pending_empty_when_all_applied(self, registry):
        migrations = [
            Migration(
                version=1, description="m1", up_sql="CREATE TABLE t1 (id INTEGER PRIMARY KEY)"
            ),
        ]
        registry.apply_all(migrations)
        assert registry.pending(migrations) == []

    def test_apply_all(self, registry):
        migrations = [
            Migration(
                version=1, description="m1", up_sql="CREATE TABLE t1 (id INTEGER PRIMARY KEY)"
            ),
            Migration(
                version=2, description="m2", up_sql="CREATE TABLE t2 (id INTEGER PRIMARY KEY)"
            ),
        ]
        applied = registry.apply_all(migrations)
        assert len(applied) == 2
        assert registry.current_version() == 2

    def test_rollback_with_down_sql(self, registry, db):
        m = Migration(
            version=1,
            description="test",
            up_sql="CREATE TABLE t1 (id INTEGER PRIMARY KEY)",
            down_sql="DROP TABLE t1",
        )
        registry.apply(m)
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='t1'").fetchone()
            is not None
        )
        registry.rollback(m)
        assert (
            db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='t1'").fetchone()
            is None
        )

    def test_rollback_without_down_sql_raises(self, registry):
        m = Migration(
            version=1,
            description="test",
            up_sql="CREATE TABLE t1 (id INTEGER PRIMARY KEY)",
        )
        registry.apply(m)
        with pytest.raises(RuntimeError, match="no rollback"):
            registry.rollback(m)

    def test_apply_failure_rolls_back(self, registry, db):
        m = Migration(
            version=1,
            description="bad migration",
            up_sql="CREATE TABLE t1 (id INTEGER PRIMARY KEY); INVALID SQL;",
        )
        with pytest.raises(RuntimeError, match="Migration v1 failed"):
            registry.apply(m)
        assert registry.current_version() == 0


class TestMigration:
    def test_checksum_computed(self):
        m = Migration(version=1, description="test", up_sql="SELECT 1")
        assert len(m.checksum) == 16

    def test_checksum_differs_for_different_sql(self):
        m1 = Migration(version=1, description="a", up_sql="SELECT 1")
        m2 = Migration(version=1, description="b", up_sql="SELECT 2")
        assert m1.checksum != m2.checksum

    def test_checksum_includes_down_sql(self):
        m1 = Migration(version=1, description="a", up_sql="SELECT 1", down_sql="DROP")
        m2 = Migration(version=1, description="b", up_sql="SELECT 1")
        assert m1.checksum != m2.checksum
