#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/runtime_state_store.py — Single-writer runtime state store
#
# Issue: #790 — Epic #787 (single source of truth for runtime state)
#
# Design:
#   - One ``RuntimeStateStore`` instance is created in bootstrap.py and
#     injected wherever runtime state needs to be written or read.
#   - All mutations replace the internal ``RuntimeState`` snapshot atomically
#     under a threading.Lock — no partial updates are visible to readers.
#   - ``snapshot()`` returns an immutable ``RuntimeState`` copy; callers must
#     not cache it across event boundaries.
#   - Subscribers (callbacks) are notified after every mutation.
#     Callbacks run synchronously — keep them fast.
#
# Concurrency policy (see docs/CONCURRENCY_POLICY.md #798):
#   - The _lock protects only the _state replacement.
#   - Subscriber callbacks are called WITHOUT holding the lock so they can
#     safely call snapshot() without deadlocking.
#   - All update_*() methods are safe to call from any thread.

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from domain.runtime_state import (
    AtemRuntimeState,
    CameraRuntimeState,
    DiagnosticsRuntimeState,
    LifecycleState,
    OperationsState,
    RuntimeState,
    SessionRuntimeState,
)
from domain.time_utils import utc_now_iso as _utc_now

logger = logging.getLogger(__name__)


class RuntimeStateStore:
    """
    Single-writer store for ``RuntimeState``.

    Only one instance should exist (created by bootstrap.py and injected
    as a dependency).  All application-layer services that own a piece of
    runtime state call the relevant ``update_*`` method to keep the snapshot
    current.

    Parameters
    ----------
    camera_ids:
        IDs of cameras known at startup.  Each gets an initial
        ``CameraRuntimeState(configured=True, connected=False)``.
    """

    def __init__(self, camera_ids: 'list[str] | None' = None) -> None:
        self._lock = threading.Lock()
        self._state = RuntimeState.clean_state(camera_ids or [])
        self._subscribers: list[Callable[[RuntimeState], None]] = []

    # ── Subscription ──────────────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[RuntimeState], None]) -> None:
        """Register a callback to be called after every state mutation."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[RuntimeState], None]) -> None:
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass

    # ── Read ──────────────────────────────────────────────────────────────────

    def snapshot(self) -> RuntimeState:
        """Return the current immutable ``RuntimeState``."""
        with self._lock:
            return self._state

    # ── Lifecycle updates ─────────────────────────────────────────────────────

    def update_lifecycle(
        self,
        *,
        startup_complete: Optional[bool] = None,
        shutdown_in_progress: Optional[bool] = None,
        last_error: Optional[str] = None,
        clear_error: bool = False,
    ) -> None:
        """Update application lifecycle phase flags."""
        with self._lock:
            current = self._state.lifecycle
            new_error = None if clear_error else (last_error if last_error is not None else current.last_error)
            self._state = RuntimeState(
                lifecycle=LifecycleState(
                    startup_complete=startup_complete if startup_complete is not None else current.startup_complete,
                    shutdown_in_progress=shutdown_in_progress if shutdown_in_progress is not None else current.shutdown_in_progress,
                    last_error=new_error,
                ),
                session=self._state.session,
                cameras=self._state.cameras,
                atem=self._state.atem,
                operations=self._state.operations,
                diagnostics=self._state.diagnostics,
            )
            snapshot = self._state
        self._notify(snapshot)

    # ── Session updates ───────────────────────────────────────────────────────

    def update_session(
        self,
        *,
        active: Optional[bool] = None,
        session_id: Optional[str] = None,
        chairman_name: Optional[str] = None,
        clear_chairman: bool = False,
        started_at: Optional[str] = None,
        clear_session_id: bool = False,
        clear_started_at: bool = False,
    ) -> None:
        """
        Update session runtime state.

        Pass ``clear_chairman=True`` to set chairman_name to None.
        Pass ``clear_session_id=True`` to set session_id to None.
        Pass ``clear_started_at=True`` to set started_at to None.
        """
        with self._lock:
            current = self._state.session
            new_chairman = None if clear_chairman else (chairman_name if chairman_name is not None else current.chairman_name)
            new_session_id = None if clear_session_id else (session_id if session_id is not None else current.session_id)
            new_started_at = None if clear_started_at else (started_at if started_at is not None else current.started_at)
            self._state = RuntimeState(
                lifecycle=self._state.lifecycle,
                session=SessionRuntimeState(
                    active=active if active is not None else current.active,
                    session_id=new_session_id,
                    chairman_name=new_chairman,
                    started_at=new_started_at,
                ),
                cameras=self._state.cameras,
                atem=self._state.atem,
                operations=self._state.operations,
                diagnostics=self._state.diagnostics,
            )
            snapshot = self._state
        self._notify(snapshot)

    # ── Camera updates ────────────────────────────────────────────────────────

    def update_camera(
        self,
        camera_id: str,
        *,
        configured: Optional[bool] = None,
        connected: Optional[bool] = None,
        movement_state: Optional[str] = None,
        active_preset: Optional[int] = None,
        clear_preset: bool = False,
        last_error: Optional[str] = None,
        clear_error: bool = False,
        last_seen_at: Optional[str] = None,
        touch_last_seen: bool = False,
    ) -> None:
        """Update a single camera's runtime state."""
        with self._lock:
            cameras = dict(self._state.cameras)
            current = cameras.get(camera_id, CameraRuntimeState(camera_id=camera_id))
            new_preset = None if clear_preset else (active_preset if active_preset is not None else current.active_preset)
            new_error = None if clear_error else (last_error if last_error is not None else current.last_error)
            new_seen = last_seen_at or (_utc_now() if touch_last_seen else current.last_seen_at)
            cameras[camera_id] = CameraRuntimeState(
                camera_id=camera_id,
                configured=configured if configured is not None else current.configured,
                connected=connected if connected is not None else current.connected,
                movement_state=movement_state if movement_state is not None else current.movement_state,
                active_preset=new_preset,
                last_error=new_error,
                last_seen_at=new_seen,
            )
            self._state = RuntimeState(
                lifecycle=self._state.lifecycle,
                session=self._state.session,
                cameras=cameras,
                atem=self._state.atem,
                operations=self._state.operations,
                diagnostics=self._state.diagnostics,
            )
            snapshot = self._state
        self._notify(snapshot)

    # ── ATEM updates ──────────────────────────────────────────────────────────

    def update_atem(
        self,
        *,
        enabled: Optional[bool] = None,
        connection_state: Optional[str] = None,
        program_input: Optional[int] = None,
        preview_input: Optional[int] = None,
        last_error: Optional[str] = None,
        clear_error: bool = False,
    ) -> None:
        """Update ATEM switcher runtime state."""
        with self._lock:
            current = self._state.atem
            new_error = None if clear_error else (last_error if last_error is not None else current.last_error)
            self._state = RuntimeState(
                lifecycle=self._state.lifecycle,
                session=self._state.session,
                cameras=self._state.cameras,
                atem=AtemRuntimeState(
                    enabled=enabled if enabled is not None else current.enabled,
                    connection_state=connection_state if connection_state is not None else current.connection_state,
                    program_input=program_input if program_input is not None else current.program_input,
                    preview_input=preview_input if preview_input is not None else current.preview_input,
                    last_error=new_error,
                ),
                operations=self._state.operations,
                diagnostics=self._state.diagnostics,
            )
            snapshot = self._state
        self._notify(snapshot)

    # ── Operations updates ────────────────────────────────────────────────────

    def begin_operation(self, action: str) -> None:
        """Record that an operator action has started."""
        with self._lock:
            self._state = RuntimeState(
                lifecycle=self._state.lifecycle,
                session=self._state.session,
                cameras=self._state.cameras,
                atem=self._state.atem,
                operations=OperationsState(
                    safety_reset_in_progress=self._state.operations.safety_reset_in_progress,
                    active_operator_action=action,
                ),
                diagnostics=self._state.diagnostics,
            )
            snapshot = self._state
        self._notify(snapshot)

    def end_operation(self) -> None:
        """Clear the active operator action."""
        with self._lock:
            self._state = RuntimeState(
                lifecycle=self._state.lifecycle,
                session=self._state.session,
                cameras=self._state.cameras,
                atem=self._state.atem,
                operations=OperationsState(
                    safety_reset_in_progress=self._state.operations.safety_reset_in_progress,
                    active_operator_action=None,
                ),
                diagnostics=self._state.diagnostics,
            )
            snapshot = self._state
        self._notify(snapshot)

    # ── Safety Reset ──────────────────────────────────────────────────────────

    def begin_safety_reset(self) -> None:
        """Mark Safety Reset as in-progress."""
        with self._lock:
            self._state = RuntimeState(
                lifecycle=self._state.lifecycle,
                session=self._state.session,
                cameras=self._state.cameras,
                atem=self._state.atem,
                operations=OperationsState(
                    safety_reset_in_progress=True,
                    active_operator_action=self._state.operations.active_operator_action,
                ),
                diagnostics=self._state.diagnostics,
            )
            snapshot = self._state
        self._notify(snapshot)

    def apply_safety_reset_clean_state(self) -> None:
        """
        Apply the post-Safety-Reset clean state.

        Clears:
          - session.active, session_id, chairman_name
          - all camera movement_state → "unknown"
          - operations.safety_reset_in_progress → False
          - operations.active_operator_action → None

        Does NOT clear:
          - camera.configured / camera.connected (hardware status unchanged)
          - lifecycle, atem, diagnostics
        """
        with self._lock:
            # Preserve camera configured/connected; reset movement and preset
            cameras = {}
            for cam_id, cam in self._state.cameras.items():
                cameras[cam_id] = CameraRuntimeState(
                    camera_id=cam_id,
                    configured=cam.configured,
                    connected=cam.connected,
                    movement_state="unknown",
                    active_preset=None,
                    last_error=None,
                    last_seen_at=cam.last_seen_at,
                )
            self._state = RuntimeState(
                lifecycle=self._state.lifecycle,
                session=SessionRuntimeState(active=False),
                cameras=cameras,
                atem=self._state.atem,
                operations=OperationsState(
                    safety_reset_in_progress=False,
                    active_operator_action=None,
                ),
                diagnostics=self._state.diagnostics,
            )
            snapshot = self._state
        self._notify(snapshot)

    # ── Diagnostics updates ───────────────────────────────────────────────────

    def update_diagnostics(
        self,
        *,
        degraded: Optional[bool] = None,
        degraded_reason: Optional[str] = None,
        clear_reason: bool = False,
    ) -> None:
        """Update runtime health/degraded-mode state."""
        with self._lock:
            current = self._state.diagnostics
            new_reason = None if clear_reason else (degraded_reason if degraded_reason is not None else current.degraded_reason)
            self._state = RuntimeState(
                lifecycle=self._state.lifecycle,
                session=self._state.session,
                cameras=self._state.cameras,
                atem=self._state.atem,
                operations=self._state.operations,
                diagnostics=DiagnosticsRuntimeState(
                    degraded=degraded if degraded is not None else current.degraded,
                    degraded_reason=new_reason,
                ),
            )
            snapshot = self._state
        self._notify(snapshot)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _notify(self, snapshot: RuntimeState) -> None:
        """Call all subscribers with the new snapshot (lock NOT held)."""
        for cb in list(self._subscribers):
            try:
                cb(snapshot)
            except Exception:
                logger.exception("RuntimeStateStore: subscriber raised during notification")
