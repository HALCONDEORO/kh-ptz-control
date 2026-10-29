# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for AccessModeService and the updated _current_operating_mode logic (#627, #628).

All tests are Qt-free and use tmp_path for file isolation.
"""
from __future__ import annotations

import json

import pytest

from application.access_mode_service import AccessModeService
from application.call_set_command_policy import CallSetCommandPolicy
from domain.call_set_policy import InputType, OperatingMode


# ── AccessModeService unit tests ──────────────────────────────────────────────

class TestAccessModeServiceDefaults:
    def test_default_is_camera_operator(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "access_mode.json")
        assert svc.mode == OperatingMode.CAMERA_OPERATOR

    def test_default_when_file_missing(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "nonexistent.json")
        assert svc.mode == OperatingMode.CAMERA_OPERATOR

    def test_default_when_file_corrupt(self, tmp_path):
        p = tmp_path / "access_mode.json"
        p.write_text("not json", encoding="utf-8")
        svc = AccessModeService(path=p)
        assert svc.mode == OperatingMode.CAMERA_OPERATOR

    def test_default_when_file_has_unknown_value(self, tmp_path):
        p = tmp_path / "access_mode.json"
        p.write_text(json.dumps({"access_mode": "superuser"}), encoding="utf-8")
        svc = AccessModeService(path=p)
        assert svc.mode == OperatingMode.CAMERA_OPERATOR

    def test_default_not_admin(self, tmp_path):
        """El defecto de instalación limpia nunca debe ser admin/installer."""
        svc = AccessModeService(path=tmp_path / "access_mode.json")
        assert svc.mode not in (OperatingMode.TECHNICIAN, OperatingMode.SYSTEM_ADMIN,
                                OperatingMode.ADMIN_INSTALLER)


class TestAccessModeServicePersistence:
    def test_save_and_reload_camera_operator(self, tmp_path):
        p = tmp_path / "access_mode.json"
        svc = AccessModeService(path=p)
        svc.set_mode(OperatingMode.CAMERA_OPERATOR)
        assert AccessModeService(path=p).mode == OperatingMode.CAMERA_OPERATOR

    def test_save_and_reload_basic_operator(self, tmp_path):
        p = tmp_path / "access_mode.json"
        svc = AccessModeService(path=p)
        svc.set_mode(OperatingMode.BASIC_OPERATOR)
        assert AccessModeService(path=p).mode == OperatingMode.BASIC_OPERATOR

    def test_save_and_reload_technician(self, tmp_path):
        p = tmp_path / "access_mode.json"
        svc = AccessModeService(path=p)
        svc.set_mode(OperatingMode.TECHNICIAN)
        assert AccessModeService(path=p).mode == OperatingMode.TECHNICIAN

    def test_save_and_reload_system_admin(self, tmp_path):
        p = tmp_path / "access_mode.json"
        svc = AccessModeService(path=p)
        svc.set_mode(OperatingMode.SYSTEM_ADMIN)
        assert AccessModeService(path=p).mode == OperatingMode.SYSTEM_ADMIN

    def test_switching_modes_persists(self, tmp_path):
        p = tmp_path / "access_mode.json"
        svc = AccessModeService(path=p)
        svc.set_mode(OperatingMode.BASIC_OPERATOR)
        svc.set_mode(OperatingMode.TECHNICIAN)
        assert AccessModeService(path=p).mode == OperatingMode.TECHNICIAN

    def test_file_content_is_valid_json(self, tmp_path):
        p = tmp_path / "access_mode.json"
        svc = AccessModeService(path=p)
        svc.set_mode(OperatingMode.CAMERA_OPERATOR)
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data == {"access_mode": "camera_operator"}

    def test_invalid_mode_raises(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "access_mode.json")
        with pytest.raises(ValueError):
            svc.set_mode(OperatingMode.NAME_EDIT)  # workspace mode, not a persistent role

    def test_demo_mode_raises(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "access_mode.json")
        with pytest.raises(ValueError):
            svc.set_mode(OperatingMode.DEMO)  # not a valid persistent mode


class TestAccessModeServiceMigration:
    def test_legacy_operator_migrates_to_basic_operator(self, tmp_path):
        p = tmp_path / "access_mode.json"
        p.write_text(json.dumps({"access_mode": "operator"}), encoding="utf-8")
        svc = AccessModeService(path=p)
        assert svc.mode == OperatingMode.BASIC_OPERATOR

    def test_legacy_admin_installer_migrates_to_technician(self, tmp_path):
        p = tmp_path / "access_mode.json"
        p.write_text(json.dumps({"access_mode": "admin_installer"}), encoding="utf-8")
        svc = AccessModeService(path=p)
        assert svc.mode == OperatingMode.TECHNICIAN


class TestAccessModeServiceEnvOverride:
    def test_env_camera_operator_overrides_file(self, tmp_path, monkeypatch):
        p = tmp_path / "access_mode.json"
        p.write_text(json.dumps({"access_mode": "technician"}), encoding="utf-8")
        monkeypatch.setenv("HALLPTZ_ACCESS_ROLE", "camera_operator")
        svc = AccessModeService(path=p)
        assert svc.mode == OperatingMode.CAMERA_OPERATOR

    def test_env_technician_overrides_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALLPTZ_ACCESS_ROLE", "technician")
        svc = AccessModeService(path=tmp_path / "access_mode.json")
        assert svc.mode == OperatingMode.TECHNICIAN

    def test_legacy_env_hallptz_access_mode_accepted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALLPTZ_ACCESS_MODE", "basic_operator")
        svc = AccessModeService(path=tmp_path / "access_mode.json")
        assert svc.mode == OperatingMode.BASIC_OPERATOR

    def test_legacy_env_operator_migrates(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALLPTZ_ACCESS_ROLE", "operator")
        svc = AccessModeService(path=tmp_path / "access_mode.json")
        assert svc.mode == OperatingMode.BASIC_OPERATOR

    def test_legacy_env_admin_installer_migrates(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALLPTZ_ACCESS_ROLE", "admin_installer")
        svc = AccessModeService(path=tmp_path / "access_mode.json")
        assert svc.mode == OperatingMode.TECHNICIAN

    def test_invalid_env_falls_back_to_file(self, tmp_path, monkeypatch):
        p = tmp_path / "access_mode.json"
        p.write_text(json.dumps({"access_mode": "technician"}), encoding="utf-8")
        monkeypatch.setenv("HALLPTZ_ACCESS_ROLE", "superuser")
        svc = AccessModeService(path=p)
        assert svc.mode == OperatingMode.TECHNICIAN


# ── _current_operating_mode stub (mirrors updated main_window logic) ──────────

class _OperatingModeLogic:
    """
    Stub that mirrors MainWindow._current_operating_mode:
      - names_open → NAME_EDIT (workspace mode, blocks camera)
      - otherwise  → AccessModeService.mode (persistent role)
    """

    def __init__(self, svc: AccessModeService):
        self._names_open = False
        self._svc = svc

    def current_operating_mode(self) -> OperatingMode:
        if self._names_open:
            return OperatingMode.NAME_EDIT
        return self._svc.mode


# ── Tests: _current_operating_mode with AccessModeService ─────────────────────

class TestCurrentOperatingMode:
    def test_names_open_overrides_technician(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.TECHNICIAN)
        logic = _OperatingModeLogic(svc)
        logic._names_open = True
        assert logic.current_operating_mode() == OperatingMode.NAME_EDIT

    def test_names_open_overrides_camera_operator(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.CAMERA_OPERATOR)
        logic = _OperatingModeLogic(svc)
        logic._names_open = True
        assert logic.current_operating_mode() == OperatingMode.NAME_EDIT

    def test_technician_mode_when_names_closed(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.TECHNICIAN)
        logic = _OperatingModeLogic(svc)
        assert logic.current_operating_mode() == OperatingMode.TECHNICIAN

    def test_camera_operator_mode_when_names_closed(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.CAMERA_OPERATOR)
        logic = _OperatingModeLogic(svc)
        assert logic.current_operating_mode() == OperatingMode.CAMERA_OPERATOR

    def test_leaving_names_restores_technician(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.TECHNICIAN)
        logic = _OperatingModeLogic(svc)
        logic._names_open = True
        assert logic.current_operating_mode() == OperatingMode.NAME_EDIT
        logic._names_open = False
        assert logic.current_operating_mode() == OperatingMode.TECHNICIAN

    def test_leaving_names_restores_camera_operator(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.CAMERA_OPERATOR)
        logic = _OperatingModeLogic(svc)
        logic._names_open = True
        logic._names_open = False
        assert logic.current_operating_mode() == OperatingMode.CAMERA_OPERATOR


# ── Tests: policy behaviour driven by AccessModeService ──────────────────────

class _PolicyLogic(_OperatingModeLogic):
    """Extends stub with full CALL/SET dispatch driven by AccessModeService."""

    def __init__(self, svc: AccessModeService):
        super().__init__(svc)
        self._session_active = True
        self._policy = CallSetCommandPolicy()
        self.calls: list[int] = []
        self.sets:  list[int] = []

    def call_preset(self, preset: int) -> None:
        d = self._policy.decide(
            mode=self.current_operating_mode(),
            input_type=InputType.TAP,
            session_active=self._session_active,
            camera_available=True,
        )
        if d.allowed:
            self.calls.append(preset)

    def set_preset(self, preset: int) -> None:
        d = self._policy.decide(
            mode=self.current_operating_mode(),
            input_type=InputType.LONG_PRESS,
            session_active=self._session_active,
            camera_available=True,
        )
        if d.allowed:
            self.sets.append(preset)


class TestPolicyWithAccessMode:
    def test_camera_operator_can_set(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.CAMERA_OPERATOR)
        logic = _PolicyLogic(svc)
        logic.set_preset(42)
        assert logic.sets == [42]

    def test_technician_can_set(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.TECHNICIAN)
        logic = _PolicyLogic(svc)
        logic.set_preset(42)
        assert logic.sets == [42]

    def test_basic_operator_cannot_set(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.BASIC_OPERATOR)
        logic = _PolicyLogic(svc)
        logic.set_preset(42)
        assert logic.sets == []

    def test_basic_operator_can_call(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.BASIC_OPERATOR)
        logic = _PolicyLogic(svc)
        logic.call_preset(42)
        assert logic.calls == [42]

    def test_camera_operator_can_call(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.CAMERA_OPERATOR)
        logic = _PolicyLogic(svc)
        logic.call_preset(42)
        assert logic.calls == [42]

    def test_name_edit_blocks_call_regardless_of_role(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.TECHNICIAN)
        logic = _PolicyLogic(svc)
        logic._names_open = True
        logic.call_preset(42)
        assert logic.calls == []

    def test_name_edit_blocks_set_regardless_of_role(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.TECHNICIAN)
        logic = _PolicyLogic(svc)
        logic._names_open = True
        logic.set_preset(42)
        assert logic.sets == []

    def test_switching_from_basic_to_camera_operator_enables_set(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        svc.set_mode(OperatingMode.BASIC_OPERATOR)
        logic = _PolicyLogic(svc)
        logic.set_preset(1)
        assert logic.sets == []
        svc.set_mode(OperatingMode.CAMERA_OPERATOR)
        logic.set_preset(1)
        assert logic.sets == [1]

    def test_session_inactive_blocks_call(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        logic = _PolicyLogic(svc)
        logic._session_active = False
        logic.call_preset(5)
        assert logic.calls == []


# ── AccessModeService observer tests ─────────────────────────────────────────

class TestAccessModeServiceObserver:
    def test_observer_called_on_set_mode(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        received: list[OperatingMode] = []
        svc.subscribe(received.append)
        svc.set_mode(OperatingMode.TECHNICIAN)
        assert received == [OperatingMode.TECHNICIAN]

    def test_observer_receives_new_mode(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        received: list[OperatingMode] = []
        svc.subscribe(received.append)
        svc.set_mode(OperatingMode.BASIC_OPERATOR)
        svc.set_mode(OperatingMode.SYSTEM_ADMIN)
        assert received == [OperatingMode.BASIC_OPERATOR, OperatingMode.SYSTEM_ADMIN]

    def test_multiple_observers_all_notified(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        a: list[OperatingMode] = []
        b: list[OperatingMode] = []
        svc.subscribe(a.append)
        svc.subscribe(b.append)
        svc.set_mode(OperatingMode.CAMERA_OPERATOR)
        assert a == [OperatingMode.CAMERA_OPERATOR]
        assert b == [OperatingMode.CAMERA_OPERATOR]

    def test_unsubscribe_stops_notifications(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        received: list[OperatingMode] = []
        svc.subscribe(received.append)
        svc.set_mode(OperatingMode.TECHNICIAN)
        svc.unsubscribe(received.append)
        svc.set_mode(OperatingMode.BASIC_OPERATOR)
        assert received == [OperatingMode.TECHNICIAN]

    def test_subscribe_same_callback_once(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        received: list[OperatingMode] = []
        cb = received.append
        svc.subscribe(cb)
        svc.subscribe(cb)  # duplicate — must not register twice
        svc.set_mode(OperatingMode.TECHNICIAN)
        assert received == [OperatingMode.TECHNICIAN]

    def test_observer_error_does_not_abort_set_mode(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        received: list[OperatingMode] = []

        def bad_observer(_mode):
            raise RuntimeError("simulated observer failure")

        svc.subscribe(bad_observer)
        svc.subscribe(received.append)
        svc.set_mode(OperatingMode.TECHNICIAN)  # must not raise
        assert svc.mode == OperatingMode.TECHNICIAN
        assert received == [OperatingMode.TECHNICIAN]

    def test_no_observer_called_on_invalid_mode(self, tmp_path):
        svc = AccessModeService(path=tmp_path / "a.json")
        received: list[OperatingMode] = []
        svc.subscribe(received.append)
        with pytest.raises(ValueError):
            svc.set_mode(OperatingMode.NAME_EDIT)
        assert received == []
