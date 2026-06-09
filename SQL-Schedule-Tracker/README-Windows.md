# Schedule Tracker — Windows Quick Start

All batch files go in `SQL-Schedule-Tracker\`. Double-click to run.

## First time setup

1. **Clone/pull** the repo to `Downloads\Code Projects\SQL-Schedule-App\`
2. Double-click **`setup.bat`** — creates a virtualenv and installs all dependencies

## Daily workflow

| Task | File |
|---|---|
| Migrate workbook → SQLite | `migrate.bat` |
| Run the app | `run.bat` |
| Run tests | `test.bat` |

## After pulling new code

Just double-click the batch file for what you want to do. The venv already has everything installed.

If dependencies changed (new pip packages), run `setup.bat` again — it's fast on re-run.

## Folder structure expected

```
SQL-Schedule-App/
├── SCHDetailingReport_all_plants_MASTER.xlsm   ← your workbook
├── schedule.db                                  ← migrated database (created by migrate.bat)
├── requirements.txt
└── SQL-Schedule-Tracker/
    ├── main.py
    ├── setup.bat
    ├── migrate.bat
    ├── run.bat
    └── test.bat
```
