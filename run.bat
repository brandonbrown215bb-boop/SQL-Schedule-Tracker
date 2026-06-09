@echo off
REM ============================================================
REM run.bat — Launch the Schedule Tracker application
REM Run from: repo root (where main.py lives)
REM ============================================================
setlocal

REM Activate venv if it exists, otherwise fall back to system Python
if exist ".venv\Scripts\python.exe" (
    set PY=.venv\Scripts\python.exe
) else (
    set PY=py -3.14
)

REM Check that schedule.db exists (in parent dir alongside the .xlsm)
if not exist "%~dp0..\schedule.db" (
    echo ============================================================
    echo  WARNING: schedule.db not found!
    echo.
    echo  Run migrate.bat first to create the database from your
    echo  Excel workbook.
    echo ============================================================
    pause
    exit /b 1
)

echo Starting Schedule Tracker...
echo.

%PY% "%~dp0main.py" %*

endlocal
