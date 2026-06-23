"""ConfigService — config.yaml loading, validation, and persistence.

Zero Qt dependencies. Used by main.py and MainWindow.
"""

from __future__ import annotations

import logging
import os
from copy import deepcopy

import yaml

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULTS: dict = {
    "sqlite_path": "",
    "excel_path": "",
    "unedited_reports_dir": "",
    "ssrs_url": "",
    "ssrs_lookback_days": 30,
    "ssrs_lookahead_days": 365,
    "default_detailers": [],
    "status_labels": {},
    "multi_user": {
        "enabled": False,
        "fallback_mode": "block",
    },
    "ui": {
        "theme": "light",
        "colorblind_mode": "none",
        "high_contrast": False,
        "auto_refresh_minutes": 0,
        "last_view": "calendar",
        "splitter_sizes": None,
        "list_column_widths": {},
        "list_visible_columns": [],
        "list_sort_column": "detailing_due_date",
        "list_sort_ascending": True,
        "onboarding_completed": False,
    },
}

# Mandatory keys that must be present (but may be empty)
MANDATORY_KEYS = ["sqlite_path"]

# Keys that must be present with non-empty values for the app to function
REQUIRED_FOR_FUNCTION = ["sqlite_path"]


class ConfigValidationError(Exception):
    """Raised when config validation fails."""

    pass


class ConfigService:
    """Service for loading, validating, and persisting config.yaml.

    Usage:
        config = Config_service.load("/path/to/config.yaml")
        warnings = ConfigService.validate(config)
        ConfigService.save("/path/to/config.yaml", config)
    """

    @staticmethod
    def load(path: str) -> dict:
        """Load config from YAML file, merging with defaults.

        Args:
            path: Path to config.yaml.

        Returns:
            Config dict with defaults merged in.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ConfigValidationError: If config file is not valid YAML or not a dict.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"config.yaml not found at: {path}")

        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            raise ConfigValidationError(
                f"config.yaml did not parse as a valid mapping (dict), got {type(raw).__name__}"
            )

        # Deep merge with defaults
        config = deepcopy(DEFAULTS)
        ConfigService._deep_merge(config, raw)

        return config

    @staticmethod
    def validate(config: dict) -> list[str]:
        """Validate config dict. Returns list of warning/error messages.

        Args:
            config: Config dict to validate.

        Returns:
            List of warning/error strings. Empty list means valid.
        """
        warnings: list[str] = []

        for key in MANDATORY_KEYS:
            if key not in config:
                warnings.append(f"Missing mandatory key: {key}")

        for key in REQUIRED_FOR_FUNCTION:
            val = config.get(key)
            if not val:
                warnings.append(f"Required key is empty: {key}")

        # Validate types
        ui = config.get("ui", {})
        if not isinstance(ui.get("theme"), str):
            warnings.append("ui.theme should be a string")
        if ui.get("theme") not in ("light", "dark"):
            warnings.append(f"ui.theme should be 'light' or 'dark', got: {ui.get('theme')}")

        if not isinstance(ui.get("auto_refresh_minutes"), (int, float)):
            warnings.append("ui.auto_refresh_minutes should be a number")

        mu = config.get("multi_user", {})
        if not isinstance(mu.get("enabled"), bool):
            warnings.append("multi_user.enabled should be a boolean")

        return warnings

    @staticmethod
    def save(path: str, config: dict) -> None:
        """Save config dict to YAML file.

        Removes runtime-only keys before saving.

        Args:
            path: Path to config.yaml.
            config: Config dict to save.
        """
        # Remove runtime-only keys that should not be persisted
        save_config = {k: v for k, v in config.items() if k != "config_path"}

        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(save_config, f, default_flow_style=False, allow_unicode=True)

        logger.info("Config saved to %s", path)

    @staticmethod
    def merge_ui_defaults(config: dict) -> dict:
        """Fill missing UI config keys with defaults.

        Args:
            config: Config dict to fill.

        Returns:
            Config dict with UI defaults merged in.
        """
        ui_defaults = deepcopy(DEFAULTS.get("ui", {}))
        ui = config.setdefault("ui", {})
        for key, val in ui_defaults.items():
            if key not in ui:
                ui[key] = val
        return config

    @staticmethod
    def get_detailer_schedules(config: dict) -> dict[str, list[int]]:
        """Extract detailer schedules from config.

        Returns dict of detailer_name -> [weekday_numbers].
        Always includes a 'default' key.
        """
        schedules: dict[str, list[int]] = {"default": [0, 1, 2, 3]}

        raw_schedules = config.get("detailer_schedules", {})
        if isinstance(raw_schedules, dict):
            for name, days in raw_schedules.items():
                if isinstance(days, list):
                    schedules[name] = days

        return schedules

    # ── Internal ──────────────────────────────────────────────────────

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Deep merge override into base. Modifies base in-place."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigService._deep_merge(base[key], value)
            else:
                base[key] = deepcopy(value)
        return base
