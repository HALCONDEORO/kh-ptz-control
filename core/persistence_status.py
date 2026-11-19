# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Process-local persistence receipts. No Qt, payloads, disk writes or callbacks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import threading
import os
import weakref


@dataclass(frozen=True)
class PersistenceSnapshot:
    last_confirmed: str | None
    unresolved_count: int
    overflow: bool


class PersistenceStatus:
    """A successful unrelated save must not hide another file's failure.

    State is session-only, not a disk audit or a guarantee for writes that do
    not use the shared atomic/JSON helpers. Paths stay private to this model.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._last_confirmed = None
        self._failed = set()
        self._overflow = False

    def record(self, path: Path, *, confirmed: bool):
        key = path_key(path)
        with self._lock:
            if confirmed:
                self._last_confirmed = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                self._failed.discard(key)
            elif len(self._failed) < 128 or key in self._failed:
                self._failed.add(key)
            else:
                self._overflow = True

    def snapshot(self):
        with self._lock:
            return PersistenceSnapshot(self._last_confirmed, len(self._failed), self._overflow)


status = PersistenceStatus()


# Registry lock is held only to find a per-destination lock, never during I/O.
_registry_lock = threading.Lock()
_path_locks = weakref.WeakValueDictionary()


def path_key(path):
    p = Path(path)
    # Resolve parent aliases, not a final symlink: replace replaces the symlink
    # itself, not its target. Hardlinked names are separate publication slots.
    return os.path.normcase(str(p.parent.resolve() / p.name))


def publication_lock(path):
    key = path_key(path)
    with _registry_lock:
        lock = _path_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _path_locks[key] = lock
        return lock


def record_safely(path, *, confirmed):
    try:
        status.record(path, confirmed=confirmed)
    except Exception:
        # Monitoring must never change the persistence result. Conservatively
        # retain an observer-health warning using an independent primitive.
        observer_failed.set()


observer_failed = threading.Event()
