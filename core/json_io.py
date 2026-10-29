#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# json_io.py — Lectura/escritura atómica de JSON con bloqueo por archivo

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _registry_lock:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def _try_bak(p: Path, default: Any) -> Any:
    """Attempt to load .bak for *p*. Returns the loaded data or *default*."""
    bak = p.with_suffix(".bak")
    if not bak.exists():
        return default
    try:
        data = json.loads(bak.read_text(encoding="utf-8"))
        logger.info("Loaded backup %s after corrupt primary file", bak)
        return data
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        logger.warning("Backup %s also unreadable: %s — using defaults", bak, exc)
        return default


def _preserve_corrupt(p: Path) -> None:
    """Rename the corrupt file to .corrupt.TIMESTAMP so it can be diagnosed."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    corrupt_path = p.with_name(f"{p.stem}.corrupt.{timestamp}{p.suffix}")
    try:
        shutil.copy2(p, corrupt_path)
        logger.info("Corrupt file preserved as %s", corrupt_path)
    except OSError as exc:
        logger.warning("Could not preserve corrupt file %s: %s", p, exc)


def load_json(path: Path | str, default: Any = None) -> Any:
    """
    Read JSON safely. Returns *default* if the file does not exist.

    When the file is corrupt:
    - Logs a warning with the file path (no file contents or secrets).
    - Copies the corrupt file to <name>.corrupt.TIMESTAMP for diagnosis.
    - Tries the .bak file if available.
    - Falls back to *default* with a clear warning when no backup exists.
    """
    p = Path(path)
    lock = _lock_for(p)
    with lock:
        if not p.exists():
            return default
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in %s: %s — attempting recovery", p, exc)
        except UnicodeDecodeError as exc:
            logger.warning("Cannot decode %s: %s — attempting recovery", p, exc)
        except OSError as exc:
            logger.warning("Cannot read %s: %s", p, exc)
            return default

        _preserve_corrupt(p)
        recovered = _try_bak(p, default)
        if recovered is default:
            logger.warning(
                "No valid backup for %s — using safe defaults. "
                "Check %s.corrupt.* for diagnosis.",
                p, p.stem,
            )
        return recovered


def _apply_group_access(tmp_path: str, directory: Path) -> None:
    """Let the file's group reach it when its directory says the group may.

    ``tempfile.mkstemp`` always creates 0600, and ``os.replace`` preserves that,
    so every data file ends up readable only by whoever wrote it. That is
    correct while a single identity owns the data, but it silently breaks the
    session-owned GUI (#885), where two identities share ``/var/lib/hallptz``
    through the ``hallptz`` group: files written by the service become unreadable
    to the GUI, and files written by the GUI become unreadable to ``hallptz
    doctor`` / ``hallptz backup``.

    The directory already encodes the intent — the installer makes the runtime
    directories setgid group-writable only in that mode — so mirror it:

    * group-writable directory  -> 0660, both identities can read and write;
    * anything else             -> left at 0600, exactly as before.

    Best-effort: a filesystem that cannot express this (or a chmod denied by
    the OS) must never fail the write itself.
    """
    from core.atomic_write import group_shared_mode

    mode = group_shared_mode(directory)
    if mode is None:
        return
    try:
        os.chmod(tmp_path, mode)
    except OSError as exc:  # noqa: BLE001 - never fail a save over permissions
        logger.debug("No se pudo ajustar el acceso de grupo en %s: %s", tmp_path, exc)


def save_json(path: Path | str, data: Any, indent: int = 2) -> bool:
    """
    Escribe `data` en `path` de forma atómica (temp-file + os.replace) con backup
    y bloqueo por archivo. Si el archivo ya existe, crea `.bak` antes de reemplazarlo.
    Devuelve True si tuvo éxito.
    """
    p = Path(path)
    lock = _lock_for(p)
    with lock:
        try:
            text = json.dumps(data, ensure_ascii=False, indent=indent)
            dir_ = p.parent
            dir_.mkdir(parents=True, exist_ok=True)

            if p.exists():
                bak = p.with_suffix('.bak')
                try:
                    shutil.copy2(p, bak)
                except OSError as exc:
                    logger.warning("No se pudo crear backup de %s: %s", p, exc)

            fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(text)
                    fh.flush()
                    try:
                        os.fsync(fh.fileno())
                    except OSError:
                        pass
                _apply_group_access(tmp, dir_)
                os.replace(tmp, p)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            return True
        except (OSError, TypeError, ValueError):
            return False


def detect_leftover_files(directory: Path | str) -> list[Path]:
    """Scan *directory* for leftover temporary or diagnostic files from interrupted writes.

    Returns a list of suspicious files. Does NOT delete anything.

    Files reported:
    - `.tmp_*.json`  — temp files from an interrupted atomic write
    - `*.corrupt.*`  — diagnostic copies preserved after json_io recovered from corruption

    Callers should log a warning for each returned path so operators and support
    know that a previous write was interrupted. Do not auto-delete these files;
    they may be needed for diagnosis.
    """
    d = Path(directory)
    if not d.is_dir():
        return []

    found: list[Path] = []
    for pattern in (".tmp_*.json", "*.corrupt.*"):
        found.extend(d.glob(pattern))
    return sorted(found)
