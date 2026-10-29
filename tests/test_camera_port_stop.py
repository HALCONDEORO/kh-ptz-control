#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_camera_port_stop.py — CameraPort stop/stop_all contract tests (#780)

from __future__ import annotations


from adapters.fake_camera_port import FakeCameraPort
from ports.camera_port import make_command_result


# ── FakeCameraPort stop ───────────────────────────────────────────────────────

def test_fake_records_stop_move():
    port = FakeCameraPort(known_cameras={"cam1": "main"})
    port.stop_move("cam1")
    assert "stop_move:cam1" in port.calls


def test_fake_records_stop_all():
    port = FakeCameraPort(known_cameras={"cam1": "main", "cam2": "comments"})
    port.stop_all()
    assert "stop_all" in port.calls


def test_stop_all_records_individual_stop_for_each_camera():
    port = FakeCameraPort(known_cameras={"cam1": "main", "cam2": "comments"})
    port.stop_all()
    assert "stop_move:cam1" in port.calls
    assert "stop_move:cam2" in port.calls


def test_stop_move_returns_command_result():
    port = FakeCameraPort(known_cameras={"cam1": "main"})
    result = port.stop_move("cam1")
    assert result.ok is True
    assert result.command == "stop_move"
    assert result.target == "cam1"


def test_stop_all_returns_command_result():
    port = FakeCameraPort(known_cameras={"cam1": "main", "cam2": "comments"})
    result = port.stop_all()
    assert result.ok is True
    assert result.command == "stop_all"


def test_stop_all_attempts_all_cameras():
    port = FakeCameraPort(known_cameras={"cam1": "main", "cam2": "comments"})
    port.stop_all()
    stop_calls = [c for c in port.calls if c.startswith("stop_move:")]
    camera_ids = {c.split(":")[1] for c in stop_calls}
    assert "cam1" in camera_ids
    assert "cam2" in camera_ids


def test_stop_move_sets_camera_not_moving():
    port = FakeCameraPort(known_cameras={"cam1": "main"})
    port.move("cam1", 10, 0)
    assert port.is_moving("cam1") is True
    port.stop_move("cam1")
    assert port.is_moving("cam1") is False


def test_stop_all_sets_all_cameras_not_moving():
    port = FakeCameraPort(known_cameras={"cam1": "main", "cam2": "comments"})
    port.move("cam1", 5, 0)
    port.move("cam2", 0, 5)
    port.stop_all()
    assert port.is_moving("cam1") is False
    assert port.is_moving("cam2") is False


def test_stop_all_reports_partial_failure():
    """stop_all records all attempts even when one camera fails."""
    from domain.supportability import CommandResult
    import uuid

    port = FakeCameraPort(known_cameras={"cam1": "main", "cam2": "comments"})

    original_stop = port.stop_move
    call_count = {"n": 0}

    def _patched_stop(camera_id):
        call_count["n"] += 1
        if camera_id == "cam2":
            port.calls.append(f"stop_move:{camera_id}")
            return CommandResult(
                ok=False,
                command="stop_move",
                target=camera_id,
                duration_ms=None,
                correlation_id=str(uuid.uuid4()),
                error_code="CAMERA_ERROR",
                message="Timeout",
            )
        return original_stop(camera_id)

    port.stop_move = _patched_stop
    port.stop_all()
    # Both cameras were attempted
    assert call_count["n"] == 2
    # cam1 was still called
    assert "stop_move:cam1" in port.calls


# ── make_command_result helper ────────────────────────────────────────────────

def test_make_command_result_ok():
    r = make_command_result(ok=True, command="stop_all", camera_id="all")
    assert r.ok is True
    assert r.error_code is None


def test_make_command_result_failure():
    r = make_command_result(ok=False, command="stop_all", camera_id="all")
    assert r.ok is False
    assert r.error_code is not None
