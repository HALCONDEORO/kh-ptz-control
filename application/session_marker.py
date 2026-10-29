#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# session_marker.py — Runtime marker for interrupted-session detection (#120)
#
# Writes a small file when a session becomes active and removes it on clean end.
# On startup, a surviving marker means the previous session was interrupted
# (power loss, crash, kill -9) before shutdown() was called.
#
# The marker stores no personal data — only a timestamp for diagnostics.

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_WARNING_MESSAGE = (
    "Previous session may have ended unexpectedly. "
    "Check cameras before continuing."
)


def _default_marker_path() -> Path:
    from runtime.path_resolver import RuntimePathResolver
    return RuntimePathResolver().session_marker_file


def mark_session_active(path: Path | None = None) -> None:
    """Write the session-active marker. Called when a session starts."""
    if path is None:
        path = _default_marker_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(datetime.now().isoformat(), encoding="utf-8")
        logger.debug("Session marker created: %s", path)
    except OSError as exc:
        logger.warning("Could not write session marker %s: %s", path, exc)


def clear_session_marker(path: Path | None = None) -> None:
    """Remove the session-active marker. Called on clean session end."""
    if path is None:
        path = _default_marker_path()
    try:
        path.unlink(missing_ok=True)
        logger.debug("Session marker cleared: %s", path)
    except OSError as exc:
        logger.warning("Could not remove session marker %s: %s", path, exc)


def was_session_interrupted(path: Path | None = None) -> bool:
    """Return True if a session-active marker exists from a previous run.

    A surviving marker means the app did not reach the clean shutdown path
    (power loss, crash, SIGKILL) before clearing it. Logs a warning so
    operators and support see the event without any camera movement.
    """
    if path is None:
        path = _default_marker_path()
    if not path.exists():
        return False
    started_at = ""
    try:
        started_at = path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    logger.warning(
        "[STARTUP] %s (session started at: %s)",
        _WARNING_MESSAGE,
        started_at or "unknown",
    )
    return True
