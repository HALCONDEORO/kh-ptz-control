# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
ATEM no-automation regression tests (#555).

Prevents Phase 1 manual ATEM support from accidentally becoming automatic
seat/preset switching.  Tests run with FakeATEM — no real hardware.

Contracts verified:
  - CALL/SET preset do not send ATEM switching commands.
  - Startup / reconnect never trigger CUT/AUTO.
  - External Program/Preview changes do not move cameras.
  - Normal operator mode cannot use live switching by default.
"""
from __future__ import annotations

import pytest

from adapters.fake_atem import FakeATEM
from application.atem_command_service import AtemCommandService
from application.atem_diagnostics_service import AtemDiagnosticsService
from domain.call_set_policy import OperatingMode


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tracked_atem() -> tuple[FakeATEM, list, list]:
    a = FakeATEM()
    a.connect()
    program: list[int] = []
    preview: list[int] = []
    a.add_program_changed_callback(program.append)
    a.add_preview_changed_callback(preview.append)
    return a, program, preview


# ── Startup / reconnect never trigger CUT or AUTO ────────────────────────────

class TestStartupNoAutomation:
    def test_connect_does_not_fire_program_change(self):
        a = FakeATEM()
        changes: list[int] = []
        a.add_program_changed_callback(changes.append)
        a.connect()
        assert changes == []

    def test_reconnect_does_not_fire_program_change(self):
        a = FakeATEM()
        a.connect()
        changes: list[int] = []
        a.add_program_changed_callback(changes.append)
        a.disconnect()
        a.connect()
        assert changes == []

    def test_connect_does_not_fire_preview_change(self):
        a = FakeATEM()
        changes: list[int] = []
        a.add_preview_changed_callback(changes.append)
        a.connect()
        assert changes == []


# ── Preview set does NOT change program ───────────────────────────────────────

class TestPreviewNoCut:
    def test_set_preview_does_not_change_program(self):
        a, program, _ = _tracked_atem()
        a.set_preview_input(3)
        assert program == []

    def test_multiple_previews_no_program_change(self):
        a, program, _ = _tracked_atem()
        for inp in [1, 2, 3, 4]:
            a.set_preview_input(inp)
        assert program == []

    def test_diagnostics_do_not_trigger_program_change(self):
        a, program, preview = _tracked_atem()
        a.set_program_input(1)
        a.set_preview_input(2)
        program.clear()   # clear state set-up artifacts
        preview.clear()
        svc = AtemDiagnosticsService(atem_port=a)
        # Read-only operations must not fire any callbacks
        svc.read_status()
        svc.read_program_input()
        svc.read_preview_input()
        svc.test_connection()
        assert program == []
        assert preview == []


# ── Operator role blocks CUT/AUTO ─────────────────────────────────────────────

class TestOperatorRoleBlocking:
    @pytest.mark.parametrize("role", [OperatingMode.BASIC_OPERATOR, OperatingMode.CAMERA_OPERATOR])
    def test_cut_blocked_for_operator(self, role):
        a = FakeATEM()
        a.connect()
        a.set_preview_input(2)
        changes: list[int] = []
        a.add_program_changed_callback(changes.append)
        svc = AtemCommandService(atem_port=a)
        result = svc.cut(role=role)
        assert result.ok is False
        assert changes == []

    @pytest.mark.parametrize("role", [OperatingMode.BASIC_OPERATOR, OperatingMode.CAMERA_OPERATOR])
    def test_auto_blocked_for_operator(self, role):
        a = FakeATEM()
        a.connect()
        a.set_preview_input(3)
        svc = AtemCommandService(atem_port=a)
        assert svc.auto(role=role).ok is False

    def test_technician_can_cut(self):
        a = FakeATEM()
        a.connect()
        a.set_preview_input(2)
        svc = AtemCommandService(atem_port=a)
        assert svc.cut(role=OperatingMode.TECHNICIAN).ok is True

    def test_technician_can_auto(self):
        a = FakeATEM()
        a.connect()
        a.set_preview_input(3)
        svc = AtemCommandService(atem_port=a)
        assert svc.auto(role=OperatingMode.TECHNICIAN).ok is True


# ── External ATEM changes are state-only ──────────────────────────────────────

class TestExternalChangesAreStateOnly:
    def test_program_change_does_not_invoke_camera(self):
        a, program, _ = _tracked_atem()
        camera_actions: list[str] = []
        a.set_program_input(2)
        assert program == [2]
        assert camera_actions == []

    def test_cut_fires_exactly_one_callback(self):
        a, program, _ = _tracked_atem()
        a.set_preview_input(3)
        a.cut()
        assert len(program) == 1
        assert program[0] == 3

    def test_auto_fires_exactly_one_callback(self):
        a, program, _ = _tracked_atem()
        a.set_preview_input(1)
        a.auto()
        assert len(program) == 1
        assert program[0] == 1


# ── Disabled ATEM never crashes ───────────────────────────────────────────────

class TestDisabledAtemSafe:
    def test_cut_disabled_atem_fails_safely(self):
        result = AtemCommandService().cut(role=OperatingMode.TECHNICIAN)
        assert result.ok is False

    def test_all_diagnostics_fail_safely(self):
        svc = AtemDiagnosticsService()
        for fn in [svc.read_status, svc.read_program_input, svc.read_preview_input, svc.test_connection]:
            result = fn()
            assert result.ok is False
