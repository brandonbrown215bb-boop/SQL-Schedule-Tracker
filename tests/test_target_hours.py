# tests/test_target_hours.py
"""Target hours = Dept Hours - IEC Hours + Target Adjustment.

Only the earliest unit of a contract (the one that is detailed) counts toward
the total; the other identicals and cancelled units count 0. Cancelled units
are left out of the reporting feed. Regression tests for the 2026-10 target
hours discrepancy between the feed and the scheduler's numbers.
"""

import sqlite3
from datetime import date

import pytest

from automation.create_db import create_database
from automation.import_csv import upsert_row
from data.db import _migrate_schema, close_db, get_db
from data.loader import load_units
from data.models import Unit
from data.writer import save_unit
from services.assignment import mark_cancelled
from services.pre_save_hooks import (
    PreSaveHookRegistry,
    non_primary_identical_hook,
    target_adjustment_reason_hook,
    target_hours_hook,
)
from services.validation import _DEFAULT_DETAILERS, ValidationError, update_allowed_detailers

# (com, contract, due, dept, iec, detailer)
UNITS = [
    ("1001", "CN-1", "2026-11-02", 30.0, 5.0, "Carl M"),
    ("1002", "CN-1", "2026-11-09", 30.0, 0.0, ""),
    ("2001", "CN-2", "2026-11-05", 12.0, 2.0, "Carl M"),
    ("3001", "", "2026-11-06", 8.0, 0.0, ""),
]


@pytest.fixture(autouse=True)
def _allow_cancelled():
    before = [d for d in _DEFAULT_DETAILERS]
    update_allowed_detailers([*before, "Carl M", "Cancelled"])
    yield
    update_allowed_detailers(before)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "targets.db")
    create_database(path)
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO units (com_number, top_level_number, detailing_due_date, department_hours, "
        "iec_internal_hours, target_dept_hours, detailer) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(com, cn, due, d, i, max(0.0, d - i), det) for com, cn, due, d, i, det in UNITS],
    )
    conn.commit()
    conn.close()
    yield path
    close_db()


@pytest.fixture
def hooks():
    registry = PreSaveHookRegistry()
    registry.register("non_primary_identical", non_primary_identical_hook, priority=30)
    registry.register("target_hours", target_hours_hook, priority=40)
    registry.register("target_adjustment_reason", target_adjustment_reason_hook, priority=45)
    return registry


def _units(path):
    return {u.com_number: u for u in load_units(path)}


def _feed(path):
    conn = get_db(path)
    return {
        r["com_number"]: dict(r)
        for r in conn.execute("SELECT * FROM v_reporting_export")
    }


def _import(path, com, **fields):
    conn = sqlite3.connect(path)
    row = {"com_number": com, **fields}
    result = upsert_row(conn.cursor(), row, 2)
    conn.commit()
    conn.close()
    return result


# ── Formula ────────────────────────────────────────────────────────────


def test_unit_target_is_dept_minus_iec_plus_adjustment():
    u = Unit("1", "", "", "", "", "", department_hours=50.0, iec_internal_hours=8.0,
             target_adjustment_hours=-12.0)
    assert u.unit_target_hours == 30.0
    u.target_adjustment_hours = -100.0
    assert u.unit_target_hours == 0.0


def test_app_and_feed_agree(db):
    units = _units(db)
    feed = _feed(db)
    for com, row in feed.items():
        assert row["target_dept_hours"] == pytest.approx(units[com].target_department_hours)


# ── Bug 1: cancelled units ─────────────────────────────────────────────


def test_cancelled_unit_stays_at_zero_after_import(db, hooks):
    unit = _units(db)["2001"]
    save_unit(db, mark_cancelled(unit), hook_registry=hooks)

    # Next SSRS import moves the due date (forces an update).
    assert _import(db, "2001", detailing_due_date="2026-11-12", department_hours=12.0) == "updated"

    assert _units(db)["2001"].target_department_hours == 0.0
    assert "2001" not in _feed(db)


def test_cancelled_units_are_left_out_of_the_feed(db):
    conn = get_db(db)
    conn.execute("UPDATE units SET detailer = 'Cancelled' WHERE com_number = '3001'")
    conn.commit()
    assert set(_feed(db)) == {"1001", "1002", "2001"}


# ── Bug 2: a typed target can't be silently replaced / a correction survives ──


def test_adjustment_survives_import_with_new_dept_hours(db, hooks):
    unit = _units(db)["2001"]
    unit.target_adjustment_hours = 6.0
    unit.target_adjustment_reason = "SSRS missing the damper section"
    save_unit(db, unit, hook_registry=hooks)

    _import(db, "2001", detailing_due_date="2026-11-05", department_hours=20.0)

    reloaded = _units(db)["2001"]
    assert reloaded.target_adjustment_hours == 6.0
    assert reloaded.target_department_hours == 24.0  # 20 - 2 + 6
    assert _feed(db)["2001"]["target_dept_hours"] == 24.0


def test_adjustment_requires_a_reason(db, hooks):
    unit = _units(db)["2001"]
    unit.target_adjustment_hours = 6.0
    with pytest.raises(ValidationError):
        save_unit(db, unit, hook_registry=hooks)


# ── Bug 3: feed and app used different fallbacks ────────────────────────


def test_feed_subtracts_iec_even_when_stored_target_is_blank(db):
    conn = get_db(db)
    conn.execute("UPDATE units SET target_dept_hours = NULL WHERE com_number = '2001'")
    conn.commit()
    assert _feed(db)["2001"]["target_dept_hours"] == 10.0  # 12 - 2, not 12
    assert _units(db)["2001"].target_department_hours == 10.0


# ── Identicals ─────────────────────────────────────────────────────────


def test_only_the_earliest_identical_counts(db):
    units, feed = _units(db), _feed(db)
    assert units["1001"].target_department_hours == 25.0
    assert units["1002"].target_department_hours == 0.0
    assert units["1002"].detailed_on_com == "1001"
    assert feed["1002"]["target_dept_hours"] == 0.0
    assert feed["1002"]["unit_target_hours"] == 30.0
    assert feed["1002"]["detailed_on_com"] == "1001"
    assert feed["1001"]["detailed_on_com"] == ""


def test_cancelled_unit_is_never_the_counted_identical(db, hooks):
    save_unit(db, mark_cancelled(_units(db)["1001"]), hook_registry=hooks)
    units, feed = _units(db), _feed(db)
    assert units["1001"].target_department_hours == 0.0
    assert units["1002"].target_department_hours == 30.0
    assert not units["1002"].is_non_primary_identical
    assert feed["1002"]["target_dept_hours"] == 30.0


def test_saving_a_non_primary_identical_keeps_it_at_zero(db, hooks):
    unit = _units(db)["1002"]
    unit.notes = "checked"
    save_unit(db, unit, hook_registry=hooks)
    assert _units(db)["1002"].target_department_hours == 0.0
    assert _feed(db)["1002"]["target_dept_hours"] == 0.0


# ── Migration ──────────────────────────────────────────────────────────


def test_migration_carries_open_overrides_and_drops_closed_ones(tmp_path):
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE units (com_number TEXT UNIQUE, top_level_number TEXT, detailer TEXT, "
        "detailing_due_date TEXT, department_hours REAL, iec_internal_hours REAL, "
        "target_dept_hours REAL, percent_complete REAL, "
        "unit_moved_to_checking_date TEXT, unit_detailing_completion_date TEXT)"
    )
    conn.executemany(
        "INSERT INTO units VALUES (?, '', 'Carl M', '2026-11-01', ?, ?, ?, ?, NULL, NULL)",
        [
            ("open-override", 40.0, 4.0, 50.0, 0.2),   # open: keep +14 as adjustment
            ("open-formula", 40.0, 4.0, 36.0, 0.2),    # open, no override
            ("open-zero", 40.0, 4.0, 0.0, 0.0),        # 0 meant "unset"
            ("closed-override", 40.0, 0.0, 26.0, 1.0), # old workbook ratio: dropped
        ],
    )
    conn.commit()
    _migrate_schema(conn)
    rows = {
        r[0]: r[1:]
        for r in conn.execute(
            "SELECT com_number, target_adjustment_hours, target_dept_hours FROM units"
        )
    }
    conn.close()
    assert rows["open-override"] == (14.0, 50.0)
    assert rows["open-formula"] == (0.0, 36.0)
    assert rows["open-zero"] == (0.0, 36.0)
    assert rows["closed-override"] == (0.0, 40.0)


# ── Edit form ──────────────────────────────────────────────────────────


@pytest.fixture
def edit_form():
    from PyQt5.QtWidgets import QApplication

    from gui.edit_form import EditForm

    QApplication.instance() or QApplication([])
    form = EditForm(default_detailers=["— Unassigned —", "Carl M", "Cancelled"])
    yield form
    form.deleteLater()


def _form_unit(**kw):
    base = dict(
        com_number="5001", job_name="J", contract_number="CN-5", description="D",
        detailer="Carl M", checking_status="", department_hours=40.0,
        iec_internal_hours=4.0, detailing_due_date=date(2026, 11, 2),
    )
    base.update(kw)
    return Unit(**base)


def test_form_target_follows_iec_and_adjustment(edit_form):
    edit_form.set_unit(_form_unit())
    assert edit_form.target_hours_spin.value() == 36.0
    edit_form.target_adj_spin.setValue(-6.0)
    assert edit_form.target_hours_spin.value() == 30.0
    edit_form.iec_hours_spin.setValue(10.0)
    assert edit_form.target_hours_spin.value() == 24.0


def test_form_blocks_adjustment_without_reason(edit_form):
    saved = []
    edit_form.saved.connect(saved.append)
    edit_form.set_unit(_form_unit())
    edit_form.target_adj_spin.setValue(5.0)
    edit_form._on_save()
    assert saved == []
    edit_form.target_adj_reason_edit.setText("Dept hours low")
    edit_form._on_save()
    assert saved[0].target_adjustment_hours == 5.0
    assert saved[0].target_adjustment_reason == "Dept hours low"


def test_form_save_keeps_identical_flag(edit_form):
    unit = _form_unit()
    unit.is_non_primary_identical = True
    unit.detailed_on_com = "5000"
    saved = []
    edit_form.saved.connect(saved.append)
    edit_form.set_unit(unit)
    assert edit_form.target_hours_spin.value() == 0.0
    assert "5000" in edit_form.target_note_label.text()
    edit_form._on_save()
    assert saved[0].is_non_primary_identical
    assert saved[0].detailed_on_com == "5000"
