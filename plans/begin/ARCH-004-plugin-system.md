# ARCH-004: Plugin Architecture

**Status**: Draft  
**Priority**: Medium  
**Effort**: L (13 days)  
**Depends on**: ARCH-001  
**Required by**: FEAT-019, FEAT-020  

---

## Problem Statement

Every new import format, export target, or sync backend requires modifying core application code:

| Capability | Current Implementation | Pain Point |
|-----------|----------------------|------------|
| Import CSV | `automation/import_csv.py` — hardcoded column mapping | Adding JSON import means writing new module and wiring into MainWindow |
| Import SSRS | `automation/import_atomsvc.py` — hardcoded fetch + parse | Adding a different SSRS endpoint requires code changes |
| Export Excel | `automation/export_to_workbook.py` — hardcoded column layout | Adding PDF export means new code + MainWindow wiring |
| Sync | `sync/` package — file-based only | Adding Redis sync requires modifying MainWindow |
| Notifications | None | No way to add Slack/email alerts without modifying core |

---

## Proposed Solution

A plugin system with well-defined base classes, automatic discovery, sandboxed execution for untrusted plugins, and a plugin registry UI.

### Architecture

```
app/
├── services/
│   └── plugin_manager.py    # Plugin discovery, loading, lifecycle
├── plugins/                 # All plugins live here
│   ├── builtin/             # Built-in plugins (shipped with app)
│   │   ├── csv_import/
│   │   │   ├── __init__.py
│   │   │   └── manifest.json
│   │   ├── ssrs_import/
│   │   │   ├── __init__.py
│   │   │   └── manifest.json
│   │   ├── excel_export/
│   │   │   ├── __init__.py
│   │   │   └── manifest.json
│   │   └── file_sync/
│   │       ├── __init__.py
│   │       └── manifest.json
│   └── external/            # User-installed plugins (git-ignored)
│       └── ...
└── plugin_sdk/              # SDK for third-party plugin developers
    ├── base_classes.py      # Abstract base classes
    ├── exceptions.py        # Plugin exception hierarchy
    └── testing.py           # Test helpers for plugin developers
```

### Plugin Base Classes

```python
# plugin_sdk/base_classes.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginManifest:
    id: str                    # unique identifier (e.g., "csv_import_v1")
    name: str                  # human-readable name
    version: str               # semver
    author: str
    description: str
    plugin_type: str           # "import", "export", "sync", "notification", "ui"
    requires: list[str] = field(default_factory=list)  # plugin IDs this depends on
    min_app_version: str = "2.0.0"
    max_app_version: str | None = None


class PluginBase(ABC):
    """Base class for all plugins."""
    
    @abstractmethod
    def initialize(self, context: dict) -> None:
        """Called once when plugin is loaded. 
        `context` contains: db_path, config, logger, event_bus.
        """
    
    @abstractmethod
    def shutdown(self) -> None:
        """Called when app closes or plugin is disabled."""
    
    @property
    @abstractmethod
    def manifest(self) -> PluginManifest:
        ...


class ImportPlugin(PluginBase):
    """Plugin that imports data into the application."""
    
    @abstractmethod
    def detect(self, source: str) -> bool:
        """Return True if this plugin can handle the given source (path or URL)."""
    
    @abstractmethod
    def parse(self, source: str, **kwargs) -> list[dict]:
        """Parse source and return list of raw row dicts."""
    
    @abstractmethod
    def validate(self, rows: list[dict]) -> list[str]:
        """Validate parsed rows. Return list of error messages (empty = valid)."""
    
    def transform(self, rows: list[dict]) -> list[dict]:
        """Optional: transform raw rows before upsert. Default: identity."""
        return rows


class ExportPlugin(PluginBase):
    """Plugin that exports data out of the application."""
    
    @abstractmethod
    def supported_formats(self) -> list[str]:
        """Return list of MIME types or file extensions (e.g., ['pdf', 'csv'])."""
    
    @abstractmethod
    def export(self, units: list, path: str, format: str, **options) -> int:
        """Export units to file. Returns number of records exported."""
    
    @abstractmethod
    def validate_path(self, path: str) -> str | None:
        """Validate export path. Return error string or None if valid."""


class SyncPlugin(PluginBase):
    """Plugin that provides multi-user synchronization."""
    
    @abstractmethod
    def connect(self) -> None:
        """Establish connection to sync backend."""
    
    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully disconnect."""
    
    @abstractmethod
    def acquire_lock(self, com_number: str, timeout: float = 10.0) -> bool: ...
    
    @abstractmethod
    def release_lock(self, com_number: str) -> None: ...
    
    @abstractmethod
    def get_revision(self, com_number: str) -> int: ...
    
    @abstractmethod
    def commit_revision(self, com_number: str, base: int, fingerprint: str,
                        modified_by: str) -> dict: ...
    
    @abstractmethod
    def heartbeat(self) -> None: ...
    
    @abstractmethod
    def list_active_sessions(self) -> list[dict]: ...


class NotificationPlugin(PluginBase):
    """Plugin that sends notifications (Slack, email, webhook)."""
    
    @abstractmethod
    def send(self, title: str, message: str, severity: str = "info", **options) -> bool: ...
    
    @abstractmethod
    def is_available(self) -> bool: ...
```

### PluginManager

```python
# services/plugin_manager.py

import importlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PluginError(Exception): ...
class PluginNotFoundError(PluginError): ...
class PluginLoadError(PluginError): ...
class PluginDependencyError(PluginError): ...
class PluginSandboxError(PluginError): ...


class PluginManager:
    """Discovers, loads, and manages plugins."""
    
    def __init__(self, app_context: dict):
        self._context = app_context
        self._plugins: dict[str, PluginBase] = {}
        self._builtin_dir = Path(__file__).parent.parent / "plugins" / "builtin"
        self._external_dir = Path(__file__).parent.parent / "plugins" / "external"
        self._sandbox_enabled = self._context.get("config", {}).get(
            "plugin_sandbox", False
        )
    
    def discover(self) -> list[PluginManifest]:
        """Scan plugin directories and return all discovered manifests."""
        manifests = []
        
        # Built-in plugins
        if self._builtin_dir.exists():
            for entry in self._builtin_dir.iterdir():
                if entry.is_dir():
                    manifest_path = entry / "manifest.json"
                    if manifest_path.exists():
                        manifests.append(self._load_manifest(manifest_path))
        
        # External plugins
        if self._external_dir.exists():
            for entry in self._external_dir.iterdir():
                if entry.is_dir():
                    manifest_path = entry / "manifest.json"
                    if manifest_path.exists():
                        manifests.append(self._load_manifest(manifest_path))
        
        return manifests
    
    def load(self, plugin_id: str) -> PluginBase:
        """Load a plugin by ID. Raises PluginNotFoundError if not found."""
        # Find the plugin directory
        for base_dir in [self._builtin_dir, self._external_dir]:
            plugin_dir = base_dir / plugin_id
            if plugin_dir.exists() and (plugin_dir / "manifest.json").exists():
                manifest = self._load_manifest(plugin_dir / "manifest.json")
                
                # Check dependencies
                for dep_id in manifest.requires:
                    if dep_id not in self._plugins:
                        self.load(dep_id)
                
                # Check sandbox mode
                if self._sandbox_enabled and base_dir == self._external_dir:
                    return self._load_sandboxed(plugin_dir, manifest)
                
                return self._load_direct(plugin_dir, manifest)
        
        raise PluginNotFoundError(f"Plugin not found: {plugin_id}")
    
    def _load_manifest(self, path: Path) -> PluginManifest:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return PluginManifest(**data)
    
    def _load_direct(self, plugin_dir: Path, manifest: PluginManifest) -> PluginBase:
        """Load plugin directly in-process."""
        sys.path.insert(0, str(plugin_dir))
        try:
            module = importlib.import_module(manifest.id)
            # Find the plugin class (must be a subclass of PluginBase)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, PluginBase) and attr is not PluginBase:
                    instance = attr()
                    instance.initialize(self._context)
                    self._plugins[manifest.id] = instance
                    logger.info(f"Loaded plugin: {manifest.name} v{manifest.version}")
                    return instance
            raise PluginLoadError(f"No PluginBase subclass found in {manifest.id}")
        finally:
            sys.path.pop(0)
    
    def _load_sandboxed(self, plugin_dir: Path, manifest: PluginManifest) -> PluginBase:
        """Load plugin in a subprocess for isolation (future)."""
        # Placeholder: in a real implementation, this would spawn a child process
        # and communicate via protocol buffers or JSON-RPC
        raise PluginSandboxError("Sandboxed plugin loading not yet implemented")
    
    def get(self, plugin_id: str, plugin_type: str | None = None) -> PluginBase:
        """Get a loaded plugin by ID, optionally filtering by type."""
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise PluginNotFoundError(plugin_id)
        if plugin_type and not isinstance(plugin, {
            "import": ImportPlugin,
            "export": ExportPlugin,
            "sync": SyncPlugin,
            "notification": NotificationPlugin,
        }.get(plugin_type, PluginBase)):
            raise PluginError(f"Plugin {plugin_id} is not of type {plugin_type}")
        return plugin
    
    def get_all_by_type(self, plugin_type: str) -> list[PluginBase]:
        """Get all loaded plugins of a given type."""
        type_map = {
            "import": ImportPlugin,
            "export": ExportPlugin,
            "sync": SyncPlugin,
            "notification": NotificationPlugin,
        }
        cls = type_map.get(plugin_type)
        if cls is None:
            return []
        return [p for p in self._plugins.values() if isinstance(p, cls)]
    
    def shutdown_all(self) -> None:
        """Gracefully shut down all plugins."""
        for plugin_id, plugin in list(self._plugins.items()):
            try:
                plugin.shutdown()
            except Exception as e:
                logger.error(f"Plugin {plugin_id} shutdown error: {e}")
        self._plugins.clear()
```

### Plugin Manifest Schema

```json
{
  "manifest.json schema": {
    "id": "string (unique, e.g. 'csv_import_v1')",
    "name": "string (human-readable)",
    "version": "string (semver)",
    "author": "string",
    "description": "string",
    "plugin_type": "string (import|export|sync|notification|ui)",
    "requires": ["array of plugin IDs"],
    "min_app_version": "string (semver)",
    "max_app_version": "string (semver, optional)",
    "settings": {
      "schema": {
        "type": "object",
        "properties": {}
      },
      "defaults": {}
    }
  }
}
```

### Configuration

```yaml
# config.yaml additions
plugins:
  enabled: true
  sandbox: false  # enable subprocess isolation for external plugins
  blacklist: []   # plugin IDs to never load
  settings:
    slack_notifier:
      webhook_url: "https://hooks.slack.com/..."
      notify_on: ["overdue", "urgent"]
```

---

## Implementation Phases

### Phase 1: Plugin Base Classes + Registry (3 days)
1. Define `PluginBase`, `ImportPlugin`, `ExportPlugin`, `SyncPlugin`, `NotificationPlugin` ABCs
2. Define `PluginManifest` dataclass
3. Implement `PluginManager` with `discover()`, `load()`, `get()`, `shutdown_all()`
4. **Tests**: Test plugin discovery, loading, dependency resolution

### Phase 2: Plugin Discovery + Sandbox (2 days)
1. Implement `plugins/builtin/` and `plugins/external/` directory structure
2. Add `manifest.json` reading and validation
3. Add sandbox infrastructure (subprocess isolation stubs)
4. **Tests**: Test manifest parsing, directory scanning, error handling

### Phase 3: Migrate Existing Import/Export to Plugins (3 days)
1. Create `plugins/builtin/csv_import/` with manifest and plugin class wrapping `import_csv.py`
2. Create `plugins/builtin/ssrs_import/` wrapping `import_atomsvc.py`
3. Create `plugins/builtin/excel_export/` wrapping `export_to_workbook.py`
4. Create `plugins/builtin/file_sync/` wrapping `sync/` package
5. Wire `PluginManager` into `MainWindow` or `ServiceRegistry`
6. **Tests**: End-to-end tests for each plugin producing same output as current code

### Phase 4: Plugin Marketplace UI (5 days)
1. Add plugin management dialog: list installed, enable/disable, view details
2. Add plugin settings UI (per-plugin configuration form)
3. Add plugin status indicator in status bar
4. **Tests**: UI tests for plugin dialog

---

## Success Criteria

1. All existing import/export/sync functionality works through plugins
2. New plugin can be added by creating a directory + manifest + Python class — no code changes
3. Plugin discovery finds both built-in and external plugins
4. Plugin isolation (sandbox) works for untrusted plugins
5. Plugin management UI allows enable/disable without restart

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Plugin API changes break existing plugins | Medium | Version manifest with `min_app_version` / `max_app_version` |
| Malicious plugin damages system | Low | Sandbox via subprocess isolation; filesystem access controls |
| Performance overhead from plugin dispatch | Low | Plugin dispatch is one method call; only matters for hot paths |
| Migration breaks current functionality | Medium | Phase 3 requires parity testing between old and new code paths |

---

## Effort Estimate

| Phase | Days | Dependencies |
|-------|------|-------------|
| Phase 1: Base Classes + Registry | 3 | None |
| Phase 2: Discovery + Sandbox | 2 | Phase 1 |
| Phase 3: Migrate Existing | 3 | Phase 1 |
| Phase 4: Plugin UI | 5 | Phase 1-3 |
| **Total** | **13** | |