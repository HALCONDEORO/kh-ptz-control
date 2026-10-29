#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_runtime_safety_service.py — RuntimeSafetyService unit tests (#779)

from __future__ import annotations


from adapters.fake_camera_port import FakeCameraPort
from application.runtime_safety_service import RuntimeSafetyService
from domain.supportability import OperationCode


# ── Helpers ───────────────────────────────────────────────────────────────────

def _svc(camera_ids=None, disconnected=False):
    port = FakeCameraPort(
        known_cameras={c: "test" for c in (camera_ids or ["cam1", "cam2"])},
    )
    if disconnected:
        # Simulate disconnected by patching stop_move to return failure
        from domain.supportability import CommandResult
        import uuid

        def _fail_stop(camera_id):
            port.calls.append(f"stop_move:{camera_id}")
            return CommandResult(
                ok=False,
                command="stop_move",
                target=camera_id,
                duration_ms=None,
                correlation_id=str(uuid.uuid4()),
                error_code="CAMERA_ERROR",
                message="Disconnected",
            )

        def _fail_stop_all():
            port.calls.append("stop_all")
            for c in port._known:
                _fail_stop(c)
            from ports.camera_port import make_command_result
            return make_command_result(ok=False, command="stop_all", camera_id="all",
                                       error_code="CAMERA_ERROR")

        port.stop_move = _fail_stop
        port.stop_all = _fail_stop_all

    svc = RuntimeSafetyService(port, camera_ids=camera_ids)
    return svc, port


# ── stop_camera ───────────────────────────────────────────────────────────────

def test_stop_camera_calls_camera_port():
    svc, port = _svc()
    svc.stop_camera("cam1")
    assert any("stop_move:cam1" in c for c in port.calls)


def test_stop_camera_returns_structured_result():
    svc, _ = _svc()
    result = svc.stop_camera("cam1")
    assert result.operation == "stop_camera"
    assert result.target == "cam1"
    assert result.ok is True


def test_stop_camera_handles_disconnected_without_crash():
    svc, _ = _svc(disconnected=True)
    result = svc.stop_camera("cam1")
    assert result.ok is False
    assert result.code == OperationCode.CAMERA_COMMAND_FAILED


def test_stop_camera_handles_exception_without_crash():
    from adapters.fake_camera_port import FakeCameraPort
    port = FakeCameraPort(known_cameras={"cam1": "test"})

    def _raise(_camera_id):
        raise OSError("socket error")

    port.stop_move = _raise
    svc = RuntimeSafetyService(port)
    result = svc.stop_camera("cam1")
    assert result.ok is False
    assert result.code == OperationCode.CAMERA_UNAVAILABLE


# ── stop_all_cameras ──────────────────────────────────────────────────────────

def test_stop_all_calls_every_configured_camera():
    svc, port = _svc(camera_ids=["cam1", "cam2"])
    svc.stop_all_cameras()
    assert "stop_all" in port.calls
    assert "stop_move:cam1" in port.calls
    assert "stop_move:cam2" in port.calls


def test_stop_all_bypasses_session_guard():
    # No session started — stop_all must still work
    svc, port = _svc()
    result = svc.stop_all_cameras()
    assert result.ok is True
    assert "stop_all" in port.calls


def test_stop_all_returns_structured_result():
    svc, _ = _svc()
    result = svc.stop_all_cameras()
    assert result.operation == "stop_all_cameras"
    assert result.target == "all"


def test_stop_all_handles_disconnected_camera_without_crash():
    svc, _ = _svc(disconnected=True)
    result = svc.stop_all_cameras()
    assert result.ok is False
    assert result.code == OperationCode.CAMERA_COMMAND_FAILED


def test_stop_all_handles_exception_without_crash():
    from adapters.fake_camera_port import FakeCameraPort
    port = FakeCameraPort(known_cameras={"cam1": "test", "cam2": "test"})

    def _raise():
        raise OSError("network failure")

    port.stop_all = _raise
    svc = RuntimeSafetyService(port)
    result = svc.stop_all_cameras()
    assert result.ok is False
    assert result.code == OperationCode.CAMERA_UNAVAILABLE

