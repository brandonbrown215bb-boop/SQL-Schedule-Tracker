from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

LOCK_TIMEOUT = 60
ACQUIRE_TIMEOUT = 10
ACQUIRE_POLL_INTERVAL = 0.25


class LockError(Exception):
    """Base class for lock-related errors."""


class LockAcquisitionError(LockError):
    """Raised when a lock cannot be acquired before timeout."""


@dataclass
class LockInfo:
    owner: str
    acquired_at: str
    pid: int
    token: str
    purpose: str = ""
    com_number: str = ""

    @property
    def is_stale(self) -> bool:
        try:
            acquired = datetime.fromisoformat(self.acquired_at)
        except ValueError:
            return True
        return datetime.now() - acquired > timedelta(seconds=LOCK_TIMEOUT)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> LockInfo:
        return cls(**json.loads(raw))


class LockManager:
    """Atomic file-lock manager for shared-drive coordination."""

    def __init__(self, excel_path: str, username: str, machine: str):
        self.root_dir = Path(excel_path).parent / "UnitTracker"
        self.username = username
        self.machine = machine
        self.pid = os.getpid()
        self.owner_id = f"{username}@{machine}"
        self.token = uuid.uuid4().hex

    def acquire(
        self,
        name: str,
        timeout: float = ACQUIRE_TIMEOUT,
        purpose: str = "",
        com_number: str = "",
    ) -> LockInfo:
        """Acquire a named lock using exclusive file creation."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._lock_path(name)
        deadline = time.monotonic() + timeout

        while time.monotonic() <= deadline:
            info = self._read_lock(lock_path)
            if info and info.is_stale:
                self._remove_stale_lock(lock_path, info)

            lock_info = LockInfo(
                owner=self.owner_id,
                acquired_at=datetime.now().isoformat(),
                pid=self.pid,
                token=self.token,
                purpose=purpose,
                com_number=com_number,
            )
            try:
                with open(lock_path, "x", encoding="utf-8") as f:
                    f.write(lock_info.to_json())
                return lock_info
            except FileExistsError:
                time.sleep(min(ACQUIRE_POLL_INTERVAL, max(0.0, deadline - time.monotonic())))
            except OSError as exc:
                raise LockAcquisitionError(f"Could not create lock {lock_path}: {exc}") from exc

        holder = self._read_lock(lock_path)
        held_by = holder.owner if holder else "unknown"
        raise LockAcquisitionError(f"Could not acquire {name} lock; held by {held_by}.")

    def release(self, name: str) -> None:
        """Release a named lock only if this process owns it."""
        lock_path = self._lock_path(name)
        info = self._read_lock(lock_path)
        if info and info.owner == self.owner_id and info.token == self.token:
            with suppress(FileNotFoundError):
                lock_path.unlink()

    def write_lock(self, timeout: float = ACQUIRE_TIMEOUT):
        return _LockContext(self, "excel", timeout, "excel-write")

    def commit_lock(self, timeout: float = ACQUIRE_TIMEOUT):
        return _LockContext(self, "commit", timeout, "cache-commit")

    def _lock_path(self, name: str) -> Path:
        safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
        return self.root_dir / f"{safe_name}.lock"

    def _read_lock(self, path: Path) -> LockInfo | None:
        try:
            return LockInfo.from_json(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _remove_stale_lock(self, path: Path, info: LockInfo) -> None:
        current = self._read_lock(path)
        if current and current.token == info.token and current.is_stale:
            with suppress(FileNotFoundError):
                path.unlink()


class _LockContext:
    def __init__(self, manager: LockManager, name: str, timeout: float, purpose: str):
        self.manager = manager
        self.name = name
        self.timeout = timeout
        self.purpose = purpose

    def __enter__(self):
        self.manager.acquire(self.name, self.timeout, self.purpose)
        return self.manager

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.manager.release(self.name)
        return False
