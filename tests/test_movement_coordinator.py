# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application/movement_coordinator.py and domain/movement.py (#273)."""
from __future__ import annotations

import time


from application.movement_coordinator import MovementCoordinator
from domain.movement import MovementState


def _coord(debounce_ms=500) -> MovementCoordinator:
    return MovementCoordinator(
        camera_ids=["platform", "comments"],
        debounce_ms=debounce_ms,
    )


class TestMovementState:
    def test_values_defined(self):
        assert MovementState.IDLE == "idle"
        assert MovementState.MOVING_TO_PRESET == "moving_to_preset"
        assert MovementState.MANUAL_ACTIVE == "manual_control_active"
        assert MovementState.ERROR == "error"


class TestRequestPreset:
    def test_returns_true_on_success(self):
        coord = _coord()
        assert coord.request_preset("platform", 5) is True

    def test_state_is_moving_after_request(self):
        coord = _coord()
        coord.request_preset("platform", 5)
        assert coord.get_status("platform").state == MovementState.MOVING_TO_PRESET

    def test_pending_preset_set(self):
        coord = _coord()
        coord.request_preset("platform", 7)
        assert coord.get_status("platform").pending_preset == 7

    def test_unknown_camera_returns_false(self):
        coord = _coord()
        assert coord.request_preset("nonexistent", 1) is False

    def test_execute_cb_called(self):
        coord = _coord()
        called: list[int] = []
        coord.request_preset("platform", 3, execute_cb=called.append)
        assert called == [3]

    def test_last_click_wins(self):
        """New target replaces pending target."""
        coord = _coord()
        coord.request_preset("platform", 3)
        coord.request_preset("platform", 9)  # different target — replaces
        assert coord.get_status("platform").pending_preset == 9

    def test_execute_cb_error_marks_error_state(self):
        coord = _coord()

        def bad_cb(p):
            raise RuntimeError("network error")

        coord.request_preset("platform", 1, execute_cb=bad_cb)
        assert coord.get_status("platform").state == MovementState.ERROR


class TestDebounce:
    def test_same_target_debounced(self):
        coord = _coord(debounce_ms=500)
        called: list[int] = []
        coord.request_preset("platform", 5, execute_cb=called.append)
        result = coord.request_preset("platform", 5, execute_cb=called.append)
        assert result is False
        assert called == [5]  # only once

    def test_different_target_not_debounced(self):
        coord = _coord(debounce_ms=500)
        called: list[int] = []
        coord.request_preset("platform", 5, execute_cb=called.append)
        result = coord.request_preset("platform", 6, execute_cb=called.append)
        assert result is True
        assert called == [5, 6]

    def test_debounce_expires(self):
        coord = _coord(debounce_ms=50)
        called: list[int] = []
        coord.request_preset("platform", 5, execute_cb=called.append)
        time.sleep(0.1)   # wait past debounce
        result = coord.request_preset("platform", 5, execute_cb=called.append)
        assert result is True
        assert called == [5, 5]


class TestMarkArrived:
    def test_idle_after_arrived(self):
        coord = _coord()
        coord.request_preset("platform", 5)
        coord.mark_arrived("platform")
        assert coord.get_status("platform").state == MovementState.IDLE

    def test_pending_cleared_after_arrived(self):
        coord = _coord()
        coord.request_preset("platform", 5)
        coord.mark_arrived("platform")
        assert coord.get_status("platform").pending_preset is None

    def test_mark_arrived_unknown_camera_no_crash(self):
        coord = _coord()
        coord.mark_arrived("unknown")  # must not raise


class TestMarkError:
    def test_error_state(self):
        coord = _coord()
        coord.mark_error("platform", "timeout")
        assert coord.get_status("platform").state == MovementState.ERROR

    def test_error_message_stored(self):
        coord = _coord()
        coord.mark_error("platform", "network unreachable")
        assert coord.get_status("platform").error_message == "network unreachable"

    def test_error_clears_pending(self):
        coord = _coord()
        coord.request_preset("platform", 5)
        coord.mark_error("platform", "boom")
        assert coord.get_status("platform").pending_preset is None


class TestManualControl:
    def test_start_manual_returns_true(self):
        assert _coord().start_manual("platform") is True

    def test_state_is_manual_after_start(self):
        coord = _coord()
        coord.start_manual("platform")
        assert coord.get_status("platform").state == MovementState.MANUAL_ACTIVE

    def test_preset_request_blocked_during_manual(self):
        coord = _coord()
        coord.start_manual("platform")
        result = coord.request_preset("platform", 5)
        assert result is False

    def test_stop_manual_returns_to_idle(self):
        coord = _coord()
        coord.start_manual("platform")
        coord.stop_manual("platform")
        assert coord.get_status("platform").state == MovementState.IDLE

    def test_start_manual_cancels_pending_preset(self):
        coord = _coord()
        coord.request_preset("platform", 5)
        coord.start_manual("platform")
        assert coord.get_status("platform").pending_preset is None

    def test_unknown_camera_start_manual_returns_false(self):
        assert _coord().start_manual("nope") is False


class TestFeedbackMessage:
    def test_moving_message(self):
        coord = _coord()
        coord.request_preset("platform", 12)
        msg = coord.feedback_message("platform")
        assert "moving" in msg.lower()
        assert "12" in msg

    def test_ready_message(self):
        coord = _coord()
        msg = coord.feedback_message("platform")
        assert "ready" in msg.lower()

    def test_error_message(self):
        coord = _coord()
        coord.mark_error("platform")
        msg = coord.feedback_message("platform")
        assert "unreachable" in msg.lower()

    def test_manual_message(self):
        coord = _coord()
        coord.start_manual("platform")
        msg = coord.feedback_message("platform")
        assert "manual" in msg.lower()

    def test_unknown_camera_message(self):
        coord = _coord()
        msg = coord.feedback_message("ghost")
        assert "unknown" in msg.lower()


class TestMultiCamera:
    def test_cameras_independent(self):
        coord = _coord()
        coord.request_preset("platform", 5)
        coord.start_manual("comments")
        assert coord.get_status("platform").state == MovementState.MOVING_TO_PRESET
        assert coord.get_status("comments").state == MovementState.MANUAL_ACTIVE

