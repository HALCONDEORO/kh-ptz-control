#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Atomic file writes for critical customer data.

This module is the single implementation of safe persistence for files that
must never be left half-written or corrupted if the app crashes, power is
lost or a write fails mid-way.  Use it for all config/layout/preset/manifest
writes that are not plain JSON (which goes through core.json_io.save_json).

Policy implemented:
  1. Parent directory is created if it does not exist.
  2. Content is written to a temporary file in the same directory (same FS,
     guaranteeing that os.replace is atomic at the filesystem level).
  3. A unique temp file is created privately (0600) via mkstemp/O_EXCL, so secrets never
     have a world-readable window before the final mode is applied.
  4. The temp file is fsync'd before the rename, and the parent directory is
     fsync'd after, so a completed write survives power loss (best-effort:
     directory fsync is a no-op where unsupported, e.g. Windows).
  5. On success: os.replace atomically renames tmp → dest.
  6. On failure: the temporary file is removed so no .tmp orphan is left.
  7. For text: encoded to UTF-8 before write so the caller handles str.

An optional *mode* applies explicit permissions to the destination (e.g. 0o600
for secrets, 0o640 for service-readable config). Ownership (chown) is the
caller's responsibility — it requires privilege and lives in the provisioning
layer, not here.

When no *mode* is given the destination directory decides: a group-writable
directory yields 0o660 so both identities sharing it can read and write, and
anything else keeps the private 0600 default. See group_shared_mode() — without
it, restoring a backup or importing a layout wrote files only their creator
could read, which is how a session-owned GUI ends up with no presets after a
recovery (#885).

Concurrent writers use separate temporary files; the last rename wins.
Read-modify-write callers still need a lock (or core.json_io.save_json).

Raises OSError on failure — callers decide how to handle/log it.
"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


def group_shared_mode(directory: Path) -> "int | None":
    """Return 0o660 when *directory* is shared with its group, else None.

    Single definition of the file-access policy for runtime data (#885).

    Data files are created privately (0600), which is correct while one identity
    owns them and silently wrong once two share a directory through the ``khptz``
    group: the session-owned GUI cannot read what the service wrote, and ``khptz
    doctor`` / ``khptz backup`` cannot read what the GUI wrote. The installer
    already states the intent by making the runtime directories setgid
    group-writable in that mode, so read it back from the directory rather than
    asking every caller to know which mode the appliance is in.

    Returning None means "leave the private default alone", so a system-mode
    install is not widened at all.
    """
    try:
        if directory.stat().st_mode & stat.S_IWGRP:
            return 0o660
    except OSError:
        pass
    return None


def _fsync_dir(dirpath: Path) -> None:
    """Best-effort fsync of *dirpath* so a rename into it is durable.

    No-op where opening a directory for fsync is unsupported (e.g. Windows),
    which is acceptable: durability of the directory entry is a Linux/Pi concern.
    """
    try:
        fd = os.open(str(dirpath), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_bytes_atomic(dest: Path, data: bytes, *, mode: "int | None" = None) -> None:
    """Write *data* to *dest* atomically (tmp + fsync + os.replace).

    Creates parent directories as needed. The temp file is created privately
    (0600) and fsync'd before the rename; the parent directory is fsync'd after.
    If *mode* is given, it is applied to the file before the rename. If the
    write or rename fails, the temporary file is removed and OSError is
    re-raised so the existing *dest* is never corrupted.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    # No explicit mode: follow the directory's own intent. Callers that need a
    # specific mode (secrets pass 0o600) are honoured exactly as before.
    if mode is None:
        mode = group_shared_mode(dest.parent)
    # mkstemp uses exclusive creation (O_EXCL) and private mode, so no
    # pre-planted symlink is followed and concurrent writers never unlink or
    # overwrite one another's temporary file. Keep it on the destination FS.
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.name}.", suffix=".tmp",
                                   dir=str(dest.parent))
    tmp = Path(tmp_name)
    try:
        try:
            mv = memoryview(data)
            written = 0
            while written < len(mv):
                written += os.write(fd, mv[written:])
            if mode is not None:
                try:
                    os.fchmod(fd, mode)
                except (AttributeError, OSError):
                    pass
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    _fsync_dir(dest.parent)


def write_text_atomic(
    dest: Path, text: str, encoding: str = "utf-8", *, mode: "int | None" = None
) -> None:
    """Write *text* to *dest* atomically.

    Encodes to *encoding* (default UTF-8) then delegates to write_bytes_atomic.
    """
    write_bytes_atomic(dest, text.encode(encoding), mode=mode)
