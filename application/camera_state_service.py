#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/camera_state_service.py — Tracks live runtime state for each PTZ camera

from __future__ import annotations

import threading
import logging
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from domain.ptz_camera_state import PTZCameraRuntimeState, PTZCameraState

if TYPE_CHECKING:
    from application.runtime_state_store import RuntimeStateStore

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class CameraStateService:
    """Tracks PTZCameraRuntimeState for every registered camera. Thread-safe."""

    def __init__(
        self,
        camera_ids: list[str],
        camera_role: str = "unknown",
        runtime_state_store: 'Optional[RuntimeStateStore]' = None,
    ) -> None:
        self._lock = threading.Lock()
        self._store = runtime_state_store  # #792 — fuente unica de verdad
        self._states: dict[str, PTZCameraRuntimeState] = {
            cam_id: PTZCameraRuntimeState(
                camera_id=cam_id,
                camera_role=camera_role,
                state=PTZCameraState.UNKNOWN,
                connected=False,
            )
            for cam_id in camera_ids
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update(self, camera_id: str, **kwargs) -> None:
        """Replace the state entry for camera_id, merging in kwargs."""
        current = self._states.get(camera_id)
        if current is None:
            return
        updated = PTZCameraRuntimeState(
            camera_id=current.camera_id,
            camera_role=current.camera_role,
            state=kwargs.get("state", current.state),
            connected=kwargs.get("connected", current.connected),
            current_command_id=kwargs.get("current_command_id", current.current_command_id),
            current_command_type=kwargs.get("current_command_type", current.current_command_type),
            last_success_at=kwargs.get("last_success_at", current.last_success_at),
            last_failure_at=kwargs.get("last_failure_at", current.last_failure_at),
            last_error=kwargs.get("last_error", current.last_error),
            queue_depth=kwargs.get("queue_depth", current.queue_depth),
            recent_latency_ms=kwargs.get("recent_latency_ms", current.recent_latency_ms),
        )
        self._states[camera_id] = updated
        # Refleja el estado en RuntimeStateStore (#792).
        if self._store is not None:
            new_state = kwargs.get("state", current.state)
            new_connected = kwargs.get("connected", current.connected)
            new_error = kwargs.get("last_error", current.last_error)
            try:
                self._store.update_camera(
                    camera_id,
                    connected=new_connected,
                    movement_state=new_state.value if hasattr(new_state, "value") else str(new_state),
                    last_error=new_error,
                    clear_error=(new_error is None and "last_error" in kwargs),
                    touch_last_seen=True,
                )
            except Exception:  # noqa: BLE001
                logger.exception("CameraStateService: error reflejando estado runtime")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_command_queued(
        self, camera_id: str, command_type: str, command_id: str
    ) -> None:
        with self._lock:
            self._update(
                camera_id,
                current_command_id=command_id,
                current_command_type=command_type,
            )

    def on_movement_started(self, camera_id: str) -> None:
        with self._lock:
            self._update(camera_id, state=PTZCameraState.MOVING)

    def on_preset_recall_started(self, camera_id: str, command_id: str) -> None:
        with self._lock:
            self._update(
                camera_id,
                state=PTZCameraState.PRESET_RECALLING,
                current_command_id=command_id,
            )

    def on_stop_issued(self, camera_id: str) -> None:
        with self._lock:
            self._update(camera_id, state=PTZCameraState.STOPPING)

    def on_command_succeeded(self, camera_id: str, latency_ms: Optional[int] = None) -> None:
        with self._lock:
            current = self._states.get(camera_id)
            if current is None:
                return
            # OFFLINE state is authoritative — don't overwrite it with a stale success
            if current.state == PTZCameraState.OFFLINE:
                return
            self._update(
                camera_id,
                state=PTZCameraState.IDLE,
                last_success_at=_now(),
                last_error=None,
                recent_latency_ms=latency_ms,
                current_command_id=None,
                current_command_type=None,
            )

    def on_command_failed(self, camera_id: str, error: str) -> None:
        with self._lock:
            self._update(
                camera_id,
                state=PTZCameraState.ERROR,
                last_failure_at=_now(),
                last_error=error,
                current_command_id=None,
                current_command_type=None,
            )

    def on_camera_connected(self, camera_id: str) -> None:
        with self._lock:
            current = self._states.get(camera_id)
            if current is None:
                return
            # Only move to IDLE when not already in an active state
            new_state = (
                PTZCameraState.IDLE
                if current.state in (PTZCameraState.OFFLINE, PTZCameraState.UNKNOWN)
                else current.state
            )
            self._update(camera_id, state=new_state, connected=True)

    def on_camera_offline(self, camera_id: str) -> None:
        with self._lock:
            self._update(camera_id, state=PTZCameraState.OFFLINE, connected=False)

    def on_polling_started(self, camera_id: str) -> None:
        with self._lock:
            self._update(camera_id, state=PTZCameraState.PRESET_POLLING)

    def on_polling_stopped(self, camera_id: str) -> None:
        with self._lock:
            current = self._states.get(camera_id)
            if current is None:
                return
            if current.state == PTZCameraState.PRESET_POLLING:
                self._update(camera_id, state=PTZCameraState.IDLE)

    def on_reset(self, camera_id: str) -> None:
        with self._lock:
            current = self._states.get(camera_id)
            if current is None:
                return
            self._states[camera_id] = PTZCameraRuntimeState(
                camera_id=current.camera_id,
                camera_role=current.camera_role,
                state=PTZCameraState.IDLE,
                connected=current.connected,
            )
            if self._store is not None:
                try:
                    self._store.update_camera(
                        camera_id,
                        movement_state=PTZCameraState.IDLE.value,
                        clear_preset=True,
                        clear_error=True,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("CameraStateService: error reflejando reset runtime")

    def get_state(self, camera_id: str) -> PTZCameraRuntimeState:
        with self._lock:
            state = self._states.get(camera_id)
        if state is None:
            raise KeyError(f"camera_id {camera_id!r} not registered in CameraStateService")
        return state

    def all_states(self) -> dict[str, PTZCameraRuntimeState]:
        with self._lock:
            return dict(self._states)
