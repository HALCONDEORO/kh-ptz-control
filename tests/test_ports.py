# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for domain/ports.py — CameraPort and SwitcherPort contracts."""
from __future__ import annotations

import pytest

from domain.ports import (
    AtemCommandResult,
    AtemPort,
    CameraPort,
    CameraStatus,
    SwitcherPort,
    SwitcherStatus,
)


# ── Concrete stubs that implement both ports ──────────────────────────────────

class StubCamera(CameraPort):
    def __init__(self):
        self._status = CameraStatus(
            camera_id="cam1",
            role="platform",
            adapter_type="fake",
            connected=True,
        )
        self.calls: list[str] = []

    def power_on(self) -> bool:
        self.calls.append("power_on")
        return True

    def standby(self) -> bool:
        self.calls.append("standby")
        return True

    def recall_preset(self, preset: int) -> bool:
        self.calls.append(f"recall_preset:{preset}")
        self._status.current_preset = preset
        return True

    def save_preset(self, preset: int) -> bool:
        self.calls.append(f"save_preset:{preset}")
        return True

    def go_home(self) -> bool:
        self.calls.append("go_home")
        return True

    def stop(self) -> bool:
        self.calls.append("stop")
        return True

    def get_status(self) -> CameraStatus:
        return self._status


class StubSwitcher(SwitcherPort):
    def __init__(self):
        self._status = SwitcherStatus(adapter_type="fake", connected=True)
        self._program_input: int | None = None
        self.calls: list[str] = []

    def connect(self) -> bool:
        self.calls.append("connect")
        self._status.connected = True
        return True

    def disconnect(self) -> None:
        self.calls.append("disconnect")
        self._status.connected = False

    def get_program_input(self) -> int | None:
        return self._program_input

    def set_program_input(self, input_id: int) -> None:
        self.calls.append(f"set_program_input:{input_id}")
        self._program_input = input_id
        self._status.program_input = input_id

    def get_status(self) -> SwitcherStatus:
        return self._status


# ── CameraPort tests ──────────────────────────────────────────────────────────

class TestCameraPort:
    def test_stub_is_camera_port(self):
        cam = StubCamera()
        assert isinstance(cam, CameraPort)

    def test_abstract_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            CameraPort()  # type: ignore[abstract]

    def test_power_on_returns_bool(self):
        cam = StubCamera()
        assert cam.power_on() is True

    def test_standby_returns_bool(self):
        cam = StubCamera()
        assert cam.standby() is True

    def test_recall_preset_updates_status(self):
        cam = StubCamera()
        cam.recall_preset(5)
        assert cam.get_status().current_preset == 5

    def test_save_preset_returns_bool(self):
        cam = StubCamera()
        assert cam.save_preset(3) is True

    def test_go_home_returns_bool(self):
        cam = StubCamera()
        assert cam.go_home() is True

    def test_stop_returns_bool(self):
        cam = StubCamera()
        assert cam.stop() is True

    def test_get_status_returns_camera_status(self):
        cam = StubCamera()
        status = cam.get_status()
        assert isinstance(status, CameraStatus)
        assert status.camera_id == "cam1"
        assert status.role == "platform"
        assert status.adapter_type == "fake"
        assert status.connected is True

    def test_missing_abstract_method_raises(self):
        class Incomplete(CameraPort):
            def power_on(self): return True
            def standby(self): return True
            def recall_preset(self, p): return True
            def save_preset(self, p): return True
            def go_home(self): return True
            def stop(self): return True
            # get_status missing

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ── SwitcherPort tests ────────────────────────────────────────────────────────

class TestSwitcherPort:
    def test_stub_is_switcher_port(self):
        sw = StubSwitcher()
        assert isinstance(sw, SwitcherPort)

    def test_abstract_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            SwitcherPort()  # type: ignore[abstract]

    def test_connect_returns_bool(self):
        sw = StubSwitcher()
        assert sw.connect() is True

    def test_disconnect_sets_not_connected(self):
        sw = StubSwitcher()
        sw.disconnect()
        assert sw.get_status().connected is False

    def test_get_program_input_initially_none(self):
        sw = StubSwitcher()
        assert sw.get_program_input() is None

    def test_set_program_input_updates_state(self):
        sw = StubSwitcher()
        sw.set_program_input(2)
        assert sw.get_program_input() == 2

    def test_get_status_returns_switcher_status(self):
        sw = StubSwitcher()
        status = sw.get_status()
        assert isinstance(status, SwitcherStatus)
        assert status.adapter_type == "fake"
        assert status.connected is True

    def test_set_program_input_reflected_in_status(self):
        sw = StubSwitcher()
        sw.set_program_input(7)
        assert sw.get_status().program_input == 7


# ── CameraStatus / SwitcherStatus defaults ───────────────────────────────────

class TestStatusDefaults:
    def test_camera_status_defaults(self):
        s = CameraStatus(camera_id="x", role="comments", adapter_type="visca")
        assert s.connected is False
        assert s.moving is False
        assert s.current_preset is None
        assert s.last_error == ""

    def test_switcher_status_defaults(self):
        s = SwitcherStatus(adapter_type="atem")
        assert s.connected is False
        assert s.program_input is None
        assert s.preview_input is None
        assert s.transitioning is False
        assert s.automation_mode is False
        assert s.last_error == ""


# ── AtemCommandResult ─────────────────────────────────────────────────────────

class TestAtemCommandResult:
    def test_success_factory(self):
        r = AtemCommandResult.success("cut")
        assert r.ok is True
        assert r.command == "cut"

    def test_failure_factory(self):
        r = AtemCommandResult.failure("cut", "NOT_CONNECTED", "disconnected")
        assert r.ok is False
        assert r.error_code == "NOT_CONNECTED"

    def test_unique_correlation_ids(self):
        r1 = AtemCommandResult.success("cut")
        r2 = AtemCommandResult.success("cut")
        assert r1.correlation_id != r2.correlation_id


# ── AtemPort abstract check ───────────────────────────────────────────────────

class TestAtemPortContract:
    def test_is_switcher_port_subclass(self):
        assert issubclass(AtemPort, SwitcherPort)

    def test_abstract_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            AtemPort()  # type: ignore[abstract]
