# tests/test_checker.py
"""Checker field: dropdowns, save + audit, and the reporting feed column."""

import sqlite3

import pytest

from automation.create_db import create_database
from data.db import close_db, get_audit_trail, get_db
from data.loader import load_units
from data.writer import save_unit
from gui.edit_form import checker_choices, checking_status_choices

DETAILERS = ["— Unassigned —", "Cancelled", "Tracy V", "Matt E"]


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "checker.db")
    create_database(path)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO units (com_number, top_level_number, detailer, department_hours, "
        "checking_status) VALUES ('7001', 'CN-7', 'Matt E', 20.0, 'Tracy checked')"
    )
    conn.commit()
    conn.close()
    yield path
    close_db()


def test_checker_choices_are_people_only():
    assert checker_choices(DETAILERS) == ["", "Tracy V", "Matt E"]


def test_checking_status_choices_start_blank():
    assert checking_status_choices(["Checked", "", "In checking"]) == ["", "Checked", "In checking"]
    assert checking_status_choices()[0] == ""


def test_checker_saves_audits_and_reaches_feed(db):
    unit = next(u for u in load_units(db) if u.com_number == "7001")
    assert unit.checker == ""
    unit.checker = "Tracy V"
    unit.checking_status = "Checked"
    save_unit(db, unit)

    reloaded = next(u for u in load_units(db) if u.com_number == "7001")
    assert reloaded.checker == "Tracy V"
    assert any(e["field_name"] == "checker" for e in get_audit_trail(db, "7001"))
    row = get_db(db).execute(
        "SELECT checker, checking_status FROM v_reporting_export WHERE com_number = '7001'"
    ).fetchone()
    assert tuple(row) == ("Tracy V", "Checked")


def test_edit_form_round_trips_checker(qapp, db):
    from gui.edit_form import EditForm

    form = EditForm(default_detailers=DETAILERS)
    saved = []
    form.saved.connect(saved.append)
    unit = next(u for u in load_units(db) if u.com_number == "7001")
    form.set_unit(unit)
    # A legacy free-text status still shows and is kept on save.
    assert form.checking_status_edit.currentText() == "Tracy checked"
    form.checker_edit.setCurrentText("Tracy V")
    form._on_save()
    assert saved and saved[0].checker == "Tracy V"
    assert saved[0].checking_status == "Tracy checked"
    form.deleteLater()
