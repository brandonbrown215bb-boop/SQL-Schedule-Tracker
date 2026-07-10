"""Unit tests for the UpdateService class."""

from __future__ import annotations

import os
import shutil
import tempfile
import pytest
import yaml
from services.update_service import UpdateService


@pytest.fixture
def temp_dir():
    """Fixture to provide a clean temporary directory for file I/O tests."""
    dir_path = tempfile.mkdtemp()
    yield dir_path
    shutil.rmtree(dir_path)


class TestUpdateService:
    def test_compare_versions(self):
        # Equal versions
        assert UpdateService.compare_versions("1.0.0", "1.0.0") == 0
        assert UpdateService.compare_versions("v1.2.3", "1.2.3") == 0
        assert UpdateService.compare_versions("  1.0  ", "1.0.0") == 0

        # Newer versions
        assert UpdateService.compare_versions("1.0.1", "1.0.0") == 1
        assert UpdateService.compare_versions("1.2.0", "1.1.9") == 1
        assert UpdateService.compare_versions("1.2.10", "1.2.3") == 1
        assert UpdateService.compare_versions("2.0", "1.9.9") == 1
        assert UpdateService.compare_versions("v2.1", "v2.0.9") == 1

        # Older versions
        assert UpdateService.compare_versions("1.0.0", "1.0.1") == -1
        assert UpdateService.compare_versions("1.1.9", "1.2.0") == -1
        assert UpdateService.compare_versions("1.2.3", "1.2.10") == -1
        assert UpdateService.compare_versions("1.9.9", "2.0") == -1

    def test_get_local_version_missing(self, temp_dir):
        service = UpdateService(temp_dir)
        assert service.get_local_version() == "0.0.0"

    def test_get_local_version_valid(self, temp_dir):
        service = UpdateService(temp_dir)
        version_file = os.path.join(temp_dir, "version.txt")
        with open(version_file, "w", encoding="utf-8") as f:
            f.write("1.2.3\n")
        assert service.get_local_version() == "1.2.3"

    def test_get_local_version_invalid(self, temp_dir):
        service = UpdateService(temp_dir)
        version_file = os.path.join(temp_dir, "version.txt")
        # Empty file
        with open(version_file, "w", encoding="utf-8") as f:
            f.write("")
        assert service.get_local_version() == "0.0.0"

    def test_get_remote_version_missing_dir(self, temp_dir):
        service = UpdateService(temp_dir)
        assert service.get_remote_version(os.path.join(temp_dir, "nonexistent")) is None

    def test_get_remote_version_missing_file(self, temp_dir):
        service = UpdateService(temp_dir)
        remote_dir = os.path.join(temp_dir, "remote")
        os.makedirs(remote_dir)
        assert service.get_remote_version(remote_dir) is None

    def test_get_remote_version_valid(self, temp_dir):
        service = UpdateService(temp_dir)
        remote_dir = os.path.join(temp_dir, "remote")
        os.makedirs(remote_dir)
        version_file = os.path.join(remote_dir, "version.txt")
        with open(version_file, "w", encoding="utf-8") as f:
            f.write("1.5.0\n")
        assert service.get_remote_version(remote_dir) == "1.5.0"

    def test_check_for_update(self, temp_dir):
        # Setup local
        service = UpdateService(temp_dir)
        with open(os.path.join(temp_dir, "version.txt"), "w", encoding="utf-8") as f:
            f.write("1.0.0\n")

        # Setup remote
        remote_dir = os.path.join(temp_dir, "remote")
        os.makedirs(remote_dir)

        # 1. Remote is newer
        with open(os.path.join(remote_dir, "version.txt"), "w", encoding="utf-8") as f:
            f.write("1.0.1\n")
        available, local_v, remote_v = service.check_for_update(remote_dir)
        assert available is True
        assert local_v == "1.0.0"
        assert remote_v == "1.0.1"

        # 2. Remote is same
        with open(os.path.join(remote_dir, "version.txt"), "w", encoding="utf-8") as f:
            f.write("1.0.0\n")
        available, _, _ = service.check_for_update(remote_dir)
        assert available is False

        # 3. Remote is older
        with open(os.path.join(remote_dir, "version.txt"), "w", encoding="utf-8") as f:
            f.write("0.9.9\n")
        available, _, _ = service.check_for_update(remote_dir)
        assert available is False

        # 4. Remote is unreachable
        available, _, _ = service.check_for_update(os.path.join(temp_dir, "nonexistent"))
        assert available is False

    def test_smart_merge_config(self, temp_dir):
        service = UpdateService(temp_dir)

        # Local settings
        local_cfg = {
            "sqlite_path": "C:\\local\\schedule.db",
            "excel_path": "C:\\local\\master.xlsx",
            "ui": {
                "theme": "dark",
                "high_contrast": True,
                "list_sort_column": "job_name",
            }
        }
        local_config_path = os.path.join(temp_dir, "config.yaml")
        with open(local_config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(local_cfg, f)

        # Remote settings (new version template with new key)
        remote_cfg = {
            "sqlite_path": "P:\\remote\\schedule.db",
            "excel_path": "P:\\remote\\master.xlsm",
            "new_feature_key": "some_value",
            "ui": {
                "theme": "light",
                "new_ui_setting": 42,
                "list_sort_column": "detailing_due_date",
            }
        }
        remote_dir = os.path.join(temp_dir, "remote")
        os.makedirs(remote_dir)
        remote_config_path = os.path.join(remote_dir, "config.yaml")
        with open(remote_config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(remote_cfg, f)

        # Perform smart merge
        success = service.smart_merge_config(remote_config_path, local_config_path)
        assert success is True

        # Load merged config and verify values
        with open(local_config_path, "r", encoding="utf-8") as f:
            merged = yaml.safe_load(f)

        # Assert local values preserved
        assert merged["sqlite_path"] == "C:\\local\\schedule.db"
        assert merged["excel_path"] == "C:\\local\\master.xlsx"
        assert merged["ui"]["theme"] == "dark"
        assert merged["ui"]["high_contrast"] is True
        assert merged["ui"]["list_sort_column"] == "job_name"

        # Assert remote new keys incorporated
        assert merged["new_feature_key"] == "some_value"
        assert merged["ui"]["new_ui_setting"] == 42

    def test_generate_updater_script(self, temp_dir):
        service = UpdateService(temp_dir)
        update_source = "P:\\Detailing Schedule 2019\\Schedule App"
        local_app = "C:\\Detailing Schedule App"

        batch_path = service.generate_updater_script(update_source, local_app)
        assert os.path.exists(batch_path)
        assert batch_path.endswith(".bat")

        with open(batch_path, "r", encoding="cp1252") as f:
            content = f.read()

        # Check that it contains the robocopy command with correct paths
        assert "robocopy" in content
        assert f'robocopy "{update_source}" "{local_app}"' in content
        assert "Detailing Schedule.exe" in content

        # Clean up batch file
        os.remove(batch_path)
