@echo off
REM ============================================================
REM setup.bat — One-time environment setup for Schedule Tracker
REM Run from: repo root (where main.py lives)
REM ============================================================
setlocal

echo ============================================================
echo  Schedule Tracker — Windows Setup
echo ============================================================
echo.

REM Check for Python 3.14+ (the one with openpyxl installed)
set PYTHON_CMD=
for %%v in (3.14 3.13 3.12 3.11) do (
    where python%%v >nul 2>&1 && set PYTHON_CMD=python%%v && goto :found_python
)
REM Try py launcher with version
where py >nul 2>&1 && (
    py -3.14 -c "import sys; exit(0)" >nul 2>&1 && set PYTHON_CMD=py -3.14 && goto :found_python
    py -3.13 -c "import sys; exit(0)" >nul 2>&1 && set PYTHON_CMD=py -3.13 && goto :found_python
)
echo ERROR: No Python 3.11+ found. Install from python.org or Microsoft Store.
exit /b 1

:found_python
echo [OK] Python found: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.

REM Create venv if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create venv.
        exit /b 1
    )
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)

REM Activate venv
call .venv\Scripts\activate.bat

REM Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install runtime dependencies
echo.
echo Installing dependencies from requirements.txt...
if exist "requirements.txt" (
    python -m pip install -r requirements.txt
) else (
    echo WARNING: requirements.txt not found. Installing core deps directly...
    python -m pip install "openpyxl>=3.1.0,<4.0.0" "PyQt5>=5.15.0,<6.0.0" "PyQtChart>=5.15.0,<6.0.0" "PyYAML>=6.0,<7.0"
)

REM Install dev dependencies
echo.
echo Installing dev dependencies ^(pytest, ruff^)...
python -m pip install "pytest>=8.0,<10.0" "pytest-cov>=5.0,<7.0" "ruff>=0.8.0,<1.0.0"

echo.
echo ============================================================
echo  Setup complete!
echo.
echo  To migrate:  double-click migrate.bat
echo  To run app:  double-click run.bat
echo ============================================================
pause
endlocal
