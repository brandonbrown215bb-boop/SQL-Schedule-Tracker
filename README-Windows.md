# Schedule Tracker — Windows Quick Start

All batch files live at the repo root. Double-click to run.

## First time setup

1. **Clone/pull** the repo into your `SQL-Schedule-App/` folder:
   ```
   git clone https://github.com/brandonbrown215bb-boop/SQL-Schedule-Tracker
   ```
   This creates `SQL-Schedule-App/SQL-Schedule-Tracker/`.

2. Double-click **`setup.bat`** — creates a virtualenv and installs all dependencies

## Daily workflow

| Task | File |
|---|---|
| Migrate workbook → SQLite | `migrate.bat` |
| Run the app | `run.bat` |
| Run tests | `test.bat` |
| Fix missing detailers table | `ensure_detailers.bat` |

## After pulling new code

Just double-click the batch file for what you want to do. The venv persists between pulls so you only need `setup.bat` once (or when dependencies change).

## Folder structure expected

```
SQL-Schedule-App/
├── SCHDetailingReport_all_plants_MASTER.xlsm   ← your workbook
├── schedule.db                                  ← migrated database
└── SQL-Schedule-Tracker/                        ← cloned repo
    ├── main.py
    ├── setup.bat
    ├── migrate.bat
    ├── run.bat
    ├── test.bat
    ├── ensure_detailers.bat
    ├── scripts/
    │   ├── migrate_workbook_to_sqlite.py
    │   └── ensure_detailers.py
    ├── gui/
    ├── data/
    └── tests/
```
