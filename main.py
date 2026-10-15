# main.py
import contextlib
import faulthandler
import os
import sys
import traceback

from PyQt5.QtWidgets import QApplication, QMessageBox

from data.db import close_db, get_db


def _validate_config_paths(config: dict, application_path: str) -> None:
    """Validate sqlite_path from config.yaml."""
    db_path = config.get("sqlite_path", "")
    if not db_path:
        return
    if not os.path.isabs(db_path):
        config["sqlite_path"] = os.path.join(application_path, db_path)


def _safe_print(msg: str) -> None:
    """Print that works in both console and --windowed mode."""
    with contextlib.suppress(OSError, ValueError):
        print(msg)  # stdout is None in windowed mode


def main():
    _safe_print("Application starting...")

    # Enable DPI awareness on Windows before QApplication is created.
    if sys.platform == "win32":
        from ctypes import windll

        try:
            windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            with contextlib.suppress(Exception):
                windll.user32.SetProcessDPIAware()

    # Crash details always go to ~/.unit_tracker/error.log, also when running from a
    # console (whose output is lost when the window closes with the app).
    # When running as PyInstaller --windowed, sys.stderr is None, so it becomes the log.
    error_log = _open_error_log()
    if sys.stderr is None:
        sys.stderr = error_log

    faulthandler.enable(file=error_log or sys.stderr)
    import logging

    # Console/stderr logging at INFO. (Set it up here: once any handler exists,
    # the basicConfig() calls in other modules do nothing, leaving WARNING.)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if error_log is not None and sys.stderr is not error_log:
        # Running from a console: also keep the app's log lines next to any crash
        handler = logging.StreamHandler(error_log)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(handler)

    if getattr(sys, "frozen", False):
        application_path = os.path.dirname(sys.executable)
        _safe_print(f"Running as frozen executable. Application path: {application_path}")
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
        _safe_print(f"Running as script. Application path: {application_path}")

    config_path = os.path.join(application_path, "config.yaml")
    _safe_print(f"Looking for config.yaml at: {config_path}")

    # Windows adds a "?" (What's This) button to every dialog's title bar; the app
    # has no context help, so the button did nothing. Must be set before QApplication.
    from PyQt5.QtCore import Qt

    QApplication.setAttribute(Qt.AA_DisableWindowContextHelpButton)
    app = QApplication(sys.argv)
    _install_excepthook(error_log)
    _safe_print("QApplication created.")

    from gui.no_scroll_filter import install_no_scroll_filter
    install_no_scroll_filter(app)

    # Path safety check (guard against running loose in Documents, Desktop, etc.)
    from services.update_service import UpdateService

    safe, reason = UpdateService.is_safe_install_dir(application_path)
    if not safe:
        _safe_print(f"Startup warning: running in personal or system folder: {reason}")
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Detailing Schedule — Setup Notice")
        msg_box.setText(
            f"Detailing Schedule is running directly inside a personal folder:\n\n"
            f"{application_path}\n\n"
            f"Running loose in this folder can clutter your personal documents with application files, and automatic updates are disabled for your safety.\n\n"
            f"Would you like to move the application to its dedicated folder now?\n"
            f"(Installs to %LOCALAPPDATA%\\Programs\\Detailing Schedule and creates a Desktop shortcut)"
        )
        move_btn = msg_box.addButton("Move to Dedicated Folder (Recommended)", QMessageBox.ActionRole)
        msg_box.addButton("Continue Anyway", QMessageBox.RejectRole)
        msg_box.setDefaultButton(move_btn)
        msg_box.exec_()

        if msg_box.clickedButton() == move_btn:
            success, new_exe, move_msg = UpdateService.migrate_to_dedicated_folder(application_path)
            if success:
                QMessageBox.information(
                    None,
                    "Setup Complete",
                    f"{move_msg}\n\nA Desktop shortcut has been created. The application will now restart from its dedicated folder.",
                )
                import subprocess

                clean_env = UpdateService.clean_pyinstaller_env()
                subprocess.Popen(f'start "" "{new_exe}"', shell=True, env=clean_env)
                sys.exit(0)
            else:
                QMessageBox.critical(None, "Setup Error", f"Failed to move application:\n{move_msg}")

    if not os.path.exists(config_path):
        _safe_print(f"Error: config.yaml not found at {config_path}")
        QMessageBox.critical(
            None,
            "Configuration Error",
            f"config.yaml not found at:\n{config_path}\n\n"
            "Please ensure config.yaml is in the same directory as the application.",
        )
        sys.exit(1)

    from services.config_service import ConfigService

    try:
        # Installed builds take shared settings from the network template
        config = ConfigService.load(config_path, prefer_template=getattr(sys, "frozen", False))
    except Exception as e:
        _safe_print(f"Error loading config.yaml: {e}")
        QMessageBox.critical(
            None,
            "Configuration Error",
            f"Failed to load config.yaml:\n{e}",
        )
        sys.exit(1)

    _safe_print("config.yaml loaded and merged with defaults.")

    # ── Multi-user configuration and username check ───────────────────
    if "multi_user" not in config or not isinstance(config["multi_user"], dict):
        config["multi_user"] = {"enabled": True, "fallback_mode": "block"}
    else:
        config["multi_user"]["enabled"] = True

    import getpass

    sys_username = getpass.getuser()
    username = (config["multi_user"].get("username") or "").strip()
    if username and not ConfigService.username_belongs_to(config["multi_user"], sys_username):
        # Inherited from someone else's config (e.g. an old shared template): ask again
        username = ""

    if not username:
        from PyQt5.QtWidgets import QInputDialog

        username, ok = QInputDialog.getText(
            None,
            "Username Required",
            "Please enter your name/username for multi-user sync:",
            text=sys_username,
        )

        username = username.strip()
        if not ok or not username:
            username = sys_username or "User"

        config["multi_user"]["username"] = username

    # Remember which Windows login this username belongs to
    config["multi_user"]["os_user"] = sys_username

    # Always save back on startup to ensure config.yaml contains all keys
    try:
        ConfigService.save(config_path, config)
        _safe_print("config.yaml successfully validated and saved.")
    except Exception as e:
        _safe_print(f"Warning: Failed to save config.yaml: {e}")

    # Validate paths
    _validate_config_paths(config, application_path)

    # Initialize SQLite connection
    db_path = config.get("sqlite_path", "")
    if not db_path:
        QMessageBox.critical(None, "Configuration Error", "sqlite_path not set in config.yaml")
        sys.exit(1)
    if not os.path.isabs(db_path):
        db_path = os.path.join(application_path, db_path)
    if not os.path.exists(db_path):
        QMessageBox.critical(
            None,
            "Database Error",
            f"SQLite database not found at:\n{db_path}\n\nRun the migration script first.",
        )
        sys.exit(1)

    try:
        get_db(db_path)
    except Exception as e:
        QMessageBox.critical(None, "Database Error", f"Failed to connect to SQLite:\n{e}")
        sys.exit(1)

    _safe_print(f"Connected to SQLite: {db_path}")

    from data.db import set_audit_user

    set_audit_user(config["multi_user"].get("username", ""))

    # ── Sprint 2: Bulk backup on app startup ────────────────────────────
    try:
        _startup_backup(db_path, application_path)
    except Exception as e:
        _safe_print(f"Startup backup failed (non-fatal): {e}")

    from gui.main_window import MainWindow, ServiceRegistry

    services = ServiceRegistry(config, config_path, db_path)
    window = MainWindow(services)
    _safe_print("MainWindow created.")
    window.show()
    _safe_print("MainWindow shown. Entering event loop...")

    exit_code = app.exec_()
    close_db()
    sys.exit(exit_code)


def _open_error_log():
    """Open ~/.unit_tracker/error.log for appending, or None if that fails."""
    try:
        log_dir = os.path.join(os.path.expanduser("~"), ".unit_tracker")
        os.makedirs(log_dir, exist_ok=True)
        return open(os.path.join(log_dir, "error.log"), "a", encoding="utf-8")
    except OSError:
        return None


def _install_excepthook(error_log=None) -> None:
    """Report uncaught exceptions instead of letting PyQt abort the app.

    Since PyQt 5.5 an exception escaping a slot calls qFatal() and the whole
    app closes, losing unsaved edits. Log the traceback and show a dialog;
    the event loop keeps running.

    PyQt also calls this hook on the *worker* thread when a QThread.run()
    raises. Widgets may only be created on the GUI thread (doing it elsewhere
    is an access violation on Windows), so the dialog is always shown on the
    GUI thread via a queued signal.
    """
    import threading
    from datetime import datetime

    from PyQt5.QtCore import QObject, pyqtSignal

    showing = False

    class _Reporter(QObject):
        report = pyqtSignal(str, str)  # (summary, details); queued across threads

    def _show(summary: str, details: str) -> None:
        nonlocal showing
        if showing:
            return  # don't stack dialogs if the error repeats while one is open
        showing = True
        try:
            box = QMessageBox(QMessageBox.Critical, "Unexpected Error",
                              "Something went wrong, but the app is still running.\n\n"
                              f"{summary}\n\n"
                              "If anything looks wrong, save your work and restart the app.")
            box.setDetailedText(details)
            box.exec_()
        finally:
            showing = False

    reporter = _Reporter()  # lives on the GUI thread (created here)
    reporter.report.connect(_show)

    def _hook(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        thread = threading.current_thread().name
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for stream in {sys.stderr, error_log} - {None}:
            with contextlib.suppress(Exception):
                stream.write(f"{stamp} Uncaught exception in thread {thread}:\n{details}")
                stream.flush()
        if QApplication.instance() is None:
            return
        summary = f"{exc_type.__name__}: {exc_value}"
        if threading.current_thread() is threading.main_thread():
            _show(summary, details)
        else:
            reporter.report.emit(summary, details)

    _install_excepthook._reporter = reporter  # keep the QObject alive
    sys.excepthook = _hook


def _startup_backup(db_path: str, application_path: str) -> None:
    """Create a startup backup with retention: 7 daily, 4 weekly, 3 monthly.

    This is a safety net for ALL data operations. Backups are stored in
    a ``backups/`` subdirectory next to the database file.
    """
    import glob
    from datetime import datetime

    backup_dir = os.path.join(os.path.dirname(db_path), "backups")
    os.makedirs(backup_dir, exist_ok=True)

    # Create the backup using VACUUM INTO
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"{ts}_startup_backup.db")

    # One startup backup per day is plenty; every launch by every user would
    # otherwise copy the whole DB across the share before the window opens.
    today_prefix = datetime.now().strftime("%Y%m%d_")
    if glob.glob(os.path.join(backup_dir, f"{today_prefix}*_startup_backup.db")):
        return

    conn = get_db(db_path)
    try:
        conn.execute("VACUUM INTO ?", (backup_path,))
    except Exception:
        # Fallback: backup API
        import sqlite3

        backup_conn = sqlite3.connect(backup_path)
        conn.backup(backup_conn)
        backup_conn.close()

    _safe_print(f"Startup backup: {backup_path}")

    # ── Retention policy: 7 daily, 4 weekly, 3 monthly ──────────────────
    from data.db import startup_backups_to_prune

    all_backups = glob.glob(os.path.join(backup_dir, "*_startup_backup.db"))
    to_delete = startup_backups_to_prune(all_backups)

    for path in to_delete:
        with contextlib.suppress(OSError):
            os.remove(path)

    if to_delete:
        _safe_print(f"Startup backup: pruned {len(to_delete)} old backup(s)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"An unhandled error occurred: {e}")
        traceback.print_exc()
        input("Press Enter to exit...")
