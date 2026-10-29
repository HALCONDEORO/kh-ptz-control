# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for ApplicationController (#682).

Verifies that recall_seat() applies policy, emits the correct bus event for
CALL actions, and returns accurate CommandResult for all decision paths.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from application.app_controller import ApplicationController
from application.call_set_command_policy import CallSetCommandPolicy
from domain.call_set_policy import InputType, OperatingMode


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_ctrl(bus=None, session_active=True):
    session_svc = MagicMock()
    session_svc.active = session_active
    bus = bus or MagicMock()
    policy = CallSetCommandPolicy()
    return ApplicationController(
        session_svc=session_svc,
        call_set_policy=policy,
        bus=bus,
    ), bus


# ── recall_seat — CALL path ───────────────────────────────────────────────────

def test_recall_seat_call_emits_seat_selected():
    ctrl, bus = _make_ctrl(session_active=True)
    result = ctrl.recall_seat(
        seat_id=5,
        input_type=InputType.TAP,
        cam=1,
        mode=OperatingMode.CAMERA_OPERATOR,
        session_active=True,
        camera_available=True,
    )
    assert result.ok
    assert result.command == "recall_seat"
    assert result.error_code is None
    bus.emit.assert_called_once()
    call_kwargs = bus.emit.call_args
    from core.events import EventType
    assert call_kwargs[0][0] == EventType.SEAT_SELECTED
    # Both 'preset' (canonical) and 'seat_number' (backward compat) must be present.
    assert call_kwargs[1]["preset"] == 5
    assert call_kwargs[1]["seat_number"] == 5
    assert call_kwargs[1]["seat_id"] == "5"
    assert call_kwargs[1]["camera"] == 1


def test_recall_seat_returns_target_string():
    ctrl, _ = _make_ctrl()
    result = ctrl.recall_seat(
        seat_id=12,
        input_type=InputType.TAP,
        cam=2,
        mode=OperatingMode.CAMERA_OPERATOR,
        session_active=True,
        camera_available=True,
    )
    assert result.target == "seat:12/cam:2"


# ── recall_seat — blocked paths ───────────────────────────────────────────────

def test_recall_seat_blocked_session_inactive():
    ctrl, bus = _make_ctrl(session_active=False)
    result = ctrl.recall_seat(
        seat_id=3,
        input_type=InputType.TAP,
        cam=1,
        mode=OperatingMode.CAMERA_OPERATOR,
        session_active=False,
        camera_available=True,
    )
    assert not result.ok
    assert result.error_code == "session_inactive"
    bus.emit.assert_not_called()


def test_recall_seat_blocked_camera_unavailable():
    ctrl, bus = _make_ctrl()
    result = ctrl.recall_seat(
        seat_id=7,
        input_type=InputType.TAP,
        cam=1,
        mode=OperatingMode.CAMERA_OPERATOR,
        session_active=True,
        camera_available=False,
    )
    assert not result.ok
    assert result.error_code == "camera_unavailable"
    bus.emit.assert_not_called()


def test_recall_seat_blocked_demo_mode():
    ctrl, bus = _make_ctrl()
    result = ctrl.recall_seat(
        seat_id=5,
        input_type=InputType.TAP,
        cam=1,
        mode=OperatingMode.DEMO,
        session_active=True,
        camera_available=True,
    )
    assert not result.ok
    assert result.error_code == "demo_mode_no_real_camera"
    bus.emit.assert_not_called()


def test_recall_seat_blocked_names_mode():
    ctrl, bus = _make_ctrl()
    result = ctrl.recall_seat(
        seat_id=5,
        input_type=InputType.TAP,
        cam=1,
        mode=OperatingMode.NAMES,
        session_active=True,
        camera_available=True,
    )
    assert not result.ok
    assert result.error_code == "names_mode_data_only"
    bus.emit.assert_not_called()


# ── recall_seat — SET path ────────────────────────────────────────────────────

def test_recall_seat_set_action_not_dispatched():
    """SET actions return error_code='set_action' so UI can handle confirmation."""
    ctrl, bus = _make_ctrl()
    result = ctrl.recall_seat(
        seat_id=5,
        input_type=InputType.LONG_PRESS,
        cam=1,
        mode=OperatingMode.CAMERA_OPERATOR,
        session_active=True,
        camera_available=True,
    )
    assert not result.ok
    assert result.error_code == "set_action"
    bus.emit.assert_not_called()


# ── start_session / end_session ───────────────────────────────────────────────

def test_start_session_emits_event():
    ctrl, bus = _make_ctrl()
    result = ctrl.start_session()
    assert result.ok
    assert result.command == "start_session"
    from core.events import EventType
    bus.emit.assert_called_once_with(EventType.SESSION_START)


def test_end_session_emits_event():
    ctrl, bus = _make_ctrl()
    result = ctrl.end_session()
    assert result.ok
    assert result.command == "end_session"
    from core.events import EventType
    bus.emit.assert_called_once_with(EventType.SESSION_END)


# ── CommandResult metadata ────────────────────────────────────────────────────

def test_recall_seat_result_has_correlation_id():
    ctrl, _ = _make_ctrl()
    result = ctrl.recall_seat(
        seat_id=1,
        input_type=InputType.TAP,
        cam=1,
        mode=OperatingMode.CAMERA_OPERATOR,
        session_active=True,
        camera_available=True,
    )
    assert result.correlation_id  # non-empty
    assert len(result.correlation_id) == 8


def test_recall_seat_blocked_result_has_correlation_id():
    ctrl, _ = _make_ctrl()
    result = ctrl.recall_seat(
        seat_id=1,
        input_type=InputType.TAP,
        cam=1,
        mode=OperatingMode.CAMERA_OPERATOR,
        session_active=False,
        camera_available=True,
    )
    assert result.correlation_id
    assert len(result.correlation_id) == 8
