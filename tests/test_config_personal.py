"""Per-user vs shared config: no personal settings leak through the network template."""

from __future__ import annotations

import os

import pytest
import yaml

from automation.deploy import prepare_production_config
from services.config_service import ConfigService


def _write(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)


def _setup(tmp_path, local: dict, template: dict) -> str:
    share = tmp_path / "share"
    share.mkdir()
    _write(str(share / "config.yaml"), template)
    local = {"update_source_dir": str(share), **local}
    local_path = str(tmp_path / "config.yaml")
    _write(local_path, local)
    return local_path


LEAKY_TEMPLATE = {
    "ssrs_url": "http://new/report",
    "default_detailers": ["— Unassigned —", "Cancelled", "Jackie H"],
    "multi_user": {"enabled": True, "username": "jbrow263", "machine": "PC1"},
    "ui": {"theme": "dark", "high_contrast": True},
}


def test_template_username_and_ui_never_inherited(tmp_path):
    path = _setup(tmp_path, {"sqlite_path": "x.db"}, LEAKY_TEMPLATE)
    cfg = ConfigService.load(path)
    assert cfg["multi_user"]["username"] == ""
    assert cfg["multi_user"]["machine"] == ""
    assert cfg["ui"]["theme"] == "light"
    assert cfg["ui"]["high_contrast"] is False


def test_template_personal_keys_ignored_when_template_preferred(tmp_path):
    path = _setup(
        tmp_path,
        {"sqlite_path": "x.db", "multi_user": {"username": "Pat"}, "ui": {"theme": "light"}},
        LEAKY_TEMPLATE,
    )
    cfg = ConfigService.load(path, prefer_template=True)
    assert cfg["multi_user"]["username"] == "Pat"
    assert cfg["ui"]["theme"] == "light"


def test_template_wins_for_shared_keys_when_preferred(tmp_path):
    path = _setup(
        tmp_path,
        {
            "sqlite_path": "x.db",
            "ssrs_url": "http://old/report",
            "default_detailers": ["— Unassigned —", "Cancelled", "Jackie H", "Former Person"],
        },
        LEAKY_TEMPLATE,
    )
    cfg = ConfigService.load(path, prefer_template=True)
    assert cfg["ssrs_url"] == "http://new/report"
    # Removed from the template -> removed locally too (lists are replaced, not unioned)
    assert cfg["default_detailers"] == ["— Unassigned —", "Cancelled", "Jackie H"]


def test_local_wins_for_shared_keys_in_development(tmp_path):
    path = _setup(tmp_path, {"sqlite_path": "x.db", "ssrs_url": "http://old/report"}, LEAKY_TEMPLATE)
    cfg = ConfigService.load(path)
    assert cfg["ssrs_url"] == "http://old/report"


def test_deploy_strips_personal_keys(tmp_path):
    src = str(tmp_path / "dev.yaml")
    dest = str(tmp_path / "prod.yaml")
    _write(src, {"sqlite_path": "C:\\dev.db", **LEAKY_TEMPLATE})
    prepare_production_config(src, dest, "P:\\share")
    with open(dest, encoding="utf-8") as f:
        prod = yaml.safe_load(f)
    assert "ui" not in prod
    assert "username" not in prod["multi_user"]
    assert "machine" not in prod["multi_user"]
    assert prod["multi_user"]["enabled"] is True
    assert prod["ssrs_url"] == "http://new/report"
    assert prod["update_source_dir"] == "P:\\share"


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = str(tmp_path / "config.yaml")
    ConfigService.save(path, {"sqlite_path": "a.db", "config_path": "runtime-only"})
    ConfigService.save(path, {"sqlite_path": "b.db"})
    with open(path, encoding="utf-8") as f:
        assert yaml.safe_load(f) == {"sqlite_path": "b.db"}
    assert os.listdir(tmp_path) == ["config.yaml"]


def test_save_failure_keeps_previous_file(tmp_path, monkeypatch):
    path = str(tmp_path / "config.yaml")
    ConfigService.save(path, {"sqlite_path": "a.db"})

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(yaml, "safe_dump", boom)
    with pytest.raises(OSError):
        ConfigService.save(path, {"sqlite_path": "b.db"})
    with open(path, encoding="utf-8") as f:
        assert yaml.safe_load(f) == {"sqlite_path": "a.db"}
    assert os.listdir(tmp_path) == ["config.yaml"]


def test_username_belongs_to():
    belongs = ConfigService.username_belongs_to
    # Recorded login decides
    assert belongs({"username": "Pat S", "os_user": "psmith"}, "PSmith")
    assert not belongs({"username": "Pat S", "os_user": "psmith"}, "jdoe")
    # Older configs without a record: only trusted if the name is the login itself
    assert belongs({"username": "jdoe"}, "jdoe")
    assert not belongs({"username": "jbrow263"}, "jdoe")
