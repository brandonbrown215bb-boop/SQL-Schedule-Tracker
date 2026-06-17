# DEVOPS-004: Hot-Reload Development Mode

**Status**: Draft  
**Priority**: Medium  
**Effort**: S (3 days)  
**Depends on**: None  

---

## Problem Statement

Every code change requires a full application restart:

- **Restart cycle**: Change code → Ctrl+C → wait for cleanup → `python main.py` → wait for startup → navigate to test state
- **Time cost**: 10-20 seconds per iteration, 50+ iterations/day = 10+ minutes of waiting
- **Stylesheet changes**: Even simple QSS color changes require full restart

---

## Solution

Hot-reload development mode with two tiers:

1. **QSS live reload** — watch stylesheet changes, apply without restart
2. **Auto-restart on Python changes** — watchdog watcher kills and restarts the process

### Implementation

```python
# dev/hotreload.py

import os
import signal
import subprocess
import sys
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class QSSChangeHandler(FileSystemEventHandler):
    """Live-reload QSS stylesheets without restarting the app."""
    
    def __init__(self, app):
        self.app = app
        self._debounce_timer = None
    
    def on_modified(self, event):
        if not event.src_path.endswith('.qss'):
            return
        from PyQt5.QtCore import QTimer
        if self._debounce_timer is not None:
            self._debounce_timer.stop()
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)  # 300ms debounce
        self._debounce_timer.timeout.connect(lambda: self._reload_qss(event.src_path))
        self._debounce_timer.start()
    
    def _reload_qss(self, path: str) -> None:
        """Apply QSS stylesheet change without restart."""
        try:
            with open(path, encoding='utf-8') as f:
                stylesheet = f.read()
            self.app.setStyleSheet(stylesheet)
            print(f"[hotreload] QSS reloaded: {os.path.basename(path)}")
        except Exception as e:
            print(f"[hotreload] QSS reload failed: {e}")


class PythonRestartHandler(FileSystemEventHandler):
    """Watch Python files and auto-restart the application."""
    
    def __init__(self):
        self._last_restart = 0.0
        self._debounce_seconds = 1.0
    
    def on_modified(self, event):
        if not event.src_path.endswith('.py'):
            return
        if event.src_path.endswith('__init__.py') or 'venv' in event.src_path:
            return
        now = time.monotonic()
        if now - self._last_restart < self._debounce_seconds:
            return
        self._last_restart = now
        print(f"[hotreload] Change detected: {os.path.basename(event.src_path)}")
        print("[hotreload] Restarting application...")
        os._exit(42)  # Special exit code that launcher recognizes


class HotReloadLauncher:
    """Launcher that watches for exit code 42 and auto-restarts."""
    
    def __init__(self, script: str = "main.py"):
        self.script = script
        self._watch_python = True
        self._watch_qss = True
    
    def run(self) -> None:
        """Run the application with hot-reload support.
        
        Usage:
            python -m dev.hotreload main.py
        """
        while True:
            process = subprocess.Popen(
                [sys.executable, self.script, "--dev"],
                env={**os.environ, "UNIT_TRACKER_DEV": "1"},
            )
            process.wait()
            if process.returncode == 42:
                print("[hotreload] Restarting...")
                continue
            else:
                print(f"[hotreload] Exited with code {process.returncode}")
                break


# main.py / dev mode entry point
def enable_dev_mode(app) -> None:
    """Enable hot-reload features when --dev flag is present."""
    if "--dev" not in sys.argv and not os.environ.get("UNIT_TRACKER_DEV"):
        return
    
    # Watch QSS files
    qss_handler = QSSChangeHandler(app)
    qss_observer = Observer()
    qss_observer.schedule(qss_handler, path="gui/", recursive=False)
    qss_observer.start()
    
    # Watch Python files for restart
    if sys.platform != "win32":  # os._exit(42) doesn't work well on Windows
        py_handler = PythonRestartHandler()
        py_observer = Observer()
        py_observer.schedule(py_handler, path=".", recursive=True)
        py_observer.start()
```

### Dev Mode CLI

```bash
# Run with hot-reload (auto-restart on Python changes)
python -m dev.hotreload main.py

# Or use --dev flag directly
python main.py --dev
```

### Config

```yaml
# config.yaml additions
dev:
  hotreload:
    enabled: false  # auto-enabled when --dev flag present
    watch_python: true
    watch_qss: true
    debounce_ms: 300
```

---

## Implementation Phases

### Phase 1: QSS Live Reload (1 day)
1. Implement `QSSChangeHandler` with watchdog
2. Wire into `MainWindow` via `enable_dev_mode()`
3. Extract all stylesheets to `.qss` files
4. **Tests**: Manual verification of live QSS reload

### Phase 2: Auto-Restart + Launcher (2 days)
1. Implement `PythonRestartHandler` with exit code 42 protocol
2. Implement `HotReloadLauncher` with restart loop
3. Create `dev/hotreload.py` module
4. Add `--dev` flag support to `main.py`
5. **Tests**: Verify restart on Python file change

---

## Success Criteria

1. QSS changes take effect in < 500ms without restart
2. Python changes trigger auto-restart in < 2 seconds
3. Graceful shutdown: pending saves complete before restart
4. Works on Linux and Windows

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: QSS Live Reload | 1 |
| Phase 2: Auto-Restart | 2 |
| **Total** | **3** |