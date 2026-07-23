@echo off
setlocal enabledelayedexpansion

REM Get the directory where this batch file is located
set "APP_DIR=%~dp0"
set "CONFIG_PATH=%APP_DIR%config.yaml"

echo Checking for config.yaml...
if not exist "%CONFIG_PATH%" (
    echo [ERROR] config.yaml not found in:
    echo %APP_DIR%
    echo.
    echo Please make sure this batch file is placed in the same folder as the application and config.yaml.
    goto end
)

REM Check if update_source_dir is already set
findstr /i "update_source_dir:" "%CONFIG_PATH%" >nul
if %errorlevel% equ 0 (
    echo [INFO] update_source_dir is already configured in config.yaml.
    echo No changes were made.
    goto end
)

echo Appending update_source_dir to config.yaml...
REM Add a newline first to ensure it doesn't append to the end of an existing line
echo.>>"%CONFIG_PATH%"
echo update_source_dir: P:\Detailing Schedule 2019\Schedule App>>"%CONFIG_PATH%"

echo [SUCCESS] Added update_source_dir to config.yaml successfully!

:end
echo.
pause
