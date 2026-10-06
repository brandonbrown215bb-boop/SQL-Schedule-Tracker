@echo off
title Installing Detailing Schedule...
echo ============================================================
echo           Detailing Schedule — Quick Setup
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "TARGET_DIR=%LOCALAPPDATA%\Programs\Detailing Schedule"

echo Target installation folder: %TARGET_DIR%
if not exist "%TARGET_DIR%" (
    mkdir "%TARGET_DIR%"
)

echo.
echo Copying application files...
if exist "%SCRIPT_DIR%Detailing Schedule.exe" (
    copy /y "%SCRIPT_DIR%Detailing Schedule.exe" "%TARGET_DIR%\Detailing Schedule.exe" >nul
) else (
    echo Error: Detailing Schedule.exe not found in "%SCRIPT_DIR%".
    pause
    exit /b 1
)

if exist "%SCRIPT_DIR%config.yaml" (
    if not exist "%TARGET_DIR%\config.yaml" (
        copy /y "%SCRIPT_DIR%config.yaml" "%TARGET_DIR%\config.yaml" >nul
    )
)
if exist "%SCRIPT_DIR%version.txt" (
    copy /y "%SCRIPT_DIR%version.txt" "%TARGET_DIR%\version.txt" >nul
)

echo Creating Desktop shortcut...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Detailing Schedule.lnk')); $s.TargetPath = '%TARGET_DIR%\Detailing Schedule.exe'; $s.WorkingDirectory = '%TARGET_DIR%'; $s.Description = 'Detailing Schedule Tracker'; $s.Save()"

echo.
echo ============================================================
echo   Installation Complete!
echo   A shortcut has been placed on your Desktop.
echo ============================================================
echo.
echo Starting Detailing Schedule...
start "" /D "%TARGET_DIR%" "%TARGET_DIR%\Detailing Schedule.exe"
timeout /t 3 >nul
exit /b 0
