"""SyncService — multi-user sync coordination.

Wraps sync/lock_manager.py, sync/revision_store.py, sync/session_registry.py,
and sync/shared_cache.py to provide a clean interface for multi-user operations.
Zero Qt dependencies (QTimer heartbeat is handled by the GUI layer).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SyncStatus:
    """Current status of the multi-user sync system."""

    enabled: bool = False
    owner_id: str = ""
    active_sessions: list[str] = None  # type: ignore[assignment]
    save_blocked: bool = False

    def __post_init__(self):
        if self.active_sessions is None:
            self.active_sessions = []


class SyncService:
    """Service for multi-user sync operations.

    Provides a thin wrapper around the sync module. The GUI layer is
    responsible for QTimer-based heartbeat polling; this service provides
    the underlying operations.

    Usage:
        svc = SyncService(db_path, config)
        if svc.is_enabled():
            svc.acquire_lock("14201")
            svc.commit_revision("14201", base=0, fp="abc", user="Alice")
            svc.release_lock("14201")
    """

    def __init__(self, db_path: str, multi_user_config: dict | None = None):
        self._db_path = db_path
        self._config = multi_user_config or {}
        self._enabled = self._config.get("enabled", False)
        self._lock_manager = None
        self._revision_store = None
        self._shared_cache = None
        self._session_registry = None
        self._owner_id = ""
        self._save_blocked = False

        if self._enabled:
            self._init_sync()

    def _init_sync(self) -> None:
        """Initialize sync infrastructure from config."""
        import getpass
        import socket

        from sync.lock_manager import LockManager
        from sync.revision_store import RevisionStore
        from sync.session_registry import SessionRegistry
        from sync.shared_cache import SharedCache

        username = (
            self._config.get("username")
            or __import__("os").environ.get("USERNAME")
            or getpass.getuser()
        )
        machine = (
            self._config.get("machine")
            or __import__("os").environ.get("COMPUTERNAME")
            or socket.gethostname()
        )
        self._owner_id = f"{username}@{machine}"

        self._lock_manager = LockManager(self._db_path, username, machine)
        self._revision_store = RevisionStore(self._db_path)
        self._shared_cache = SharedCache(self._db_path)
        self._revision_store.set_shared_cache(self._shared_cache)
        self._session_registry = SessionRegistry(self._db_path, self._owner_id)

        if self._config.get("fallback_mode") == "block":
            # Test that sync is actually available
            try:
                self._session_registry.beat()
            except Exception:
                self._save_blocked = True
                logger.warning("Sync initialized but heartbeat failed — saves blocked")

    # ── Status ────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """Return True if multi-user sync is enabled and available."""
        return self._enabled

    def is_save_blocked(self) -> bool:
        """Return True if saves should be blocked due to sync unavailability."""
        return self._save_blocked

    def get_owner_id(self) -> str:
        """Return the owner ID for this session (e.g. 'Alice@PC1')."""
        return self._owner_id

    def get_status(self) -> SyncStatus:
        """Return current sync status."""
        sessions = self.get_active_sessions()
        return SyncStatus(
            enabled=self._enabled,
            owner_id=self._owner_id,
            active_sessions=[s.owner for s in sessions],
            save_blocked=self._save_blocked,
        )

    # ── Locks ─────────────────────────────────────────────────────────

    def acquire_lock(self, name: str, timeout: float = 10.0, purpose: str = "") -> bool:
        """Acquire a named lock. Returns True on success."""
        if not self._lock_manager:
            return True  # no sync = no locking needed
        try:
            self._lock_manager.acquire(name, timeout=timeout, purpose=purpose)
            return True
        except Exception as e:
            logger.warning("Failed to acquire lock %s: %s", name, e)
            return False

    def release_lock(self, name: str) -> None:
        """Release a named lock."""
        if not self._lock_manager:
            return
        self._lock_manager.release(name)

    # ── Revisions ─────────────────────────────────────────────────────

    def get_revision(self, com_number: str) -> int:
        """Get the current revision number for a COM. Returns 0 if none."""
        if not self._revision_store:
            return 0
        return self._revision_store.baseline(com_number)

    def commit_revision(
        self,
        com_number: str,
        base_revision: int,
        fingerprint: str,
        user: str,
        unit=None,
    ):
        """Commit a revision for a COM. Raises RevisionConflictError on stale base."""
        if not self._revision_store:
            from sync.revision_store import UnitRevision

            return UnitRevision(
                com_number=com_number,
                revision=1,
                fingerprint=fingerprint,
                modified_by=user,
                modified_at=__import__("datetime").datetime.now().isoformat(timespec="seconds"),
            )
        return self._revision_store.commit(com_number, base_revision, fingerprint, user, unit=unit)

    # ── Sessions ──────────────────────────────────────────────────────

    def start_heartbeat(self) -> None:
        """Write initial heartbeat file. GUI layer handles QTimer polling."""
        if self._session_registry:
            self._session_registry.beat()

    def stop_heartbeat(self) -> None:
        """Remove heartbeat file and stop session."""
        if self._session_registry:
            self._session_registry.stop()

    def get_active_sessions(self) -> list:
        """Return list of active SessionInfo objects."""
        if not self._session_registry:
            return []
        return self._session_registry.list_active(self._db_path)

    # ── Shared cache ──────────────────────────────────────────────────

    def get_cached_unit(self, com_number: str) -> dict | None:
        """Get the cached remote values for a COM (for conflict diffs)."""
        if not self._shared_cache:
            return None
        return self._shared_cache.get(com_number)
