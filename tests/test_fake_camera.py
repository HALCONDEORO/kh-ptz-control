# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for adapters/fake_camera.py — FakeCamera adapter (#296)."""
from __future__ import annotations

import time


from adapters.fake_camera import FakeCamera
from domain.ports import CameraPort, CameraStatus


def _cam(move_delay=0.0) -> FakeCamera:
    return FakeCamera(camera_id="platform", role="platform", move_delay_s=move_delay)


class TestFakeCameraIsPort:
    def test_is_camera_port(self):
        assert isinstance(_cam(), CameraPort)

    def test_adapter_type_is_fake(self):
        status = _cam().get_status()
        assert status.adapter_type == "fake"

    def test_initial_connected(self):
        assert _cam().get_status().connected is True

    def test_initial_not_moving(self):
        assert _cam().get_status().moving is False

    def test_initial_preset_none(self):
        assert _cam().get_status().current_preset is None


class TestFakeCameraActions:
    def test_power_on_returns_true(self):
        assert _cam().power_on() is True

    def test_power_on_sets_powered(self):
        cam = _cam()
        cam.power_on()
        assert cam.powered is True

    def test_standby_returns_true(self):
        assert _cam().standby() is True

    def test_standby_clears_powered(self):
        cam = _cam()
        cam.power_on()
        cam.standby()
        assert cam.powered is False

    def test_recall_preset_returns_true(self):
        assert _cam().recall_preset(5) is True

    def test_recall_preset_instant_updates_current(self):
        cam = _cam(move_delay=0.0)
        cam.recall_preset(5)
        assert cam.get_status().current_preset == 5

    def test_save_preset_returns_true(self):
        assert _cam().save_preset(3) is True

    def test_save_preset_recorded(self):
        cam = _cam()
        cam.save_preset(3)
        cam.save_preset(7)
        assert 3 in cam.saved_presets
        assert 7 in cam.saved_presets

    def test_go_home_sets_preset_zero(self):
        cam = _cam(move_delay=0.0)
        cam.go_home()
        assert cam.get_status().current_preset == 0

    def test_stop_clears_moving(self):
        cam = _cam(move_delay=5.0)
        cam.recall_preset(1)   # starts move
        cam.stop()
        assert cam.get_status().moving is False

    def test_stop_returns_true(self):
        assert _cam().stop() is True


class TestFakeCameraStatus:
    def test_get_status_returns_camera_status(self):
        status = _cam().get_status()
        assert isinstance(status, CameraStatus)

    def test_status_camera_id(self):
        cam = FakeCamera(camera_id="comments", role="comments")
        assert cam.get_status().camera_id == "comments"

    def test_status_role(self):
        cam = FakeCamera(camera_id="x", role="comments")
        assert cam.get_status().role == "comments"

    def test_status_after_power_on(self):
        cam = _cam()
        cam.power_on()
        status = cam.get_status()
        assert status.connected is True


class TestFakeMovementDelay:
    def test_moving_true_during_delay(self):
        cam = _cam(move_delay=0.3)
        cam.recall_preset(2)
        assert cam.get_status().moving is True

    def test_moving_false_after_delay(self):
        cam = _cam(move_delay=0.1)
        cam.recall_preset(2)
        time.sleep(0.25)
        assert cam.get_status().moving is False
        assert cam.get_status().current_preset == 2

    def test_no_network_calls(self, monkeypatch):
        """FakeCamera must never import or use socket."""
        import socket

        def _fail_connect(self, *args, **kwargs):
            raise AssertionError("FakeCamera must not open sockets")

        monkeypatch.setattr(socket.socket, "connect", _fail_connect)
        cam = _cam()
        cam.power_on()
        cam.recall_preset(1)
        cam.save_preset(1)
        cam.go_home()
        cam.stop()
        cam.standby()
