@echo off
REM ============================================================
REM cleanup_detailers.bat — Clean up detailer name inconsistencies
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

if not exist "%DB_PATH%" (
    echo ERROR: schedule.db not found at %DB_PATH%
    echo Run migrate.bat first.
    pause
    exit /b 1
)

echo Running cleanup_detailers.py...
echo Database: %DB_PATH%
echo.

%PY% "%SCRIPT_DIR%\cleanup_detailers.py" --db "%DB_PATH%" %* --apply

pause
endlocal
