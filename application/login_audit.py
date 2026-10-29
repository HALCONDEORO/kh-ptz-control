#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/login_audit.py — Persistent login audit log (single source of truth)
#
# Records login success/failure events to a persistent JSON file under the
# runtime data dir, and answers "when was the last successful access?".
#
# This logic used to live inline (and duplicated) inside ui/login_screen.py:
# both the writer and the last-login reader opened login_audit.json with their
# own load/save code. Centralising it here gives one owner of the file path,
# the rotation cap and the swallow-on-error contract, and lets future admin/
# support code reuse the same log instead of re-implementing it.
#
# Safe failure contract: any I/O failure is swallowed. Login must never be
# blocked by an audit-log write failure.

from __future__ import annotations

import datetime
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Keep the tail of the log bounded so the file never grows without limit.
_MAX_EVENTS = 200


def _audit_file() -> Path:
    """Location of the persistent login audit log under the runtime data dir."""
    from runtime.path_resolver import RuntimePathResolver
    return RuntimePathResolver().data_dir / "login_audit.json"


def record_login_event(success: bool, attempts: int) -> None:
    """Append a login event to the audit log and rotate if oversized.

    Never raises — a failed audit write must not block login.
    """
    try:
        from core.json_io import load_json, save_json

        audit_file = _audit_file()
        events = load_json(audit_file, default=[])
        if not isinstance(events, list):
            events = []
        events.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "event_type": "login_success" if success else "login_failure",
            "attempts": attempts,
        })
        if len(events) > _MAX_EVENTS:
            events = events[-_MAX_EVENTS:]
        save_json(audit_file, events)
    except Exception:
        logger.debug("login_audit: could not record event", exc_info=True)


def read_last_login_timestamp() -> str:
    """Return formatted last-login string, or empty string if none/unavailable."""
    try:
        from core.json_io import load_json

        events = load_json(_audit_file(), default=[])
        if not isinstance(events, list):
            return ""
        successes = [e for e in events if e.get("event_type") == "login_success"]
        if not successes:
            return ""
        ts = successes[-1].get("timestamp", "")
        if not ts:
            return ""
        dt = datetime.datetime.fromisoformat(ts)
        return dt.strftime("Last access: %Y-%m-%d %H:%M")
    except Exception:
        return ""
