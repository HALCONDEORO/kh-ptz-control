# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for ATEM integration in SafetyResetService (#782)."""
from __future__ import annotations


from adapters.fake_atem import FakeATEM


class _FakeRuntimeSafety:
    def stop_all_cameras(self):
        from domain.supportability import OperationResult
        return OperationResult.success(operation="stop_all", target="cameras", message="stopped")


class TestSafetyResetAtemCleanup:
    def _make_svc(self, atem=None):
        from application.safety_reset_service import SafetyResetService
        return SafetyResetService(
            runtime_safety=_FakeRuntimeSafety(),
            atem_port=atem,
        )

    def test_reset_without_atem_succeeds(self):
        svc = self._make_svc(atem=None)
        result = svc.reset()
        assert result.ok is True

    def test_reset_calls_atem_reset_transient_state(self):
        a = FakeATEM()
        a.connect()
        a.set_preview_input(3)
        assert a.get_preview_input() == 3

        svc = self._make_svc(atem=a)
        svc.reset()

        assert a.get_preview_input() is None  # transient state cleared

    def test_reset_calls_cancel_pending_commands(self):
        a = FakeATEM()
        a.connect()
        svc = self._make_svc(atem=a)
        # cancel_pending_commands is a no-op on FakeATEM — just must not raise
        result = svc.reset()
        assert result.ok is True

    def test_atem_cleanup_does_not_change_connection_state(self):
        a = FakeATEM()
        a.connect()
        svc = self._make_svc(atem=a)
        svc.reset()
        # Connection state preserved — reset_transient_state doesn't disconnect
        assert a.get_status().connected is True

    def test_atem_cleanup_failure_reported_in_result(self):
        class BadAtem:
            def reset_transient_state(self):
                raise RuntimeError("simulated failure")
            def cancel_pending_commands(self):
                pass

        svc = self._make_svc(atem=BadAtem())
        result = svc.reset()
        assert result.ok is False
        assert "atem" in result.message.lower()

    def test_reset_transient_state_does_not_send_atem_commands(self):
        a = FakeATEM()
        a.connect()
        a.set_preview_input(2)
        program_changes: list[int] = []
        a.add_program_changed_callback(program_changes.append)

        svc = self._make_svc(atem=a)
        svc.reset()

        assert program_changes == []  # no CUT/AUTO sent during reset
