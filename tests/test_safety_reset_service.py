#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_safety_reset_service.py — SafetyResetService unit tests (#765)

from __future__ import annotations

from unittest.mock import patch


from adapters.fake_camera_port import FakeCameraPort
from application.runtime_state_store import RuntimeStateStore
from application.runtime_safety_service import RuntimeSafetyService
from application.safety_reset_service import SafetyResetService
from application.session_service import SessionService
from core.state import SystemState


# ── Helpers ───────────────────────────────────────────────────────────────────

_MARKER_MOD = "application.session_service"


def _port(camera_ids=None):
    return FakeCameraPort(
        known_cameras={c: "test" for c in (camera_ids or ["cam1", "cam2"])}
    )


def _make_svc(port=None, with_session=True, system_state=None, runtime_state_store=None):
    p = port or _port()
    safety = RuntimeSafetyService(p)
    session = None
    if with_session:
        session = SessionService(
            p,
            system_state=system_state,
            runtime_state_store=runtime_state_store,
        )
    return SafetyResetService(safety, session_service=session), p, session


# ── Camera STOP behaviour ─────────────────────────────────────────────────────

def test_safety_reset_stops_all_cameras_even_without_active_session():
    svc, port, _ = _make_svc(with_session=False)
    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        svc.reset()
    assert "stop_all" in port.calls


def test_safety_reset_stops_both_cameras():
    svc, port, _ = _make_svc()
    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        svc.reset()
    assert "stop_move:cam1" in port.calls
    assert "stop_move:cam2" in port.calls


# ── Session state clearing ────────────────────────────────────────────────────

def test_safety_reset_clears_session_state():
    state = SystemState()
    svc, port, session = _make_svc(system_state=state)
    with patch(f"{_MARKER_MOD}.mark_session_active"):
        session.start()
    assert state.session.active is True

    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        svc.reset()
    assert state.session.active is False


def test_safety_reset_clears_chairman_name():
    state = SystemState()
    svc, port, session = _make_svc(system_state=state)
    session.set_chairman("PersonA")
    assert state.session.chairman_name == "PersonA"

    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        svc.reset()
    assert state.session.chairman_name is None


def test_safety_reset_clears_runtime_state_store_session():
    store = RuntimeStateStore()
    svc, port, session = _make_svc(runtime_state_store=store)
    with patch(f"{_MARKER_MOD}.mark_session_active"):
        session.start()
    session.set_chairman("PersonA")

    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        result = svc.reset()

    runtime_session = store.snapshot().session
    assert result.ok is True
    assert runtime_session.active is False
    assert runtime_session.session_id is None
    assert runtime_session.chairman_name is None
    assert runtime_session.started_at is None


def test_safety_reset_without_session_service_does_not_crash():
    svc, port, _ = _make_svc(with_session=False)
    result = svc.reset()
    assert result.ok is True


# ── Idempotency ───────────────────────────────────────────────────────────────

def test_safety_reset_is_idempotent():
    svc, port, _ = _make_svc()
    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        r1 = svc.reset()
        r2 = svc.reset()
    assert r1.ok is True
    assert r2.ok is True


# ── Disconnected hardware ─────────────────────────────────────────────────────

def test_safety_reset_handles_disconnected_camera_without_crash():

    p = _port()

    def _fail_stop_all():
        p.calls.append("stop_all")
        for c in p._known:
            p.calls.append(f"stop_move:{c}")
        from ports.camera_port import make_command_result
        return make_command_result(ok=False, command="stop_all", camera_id="all",
                                   error_code="CAMERA_ERROR")

    p.stop_all = _fail_stop_all
    safety = RuntimeSafetyService(p)
    session = SessionService(p)
    svc = SafetyResetService(safety, session_service=session)

    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        result = svc.reset()
    # Must not raise; result may be ok=False due to camera failure
    assert result is not None


def test_safety_reset_clears_session_even_when_stop_all_fails():
    store = RuntimeStateStore()
    p = _port()
    safety = RuntimeSafetyService(p)
    session = SessionService(p, runtime_state_store=store)
    svc = SafetyResetService(safety, session_service=session)

    with patch(f"{_MARKER_MOD}.mark_session_active"):
        session.start()
    session.set_chairman("PersonB")

    def _fail_stop_all():
        from ports.camera_port import make_command_result
        return make_command_result(
            ok=False,
            command="stop_all",
            camera_id="all",
            error_code="CAMERA_ERROR",
            message="camera offline",
        )

    p.stop_all = _fail_stop_all

    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        result = svc.reset()

    assert result.ok is False
    assert "cameras:" in result.message
    assert store.snapshot().session.active is False


# ── Config / data preservation ────────────────────────────────────────────────

def test_safety_reset_does_not_delete_config_yaml(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("cameras:\n  cam1:\n    ip: 192.168.1.10\n")

    svc, _, _ = _make_svc()
    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        svc.reset()

    assert config_file.exists(), "Safety Reset must not delete config.yaml"


def test_safety_reset_does_not_delete_room_layout(tmp_path):
    layout_file = tmp_path / "room_layout.json"
    layout_file.write_text('{"seats": []}')

    svc, _, _ = _make_svc()
    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        svc.reset()

    assert layout_file.exists(), "Safety Reset must not delete room_layout.json"


# ── Return value ──────────────────────────────────────────────────────────────

def test_safety_reset_returns_operation_result():
    svc, _, _ = _make_svc()
    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        result = svc.reset()
    assert hasattr(result, "ok")
    assert hasattr(result, "code")
    assert hasattr(result, "operation")


def test_safety_reset_result_ok_on_success():
    svc, _, _ = _make_svc()
    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        result = svc.reset()
    assert result.ok is True
    assert result.operation == "safety_reset"


# ── Integration: start session → queue move → safety reset ───────────────────

def test_safety_reset_integration_clears_state_after_active_session():
    state = SystemState()
    p = _port()
    safety = RuntimeSafetyService(p)
    session = SessionService(p, system_state=state)
    svc = SafetyResetService(safety, session_service=session)

    with patch(f"{_MARKER_MOD}.mark_session_active"):
        session.start()
    session.set_chairman("PersonB")

    assert state.session.active is True
    assert state.session.chairman_name == "PersonB"

    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        result = svc.reset()

    assert result.ok is True
    assert state.session.active is False
    assert state.session.chairman_name is None
    assert "stop_all" in p.calls

