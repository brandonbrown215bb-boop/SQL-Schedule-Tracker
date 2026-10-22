@echo off
REM ============================================================
REM reconcile_workbook.bat — One last reconciliation against the frozen workbook
REM Without --apply this is a dry run: it only writes CSV reports.
REM   reconcile_workbook.bat            (dry run)
REM   reconcile_workbook.bat --apply    (backs up schedule.db, then writes)
REM Run from: repo root (where main.py lives)
REM ============================================================
setlocal

if exist ".venv\Scripts\python.exe" (
    set PY=.venv\Scripts\python.exe
) else (
    set PY=py -3.14
)

set "SCRIPT_DIR=%~dp0automation"
set "DB_PATH=%~dp0..\schedule.db"
set "WORKBOOK=%~dp0..\SCHDetailingReport_all_plants_MASTER.xlsm"

if not exist "%DB_PATH%" (
    echo ERROR: schedule.db not found at %DB_PATH%
    echo Run migrate.bat first.
    pause
    exit /b 1
)

echo Running reconcile_workbook.py...
echo Workbook: %WORKBOOK%
echo Database: %DB_PATH%
echo.

%PY% "%SCRIPT_DIR%\reconcile_workbook.py" --workbook "%WORKBOOK%" --db "%DB_PATH%" %*

pause
endlocal
