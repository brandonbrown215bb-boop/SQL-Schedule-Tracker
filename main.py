# main.py
import faulthandler
import os
import sys
import traceback

faulthandler.enable()

import yaml
from PyQt5.QtWidgets import QApplication, QMessageBox

from data.db import get_db, close_db
from gui.main_window import MainWindow


def _validate_config_paths(config: dict, config_path: str, application_path: str) -> None:
    """Validate sqlite_path from config.yaml."""
    db_path = config.get("sqlite_path", "")
    if not db_path:
        return
    if not os.path.isabs(db_path):
        config["sqlite_path"] = os.path.join(application_path, db_path)


def main():
    print("Application starting...")

    if getattr(sys, "frozen", False):
        application_path = os.path.dirname(sys.executable)
        print(f"Running as frozen executable. Application path: {application_path}")
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
        print(f"Running as script. Application path: {application_path}")

    config_path = os.path.join(application_path, "config.yaml")
    print(f"Looking for config.yaml at: {config_path}")

    app = QApplication(sys.argv)
    print("QApplication created.")

    if not os.path.exists(config_path):
        print(f"Error: config.yaml not found at {config_path}")
        QMessageBox.critical(
            None,
            "Configuration Error",
            f"config.yaml not found at:\n{config_path}\n\n"
            "Please ensure config.yaml is in the same directory as the application.",
        )
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        print("Error: config.yaml did not parse as a mapping.")
        QMessageBox.critical(
            None, "Configuration Error", "config.yaml did not parse as a valid mapping (dict)."
        )
        sys.exit(1)

    print("config.yaml loaded successfully.")

    # Validate paths
    _validate_config_paths(config, config_path, application_path)

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

    print(f"Connected to SQLite: {db_path}")

    # Pass config_path separately — do not inject into the config dict
    window = MainWindow(config, config_path=config_path, db_path=db_path)
    print("MainWindow created.")
    window.show()
    print("MainWindow shown. Entering event loop...")

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
