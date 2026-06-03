# main.py
import os
import sys
import traceback

# Enable DPI awareness on Windows before QApplication is created.
# Without this, coordinates from mapTo/pos() may be scaled incorrectly
# on displays with >100% resolution scaling.
if sys.platform == "win32":
    from ctypes import windll
    try:
        windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# When running as a PyInstaller --windowed build, sys.stderr is None
# which crashes faulthandler.enable(). Redirect to a log file instead.
if sys.stderr is None:
    _log_dir = os.path.join(os.path.expanduser("~"), ".unit_tracker")
    os.makedirs(_log_dir, exist_ok=True)
    sys.stderr = open(os.path.join(_log_dir, "error.log"), "a", encoding="utf-8")

import faulthandler

faulthandler.enable()

import yaml
from PyQt5.QtWidgets import QApplication, QMessageBox

from data.db import close_db, get_db
from gui.main_window import MainWindow


def _validate_config_paths(config: dict, application_path: str) -> None:
    """Validate sqlite_path from config.yaml."""
    db_path = config.get("sqlite_path", "")
    if not db_path:
        return
    if not os.path.isabs(db_path):
        config["sqlite_path"] = os.path.join(application_path, db_path)


def _safe_print(msg: str) -> None:
    """Print that works in both console and --windowed mode."""
    try:
        print(msg)
    except (OSError, ValueError):
        pass  # stdout is None in windowed mode


def main():
    _safe_print("Application starting...")

    if getattr(sys, "frozen", False):
        application_path = os.path.dirname(sys.executable)
        _safe_print(f"Running as frozen executable. Application path: {application_path}")
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
        _safe_print(f"Running as script. Application path: {application_path}")

    config_path = os.path.join(application_path, "config.yaml")
    _safe_print(f"Looking for config.yaml at: {config_path}")

    app = QApplication(sys.argv)
    _safe_print("QApplication created.")

    if not os.path.exists(config_path):
        _safe_print(f"Error: config.yaml not found at {config_path}")
        QMessageBox.critical(
            None,
            "Configuration Error",
            f"config.yaml not found at:\n{config_path}\n\n"
            "Please ensure config.yaml is in the same directory as the application.",
        )
        sys.exit(1)

    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        _safe_print("Error: config.yaml did not parse as a mapping.")
        QMessageBox.critical(
            None, "Configuration Error", "config.yaml did not parse as a valid mapping (dict).",
        )
        sys.exit(1)

    _safe_print("config.yaml loaded successfully.")

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
            None, "Database Error",
            f"SQLite database not found at:\n{db_path}\n\n"
            "Run the migration script first."
        )
        sys.exit(1)

    try:
        get_db(db_path)
    except Exception as e:
        QMessageBox.critical(None, "Database Error", f"Failed to connect to SQLite:\n{e}")
        sys.exit(1)

    _safe_print(f"Connected to SQLite: {db_path}")

    window = MainWindow(config, config_path=config_path, db_path=db_path)
    _safe_print("MainWindow created.")
    window.show()
    _safe_print("MainWindow shown. Entering event loop...")

    exit_code = app.exec_()
    close_db()
    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"An unhandled error occurred: {e}")
        traceback.print_exc()
        input("Press Enter to exit...")
