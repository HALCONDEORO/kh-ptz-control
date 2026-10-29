#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_camera_state_service.py — CameraStateService unit tests

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.camera_state_service import CameraStateService
from domain.ptz_camera_state import PTZCameraState


# ── Helpers ───────────────────────────────────────────────────────────────────

def _svc(*camera_ids: str, store=None) -> CameraStateService:
    return CameraStateService(list(camera_ids), camera_role="ptz", runtime_state_store=store)


def _state(svc: CameraStateService, cam_id: str):
    return svc.get_state(cam_id)


# ── Initial state ─────────────────────────────────────────────────────────────

def test_initial_state_is_unknown_and_disconnected():
    svc = _svc("cam1")
    st = _state(svc, "cam1")
    assert st.state == PTZCameraState.UNKNOWN
    assert not st.connected
    assert st.current_command_id is None


def test_all_states_returns_all_cameras():
    svc = _svc("cam1", "cam2")
    states = svc.all_states()
    assert set(states.keys()) == {"cam1", "cam2"}


def test_unknown_camera_id_raises_on_get_state():
    svc = _svc("cam1")
    with pytest.raises(KeyError):
        svc.get_state("not_a_camera")


# ── on_command_queued ─────────────────────────────────────────────────────────

def test_on_command_queued_stores_command_info():
    svc = _svc("cam1")
    svc.on_command_queued("cam1", "move", "cmd-001")
    st = _state(svc, "cam1")
    assert st.current_command_id == "cmd-001"
    assert st.current_command_type == "move"


def test_on_command_queued_unknown_camera_is_silent():
    svc = _svc("cam1")
    svc.on_command_queued("ghost", "move", "cmd-001")  # should not raise


# ── on_movement_started ───────────────────────────────────────────────────────

def test_on_movement_started_sets_moving_state():
    svc = _svc("cam1")
    svc.on_movement_started("cam1")
    assert _state(svc, "cam1").state == PTZCameraState.MOVING


# ── on_preset_recall_started ──────────────────────────────────────────────────

def test_on_preset_recall_started_sets_state_and_command_id():
    svc = _svc("cam1")
    svc.on_preset_recall_started("cam1", "cmd-recall-7")
    st = _state(svc, "cam1")
    assert st.state == PTZCameraState.PRESET_RECALLING
    assert st.current_command_id == "cmd-recall-7"


# ── on_stop_issued ────────────────────────────────────────────────────────────

def test_on_stop_issued_sets_stopping_state():
    svc = _svc("cam1")
    svc.on_stop_issued("cam1")
    assert _state(svc, "cam1").state == PTZCameraState.STOPPING


# ── on_command_succeeded ──────────────────────────────────────────────────────

def test_on_command_succeeded_transitions_to_idle():
    svc = _svc("cam1")
    svc.on_movement_started("cam1")
    svc.on_command_succeeded("cam1", latency_ms=42)
    st = _state(svc, "cam1")
    assert st.state == PTZCameraState.IDLE
    assert st.recent_latency_ms == 42
    assert st.current_command_id is None
    assert st.last_error is None


def test_on_command_succeeded_clears_command_tracking():
    svc = _svc("cam1")
    svc.on_command_queued("cam1", "recall", "cmd-5")
    svc.on_command_succeeded("cam1")
    st = _state(svc, "cam1")
    assert st.current_command_id is None
    assert st.current_command_type is None


def test_on_command_succeeded_does_not_overwrite_offline_state():
    svc = _svc("cam1")
    svc.on_camera_offline("cam1")
    svc.on_command_succeeded("cam1")
    assert _state(svc, "cam1").state == PTZCameraState.OFFLINE


def test_on_command_succeeded_unknown_camera_is_silent():
    svc = _svc("cam1")
    svc.on_command_succeeded("ghost")  # should not raise


# ── on_command_failed ─────────────────────────────────────────────────────────

def test_on_command_failed_sets_error_state():
    svc = _svc("cam1")
    svc.on_command_failed("cam1", "timeout")
    st = _state(svc, "cam1")
    assert st.state == PTZCameraState.ERROR
    assert st.last_error == "timeout"
    assert st.current_command_id is None


# ── on_camera_connected ───────────────────────────────────────────────────────

def test_on_camera_connected_from_unknown_transitions_to_idle():
    svc = _svc("cam1")
    svc.on_camera_connected("cam1")
    st = _state(svc, "cam1")
    assert st.state == PTZCameraState.IDLE
    assert st.connected


def test_on_camera_connected_from_offline_transitions_to_idle():
    svc = _svc("cam1")
    svc.on_camera_offline("cam1")
    svc.on_camera_connected("cam1")
    assert _state(svc, "cam1").state == PTZCameraState.IDLE


def test_on_camera_connected_does_not_clobber_active_state():
    svc = _svc("cam1")
    svc.on_movement_started("cam1")
    svc.on_camera_connected("cam1")
    st = _state(svc, "cam1")
    assert st.state == PTZCameraState.MOVING
    assert st.connected


def test_on_camera_connected_unknown_camera_is_silent():
    svc = _svc("cam1")
    svc.on_camera_connected("ghost")  # should not raise


# ── on_camera_offline ─────────────────────────────────────────────────────────

def test_on_camera_offline_sets_offline_and_disconnected():
    svc = _svc("cam1")
    svc.on_camera_connected("cam1")
    svc.on_camera_offline("cam1")
    st = _state(svc, "cam1")
    assert st.state == PTZCameraState.OFFLINE
    assert not st.connected


# ── on_polling_started / on_polling_stopped ───────────────────────────────────

def test_on_polling_started_sets_preset_polling():
    svc = _svc("cam1")
    svc.on_polling_started("cam1")
    assert _state(svc, "cam1").state == PTZCameraState.PRESET_POLLING


def test_on_polling_stopped_from_polling_transitions_to_idle():
    svc = _svc("cam1")
    svc.on_polling_started("cam1")
    svc.on_polling_stopped("cam1")
    assert _state(svc, "cam1").state == PTZCameraState.IDLE


def test_on_polling_stopped_from_non_polling_does_not_change_state():
    svc = _svc("cam1")
    svc.on_movement_started("cam1")
    svc.on_polling_stopped("cam1")
    assert _state(svc, "cam1").state == PTZCameraState.MOVING


def test_on_polling_stopped_unknown_camera_is_silent():
    svc = _svc("cam1")
    svc.on_polling_stopped("ghost")  # should not raise


# ── on_reset ──────────────────────────────────────────────────────────────────

def test_on_reset_clears_transient_state_and_sets_idle():
    svc = _svc("cam1")
    svc.on_movement_started("cam1")
    svc.on_command_failed("cam1", "network error")
    svc.on_reset("cam1")
    st = _state(svc, "cam1")
    assert st.state == PTZCameraState.IDLE
    assert st.current_command_id is None
    assert st.last_error is None


def test_on_reset_preserves_connected_status():
    svc = _svc("cam1")
    svc.on_camera_connected("cam1")
    svc.on_reset("cam1")
    assert _state(svc, "cam1").connected


def test_on_reset_unknown_camera_is_silent():
    svc = _svc("cam1")
    svc.on_reset("ghost")  # should not raise


# ── RuntimeStateStore integration ─────────────────────────────────────────────

def test_store_update_camera_called_on_state_change():
    store = MagicMock()
    svc = _svc("cam1", store=store)
    svc.on_camera_connected("cam1")
    store.update_camera.assert_called()


def test_store_update_camera_called_with_correct_id():
    store = MagicMock()
    svc = _svc("cam1", "cam2", store=store)
    svc.on_camera_offline("cam2")
    calls_camera_ids = [c.args[0] for c in store.update_camera.call_args_list]
    assert "cam2" in calls_camera_ids


def test_store_update_camera_called_on_reset():
    store = MagicMock()
    svc = _svc("cam1", store=store)
    svc.on_reset("cam1")
    store.update_camera.assert_called_with(
        "cam1",
        movement_state=PTZCameraState.IDLE.value,
        clear_preset=True,
        clear_error=True,
    )


def test_store_exception_does_not_crash_service():
    store = MagicMock()
    store.update_camera.side_effect = RuntimeError("store down")
    svc = _svc("cam1", store=store)
    svc.on_camera_connected("cam1")  # should not raise
    assert _state(svc, "cam1").connected


# ── all_states snapshot isolation ─────────────────────────────────────────────

def test_all_states_returns_copy():
    svc = _svc("cam1")
    snap = svc.all_states()
    snap["cam1"] = None  # mutate the copy
    assert svc.get_state("cam1") is not None

