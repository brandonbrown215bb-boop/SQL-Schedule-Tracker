# tests/test_cleanup_detailers.py
"""Workbook detailer names map to the right canonical detailer.

The old workbook wrote "Matt" for Matt E and "Matthew" for Matthew S.
"""

import sqlite3

import pytest

from automation.cleanup_detailers import build_canonical, parse_detailer_field
from automation.create_db import create_database
from data.db import close_db, get_db
from services.config_service import ConfigService

DETAILERS = ["Jackie H", "Matthew S", "Matt E", "Brandon B", "Tracy V"]


@pytest.fixture
def canonical():
    return build_canonical(DETAILERS)


@pytest.mark.parametrize(
    "raw, detailer, notes",
    [
        ("Matt", "Matt E", ""),
        ("Matt / IEC internals complete", "Matt E", "IEC internals complete"),
        ("Matt Training Unit / IEC Internals New 34 complete", "Matt E", "IEC Internals New 34 complete"),
        ("Matthew E.", "Matt E", ""),
        ("Matthew E/IEC internals complete", "Matt E", "IEC internals complete"),
        ("Matthew Erp/Mahantesh internals complete", "Matt E", "Mahantesh internals complete"),
        ("Matthew", "Matthew S", ""),
        ("Matthew / IEC internals complete", "Matthew S", "IEC internals complete"),
        ("Matthew S./IEC internals complete", "Matthew S", "IEC internals complete"),
        ("Brandon", "Brandon B", ""),
    ],
)
def test_workbook_names(canonical, raw, detailer, notes):
    assert parse_detailer_field(raw, canonical) == (detailer, notes)


def test_shared_first_name_is_never_guessed():
    # Without an alias, a first name two detailers share picks neither.
    canonical = build_canonical(["Ryan W", "Ryan M"])
    assert "ryan" not in canonical
    assert parse_detailer_field("Ryan", canonical) == ("Ryan", "")


def test_old_config_names_are_renamed():
    config = {
        "default_detailers": ["Matthew S", "Matthew E", "Matt E"],
        "detailer_schedules": {"Matthew E": [0, 1, 2, 3]},
    }
    ConfigService.apply_detailer_renames(config)
    assert config["default_detailers"] == ["Matthew S", "Matt E"]
    assert config["detailer_schedules"] == {"Matt E": [0, 1, 2, 3]}


def test_db_migration_renames_detailer(tmp_path):
    path = str(tmp_path / "rename.db")
    create_database(path)
    conn = sqlite3.connect(path)
    conn.execute("UPDATE detailers SET name = 'Matthew E' WHERE name = 'Matt E'")
    conn.execute("INSERT INTO units (com_number, detailer) VALUES ('1', 'Matthew E')")
    conn.commit()
    conn.close()
    try:
        conn = get_db(path)
        assert conn.execute("SELECT detailer FROM units").fetchone()[0] == "Matt E"
        names = {r[0] for r in conn.execute("SELECT name FROM detailers")}
        assert "Matt E" in names and "Matthew E" not in names
    finally:
        close_db()
