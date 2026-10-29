#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/flight_recorder.py — Local black box JSONL writer (#488)
#
# Usage:
#   recorder = FlightRecorder(events_file=path_resolver.blackbox_events_file)
#   recorder.record(event)              # never raises into live operation
#   events = recorder.get_recent(50)    # list[dict], newest last
#
# Safe failure contract:
#   Any I/O failure is swallowed and logged to stderr with a [flight_recorder] prefix.
#   Camera/session/operator actions are NEVER blocked by recorder failures.
#
# Rotation:
#   When events.jsonl exceeds MAX_FILE_BYTES it is rotated to events.1.jsonl …
#   events.{MAX_ROTATED}.jsonl.  The oldest file is deleted.  Rotation is done
#   atomically by rename so the active file is always events.jsonl.
#
# See docs/BLACK_BOX_SCHEMA.md for event schema, retention and redaction policy.

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domain.blackbox_event import BlackBoxEvent, redact_event_dict

logger = logging.getLogger(__name__)

# ── Rotation constants ────────────────────────────────────────────────────────

MAX_FILE_BYTES  = 10 * 1024 * 1024   # 10 MB
MAX_ROTATED     = 5                   # keep events.1 … events.5


# ── FlightRecorder ────────────────────────────────────────────────────────────

class FlightRecorder:
    """
    Append-only JSONL black box event recorder.

    Parameters
    ----------
    events_file:
        Path to the active event log file (e.g. /var/log/khptz/blackbox/events.jsonl).
        The parent directory is created on first write if it does not exist.
    max_file_bytes:
        Rotate when the file exceeds this size. Default: 10 MB.
    max_rotated:
        Number of rotated backup files to keep. Default: 5.
    _write_fn:
        Injectable for tests — replaces the real file-append call.
        Signature: (path: Path, line: str) -> None
    """

    def __init__(
        self,
        events_file: Path | str,
        max_file_bytes: int = MAX_FILE_BYTES,
        max_rotated: int = MAX_ROTATED,
        _write_fn=None,
    ) -> None:
        self._events_file  = Path(events_file)
        self._max_bytes    = max_file_bytes
        self._max_rotated  = max_rotated
        self._write_fn     = _write_fn or self._append_line

    # ── Public API ────────────────────────────────────────────────────────────

    def record(self, event: BlackBoxEvent) -> None:
        """
        Write *event* as a single JSONL line.

        Never raises. Any failure is printed to stderr and silently dropped.
        """
        try:
            raw = redact_event_dict(event.to_dict())
            line = json.dumps(raw, ensure_ascii=True, default=str) + "\n"
            self._safe_write(line)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"record() failed: {exc}")

    def record_dict(self, data: dict[str, Any]) -> None:
        """
        Write an arbitrary dict as a JSONL line.

        Applies basic secret redaction before writing.
        Never raises.
        """
        try:
            raw = redact_event_dict(data)
            line = json.dumps(raw, ensure_ascii=True, default=str) + "\n"
            self._safe_write(line)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"record_dict() failed: {exc}")

    def get_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Return the *limit* most-recent events (newest last), each as a plain dict.

        Reads only from the active events file.  Never raises; returns [] on error.
        """
        try:
            if not self._events_file.exists():
                return []
            lines = self._events_file.read_text(encoding="utf-8", errors="replace").splitlines()
            # Take the last *limit* non-empty lines
            tail = [ln for ln in lines if ln.strip()][-limit:]
            result: list[dict[str, Any]] = []
            for line in tail:
                try:
                    result.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # skip corrupt lines
            return result
        except Exception as exc:  # noqa: BLE001
            self._warn(f"get_recent() failed: {exc}")
            return []

    def export_for_support(self, limit: int = 500) -> list[dict[str, Any]]:
        """
        Return up to *limit* recent events suitable for inclusion in a support bundle.

        Redaction has already been applied at write time; this call does not
        re-redact.  Never raises; returns [] on error.
        """
        return self.get_recent(limit)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _safe_write(self, line: str) -> None:
        """Write *line* to the events file; rotate first if the file is too large."""
        try:
            parent = self._events_file.parent
            parent.mkdir(parents=True, exist_ok=True)

            if self._events_file.exists() and self._events_file.stat().st_size >= self._max_bytes:
                self._rotate()

            self._write_fn(self._events_file, line)
        except Exception as exc:  # noqa: BLE001
            self._warn(f"_safe_write() failed: {exc}")

    def _rotate(self) -> None:
        """
        Rotate log files: events.jsonl → events.1.jsonl … events.{N}.jsonl.

        The oldest file (events.{max_rotated}.jsonl) is deleted if it exists.
        Never raises.
        """
        try:
            stem = self._events_file.stem    # "events"
            parent = self._events_file.parent

            # Delete the oldest rotated file
            oldest = parent / f"{stem}.{self._max_rotated}.jsonl"
            if oldest.exists():
                oldest.unlink()

            # Shift existing rotated files: events.4 → events.5, etc.
            for n in range(self._max_rotated - 1, 0, -1):
                src = parent / f"{stem}.{n}.jsonl"
                dst = parent / f"{stem}.{n + 1}.jsonl"
                if src.exists():
                    src.rename(dst)

            # Rotate active file to events.1.jsonl
            dest = parent / f"{stem}.1.jsonl"
            self._events_file.rename(dest)

        except Exception as exc:  # noqa: BLE001
            self._warn(f"_rotate() failed: {exc}")

    @staticmethod
    def _append_line(path: Path, line: str) -> None:
        """Default write implementation: open in append mode."""
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)

    @staticmethod
    def _warn(msg: str) -> None:
        """Emit a non-fatal warning through the standard logging system."""
        logger.warning("[flight_recorder] %s", msg)
