"""UpdateService — version check, smart config merging, and update script generation.

Zero Qt dependencies. Used by main.py and MainWindow.
"""

from __future__ import annotations

import logging
import os
import tempfile
from copy import deepcopy
import yaml
from services.config_service import ConfigService

logger = logging.getLogger(__name__)


class UpdateService:
    """Service for handling application auto-updates from a network folder."""

    def __init__(self, application_path: str):
        self.application_path = application_path

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
            with open(path, "r", encoding="utf-8") as f:
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
            with open(path, "r", encoding="utf-8") as f:
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
            with open(remote_config_path, "r", encoding="utf-8") as f:
                remote_cfg = yaml.safe_load(f) or {}
            
            # Load local config if it exists
            local_cfg = {}
            if os.path.exists(local_config_path):
                with open(local_config_path, "r", encoding="utf-8") as f:
                    local_cfg = yaml.safe_load(f) or {}

            # Perform deep merge: local_cfg overrides/merges into remote_cfg
            merged_cfg = deepcopy(remote_cfg)
            ConfigService._deep_merge(merged_cfg, local_cfg)

            # Save merged config back locally
            ConfigService.save(local_config_path, merged_cfg)
            logger.info("Successfully merged config saved to %s", local_config_path)
            return True
        except Exception as e:
            logger.error("Failed to smart-merge config.yaml: %s", e)
            return False

    def generate_updater_script(self, update_source_dir: str, local_app_dir: str) -> str:
        """Create a temporary Windows batch file to update app files.

        The batch file waits for the running exe to close, robocopies all files
        from network share (excluding config/db/logs/etc.), and restarts the app.

        Args:
            update_source_dir: Directory containing the new app files.
            local_app_dir: Directory where the local app is installed.

        Returns:
            Absolute path to the generated batch file.
        """
        # Robocopy arguments:
        # /MIR: Mirror directory tree (deletes files in dest that don't exist in source)
        # /XD: Exclude directories (backups, caches)
        # /XF: Exclude files (config.yaml, local database files, logs, updater batch)
        # /R:3: 3 retries on failed copy
        # /W:5: 5 seconds wait between retries
        batch_template = f"""@echo off
title Updating Detailing Schedule...
echo Waiting for application to exit...

:wait_loop
tasklist /FI "IMAGENAME eq Detailing Schedule.exe" 2>NUL | find /I /N "Detailing Schedule.exe">NUL
if "%ERRORLEVEL%"=="0" (
    timeout /t 1 /nobreak >nul
    goto wait_loop
)

echo.
echo Copying new version files from network share...
robocopy "{update_source_dir}" "{local_app_dir}" /MIR /XD "backups" "csv_cache" "Unedited Reports" /XF "config.yaml" "*.db" "*.log" "update_detailing_schedule.bat" /R:3 /W:5

echo.
echo Restarting application...
start "" "{local_app_dir}\\Detailing Schedule.exe"

echo.
echo Update complete!
timeout /t 2 >nul
exit
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
