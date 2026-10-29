# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Canonical UTC timestamp helpers.

Single source of truth for ISO-8601 timestamps used across logs, events,
incidents, audit trails and support bundles. Keeping one implementation here
avoids the format drift (millisecond vs second precision) that previously
existed when each service defined its own ``_utc_now``.

Pure domain code: no I/O, no PyQt.
"""

from datetime import datetime, timezone

__all__ = ["utc_now_iso", "utc_now_compact"]


def utc_now_iso() -> str:
    """UTC timestamp as ISO-8601 with millisecond precision and ``Z`` suffix.

    Example: ``2026-06-23T14:05:09.123Z``. This is the canonical format for
    all structured records (events, audit log, incidents, bundles).
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def utc_now_compact() -> str:
    """UTC timestamp safe for filenames: ``20260623-140509`` (no separators)."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
