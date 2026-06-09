@echo off
REM ============================================================
REM ensure_detailers.bat — Add detailers table if missing
REM Run from: SQL-Schedule-Tracker\
REM ============================================================
setlocal

if exist ".venv\Scripts\python.exe" (
    set PY=.venv\Scripts\python.exe
) else (
    set PY=py -3.14
)

set "SCRIPT_DIR=%~dp0..\scripts"

%PY% "%SCRIPT_DIR%\ensure_detailers.py" --db "%~dp0..\schedule.db"

pause
endlocal
