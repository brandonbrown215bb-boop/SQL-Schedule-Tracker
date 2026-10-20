"""Fixes for the remaining review items: backups, SSRS cancel, reload debounce,
Alerts filters, busy timeouts, updater/deploy safety, search, crash handler."""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from data.models import Unit

# ── #17 Startup backup retention ──────────────────────────────────────


def _backup_names(start: datetime, days: int) -> list[str]:
    return [f"/b/{(start - timedelta(days=i)):%Y%m%d_%H%M%S}_startup_backup.db" for i in range(days)]


def test_backup_retention_spreads_over_three_months():
    from data.db import startup_backups_to_prune

    paths = _backup_names(datetime(2026, 10, 15, 8, 0, 0), 120)  # one per day for 4 months
    pruned = set(startup_backups_to_prune(paths))
    kept = sorted(set(paths) - pruned, reverse=True)

    assert len(kept) <= 14
    # The 7 most recent days are all kept
    assert set(paths[:7]) <= set(kept)
    # History reaches back about 3 months, not just ~2 weeks
    oldest = datetime.strptime(os.path.basename(kept[-1])[:15], "%Y%m%d_%H%M%S")
    assert oldest <= datetime(2026, 8, 1, 8, 0, 0)


def test_backup_retention_never_deletes_unparseable_names():
    from data.db import startup_backups_to_prune

    assert startup_backups_to_prune(["/b/manual_copy_startup_backup.db"]) == []


# ── #11 SSRS fetch cancel / time limit ────────────────────────────────


def test_fetch_stops_immediately_when_cancelled():
    from automation.import_atomsvc import SSRSFetchCancelledError, fetch_csv_from_ssrs

    cancel = threading.Event()
    cancel.set()
    with pytest.raises(SSRSFetchCancelledError):
        fetch_csv_from_ssrs("http://example.invalid/report", cancel=cancel)


def test_fetch_stops_when_time_limit_passed():
    from automation.import_atomsvc import SSRSFetchTimeoutError, fetch_csv_from_ssrs

    with pytest.raises(SSRSFetchTimeoutError):
        fetch_csv_from_ssrs("http://example.invalid/report", deadline=time.monotonic() - 1)


def test_cancel_kills_running_subprocess():
    from automation.import_atomsvc import SSRSFetchCancelledError, _run_cancellable

    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    start = time.monotonic()
    with pytest.raises(SSRSFetchCancelledError):
        _run_cancellable([sys.executable, "-c", "import time; time.sleep(30)"], 30, cancel)
    assert time.monotonic() - start < 5


def test_download_ssrs_passes_one_deadline_to_every_fetch(monkeypatch):
    import automation.import_atomsvc as atom
    from services.import_service import ImportService

    calls = []

    def fake_fetch(url, filename_prefix="", deadline=None, cancel=None, **kw):
        calls.append((deadline, cancel))
        return "/tmp/x.csv"

    monkeypatch.setattr(atom, "fetch_csv_from_ssrs", fake_fetch)
    monkeypatch.setattr(atom, "merge_summary_states_into_csv", lambda *a: None)
    cancel = threading.Event()
    ImportService("db").download_ssrs("http://s/r?x", ssrs_summary_url="http://s/sum?x", cancel=cancel)
    assert len(calls) == 2
    assert calls[0][0] == calls[1][0] is not None  # same overall deadline
    assert all(c is cancel for _, c in calls)


# ── #4 Reload debounce ────────────────────────────────────────────────


def _reload_stub(tmp_path, **overrides):
    from gui.main_window import MainWindow

    db = tmp_path / "x.db"
    db.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    stub = SimpleNamespace(
        _services=SimpleNamespace(db_path=str(db)),
        _io_busy=False,
        _save_queue=[],
        _active_save_worker_running=lambda: False,
        _own_commit_stat=None,
        _reload_retries=0,
        _reload_timer=MagicMock(),
        _load_data_async=MagicMock(),
        RELOAD_MAX_RETRIES=MainWindow.RELOAD_MAX_RETRIES,
    )
    stub.__dict__.update(overrides)
    for name in ("_db_file_stat", "_db_header_ok", "_retry_reload_later", "_record_own_commit"):
        setattr(stub, name, getattr(MainWindow, name).__get__(stub))
    return stub


def test_reload_skips_our_own_save(tmp_path):
    from gui.main_window import MainWindow

    stub = _reload_stub(tmp_path)
    stub._record_own_commit()
    MainWindow._on_reload_debounced(stub)
    stub._load_data_async.assert_not_called()


def test_reload_runs_for_other_users_change(tmp_path):
    from gui.main_window import MainWindow

    stub = _reload_stub(tmp_path)
    stub._record_own_commit()
    with open(stub._services.db_path, "ab") as f:  # someone else writes after us
        f.write(b"\x00" * 10)
    MainWindow._on_reload_debounced(stub)
    stub._load_data_async.assert_called_once()


def test_reload_waits_instead_of_dropping_when_busy(tmp_path):
    from gui.main_window import MainWindow

    stub = _reload_stub(tmp_path, _io_busy=True)
    MainWindow._on_reload_debounced(stub)
    stub._load_data_async.assert_not_called()
    stub._reload_timer.start.assert_called_once()  # retried, not dropped


# ── #14 / Alerts detailer picker ──────────────────────────────────────


def _u(com: str, detailer: str) -> Unit:
    return Unit(
        com_number=com, job_name="J", contract_number=f"C{com}", description="", detailer=detailer,
        checking_status="", department_hours=10.0, target_department_hours=10.0,
        detailing_due_date=date.today() + timedelta(days=10),
    )


@pytest.fixture
def alerts(qtbot):
    from gui.alert_panel import AlertPanel

    p = AlertPanel()
    qtbot.addWidget(p)
    p.show()
    p.set_units([_u("10001", "Jackie H"), _u("10002", ""), _u("10003", "— Unassigned —"), _u("10004", "Tommy N")])
    return p


def _shown_coms(panel) -> set[str]:
    from PyQt5.QtCore import Qt

    return {panel.list_widget.item(i).data(Qt.UserRole).com_number for i in range(panel.list_widget.count())}


def test_alerts_unassigned_filter(alerts):
    from gui.alert_panel import UNASSIGNED_FILTER

    alerts.detailer_combo.setCurrentText(UNASSIGNED_FILTER)
    assert _shown_coms(alerts) == {"10002", "10003"}
    assert alerts.capacity_label.isHidden()


def test_alerts_picker_keeps_choice_after_reload(alerts):
    alerts.detailer_combo.setCurrentText("Tommy N")
    alerts.set_units([_u("10001", "Jackie H"), _u("10004", "Tommy N")])
    assert alerts.detailer_combo.currentText() == "Tommy N"
    assert _shown_coms(alerts) == {"10004"}


def test_alerts_picker_has_no_unassigned_or_cancelled_as_names(alerts):
    names = [alerts.detailer_combo.itemText(i) for i in range(alerts.detailer_combo.count())]
    assert names.count("— Unassigned —") == 1  # the filter entry only
    assert "Cancelled" not in names


def test_list_reload_keeps_cancelled_detailer_filter(qtbot):
    from gui.list_panel import ListPanel

    a, b = _u("10001", "Jackie H"), _u("10002", "Cancelled")
    panel = ListPanel([a, b])
    qtbot.addWidget(panel)
    panel.detailer_filter.set_selected({"Jackie H", "Cancelled"}, emit=True)
    assert {u.com_number for u in panel._model.filtered_units} == {"10001", "10002"}
    panel.refresh([_u("10001", "Jackie H"), _u("10002", "Cancelled")])
    assert {u.com_number for u in panel._model.filtered_units} == {"10001", "10002"}
    assert panel.detailer_filter.selected() == {"Jackie H", "Cancelled"}


# ── #5 UI read timeout ────────────────────────────────────────────────


def test_ui_thread_busy_timeout_applies_to_connection(tmp_path):
    from data import db as dbmod

    path = str(tmp_path / "t.db")
    sqlite3.connect(path).close()
    result = {}

    def worker():
        conn = dbmod.get_db(path)
        dbmod.set_thread_busy_timeout(dbmod.UI_BUSY_TIMEOUT_MS)
        result["timeout"] = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        conn.close()
        dbmod._local.conn = None

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert result["timeout"] == dbmod.UI_BUSY_TIMEOUT_MS


def test_is_busy_error():
    from data.db import DatabaseBusyError, is_busy_error

    assert is_busy_error(sqlite3.OperationalError("database is locked"))
    assert is_busy_error(DatabaseBusyError())
    assert not is_busy_error(sqlite3.OperationalError("no such table: units"))


# ── #12 Updater / deploy ──────────────────────────────────────────────


def test_updater_copies_version_only_after_exe(tmp_path):
    from services.update_service import UpdateService

    local = tmp_path / "Programs" / "Detailing Schedule"
    local.mkdir(parents=True)
    path = UpdateService(str(local)).generate_updater_script(str(tmp_path / "share"), str(local))
    with open(path, encoding="cp1252") as f:
        script = f.read()
    exe_copy = script.index('"Detailing Schedule.exe" /R:3')
    version_copy = script.index('"version.txt" /R:3')
    assert exe_copy < version_copy
    assert "goto copy_failed" in script[exe_copy:version_copy]
    # The wait loop is bounded and doesn't rely on %VAR% inside a ( ) block
    assert "if %WAIT_COUNT% GEQ 60 goto wait_timeout" in script


def test_copy_atomic_replaces_and_leaves_no_temp(tmp_path):
    from automation.deploy import copy_atomic

    src, dest = tmp_path / "new.exe", tmp_path / "app.exe"
    src.write_bytes(b"new")
    dest.write_bytes(b"old")
    copy_atomic(str(src), str(dest))
    assert dest.read_bytes() == b"new"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["app.exe", "new.exe"]


# ── Global search / refresh cooldown / overlay / excepthook ──────────


def test_global_search_typing_does_not_switch_view():
    from gui.main_window import MainWindow

    stub = MagicMock()
    stub._search_edit.text.return_value = "j"  # matches both job names "J"
    stub.units = [_u("10001", ""), _u("10002", "")]
    MainWindow._on_global_search(stub)
    assert len(stub._search_matches) == 2
    stub._switch_view.assert_not_called()
    stub.list_panel.com_search.setFocus.assert_not_called()
    stub.list_panel.com_search.setText.assert_not_called()
    assert "2 matches" in stub.status_bar.showMessage.call_args.args[0]


def test_global_search_enter_lists_matches_and_keeps_focus():
    from gui.main_window import MainWindow

    stub = MagicMock()
    stub._search_timer.isActive.return_value = False
    stub._search_edit.text.return_value = "J"
    stub._search_matches = [_u("10001", ""), _u("10002", "")]
    MainWindow._on_search_entered(stub)
    stub._switch_view.assert_called_once_with("list")
    stub._search_edit.setFocus.assert_called_once()


def test_refresh_cooldown_disables_toolbar_action(qtbot):
    from PyQt5.QtWidgets import QAction, QWidget

    from gui.main_window import MainWindow

    holder = QWidget()
    qtbot.addWidget(holder)
    action = QAction("Refresh", holder)
    stub = SimpleNamespace(_refresh_action=action, REFRESH_COOLDOWN_MS=50)
    MainWindow._apply_refresh_cooldown(stub)
    assert not action.isEnabled()
    qtbot.waitUntil(action.isEnabled, timeout=2000)


def test_loading_overlay_cancel_button(qtbot):
    from PyQt5.QtWidgets import QWidget

    from gui.loading_overlay import LoadingOverlay

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.show()
    overlay = LoadingOverlay(parent)
    clicks = []
    overlay.show_with_message("Fetching", on_cancel=lambda: clicks.append(1))
    assert overlay._cancel_btn.isVisible()
    overlay._cancel_btn.click()
    overlay._cancel_btn.click()  # second click ignored
    assert clicks == [1]
    overlay.show_with_message("Loading")
    assert not overlay._cancel_btn.isVisible()


def test_excepthook_reports_instead_of_exiting(monkeypatch, qapp, tmp_path):
    import main as app_main

    shown = []
    monkeypatch.setattr(app_main.QMessageBox, "exec_", lambda self: shown.append(self.text()))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    log = open(tmp_path / "error.log", "a", encoding="utf-8")  # noqa: SIM115
    app_main._install_excepthook(log)
    try:
        raise ValueError("boom")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    log.close()
    assert len(shown) == 1 and "ValueError: boom" in shown[0]
    assert "ValueError: boom" in (tmp_path / "error.log").read_text(encoding="utf-8")


def test_excepthook_from_worker_thread_shows_dialog_on_gui_thread(monkeypatch, qtbot):
    """PyQt calls sys.excepthook on the QThread when run() raises. Building the
    dialog there is an access violation on Windows, so it must be marshalled."""
    from PyQt5.QtCore import QThread

    import main as app_main

    shown_on = []
    monkeypatch.setattr(app_main.QMessageBox, "exec_", lambda self: shown_on.append(threading.current_thread().name))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    app_main._install_excepthook()

    class Boom(QThread):
        def run(self):
            try:
                raise RuntimeError("worker failed")
            except RuntimeError:
                sys.excepthook(*sys.exc_info())

    t = Boom()
    t.start()
    t.wait(5000)
    qtbot.waitUntil(lambda: bool(shown_on), timeout=3000)
    assert shown_on == [threading.main_thread().name]


# ── SSRS cancel freeze: notification flush vs. loading overlay ────────


@pytest.fixture
def window_with_overlay(qtbot):
    from PyQt5.QtWidgets import QMainWindow, QWidget

    from gui.loading_overlay import LoadingOverlay
    from gui.notification_panel import NotificationPanel

    win = QMainWindow()
    win.setCentralWidget(QWidget())
    win.resize(800, 600)
    win.loading_overlay = LoadingOverlay(win.centralWidget())
    win.notification_panel = NotificationPanel(win.centralWidget())
    qtbot.addWidget(win)
    win.show()
    return win


def test_flush_while_overlay_still_visible_does_not_hang(window_with_overlay, qtbot):
    """Regression: flush_queue() looped forever when the overlay's minimum display
    time kept it visible, freezing the app after cancelling an SSRS pull."""
    win = window_with_overlay
    panel = win.notification_panel
    win.loading_overlay.show_with_message("Fetching…", on_cancel=lambda: None)
    panel.show_notification("Config saved", "info")  # queued behind the overlay
    assert panel._queue

    win.loading_overlay.hide()   # deferred: shown < 200 ms ago
    assert win.loading_overlay.isVisible()
    panel.flush_queue()          # used to spin forever here
    assert panel._queue          # still waiting, not lost

    qtbot.waitUntil(lambda: not win.loading_overlay.isVisible(), timeout=2000)
    qtbot.waitUntil(lambda: not panel._queue, timeout=2000)
    assert len(panel._toasts) == 1


def test_changing_overlay_message_does_not_extend_min_display(window_with_overlay):
    overlay = window_with_overlay.loading_overlay
    overlay.show_with_message("Fetching…")
    first = overlay._show_timestamp
    time.sleep(0.05)
    overlay.show_with_message("Cancelling…")
    assert overlay._show_timestamp == first


def test_reshow_cancels_pending_delayed_hide(window_with_overlay, qtbot):
    overlay = window_with_overlay.loading_overlay
    overlay.show_with_message("Importing…")
    overlay.hide()                       # deferred hide scheduled
    overlay.show_with_message("Loading…")  # next operation starts right away
    qtbot.wait(400)
    assert overlay.isVisible()
