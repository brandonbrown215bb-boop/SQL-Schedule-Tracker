# sync/session_registry.py
"""Session heartbeat and presence detection for multi-user awareness.

Each running app instance writes a heartbeat file to
``UnitTracker/sessions/<owner_id>.json`` and refreshes it every 30 seconds.
Stale sessions (no heartbeat for >90 seconds) are considered dead.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import ClassVar

HEARTBEAT_INTERVAL = 30   # seconds between heartbeat writes
HEARTBEAT_TIMEOUT = 90    # seconds — sessions older than this are stale

SESSIONS_DIR = "sessions"


@dataclass
class SessionInfo:
    """Information about a running app session."""
    owner: str
    session_id: str
    pid: int
    started_at: str
    last_heartbeat: str

    @property
    def is_stale(self) -> bool:
        try:
            last = datetime.fromisoformat(self.last_heartbeat)
        except ValueError:
            return True
        return datetime.now() - last > timedelta(seconds=HEARTBEAT_TIMEOUT)

    @property
    def age_seconds(self) -> int:
        """Approximate seconds since this session started (best-effort)."""
        try:
            start = datetime.fromisoformat(self.started_at)
            return int((datetime.now() - start).total_seconds())
        except ValueError:
            return 0


class SessionRegistry:
    """Manages session heartbeat files for multi-user presence.

    Usage::

        registry = SessionRegistry(excel_path, owner_id)
        registry.start(qt_parent)  # begins heartbeat timer
        # ... on app close:
        registry.stop()

    Other instances can query active sessions::

        sessions = SessionRegistry.list_active(excel_path)
    """

    def __init__(self, excel_path: str, owner_id: str):
        self.root_dir = Path(excel_path).parent / "UnitTracker"
        self.sessions_dir = self.root_dir / SESSIONS_DIR
        self.owner_id = owner_id
        self.session_id = uuid.uuid4().hex[:12]
        self._session_path = self.sessions_dir / f"{owner_id}.json"
        self._timer = None  # QTimer, set externally via start()
        self._lock = Lock()
        self._stopped = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, parent: "QObject | None" = None) -> None:
        """Begin heartbeat writing.

        If *parent* is provided (a QObject), a QTimer is created as a child
        of *parent* and fires every *HEARTBEAT_INTERVAL* seconds.
        Otherwise the caller must call :meth:`beat` manually.
        """
        self._write_heartbeat()
        if parent is not None:
            try:
                from PyQt5.QtCore import QTimer
                self._timer = QTimer(parent)
                self._timer.setInterval(HEARTBEAT_INTERVAL * 1000)
                self._timer.timeout.connect(self.beat)
                self._timer.start()
            except ImportError:
                pass  # no Qt available — caller must beat() manually

    def stop(self) -> None:
        """Remove the session file and stop the timer."""
        self._stopped = True
        self._stop_timer()
        with self._lock:
            try:
                if self._session_path.exists():
                    self._session_path.unlink()
            except OSError:
                pass

    def beat(self) -> None:
        """Refresh the heartbeat timestamp (called by timer)."""
        if self._stopped:
            return
        self._write_heartbeat()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @staticmethod
    def list_active(excel_path: str) -> list[SessionInfo]:
        """Return all non-stale sessions for this workbook."""
        sessions_dir = (
            Path(excel_path).parent / "UnitTracker" / SESSIONS_DIR
        )
        if not sessions_dir.is_dir():
            return []

        active: list[SessionInfo] = []
        for entry in sessions_dir.iterdir():
            if not entry.name.endswith(".json"):
                continue
            try:
                data = json.loads(entry.read_text(encoding="utf-8"))
                info = SessionInfo(**data)
                if not info.is_stale:
                    active.append(info)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
        return active

    @staticmethod
    def count_active(excel_path: str) -> int:
        """Return the number of active sessions (excluding ourselves)."""
        return len(SessionRegistry.list_active(excel_path))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _write_heartbeat(self) -> None:
        with self._lock:
            self.sessions_dir.mkdir(parents=True, exist_ok=True)
            info = SessionInfo(
                owner=self.owner_id,
                session_id=self.session_id,
                pid=os.getpid(),
                started_at=self._read_started_at(),
                last_heartbeat=datetime.now().isoformat(timespec="seconds"),
            )
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.sessions_dir,
                delete=False,
            ) as f:
                json.dump(asdict(info), f, indent=2)
                temp_name = f.name
            Path(temp_name).replace(self._session_path)

    def _read_started_at(self) -> str:
        """Return the original ``started_at`` from the file, else now."""
        try:
            data = json.loads(
                self._session_path.read_text(encoding="utf-8")
            )
            return data.get("started_at", datetime.now().isoformat(timespec="seconds"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return datetime.now().isoformat(timespec="seconds")

    def _stop_timer(self) -> None:
        t = self._timer
        self._timer = None
        if t is None:
            return
        try:
            t.stop()
            t.deleteLater()
        except RuntimeError:
            pass