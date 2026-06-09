@echo off
REM ============================================================
REM test.bat — Run the test suite
REM Run from: repo root (where main.py lives)
REM ============================================================
setlocal

REM Activate venv if it exists, otherwise fall back to system Python
if exist ".venv\Scripts\python.exe" (
    set PY=.venv\Scripts\python.exe
) else (
    set PY=py -3.14
)

echo Running tests...
echo.

%PY% -m pytest tests/ -m "not integration and not slow" --tb=short -q %*

echo.
if errorlevel 1 (
    echo TESTS FAILED
) else (
    echo ALL TESTS PASSED
)
echo.

pause
endlocal
