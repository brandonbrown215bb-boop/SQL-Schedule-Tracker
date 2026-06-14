# tests/test_audit.py
"""Tests for the audit log system (Sprint 2: Data Integrity & Audit)."""
from __future__ import annotations

import sqlite3

import pytest

from data.db import _ensure_audit_log, get_audit_trail, log_field_changes
from data.models import Unit
from data.writer import save_unit


@pytest.fixture
def audit_db(db_path):
    """Database with units and audit log table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_audit_log(conn)
    conn.close()
    return db_path


class TestAuditLog:
    def test_audit_table_created(self, audit_db):
        """_audit_log table should exist after _ensure_audit_log."""
        conn = sqlite3.connect(audit_db)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "_audit_log" in tables

    def test_log_field_changes_records_changes(self, audit_db):
        """log_field_changes should record entries when values differ."""
        conn = sqlite3.connect(audit_db)
        conn.row_factory = sqlite3.Row
        # Create a fake old row
        old_row = conn.execute(
            "INSERT INTO units (com_number, detailer, percent_complete) VALUES (?, ?, ?)",
            ("TEST001", "Carl M", 0.50),
        ).fetchone()
        conn.commit()
        # Read back the row
        old_row = conn.execute(
            "SELECT * FROM units WHERE com_number = 'TEST001'"
        ).fetchone()

        new_values = {
            "detailer": "Brandon B",
            "percent_complete": 0.75,
        }

        changes = log_field_changes(conn, "TEST001", old_row, new_values)
        assert changes == 2

        # Check the audit log has entries
        entries = get_audit_trail(audit_db, com_number="TEST001")
        assert len(entries) == 2
        detailer_entry = next((e for e in entries if e["field_name"] == "detailer"), None)
        assert detailer_entry["old_value"] == "Carl M"
        assert detailer_entry["new_value"] == "Brandon B"

    def test_log_field_changes_no_changes(self, audit_db):
        """log_field_changes should return 0 when nothing changed."""
        conn = sqlite3.connect(audit_db)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO units (com_number, detailer) VALUES (?, ?)",
            ("TEST002", "Carl M"),
        )
        conn.commit()
        old_row = conn.execute(
            "SELECT * FROM units WHERE com_number = 'TEST002'"
        ).fetchone()

        new_values = {"detailer": "Carl M"}
        changes = log_field_changes(conn, "TEST002", old_row, new_values)
        assert changes == 0

    def test_log_field_changes_none_old_row(self, audit_db):
        """log_field_changes should return 0 when old_row is None."""
        conn = sqlite3.connect(audit_db)
        changes = log_field_changes(conn, "TEST003", None, {"detailer": "X"})
        assert changes == 0

    def test_save_unit_records_audit(self, audit_db):
        """save_unit should record audit entries when values change."""
        conn = sqlite3.connect(audit_db)
        conn.row_factory = sqlite3.Row
        # Insert a default row (simulating an existing unit)
        conn.execute(
            "INSERT INTO units (com_number, detailer, percent_complete) VALUES (?, ?, ?)",
            ("14201", "Carl M", 0.50),
        )
        conn.commit()
        conn.close()

        # Now save a unit with a changed detailer
        unit = Unit(
            com_number="14201",
            job_name="Test Job",
            contract_number="CN-001",
            description="",
            detailer="Brandon B",
            checking_status="",
            department_hours=40.0,
            percent_complete=50.0,
            actual_hours=20.0,
        )
        save_unit(audit_db, unit)

        # Check audit log for the detailer change
        entries = get_audit_trail(audit_db, com_number="14201")
        assert len(entries) >= 1
        detailer_entry = next((e for e in entries if e["field_name"] == "detailer"), None)
        assert detailer_entry is not None
        assert detailer_entry["new_value"] == "Brandon B"

    def test_get_audit_trail_filter_by_com(self, audit_db):
        """get_audit_trail should filter by com_number when provided."""
        conn = sqlite3.connect(audit_db)
        _ensure_audit_log(conn)
        conn.execute(
            "INSERT INTO _audit_log (com_number, field_name, old_value, new_value) VALUES (?, ?, ?, ?)",
            ("14201", "detailer", "Carl M", "Brandon B"),
        )
        conn.execute(
            "INSERT INTO _audit_log (com_number, field_name, old_value, new_value) VALUES (?, ?, ?, ?)",
            ("14202", "detailer", "Matt E", "Carl M"),
        )
        conn.commit()
        conn.close()

        entries = get_audit_trail(audit_db, com_number="14201")
        assert len(entries) == 1
        assert entries[0]["com_number"] == "14201"

    def test_get_audit_trail_limit(self, audit_db):
        """get_audit_trail should respect the limit parameter."""
        conn = sqlite3.connect(audit_db)
        _ensure_audit_log(conn)
        for i in range(5):
            conn.execute(
                "INSERT INTO _audit_log (com_number, field_name, old_value, new_value) VALUES (?, ?, ?, ?)",
                ("TEST", "field", f"old{i}", f"new{i}"),
            )
        conn.commit()
        conn.close()

        entries = get_audit_trail(audit_db, com_number="TEST", limit=3)
        assert len(entries) == 3

    def test_audit_index_created(self, audit_db):
        """Audit indexes should be created after _ensure_audit_log."""
        conn = sqlite3.connect(audit_db)
        idx_names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        conn.close()
        assert "idx_audit_com" in idx_names
        assert "idx_audit_saved_at" in idx_names

    def test_audit_idempotent(self, audit_db):
        """Calling _ensure_audit_log multiple times should not raise."""
        conn = sqlite3.connect(audit_db)
        _ensure_audit_log(conn)
        _ensure_audit_log(conn)
        # Should still work
        changes = log_field_changes(conn, "TEST", None, {})
        assert changes == 0
        conn.close()
