@echo off
REM ============================================================
REM deploy.bat — Auto-bump, build, and deploy the application
REM Run from: repo root (where main.py lives)
REM ============================================================
setlocal

REM Activate venv if it exists, otherwise fall back to system Python
if exist ".venv\Scripts\python.exe" (
    set PY=.venv\Scripts\python.exe
) else (
    set PY=py -3.14
)

REM Execute the bump and deploy script
%PY% "%~dp0automation\bump_and_deploy.py" %*

endlocal
