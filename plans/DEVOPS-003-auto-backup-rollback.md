# DEVOPS-003: Automated Backup & Rollback

**Status**: Draft  
**Priority**: Medium  
**Effort**: S (4 days)  
**Depends on**: ARCH-003  

---

## Problem Statement

No backup or rollback mechanism exists:

| Scenario | Current Behavior | Impact |
|----------|-----------------|--------|
| CSV import corrupts data | Irreversible | Data lost; must restore from shared drive |
| Schema migration fails | `_migrate_schema` in transaction | Partial migration possible |
| User edits wrong unit | No undo | Must manually re-enter old values |
| App crashes during save | SQLite WAL may be in inconsistent state | Data loss on next open |

---

## Solution

Three-tier backup system:

1. **Pre-operation backup** — `VACUUM INTO` before imports and schema changes
2. **Auto-backup on startup** — configurable backup schedule per session
3. **Point-in-time recovery** — restore from any backup file

### Backup Manager

```python
# services/backup_service.py

import glob
import logging
import os
import re
import shutil
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class BackupService:
    """Manages SQLite database backups."""
    
    def __init__(self, db_path: str, backup_dir: str | None = None):
        self.db_path = db_path
        self.backup_dir = backup_dir or os.path.join(
            os.path.dirname(db_path), "backups"
        )
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def backup(self, label: str = "") -> str:
        """Create a point-in-time backup using VACUUM INTO.
        
        Args:
            label: Optional label for the backup (e.g., "pre-import").
        
        Returns:
            Path to the backup file.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_label = re.sub(r'[^a-zA-Z0-9_-]', '_', label) if label else ""
        if safe_label:
            backup_name = f"schedule_{timestamp}_{safe_label}.db"
        else:
            backup_name = f"schedule_{timestamp}.db"
        backup_path = os.path.join(self.backup_dir, backup_name)
        
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(f"VACUUM INTO ?", (backup_path,))
            size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            logger.info(f"Backup created: {backup_path} ({size_mb:.1f} MB)")
            return backup_path
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            # Fallback: file copy
            shutil.copy2(self.db_path, backup_path)
            logger.warning(f"Fallback backup (file copy): {backup_path}")
            return backup_path
        finally:
            conn.close()
    
    def restore(self, backup_path: str) -> bool:
        """Restore database from a backup file.
        
        Creates a backup of the current database first, then replaces it.
        """
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        
        # Backup current state first (safety net)
        self.backup(label="pre-restore")
        
        # Verify backup integrity
        if not self._verify_backup(backup_path):
            raise ValueError(f"Backup integrity check failed: {backup_path}")
        
        # Restore
        conn = sqlite3.connect(backup_path)
        try:
            # Use VACUUM INTO to clone backup into original location
            conn.execute(f"VACUUM INTO ?", (self.db_path + ".restore",))
            conn.close()
            os.replace(self.db_path + ".restore", self.db_path)
            logger.info(f"Database restored from: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False
    
    def list_backups(self) -> list[dict]:
        """List all available backups with metadata."""
        backups = []
        for f in sorted(glob.glob(os.path.join(self.backup_dir, "*.db")), reverse=True):
            size = os.path.getsize(f)
            mtime = os.path.getmtime(f)
            backups.append({
                "path": f,
                "name": os.path.basename(f),
                "size_mb": size / (1024 * 1024),
                "modified": datetime.fromtimestamp(mtime).isoformat(),
            })
        return backups
    
    def enforce_retention(self) -> None:
        """Enforce backup retention policy: 7 daily, 4 weekly, 3 monthly."""
        backups = self.list_backups()
        if len(backups) <= 14:  # minimum to have anything to prune
            return
        
        # Group by date
        daily: dict[str, list] = {}
        for b in backups:
            date_key = b["modified"][:10]  # YYYY-MM-DD
            daily.setdefault(date_key, []).append(b)
        
        # Keep newest backup per day (for last 7 days)
        to_keep = set()
        sorted_dates = sorted(daily.keys(), reverse=True)
        
        # Daily: keep last 7 days
        for date_key in sorted_dates[:7]:
            to_keep.add(daily[date_key][0]["path"])
        
        # Weekly: keep last 4 weeks (Sunday backups)
        weeks_kept = 0
        for date_key in sorted_dates:
            dt = datetime.strptime(date_key, "%Y-%m-%d")
            if dt.weekday() == 6:  # Sunday
                if weeks_kept < 4:
                    to_keep.add(daily[date_key][0]["path"])
                    weeks_kept += 1
        
        # Monthly: keep last 3 months (1st of month)
        months_kept = set()
        for date_key in sorted_dates:
            month_key = date_key[:7]  # YYYY-MM
            if month_key not in months_kept and len(months_kept) < 3:
                to_keep.add(daily[date_key][0]["path"])
                months_kept.add(month_key)
        
        # Delete unneeded backups
        for b in backups:
            if b["path"] not in to_keep:
                try:
                    os.remove(b["path"])
                    logger.info(f"Pruned old backup: {b['name']}")
                except OSError:
                    pass
    
    def _verify_backup(self, backup_path: str) -> bool:
        """Verify backup file integrity using PRAGMA integrity_check."""
        try:
            conn = sqlite3.connect(backup_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            conn.close()
            return result == "ok"
        except Exception:
            return False
    
    def auto_backup(self) -> None:
        """Create an auto-backup (called on app startup)."""
        self.backup(label="auto")
        self.enforce_retention()
```

### Integration Points

```python
# In main.py, before get_db()
backup_service = BackupService(db_path)
if config.get("backup", {}).get("on_startup", True):
    backup_service.auto_backup()

# In ImportService, before upsert
def from_csv(self, csv_path: str) -> ImportResult:
    self._backup.backup(label="pre-import")
    result = super().from_csv(csv_path)
    return result

# In migration (ARCH-003), before schema change
def apply(self, migration: Migration) -> None:
    self._backup.backup(label=f"pre-migration-v{migration.version}")
    super().apply(migration)
```

### Config

```yaml
# config.yaml additions
backup:
  enabled: true
  directory: ""                          # defaults to <db_dir>/backups
  on_startup: true                       # auto-backup on app launch
  on_import: true                        # backup before CSV/SSRS import
  on_schema_change: true                 # backup before migrations
  retention:
    daily: 7
    weekly: 4
    monthly: 3
```

---

## Implementation Phases

### Phase 1: Backup Service (2 days)
1. Implement `BackupService` with `backup()`, `restore()`, `list_backups()`
2. Implement `_verify_backup()` using `PRAGMA integrity_check`
3. Add integration points in `main.py` and `ImportService`
4. **Tests**: Test backup/restore roundtrip, verify integrity check

### Phase 2: Retention & Recovery (1 day)
1. Implement `enforce_retention()` with daily/weekly/monthly policy
2. Add backup restore dialog (GUI for browsing and restoring backups)
3. **Tests**: Test retention policy pruning, verify no data loss

### Phase 3: UI Integration (1 day)
1. Add backup status indicator in status bar
2. Add backup management dialog in File menu
3. Add manual backup button in automation bar
4. **Tests**: Verify backup dialog lists backups, restore works

---

## Success Criteria

1. Pre-import backups created automatically (verified by file listing)
2. Integrity check passes for all backups
3. Retention policy correctly prunes old backups
4. Restore correctly replaces current DB
5. Backup dialog shows backups with sizes and timestamps

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Backup Service | 2 |
| Phase 2: Retention & Recovery | 1 |
| Phase 3: UI Integration | 1 |
| **Total** | **4** |