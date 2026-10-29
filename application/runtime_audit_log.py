#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/runtime_audit_log.py — Runtime state-transition audit log
#
# Issue: #799 — Epic #787 (single source of truth for runtime state)
#
# Purpose:
#   A snapshot tells support what the app believes NOW.
#   This audit log tells support HOW IT GOT THERE.
#
#   Records important runtime transitions: session start/end, Safety Reset,
#   camera connect/disconnect, ATEM state changes and operator actions.
#
# Design:
#   - In-memory ring buffer (configurable max entries, default 200).
#   - Thread-safe via threading.Lock.
#   - Serialisable to plain dict list for export (support bundle, khptz doctor).
#   - PII-free: chairman names not stored; session IDs are OK (non-sensitive).
#   - Subscribes to RuntimeStateStore changes and records diffs automatically.
#
# Usage:
#   log = RuntimeAuditLog()
#   store.subscribe(log.on_state_change)
#   # — or record manually —
#   log.record("safety_reset_initiated", {"source": "operator"})

from __future__ import annotations

import threading
from collections import deque
from typing import Optional

from domain.runtime_state import RuntimeState
from domain.time_utils import utc_now_iso as _utc_now


class AuditEntry:
    """A single immutable audit log entry."""

    __slots__ = ("timestamp", "event", "details")

    def __init__(self, event: str, details: dict | None = None) -> None:
        self.timestamp: str = _utc_now()
        self.event: str = event
        self.details: dict = details or {}

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "event": self.event,
            "details": self.details,
        }


class RuntimeAuditLog:
    """
    In-memory ring buffer of runtime state-transition events.

    Thread-safe.  PII-free: chairman names are not stored.

    Parameters
    ----------
    max_entries:
        Maximum number of entries retained (oldest are discarded).
        Default: 200.
    """

    def __init__(self, max_entries: int = 200) -> None:
        self._lock = threading.Lock()
        self._entries: deque[AuditEntry] = deque(maxlen=max_entries)
        self._prev_snapshot: Optional[RuntimeState] = None

    # ── Manual recording ──────────────────────────────────────────────────────

    def record(self, event: str, details: dict | None = None) -> None:
        """Append a manual audit entry."""
        with self._lock:
            self._entries.append(AuditEntry(event, details))

    # ── Automatic recording via RuntimeStateStore subscription ────────────────

    def on_state_change(self, new_state: RuntimeState) -> None:
        """
        Subscriber callback — call this from RuntimeStateStore.subscribe().

        Diffs the new state against the previous snapshot and records
        interesting transitions automatically.
        """
        with self._lock:
            prev = self._prev_snapshot
            first = prev is None
            # Use the default clean state as the baseline for the first diff
            prev_for_diff = prev if prev is not None else RuntimeState()
            self._prev_snapshot = new_state
            entries = list(self._detect_transitions(prev_for_diff, new_state, first=first))
            for entry in entries:
                self._entries.append(entry)

    def _detect_transitions(
        self, prev: RuntimeState, new: RuntimeState, *, first: bool = False
    ) -> 'list[AuditEntry]':
        entries: list[AuditEntry] = []

        if first:
            entries.append(AuditEntry("runtime_state_initialized", {
                "session_active": new.session.active,
                "cameras": list(new.cameras.keys()),
            }))

        # Session transitions
        if prev.session.active != new.session.active:
            if new.session.active:
                entries.append(AuditEntry("session_started", {
                    "session_id": new.session.session_id,
                }))
            else:
                entries.append(AuditEntry("session_ended", {
                    "previous_session_id": prev.session.session_id,
                }))

        # Chairman assigned/cleared (name not stored — PII)
        prev_has_chairman = prev.session.chairman_name is not None
        new_has_chairman = new.session.chairman_name is not None
        if not prev_has_chairman and new_has_chairman:
            entries.append(AuditEntry("chairman_assigned", {}))
        elif prev_has_chairman and not new_has_chairman:
            entries.append(AuditEntry("chairman_cleared", {}))

        # Safety Reset transitions
        if not prev.operations.safety_reset_in_progress and new.operations.safety_reset_in_progress:
            entries.append(AuditEntry("safety_reset_initiated", {}))
        if prev.operations.safety_reset_in_progress and not new.operations.safety_reset_in_progress:
            entries.append(AuditEntry("safety_reset_complete", {}))

        # Operator actions
        if prev.operations.active_operator_action != new.operations.active_operator_action:
            if new.operations.active_operator_action:
                entries.append(AuditEntry("operator_action_started", {
                    "action": new.operations.active_operator_action,
                }))
            elif prev.operations.active_operator_action:
                entries.append(AuditEntry("operator_action_ended", {
                    "action": prev.operations.active_operator_action,
                }))

        # Camera state transitions
        all_ids = set(prev.cameras) | set(new.cameras)
        for cam_id in sorted(all_ids):
            prev_cam = prev.cameras.get(cam_id)
            new_cam = new.cameras.get(cam_id)
            if prev_cam is None and new_cam is not None:
                entries.append(AuditEntry("camera_registered", {"camera_id": cam_id}))
                if new_cam.connected:
                    entries.append(AuditEntry("camera_connected", {"camera_id": cam_id}))
                continue
            if prev_cam is None or new_cam is None:
                continue
            if prev_cam.connected != new_cam.connected:
                if new_cam.connected:
                    entries.append(AuditEntry("camera_connected", {"camera_id": cam_id}))
                else:
                    entries.append(AuditEntry("camera_disconnected", {"camera_id": cam_id}))
            if prev_cam.movement_state != new_cam.movement_state:
                entries.append(AuditEntry("camera_movement_state_changed", {
                    "camera_id": cam_id,
                    "from": prev_cam.movement_state,
                    "to": new_cam.movement_state,
                }))

        # ATEM state transitions
        if prev.atem.connection_state != new.atem.connection_state:
            entries.append(AuditEntry("atem_state_changed", {
                "from": prev.atem.connection_state,
                "to": new.atem.connection_state,
            }))

        # Lifecycle transitions
        if not prev.lifecycle.startup_complete and new.lifecycle.startup_complete:
            entries.append(AuditEntry("startup_complete", {}))
        if not prev.lifecycle.shutdown_in_progress and new.lifecycle.shutdown_in_progress:
            entries.append(AuditEntry("shutdown_initiated", {}))

        return entries

    # ── Export ────────────────────────────────────────────────────────────────

    def entries(self) -> list[AuditEntry]:
        """Return a copy of all current entries (oldest first)."""
        with self._lock:
            return list(self._entries)

    def to_dict_list(self) -> list[dict]:
        """Serialisable list of entry dicts for export."""
        return [e.to_dict() for e in self.entries()]

    def clear(self) -> None:
        """Clear all entries (e.g. after export)."""
        with self._lock:
            self._entries.clear()
            self._prev_snapshot = None
