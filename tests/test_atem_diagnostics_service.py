# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application/atem_diagnostics_service.py (#552)."""
from __future__ import annotations


from adapters.fake_atem import FakeATEM
from application.atem_diagnostics_service import AtemDiagnosticsService


def _svc_connected() -> AtemDiagnosticsService:
    a = FakeATEM()
    a.connect()
    return AtemDiagnosticsService(atem_port=a)


def _svc_disconnected() -> AtemDiagnosticsService:
    return AtemDiagnosticsService(atem_port=FakeATEM())


class TestDisabledAtem:
    def test_read_status_when_none(self):
        svc = AtemDiagnosticsService()
        result = svc.read_status()
        assert result.ok is False
        assert "disabled" in result.message.lower()

    def test_test_connection_when_none(self):
        result = AtemDiagnosticsService().test_connection()
        assert result.ok is False

    def test_doctor_check_not_applicable(self):
        check = AtemDiagnosticsService().doctor_check()
        assert check["status"] == "NOT_APPLICABLE"

    def test_read_program_when_none(self):
        result = AtemDiagnosticsService().read_program_input()
        assert result.ok is False

    def test_read_preview_when_none(self):
        result = AtemDiagnosticsService().read_preview_input()
        assert result.ok is False


class TestConnectedAtem:
    def test_read_status_ok(self):
        result = _svc_connected().read_status()
        assert result.ok is True
        assert result.data["connected"] is True

    def test_read_status_disconnected(self):
        result = _svc_disconnected().read_status()
        assert result.ok is False

    def test_test_connection_ok(self):
        result = _svc_connected().test_connection()
        assert result.ok is True

    def test_test_connection_fail_when_disconnected(self):
        result = _svc_disconnected().test_connection()
        assert result.ok is False

    def test_read_program_stale_when_no_data(self):
        result = _svc_connected().read_program_input()
        assert result.data["is_stale"] is True

    def test_read_program_ok_after_set(self):
        a = FakeATEM()
        a.connect()
        a.set_program_input(2)
        svc = AtemDiagnosticsService(atem_port=a)
        result = svc.read_program_input()
        assert result.ok is True
        assert result.data["program_input"] == 2
        assert result.data["is_stale"] is False

    def test_read_preview_ok_after_set(self):
        a = FakeATEM()
        a.connect()
        a.set_preview_input(3)
        svc = AtemDiagnosticsService(atem_port=a)
        result = svc.read_preview_input()
        assert result.ok is True
        assert result.data["preview_input"] == 3

    def test_doctor_check_ok(self):
        check = _svc_connected().doctor_check()
        assert check["status"] == "OK"

    def test_doctor_check_warning_disconnected(self):
        check = _svc_disconnected().doctor_check()
        assert check["status"] == "WARNING"

    def test_read_ops_never_call_cut_auto(self):
        a = FakeATEM()
        a.connect()
        a.set_preview_input(2)
        program_changes: list[int] = []
        a.add_program_changed_callback(program_changes.append)
        svc = AtemDiagnosticsService(atem_port=a)
        svc.read_status()
        svc.read_program_input()
        svc.read_preview_input()
        svc.test_connection()
        assert program_changes == []  # no CUT/AUTO fired by diagnostics


class TestResultStructure:
    def test_read_status_data_has_expected_keys(self):
        result = _svc_connected().read_status()
        assert "connected" in result.data
        assert "program_input" in result.data
        assert "preview_input" in result.data
        assert "adapter_type" in result.data

    def test_test_connection_data_has_correlation_id(self):
        result = _svc_connected().test_connection()
        assert result.ok is True
        assert "correlation_id" in result.data
