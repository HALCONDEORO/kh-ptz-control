#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_ptz_runtime_state.py — Tests for PTZ runtime camera state model (#701)

from __future__ import annotations

import pytest

from application.camera_state_service import CameraStateService
from application.runtime_state_store import RuntimeStateStore
from domain.ptz_camera_state import PTZCameraState


CAM = "cam-1"
CAM2 = "cam-2"


def make_service(*camera_ids: str) -> CameraStateService:
    return CameraStateService(list(camera_ids), camera_role="wide")


def make_service_with_store(*camera_ids: str) -> tuple[CameraStateService, RuntimeStateStore]:
    store = RuntimeStateStore(camera_ids=list(camera_ids))
    return CameraStateService(
        list(camera_ids),
        camera_role="wide",
        runtime_state_store=store,
    ), store


# ------------------------------------------------------------------
# Initial state
# ------------------------------------------------------------------


def test_initial_state_is_unknown() -> None:
    svc = make_service(CAM)
    assert svc.get_state(CAM).state == PTZCameraState.UNKNOWN


# ------------------------------------------------------------------
# Movement
# ------------------------------------------------------------------


def test_movement_transitions_to_moving() -> None:
    svc = make_service(CAM)
    svc.on_movement_started(CAM)
    assert svc.get_state(CAM).state == PTZCameraState.MOVING


# ------------------------------------------------------------------
# Stop
# ------------------------------------------------------------------


def test_stop_transitions_to_stopping() -> None:
    svc = make_service(CAM)
    svc.on_movement_started(CAM)
    svc.on_stop_issued(CAM)
    assert svc.get_state(CAM).state == PTZCameraState.STOPPING


def test_command_succeeded_from_stopping_transitions_to_idle() -> None:
    svc = make_service(CAM)
    svc.on_movement_started(CAM)
    svc.on_stop_issued(CAM)
    svc.on_command_succeeded(CAM, latency_ms=12)
    state = svc.get_state(CAM)
    assert state.state == PTZCameraState.IDLE
    assert state.recent_latency_ms == 12


# ------------------------------------------------------------------
# Failures
# ------------------------------------------------------------------


def test_command_failed_transitions_to_error() -> None:
    svc = make_service(CAM)
    svc.on_movement_started(CAM)
    svc.on_command_failed(CAM, error="timeout")
    state = svc.get_state(CAM)
    assert state.state == PTZCameraState.ERROR
    assert state.last_error == "timeout"
    assert state.last_failure_at is not None


# ------------------------------------------------------------------
# OFFLINE guard
# ------------------------------------------------------------------


def test_offline_not_overwritten_by_stale_success() -> None:
    svc = make_service(CAM)
    svc.on_movement_started(CAM)
    svc.on_camera_offline(CAM)
    svc.on_command_succeeded(CAM)
    assert svc.get_state(CAM).state == PTZCameraState.OFFLINE


# ------------------------------------------------------------------
# Preset recall
# ------------------------------------------------------------------


def test_preset_recall_state() -> None:
    svc = make_service(CAM)
    svc.on_preset_recall_started(CAM, command_id="cmd-42")
    state = svc.get_state(CAM)
    assert state.state == PTZCameraState.PRESET_RECALLING
    assert state.current_command_id == "cmd-42"


# ------------------------------------------------------------------
# Polling
# ------------------------------------------------------------------


def test_polling_state() -> None:
    svc = make_service(CAM)
    svc.on_polling_started(CAM)
    assert svc.get_state(CAM).state == PTZCameraState.PRESET_POLLING


def test_polling_stopped_clears_to_idle() -> None:
    svc = make_service(CAM)
    svc.on_polling_started(CAM)
    svc.on_polling_stopped(CAM)
    assert svc.get_state(CAM).state == PTZCameraState.IDLE


# ------------------------------------------------------------------
# Connection
# ------------------------------------------------------------------


def test_camera_connected_sets_idle_when_offline() -> None:
    svc = make_service(CAM)
    svc.on_camera_offline(CAM)
    assert svc.get_state(CAM).state == PTZCameraState.OFFLINE
    svc.on_camera_connected(CAM)
    state = svc.get_state(CAM)
    assert state.state == PTZCameraState.IDLE
    assert state.connected is True


def test_camera_connected_is_mirrored_to_runtime_state_store() -> None:
    svc, store = make_service_with_store(CAM)

    svc.on_camera_connected(CAM)

    camera = store.snapshot().cameras[CAM]
    assert camera.connected is True
    assert camera.movement_state == PTZCameraState.IDLE.value
    assert camera.last_seen_at is not None


def test_camera_failure_is_mirrored_to_runtime_state_store() -> None:
    svc, store = make_service_with_store(CAM)

    svc.on_command_failed(CAM, error="timeout")

    camera = store.snapshot().cameras[CAM]
    assert camera.connected is False
    assert camera.movement_state == PTZCameraState.ERROR.value
    assert camera.last_error == "timeout"


def test_camera_offline_is_mirrored_to_runtime_state_store() -> None:
    svc, store = make_service_with_store(CAM)
    svc.on_camera_connected(CAM)

    svc.on_camera_offline(CAM)

    camera = store.snapshot().cameras[CAM]
    assert camera.connected is False
    assert camera.movement_state == PTZCameraState.OFFLINE.value


def test_stale_success_while_offline_does_not_update_runtime_state_store() -> None:
    svc, store = make_service_with_store(CAM)
    svc.on_camera_offline(CAM)

    svc.on_command_succeeded(CAM)

    camera = store.snapshot().cameras[CAM]
    assert camera.connected is False
    assert camera.movement_state == PTZCameraState.OFFLINE.value


def test_camera_reset_clears_runtime_state_error_and_preset() -> None:
    svc, store = make_service_with_store(CAM)
    store.update_camera(CAM, active_preset=7, last_error="timeout")
    svc.on_command_failed(CAM, error="timeout")

    svc.on_reset(CAM)

    camera = store.snapshot().cameras[CAM]
    assert camera.movement_state == PTZCameraState.IDLE.value
    assert camera.active_preset is None
    assert camera.last_error is None


def test_unknown_camera_does_not_register_in_runtime_state_store() -> None:
    svc, store = make_service_with_store(CAM)

    svc.on_camera_connected("missing")

    assert set(store.snapshot().cameras) == {CAM}


def test_store_failure_does_not_prevent_local_camera_state_update() -> None:
    class BrokenStore:
        def update_camera(self, *args, **kwargs):
            raise RuntimeError("store unavailable")

    svc = CameraStateService([CAM], camera_role="wide", runtime_state_store=BrokenStore())

    svc.on_command_failed(CAM, error="timeout")

    state = svc.get_state(CAM)
    assert state.state == PTZCameraState.ERROR
    assert state.last_error == "timeout"


def test_store_failure_does_not_prevent_local_reset() -> None:
    class BrokenStore:
        def update_camera(self, *args, **kwargs):
            raise RuntimeError("store unavailable")

    svc = CameraStateService([CAM], camera_role="wide", runtime_state_store=BrokenStore())
    svc.on_command_failed(CAM, error="timeout")

    svc.on_reset(CAM)

    state = svc.get_state(CAM)
    assert state.state == PTZCameraState.IDLE
    assert state.last_error is None


# ------------------------------------------------------------------
# Multiple cameras
# ------------------------------------------------------------------


def test_multiple_cameras_tracked_independently() -> None:
    svc = make_service(CAM, CAM2)
    svc.on_movement_started(CAM)
    svc.on_camera_offline(CAM2)
    assert svc.get_state(CAM).state == PTZCameraState.MOVING
    assert svc.get_state(CAM2).state == PTZCameraState.OFFLINE


def test_all_states_returns_all_cameras() -> None:
    svc = make_service(CAM, CAM2)
    states = svc.all_states()
    assert set(states.keys()) == {CAM, CAM2}


# ------------------------------------------------------------------
# Reset
# ------------------------------------------------------------------


def test_on_reset_returns_to_idle() -> None:
    svc = make_service(CAM)
    svc.on_movement_started(CAM)
    svc.on_command_failed(CAM, error="oops")
    svc.on_reset(CAM)
    state = svc.get_state(CAM)
    assert state.state == PTZCameraState.IDLE
    assert state.last_error is None
    assert state.current_command_id is None


# ------------------------------------------------------------------
# Bug regression: get_state with unknown camera_id
# ------------------------------------------------------------------


def test_get_state_unknown_camera_raises_key_error() -> None:
    """get_state() with an unregistered camera_id must raise KeyError, not silently return wrong state."""
    svc = make_service(CAM)
    with pytest.raises(KeyError, match="not registered"):
        svc.get_state("unknown-camera")


def test_get_state_known_camera_returns_state() -> None:
    """get_state() returns a valid state object for registered cameras."""
    svc = make_service(CAM)
    state = svc.get_state(CAM)
    assert state is not None
    assert state.state == PTZCameraState.UNKNOWN
