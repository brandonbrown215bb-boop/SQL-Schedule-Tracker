"""UpdateService — version check, smart config merging, and update script generation.

Zero Qt dependencies. Used by main.py and MainWindow.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy

import yaml

from services.config_service import ConfigService

logger = logging.getLogger(__name__)


class UnsafeInstallationDirectoryError(Exception):
    """Raised when an update is attempted in an unsafe personal or system root folder."""


class UpdateService:
    """Service for handling application auto-updates from a network folder."""

    def __init__(self, application_path: str):
        self.application_path = application_path

    @staticmethod
    def get_forbidden_directories() -> set[str]:
        """Collect paths of personal root folders and system directories where the app should never be loose."""
        forbidden: set[str] = set()

        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            forbidden.add(os.path.realpath(userprofile).lower())

        home = os.path.expanduser("~")
        if home:
            forbidden.add(os.path.realpath(home).lower())

        # Standard user subdirectories under userprofile / home
        standard_names = ["documents", "desktop", "downloads", "pictures", "music", "videos"]
        for base in [userprofile, home]:
            if base:
                for name in standard_names:
                    forbidden.add(os.path.realpath(os.path.join(base, name)).lower())

        # Windows registry User Shell Folders (handles OneDrive folder redirection)
        if sys.platform == "win32":
            try:
                import winreg

                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                )
                reg_names = [
                    "Personal",  # Documents
                    "Desktop",
                    "{374DE290-123F-4565-9164-39C4925E467B}",  # Downloads
                    "My Pictures",
                    "My Music",
                    "My Video",
                ]
                for reg_name in reg_names:
                    try:
                        val, _ = winreg.QueryValueEx(key, reg_name)
                        expanded = os.path.expandvars(val)
                        forbidden.add(os.path.realpath(expanded).lower())
                    except FileNotFoundError:
                        pass
                winreg.CloseKey(key)
            except Exception:
                pass

        # System and root environment directories
        for env_var in ["SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "APPDATA", "LOCALAPPDATA"]:
            val = os.environ.get(env_var)
            if val:
                forbidden.add(os.path.realpath(val).lower())

        return forbidden

    @staticmethod
    def is_safe_install_dir(path: str, update_source_dir: str = "") -> tuple[bool, str]:
        """Check if an application installation directory is safe from file conflicts.

        Args:
            path: Directory where the local app is installed.
            update_source_dir: Optional path to network deployment share.

        Returns:
            Tuple of (is_safe: bool, reason: str).
        """
        if not path or not path.strip():
            return False, "Application path is empty"

        abs_path = os.path.realpath(os.path.abspath(path)).lower().rstrip("\\/")

        # Check drive root (e.g. C:, D:)
        drive, rest = os.path.splitdrive(abs_path)
        if not rest or rest in ("\\", "/"):
            return False, f"Application cannot be installed directly in drive root '{path}'"

        # Check forbidden personal/system folders
        forbidden = UpdateService.get_forbidden_directories()
        if abs_path in forbidden:
            return False, f"Application cannot be installed directly in protected/personal directory '{path}'"

        # Check update_source_dir
        if update_source_dir:
            abs_source = os.path.realpath(os.path.abspath(update_source_dir)).lower().rstrip("\\/")
            if abs_path == abs_source:
                return False, f"Application cannot be installed inside update source directory '{path}'"

        return True, ""

    @staticmethod
    def create_desktop_shortcut(
        target_exe: str, shortcut_name: str = "Detailing Schedule.lnk", description: str = "Detailing Schedule Tracker"
    ) -> str | None:
        """Create a Windows desktop shortcut pointing to the application executable."""
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if sys.platform == "win32":
            import winreg

            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
                )
                val, _ = winreg.QueryValueEx(key, "Desktop")
                winreg.CloseKey(key)
                desktop = os.path.expandvars(val)
            except Exception:
                pass

        if not os.path.isdir(desktop):
            logger.warning("Desktop folder not found at %s", desktop)
            return None

        shortcut_path = os.path.join(desktop, shortcut_name)
        ps_cmd = (
            f"$WshShell = New-Object -ComObject WScript.Shell; "
            f"$Shortcut = $WshShell.CreateShortcut('{shortcut_path}'); "
            f"$Shortcut.TargetPath = '{target_exe}'; "
            f"$Shortcut.WorkingDirectory = '{os.path.dirname(target_exe)}'; "
            f"$Shortcut.Description = '{description}'; "
            f"$Shortcut.Save()"
        )
        creation_flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                creationflags=creation_flags,
            )
            if res.returncode == 0 and os.path.exists(shortcut_path):
                logger.info("Successfully created desktop shortcut at %s", shortcut_path)
                return shortcut_path
            logger.error("PowerShell shortcut creation failed: %s", res.stderr)
        except Exception as e:
            logger.error("Failed to create desktop shortcut: %s", e)
        return None

    @classmethod
    def migrate_to_dedicated_folder(
        cls, current_app_path: str, target_dir: str | None = None
    ) -> tuple[bool, str, str]:
        """Safely copy the application and its config into a dedicated directory.

        Default destination is %LOCALAPPDATA%\\Programs\\Detailing Schedule.
        Also creates a Desktop shortcut. Old personal documents are NEVER deleted.

        Args:
            current_app_path: Current folder where app/config is located.
            target_dir: Optional target folder. Defaults to %LOCALAPPDATA%\\Programs\\Detailing Schedule.

        Returns:
            Tuple of (success: bool, target_exe_path: str, message: str).
        """
        if not target_dir:
            local_appdata = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
            target_dir = os.path.join(local_appdata, "Programs", "Detailing Schedule")

        try:
            os.makedirs(target_dir, exist_ok=True)

            # Locate the executable to copy
            exe_name = "Detailing Schedule.exe"
            source_exe = os.path.join(current_app_path, exe_name)
            if not os.path.exists(source_exe) and getattr(sys, "frozen", False):
                source_exe = sys.executable

            target_exe = os.path.join(target_dir, exe_name)
            if os.path.exists(source_exe):
                shutil.copy2(source_exe, target_exe)
            else:
                logger.warning("Source executable not found at %s during migration", source_exe)

            # Copy config.yaml if present
            source_config = os.path.join(current_app_path, "config.yaml")
            target_config = os.path.join(target_dir, "config.yaml")
            if os.path.exists(source_config):
                shutil.copy2(source_config, target_config)

            # Copy version.txt if present
            source_version = os.path.join(current_app_path, "version.txt")
            target_version = os.path.join(target_dir, "version.txt")
            if os.path.exists(source_version):
                shutil.copy2(source_version, target_version)

            # Copy local databases if present (*.db)
            if os.path.isdir(current_app_path):
                for fname in os.listdir(current_app_path):
                    if fname.endswith(".db"):
                        shutil.copy2(os.path.join(current_app_path, fname), os.path.join(target_dir, fname))

            # Create Desktop shortcut
            cls.create_desktop_shortcut(target_exe)

            msg = f"Application successfully moved to:\n{target_dir}"
            logger.info(msg)
            return True, target_exe, msg
        except Exception as e:
            err_msg = f"Failed to migrate application: {e}"
            logger.error(err_msg)
            return False, "", err_msg

    def get_local_version(self) -> str:
        """Read the local version.txt next to the executable.

        Returns:
            Version string (e.g. '1.0.0'), or '0.0.0' if missing/invalid.
        """
        path = os.path.join(self.application_path, "version.txt")
        if not os.path.exists(path):
            logger.info("Local version.txt not found at %s. Defaulting to 0.0.0", path)
            return "0.0.0"

        try:
            with open(path, encoding="utf-8") as f:
                return f.readline().strip() or "0.0.0"
        except Exception as e:
            logger.error("Failed to read local version.txt: %s. Defaulting to 0.0.0", e)
            return "0.0.0"

    def get_remote_version(self, update_source_dir: str) -> str | None:
        """Read the version.txt from the network deployment folder.

        Args:
            update_source_dir: Path to the network deployment folder.

        Returns:
            Version string, or None if network folder is unreachable/unreadable.
        """
        if not update_source_dir or not os.path.isdir(update_source_dir):
            logger.info("Network update directory %s is invalid or unreachable", update_source_dir)
            return None

        path = os.path.join(update_source_dir, "version.txt")
        if not os.path.exists(path):
            logger.info("Remote version.txt not found at %s", path)
            return None

        try:
            with open(path, encoding="utf-8") as f:
                return f.readline().strip() or None
        except Exception as e:
            logger.error("Failed to read remote version.txt: %s", e)
            return None

    @staticmethod
    def compare_versions(v1: str, v2: str) -> int:
        """Compare two version strings semantically.

        Args:
            v1: First version string (e.g. '1.2.10').
            v2: Second version string (e.g. '1.2.3').

        Returns:
            1 if v1 > v2, -1 if v1 < v2, 0 if v1 == v2.
        """
        def parse(v: str) -> list[int]:
            clean = v.strip().lower().lstrip("v")
            parts = []
            for part in clean.split("."):
                try:
                    parts.append(int(part))
                except ValueError:
                    parts.append(0)
            return parts

        p1 = parse(v1)
        p2 = parse(v2)

        # Pad lists with zeros to compare them at equal lengths
        max_len = max(len(p1), len(p2))
        p1 += [0] * (max_len - len(p1))
        p2 += [0] * (max_len - len(p2))

        if p1 > p2:
            return 1
        elif p1 < p2:
            return -1
        return 0

    def check_for_update(self, update_source_dir: str) -> tuple[bool, str, str]:
        """Check if a new update is available on the network share.

        Args:
            update_source_dir: Path to the network folder.

        Returns:
            Tuple of (update_available: bool, local_version: str, remote_version: str).
        """
        local_v = self.get_local_version()
        remote_v = self.get_remote_version(update_source_dir)

        if not remote_v:
            return False, local_v, "0.0.0"

        is_newer = self.compare_versions(remote_v, local_v) > 0
        return is_newer, local_v, remote_v

    def smart_merge_config(self, remote_config_path: str, local_config_path: str) -> bool:
        """Deep merge local configuration settings on top of the remote config template.

        Preserves user paths and preferences while incorporating new default configuration keys.

        Args:
            remote_config_path: Path to the remote network config.yaml template.
            local_config_path: Path to the user's local config.yaml.

        Returns:
            True if merged and saved successfully, False otherwise.
        """
        if not os.path.exists(remote_config_path):
            logger.warning("Remote template config does not exist at %s, skipping merge", remote_config_path)
            return False

        try:
            with open(remote_config_path, encoding="utf-8") as f:
                remote_cfg = yaml.safe_load(f) or {}

            # Load local config if it exists
            local_cfg = {}
            if os.path.exists(local_config_path):
                with open(local_config_path, encoding="utf-8") as f:
                    local_cfg = yaml.safe_load(f) or {}

            # Perform deep merge: start with remote network template, merge local user config on top
            merged_cfg = deepcopy(remote_cfg)
            ConfigService._deep_merge(merged_cfg, local_cfg)

            # Save merged config back locally
            ConfigService.save(local_config_path, merged_cfg)
            logger.info("Successfully merged config saved to %s", local_config_path)
            return True
        except Exception as e:
            logger.error("Failed to smart-merge config.yaml: %s", e)
            return False

    @staticmethod
    def clean_pyinstaller_env(env: dict[str, str] | None = None) -> dict[str, str]:
        """Return an environment dictionary stripped of PyInstaller runtime and IPC variables.

        Ensures child processes or restarted instances unpack into a fresh temporary
        runtime folder rather than inheriting references to a terminating process's
        _MEIxxxxxx directory (which triggers 'Failed to load Python DLL').

        Args:
            env: Optional environment dictionary to sanitize. Defaults to os.environ.copy().

        Returns:
            Sanitized environment dictionary with PYINSTALLER_RESET_ENVIRONMENT=1.
        """
        clean = os.environ.copy() if env is None else env.copy()

        # Remove all PyInstaller internal variables
        keys_to_remove = [
            k for k in clean
            if k.startswith(("_PYI_", "_MEI")) or k in ("_MEIPASS", "_MEIPASS2")
        ]
        for k in keys_to_remove:
            clean.pop(k, None)

        # Force PyInstaller bootloader to treat any new instance as a top-level process
        clean["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

        # Remove the temporary _MEI directory from PATH if present
        mei_dir = getattr(sys, "_MEIPASS", None)
        path = clean.get("PATH", "")
        if path:
            cleaned_parts = []
            for part in path.split(os.pathsep):
                part_stripped = part.strip()
                if not part_stripped:
                    continue
                if mei_dir and os.path.realpath(part_stripped).lower() == os.path.realpath(mei_dir).lower():
                    continue
                if "_mei" in os.path.basename(part_stripped.lower()):
                    continue
                cleaned_parts.append(part_stripped)
            clean["PATH"] = os.pathsep.join(cleaned_parts)

        return clean

    def generate_updater_script(self, update_source_dir: str, local_app_dir: str) -> str:
        """Create a temporary Windows batch file to update app files.

        The batch file waits for the running exe to close, creates a backup,
        robocopies ONLY the application binaries from network share (NEVER using /MIR or /PURGE),
        checks exit codes with automatic rollback on error, and restarts the app.

        Args:
            update_source_dir: Directory containing the new app files.
            local_app_dir: Directory where the local app is installed.

        Returns:
            Absolute path to the generated batch file.

        Raises:
            UnsafeInstallationDirectoryError: If local_app_dir is an unsafe personal or system directory.
        """
        safe, reason = self.is_safe_install_dir(local_app_dir, update_source_dir)
        if not safe:
            raise UnsafeInstallationDirectoryError(
                f"Cannot update unsafe installation directory '{local_app_dir}': {reason}"
            )

        batch_template = f"""@echo off
title Updating Detailing Schedule...

rem Clear all PyInstaller runtime and IPC variables so restarted app extracts a clean temporary runtime
set _MEIPASS=
set _MEIPASS2=
set _PYI_APPLICATION_HOME_DIR=
set _PYI_PARENT_PROCESS_LEVEL=
set _PYI_ARCHIVE_FILE=
set _PYI_SPLASH_IPC=
set _PYI_LINUX_PROCESS_NAME=
set PYINSTALLER_RESET_ENVIRONMENT=1

set LOG_FILE=%TEMP%\\detailing_schedule_update.log
echo ====================================================== > "%LOG_FILE%"
echo Detailing Schedule Update Started: %DATE% %TIME% >> "%LOG_FILE%"
echo Source: "{update_source_dir}" >> "%LOG_FILE%"
echo Destination: "{local_app_dir}" >> "%LOG_FILE%"

echo Waiting for application to exit...

:wait_loop
tasklist /FI "IMAGENAME eq Detailing Schedule.exe" 2>NUL | find /I /N "Detailing Schedule.exe">NUL
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >nul
    goto wait_loop
)

rem Extra pause to guarantee process file locks & PyInstaller cleanup complete
timeout /t 2 /nobreak >nul

rem Backup existing executable if present
if exist "{local_app_dir}\\Detailing Schedule.exe" (
    copy /y "{local_app_dir}\\Detailing Schedule.exe" "{local_app_dir}\\Detailing Schedule.exe.bak" >nul 2>&1
)

echo.
echo Copying new version files from network share...
rem Explicitly target ONLY application binaries. Never mirror or purge destination.
robocopy "{update_source_dir}" "{local_app_dir}" "Detailing Schedule.exe" "version.txt" /R:3 /W:5 >> "%LOG_FILE%" 2>&1

rem Robocopy exit codes 0-7 indicate success or no changes; 8+ indicates serious failure
if %ERRORLEVEL% GEQ 8 (
    echo. >> "%LOG_FILE%"
    echo ERROR: Robocopy failed with error code %ERRORLEVEL%. >> "%LOG_FILE%"
    echo Update failed! Restoring backup...
    if exist "{local_app_dir}\\Detailing Schedule.exe.bak" (
        copy /y "{local_app_dir}\\Detailing Schedule.exe.bak" "{local_app_dir}\\Detailing Schedule.exe" >nul 2>&1
    )
    echo Update could not be completed. Please check "%LOG_FILE%".
    pause
    exit /b 1
)

rem Success - remove backup
if exist "{local_app_dir}\\Detailing Schedule.exe.bak" (
    del /f /q "{local_app_dir}\\Detailing Schedule.exe.bak" >nul 2>&1
)

echo.
echo Restarting application...
set _MEIPASS=
set _MEIPASS2=
set _PYI_APPLICATION_HOME_DIR=
set _PYI_PARENT_PROCESS_LEVEL=
set _PYI_ARCHIVE_FILE=
set _PYI_SPLASH_IPC=
set _PYI_LINUX_PROCESS_NAME=
set PYINSTALLER_RESET_ENVIRONMENT=1
start "" /D "{local_app_dir}" "{local_app_dir}\\Detailing Schedule.exe"

echo.
echo Update complete!
timeout /t 2 >nul
exit /b 0
"""
        temp_dir = tempfile.gettempdir()
        batch_path = os.path.join(temp_dir, "update_detailing_schedule.bat")

        try:
            with open(batch_path, "w", encoding="cp1252") as f:
                f.write(batch_template)
            logger.info("Generated updater batch file at %s", batch_path)
            return batch_path
        except Exception as e:
            logger.error("Failed to generate updater batch file: %s", e)
            raise

