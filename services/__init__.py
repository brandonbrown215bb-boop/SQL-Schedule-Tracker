# services/__init__.py
"""Service layer — business logic extracted from GUI.

Each service is a pure Python class with zero Qt dependencies.
Services import from ``data.*`` and ``sync.*`` only; never from ``gui.*``.
"""

from services.config_service import ConfigService
from services.export_service import ExportService
from services.import_service import ImportService
from services.migration_registry import Migration, SchemaMigrationRegistry
from services.sanitizer import InputSanitizer
from services.sync_service import SyncService
from services.unit_service import UnitService
from services.validation import (
    UNIT_FIELD_RULES,
    FieldRule,
    ValidationError,
    validate_unit,
)

__all__ = [
    "UNIT_FIELD_RULES",
    "ConfigService",
    "ExportService",
    "FieldRule",
    "ImportService",
    "InputSanitizer",
    "Migration",
    "SchemaMigrationRegistry",
    "SyncService",
    "UnitService",
    "ValidationError",
    "validate_unit",
]
