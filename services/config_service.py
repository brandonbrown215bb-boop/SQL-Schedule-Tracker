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
    "sqlite_path": "P:\\Detailing Schedule 2019\\schedule.db",
    "excel_path": "P:\\Detailing Schedule 2019\\SCHDetailingReport_all_plants_MASTER.xlsm",
    "unedited_reports_dir": "P:\\Detailing Schedule 2019\\Unedited Reports",
    "csv_output_dir": "./csv_cache",
    "ssrs_url": "http://j030m1p3/ReportServer?%2fCustom%2fProduction+Control%2fSCHDetailingReport",
    "ssrs_summary_url": "http://j030m1p3/ReportServer?%2fCustom%2fProduction+Control%2fSCHSchedulingSummaryReport",  # Legacy/Optional: SCHDetailingReport contains unit_state directly
    "update_source_dir": "P:\\Detailing Schedule 2019\\Schedule App",
    "ssrs_lookback_days": 30,
    "ssrs_lookahead_days": 365,
    "default_detailers": [
        "— Unassigned —",
        "Cancelled",
        "Jackie H",
        "Tommy N",
        "Matthew S",
        "Matthew E",
        "Carl M",
        "Stewart D",
        "Austin K",
        "Kris L",
        "Emilio P",
        "Timothy B",
        "Jeremy B",
        "Brandon B",
        "Tracy V",
        "Tanner D",
    ],
    "detailer_schedules": {
        "Brandon B": [1, 2, 3, 4],
        "Carl M": [0, 1, 2, 3],
        "Emilio P": [0, 1, 2, 3],
        "Jackie H": [0, 1, 2, 3],
        "Jeremy B": [0, 1, 2, 3],
        "Kris L": [0, 1, 2, 3],
        "Matthew E": [1, 2, 3, 4],
        "Matthew S": [1, 2, 3, 4],
        "Stewart D": [1, 2, 3, 4],
        "Tanner D": [0, 1, 2, 3],
        "Timothy B": [1, 2, 3, 4],
        "Tommy N": [1, 2, 3, 4],
        "Tracy V": [0, 1, 2, 3],
        "default": [0, 1, 2, 3],
    },
    "status_labels": {
        "gray": "Unassigned (0%)",
        "green": "Released (100%)",
        "orange": "Checked & Returned (95%)",
        "purple": "Ready for Checking (90%)",
        "red": "Overdue",
        "yellow": "In Progress (1-89%)",
    },
    "multi_user": {
        "enabled": True,
        "fallback_mode": "block",
        "machine": "",
        "username": "",
    },
    "ui": {
        "theme": "light",
        "colorblind_mode": "none",
        "high_contrast": False,
        "auto_refresh_minutes": 0,
        "last_view": "calendar",
        "splitter_sizes": None,
        "list_column_widths": {},
        "list_visible_columns": [
            "com_number",
            "unit_state",
            "detailing_due_date",
            "dept_due_date_previous",
            "job_name",
            "detailer",
            "status_color",
            "percent_complete",
            "description_tags",
            "department_hours",
            "actual_hours",
            "target_department_hours",
            "checking_status",
            "dr_checks",
            "dvl_checks",
            "contract_number",
            "unit_detailing_start_date",
            "notes",
            "alert_level",
        ],
        "list_column_order": [
            "com_number",
            "unit_state",
            "detailing_due_date",
            "dept_due_date_previous",
            "job_name",
            "detailer",
            "status_color",
            "percent_complete",
            "description_tags",
            "department_hours",
            "actual_hours",
            "target_department_hours",
            "checking_status",
            "dr_checks",
            "dvl_checks",
            "contract_number",
            "build_date",
            "unit_detailing_start_date",
            "working_days_in_checking",
            "notes",
            "alert_level",
        ],
        "list_sort_column": "detailing_due_date",
        "list_sort_ascending": True,
        "onboarding_completed": False,
        "show_inline_edit": True,
        "right_panel_collapsed": False,
        "timeline_collapsed": True,
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
        config = ConfigService.load("/path/to/config.yaml")
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

        # Base defaults start from hardcoded DEFAULTS
        base_defaults = deepcopy(DEFAULTS)

        # If update_source_dir points to an accessible network folder with config.yaml,
        # merge network template into base_defaults so new network settings take precedence over hardcoded DEFAULTS
        update_dir = raw.get("update_source_dir") or DEFAULTS.get("update_source_dir", "")
        if update_dir and os.path.isdir(update_dir):
            remote_config_path = os.path.join(update_dir, "config.yaml")
            if os.path.exists(remote_config_path) and os.path.abspath(remote_config_path) != os.path.abspath(path):
                try:
                    with open(remote_config_path, encoding="utf-8") as rf:
                        remote_raw = yaml.safe_load(rf) or {}
                    if isinstance(remote_raw, dict):
                        ConfigService._deep_merge(base_defaults, remote_raw)
                except Exception as e:
                    logger.warning(f"Could not sync network config template from {remote_config_path}: {e}")

        # Deep merge local user config on top of base defaults
        config = base_defaults
        ConfigService._deep_merge(config, raw)

        try:
            from services.validation import update_allowed_detailers
            update_allowed_detailers(config.get("default_detailers", []))
        except Exception as e:
            logger.warning(f"Failed to update allowed detailers in validation rules: {e}")

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
    def _deep_merge(base: dict, override: dict, fill_empty_scalars: bool = True) -> dict:
        """Deep merge override into base. Modifies base in-place."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigService._deep_merge(base[key], value, fill_empty_scalars=fill_empty_scalars)
            elif key in base and isinstance(base[key], list) and isinstance(value, list):
                merged_list = deepcopy(value)
                for item in base[key]:
                    if item not in merged_list:
                        merged_list.append(deepcopy(item))
                base[key] = merged_list
            elif (
                fill_empty_scalars
                and key in base
                and isinstance(base[key], str)
                and base[key].strip() != ""
                and (value is None or (isinstance(value, str) and value.strip() == ""))
            ):
                # Keep non-empty base default string when override string is empty/None
                pass
            else:
                base[key] = deepcopy(value)
        return base
