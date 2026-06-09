@echo off
REM ============================================================
REM migrate.bat — Migrate Excel workbook to SQLite database
REM Run from: repo root (where main.py lives)
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

REM Paths: repo root is where this .bat lives; parent has the .xlsm
set "REPO_DIR=%~dp0"
set "APP_DIR=%~dp0.."
set "SCRIPT_DIR=%~dp0scripts"

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

echo.
echo Ensuring detailers table is seeded...
%PY% "%SCRIPT_DIR%\ensure_detailers.py" --db "%APP_DIR%\schedule.db"

pause
endlocal
