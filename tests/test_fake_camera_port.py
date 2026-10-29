#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_fake_camera_port.py — Tests for adapters/fake_camera_port.py

from __future__ import annotations


from adapters.fake_camera_port import FakeCameraPort
from domain.ports import CameraStatus
from domain.supportability import CommandResult


# ═══════════════════════════════════════════════════════════════════════════════
# Auto-registration and initial state
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutoRegistration:
    def test_unknown_camera_auto_registered_on_first_call(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 5)
        status = port.get_status("cam1")
        assert status.camera_id == "cam1"

    def test_new_camera_not_powered_by_default(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 1)
        assert not port.is_powered("cam1")

    def test_new_camera_not_moving_by_default(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 1)
        assert not port.is_moving("cam1")

    def test_new_camera_has_no_current_preset(self):
        port = FakeCameraPort()
        assert port.current_preset("cam1") is None

    def test_known_cameras_pre_registered_with_role(self):
        port = FakeCameraPort(known_cameras={"cam1": "platform"})
        status = port.get_status("cam1")
        assert status.role == "platform"

    def test_unknown_camera_gets_unknown_role(self):
        port = FakeCameraPort()
        status = port.get_status("cam1")
        assert status.role == "unknown"

    def test_multiple_cameras_tracked_independently(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 5)
        port.recall_preset("cam2", 10)
        assert port.current_preset("cam1") == 5
        assert port.current_preset("cam2") == 10


# ═══════════════════════════════════════════════════════════════════════════════
# recall_preset
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecallPreset:
    def test_returns_ok_result(self):
        port = FakeCameraPort()
        result = port.recall_preset("cam1", 5)
        assert isinstance(result, CommandResult)
        assert result.ok is True

    def test_sets_current_preset(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 7)
        assert port.current_preset("cam1") == 7

    def test_overrides_previous_preset(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 3)
        port.recall_preset("cam1", 9)
        assert port.current_preset("cam1") == 9

    def test_clears_moving_flag(self):
        port = FakeCameraPort()
        port.move("cam1", 5, 0)
        assert port.is_moving("cam1")
        port.recall_preset("cam1", 1)
        assert not port.is_moving("cam1")

    def test_logs_call(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 5)
        assert "recall_preset:cam1:5" in port.calls

    def test_result_command_field(self):
        port = FakeCameraPort()
        result = port.recall_preset("cam1", 3)
        assert result.command == "recall_preset"

    def test_result_target_field(self):
        port = FakeCameraPort()
        result = port.recall_preset("cam1", 3)
        assert result.target == "cam1"


# ═══════════════════════════════════════════════════════════════════════════════
# save_preset
# ═══════════════════════════════════════════════════════════════════════════════

class TestSavePreset:
    def test_returns_ok_result(self):
        port = FakeCameraPort()
        result = port.save_preset("cam1", 5)
        assert result.ok is True

    def test_logs_call(self):
        port = FakeCameraPort()
        port.save_preset("cam1", 12)
        assert "save_preset:cam1:12" in port.calls

    def test_result_command_field(self):
        port = FakeCameraPort()
        result = port.save_preset("cam1", 5)
        assert result.command == "save_preset"


# ═══════════════════════════════════════════════════════════════════════════════
# move
# ═══════════════════════════════════════════════════════════════════════════════

class TestMove:
    def test_returns_ok_result(self):
        port = FakeCameraPort()
        result = port.move("cam1", 3, 0)
        assert result.ok is True

    def test_nonzero_pan_sets_moving(self):
        port = FakeCameraPort()
        port.move("cam1", 5, 0)
        assert port.is_moving("cam1")

    def test_nonzero_tilt_sets_moving(self):
        port = FakeCameraPort()
        port.move("cam1", 0, 3)
        assert port.is_moving("cam1")

    def test_both_nonzero_sets_moving(self):
        port = FakeCameraPort()
        port.move("cam1", 2, 2)
        assert port.is_moving("cam1")

    def test_both_zero_clears_moving(self):
        port = FakeCameraPort()
        port.move("cam1", 5, 0)
        port.move("cam1", 0, 0)
        assert not port.is_moving("cam1")

    def test_logs_call_with_speeds(self):
        port = FakeCameraPort()
        port.move("cam1", 3, 2)
        assert "move:cam1:3:2" in port.calls


# ═══════════════════════════════════════════════════════════════════════════════
# stop_move
# ═══════════════════════════════════════════════════════════════════════════════

class TestStopMove:
    def test_returns_ok_result(self):
        port = FakeCameraPort()
        result = port.stop_move("cam1")
        assert result.ok is True

    def test_clears_moving_flag(self):
        port = FakeCameraPort()
        port.move("cam1", 5, 0)
        port.stop_move("cam1")
        assert not port.is_moving("cam1")

    def test_logs_call(self):
        port = FakeCameraPort()
        port.stop_move("cam1")
        assert "stop_move:cam1" in port.calls


# ═══════════════════════════════════════════════════════════════════════════════
# zoom
# ═══════════════════════════════════════════════════════════════════════════════

class TestZoom:
    def test_returns_ok_result(self):
        port = FakeCameraPort()
        result = port.zoom("cam1", 50)
        assert result.ok is True

    def test_logs_call_with_speed(self):
        port = FakeCameraPort()
        port.zoom("cam1", 75)
        assert "zoom:cam1:75" in port.calls


# ═══════════════════════════════════════════════════════════════════════════════
# power_on / standby
# ═══════════════════════════════════════════════════════════════════════════════

class TestPower:
    def test_power_on_returns_ok(self):
        port = FakeCameraPort()
        result = port.power_on("cam1")
        assert result.ok is True

    def test_power_on_sets_powered(self):
        port = FakeCameraPort()
        port.power_on("cam1")
        assert port.is_powered("cam1")

    def test_standby_clears_powered(self):
        port = FakeCameraPort()
        port.power_on("cam1")
        port.standby("cam1")
        assert not port.is_powered("cam1")

    def test_standby_clears_moving(self):
        port = FakeCameraPort()
        port.move("cam1", 5, 0)
        port.standby("cam1")
        assert not port.is_moving("cam1")

    def test_power_on_logs_call(self):
        port = FakeCameraPort()
        port.power_on("cam1")
        assert "power_on:cam1" in port.calls

    def test_standby_logs_call(self):
        port = FakeCameraPort()
        port.standby("cam1")
        assert "standby:cam1" in port.calls


# ═══════════════════════════════════════════════════════════════════════════════
# home
# ═══════════════════════════════════════════════════════════════════════════════

class TestHome:
    def test_returns_ok(self):
        port = FakeCameraPort()
        result = port.home("cam1")
        assert result.ok is True

    def test_sets_preset_to_zero(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 5)
        port.home("cam1")
        assert port.current_preset("cam1") == 0

    def test_clears_moving(self):
        port = FakeCameraPort()
        port.move("cam1", 3, 0)
        port.home("cam1")
        assert not port.is_moving("cam1")

    def test_logs_call(self):
        port = FakeCameraPort()
        port.home("cam1")
        assert "home:cam1" in port.calls


# ═══════════════════════════════════════════════════════════════════════════════
# get_status
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetStatus:
    def test_returns_camera_status(self):
        port = FakeCameraPort()
        status = port.get_status("cam1")
        assert isinstance(status, CameraStatus)

    def test_camera_id_matches(self):
        port = FakeCameraPort()
        status = port.get_status("cam99")
        assert status.camera_id == "cam99"

    def test_adapter_type_is_fake(self):
        port = FakeCameraPort()
        status = port.get_status("cam1")
        assert status.adapter_type == "fake"

    def test_connected_true_by_default(self):
        port = FakeCameraPort()
        status = port.get_status("cam1")
        assert status.connected is True

    def test_moving_reflects_state(self):
        port = FakeCameraPort()
        port.move("cam1", 5, 0)
        assert port.get_status("cam1").moving is True
        port.stop_move("cam1")
        assert port.get_status("cam1").moving is False

    def test_current_preset_reflected(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 8)
        assert port.get_status("cam1").current_preset == 8

    def test_known_camera_role(self):
        port = FakeCameraPort(known_cameras={"cam1": "platform", "cam2": "comments"})
        assert port.get_status("cam1").role == "platform"
        assert port.get_status("cam2").role == "comments"


# ═══════════════════════════════════════════════════════════════════════════════
# call log accumulation
# ═══════════════════════════════════════════════════════════════════════════════

class TestCallLog:
    def test_calls_accumulate(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 1)
        port.move("cam1", 3, 0)
        port.stop_move("cam1")
        assert len(port.calls) == 3

    def test_calls_preserve_order(self):
        port = FakeCameraPort()
        port.power_on("cam1")
        port.recall_preset("cam1", 5)
        assert port.calls[0].startswith("power_on")
        assert port.calls[1].startswith("recall_preset")

    def test_calls_from_multiple_cameras_interleaved(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 1)
        port.recall_preset("cam2", 2)
        assert any("cam1" in c for c in port.calls)
        assert any("cam2" in c for c in port.calls)
