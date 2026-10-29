# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Fault injection tests for FakeATEM (#805)."""
from __future__ import annotations


from adapters.fake_atem import FakeATEM, FakeAtemFault


def _atem() -> FakeATEM:
    a = FakeATEM()
    a.connect()
    a.set_preview_input(2)
    return a


class TestFaultDisconnected:
    def test_set_preview_fails(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.DISCONNECTED)
        result = a.set_preview_input(3)
        assert result.ok is False
        assert result.error_code == "NOT_CONNECTED"

    def test_cut_fails(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.DISCONNECTED)
        assert a.cut().ok is False

    def test_auto_fails(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.DISCONNECTED)
        assert a.auto().ok is False

    def test_test_connection_fails(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.DISCONNECTED)
        assert a.test_connection().ok is False

    def test_clear_fault_restores_behaviour(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.DISCONNECTED)
        a.clear_fault()
        assert a.set_preview_input(3).ok is True


class TestFaultTimeout:
    def test_set_preview_timeout(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.TIMEOUT)
        result = a.set_preview_input(3)
        assert result.ok is False
        assert result.error_code == "TIMEOUT"

    def test_cut_timeout(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.TIMEOUT)
        result = a.cut()
        assert result.ok is False
        assert result.error_code == "TIMEOUT"

    def test_auto_timeout(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.TIMEOUT)
        result = a.auto()
        assert result.ok is False
        assert result.error_code == "TIMEOUT"

    def test_test_connection_timeout(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.TIMEOUT)
        result = a.test_connection()
        assert result.ok is False
        assert result.error_code == "TIMEOUT"


class TestFaultReject:
    def test_cut_rejected(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.REJECT)
        result = a.cut()
        assert result.ok is False
        assert result.error_code == "REJECTED"

    def test_auto_rejected(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.REJECT)
        result = a.auto()
        assert result.ok is False
        assert result.error_code == "REJECTED"

    def test_set_preview_rejected(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.REJECT)
        result = a.set_preview_input(3)
        assert result.ok is False
        assert result.error_code == "REJECTED"


class TestFaultProperties:
    def test_default_fault_is_none(self):
        assert FakeATEM().active_fault == FakeAtemFault.NONE

    def test_inject_sets_active_fault(self):
        a = FakeATEM()
        a.inject_fault(FakeAtemFault.TIMEOUT)
        assert a.active_fault == FakeAtemFault.TIMEOUT

    def test_clear_resets_to_none(self):
        a = FakeATEM()
        a.inject_fault(FakeAtemFault.REJECT)
        a.clear_fault()
        assert a.active_fault == FakeAtemFault.NONE

    def test_legacy_set_program_unaffected_by_fault(self):
        a = FakeATEM()
        received: list[int] = []
        a.add_program_changed_callback(received.append)
        a.inject_fault(FakeAtemFault.DISCONNECTED)
        a.set_program_input(1)  # legacy path — no fault check
        assert received == [1]

    def test_last_command_result_stored_on_fault(self):
        a = _atem()
        a.inject_fault(FakeAtemFault.TIMEOUT)
        a.cut()
        assert a.last_command_result is not None
        assert a.last_command_result.ok is False
        assert a.last_command_result.error_code == "TIMEOUT"


class TestResetTransientState:
    def test_reset_clears_preview(self):
        a = _atem()
        assert a.get_preview_input() == 2
        a.reset_transient_state()
        assert a.get_preview_input() is None

    def test_reset_clears_last_command_result(self):
        a = _atem()
        a.cut()
        assert a.last_command_result is not None
        a.reset_transient_state()
        assert a.last_command_result is None

    def test_reset_is_idempotent(self):
        a = _atem()
        a.reset_transient_state()
        a.reset_transient_state()
        assert a.get_preview_input() is None

    def test_reset_safe_when_disconnected(self):
        a = FakeATEM()
        a.reset_transient_state()  # no error

    def test_cancel_pending_commands_noop(self):
        a = _atem()
        a.cancel_pending_commands()  # must not raise or change state
        assert a.get_preview_input() == 2

