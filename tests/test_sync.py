from __future__ import annotations

import pytest

from sync.lock_manager import LockAcquisitionError, LockManager
from sync.revision_store import RevisionConflictError, RevisionStore


def test_atomic_lock_blocks_second_owner(tmp_path):
    excel = tmp_path / "workbook.xlsm"
    excel.write_bytes(b"fake")

    alice = LockManager(str(excel), "Alice", "PC1")
    bob = LockManager(str(excel), "Bob", "PC2")

    alice.acquire("excel")
    try:
        with pytest.raises(LockAcquisitionError):
            bob.acquire("excel", timeout=0.01)
    finally:
        alice.release("excel")

    bob.acquire("excel", timeout=0.01)
    bob.release("excel")


def test_revision_store_detects_stale_baseline(tmp_path):
    excel = tmp_path / "workbook.xlsm"
    excel.write_bytes(b"fake")
    store = RevisionStore(str(excel))

    first = store.commit("COM-001", 0, "abc", "Alice@PC1")
    assert first.revision == 1

    with pytest.raises(RevisionConflictError) as exc:
        store.commit("COM-001", 0, "def", "Bob@PC2")

    assert exc.value.latest.revision == 1
    assert exc.value.latest.modified_by == "Alice@PC1"

    second = store.commit("COM-001", 1, "def", "Bob@PC2")
    assert second.revision == 2
