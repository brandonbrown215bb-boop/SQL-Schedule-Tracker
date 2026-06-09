@echo off
REM ============================================================
REM migrate.bat — Migrate Excel workbook to SQLite database
REM Run from: SQL-Schedule-Tracker\
REM ============================================================
setlocal

echo ============================================================
echo  Schedule Tracker — Workbook Migration
echo ============================================================
echo.

REM Activate venv if it exists, otherwise fall back to system Python
if exist ".venv\Scripts\python.exe" (
    set PY=.venv\Scripts\python.exe
) else (
    set PY=py -3.14
)

REM Determine paths relative to this script
set "APP_DIR=%~dp0.."
set "SCRIPT_DIR=%~dp0..\scripts"

if not exist "%SCRIPT_DIR%\migrate_workbook_to_sqlite.py" (
    echo ERROR: migrate_workbook_to_sqlite.py not found in scripts\
    echo Make sure you've pulled the latest from git.
    pause
    exit /b 1
)

echo Running migration...
echo.

%PY% "%SCRIPT_DIR%\migrate_workbook_to_sqlite.py" --workbook "%APP_DIR%\SCHDetailingReport_all_plants_MASTER.xlsm" --db "%APP_DIR%\schedule.db"

if errorlevel 1 (
    echo.
    echo ============================================================
    echo  MIGRATION FAILED — see errors above
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Migration successful!
echo  Database: %APP_DIR%\schedule.db
echo ============================================================
pause
endlocal
