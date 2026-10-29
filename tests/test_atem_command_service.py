# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application/atem_command_service.py (#553)."""
from __future__ import annotations

import pytest

from adapters.fake_atem import FakeATEM
from application.atem_command_service import AtemCommandService
from domain.call_set_policy import OperatingMode


def _svc(connected: bool = True) -> tuple[AtemCommandService, FakeATEM]:
    a = FakeATEM()
    if connected:
        a.connect()
    return AtemCommandService(atem_port=a), a


class TestDisabledAtem:
    def test_cut_fails_when_disabled(self):
        svc = AtemCommandService()
        assert svc.cut(role=OperatingMode.TECHNICIAN).ok is False

    def test_auto_fails_when_disabled(self):
        assert AtemCommandService().auto(role=OperatingMode.TECHNICIAN).ok is False

    def test_set_preview_fails_when_disabled(self):
        assert AtemCommandService().set_preview(1).ok is False


class TestSetPreview:
    @pytest.mark.parametrize("role", list(OperatingMode))
    def test_ok_for_any_role(self, role):
        svc, _ = _svc()
        assert svc.set_preview(1, role=role).ok is True

    def test_fails_when_disconnected(self):
        svc, _ = _svc(connected=False)
        assert svc.set_preview(1).ok is False

    def test_result_data_has_correlation_id(self):
        svc, _ = _svc()
        result = svc.set_preview(2)
        assert result.ok is True
        assert "correlation_id" in result.data


class TestCut:
    @pytest.mark.parametrize("role", [OperatingMode.CAMERA_OPERATOR, OperatingMode.BASIC_OPERATOR])
    def test_blocked_for_non_technician(self, role):
        svc, a = _svc()
        a.set_preview_input(2)
        result = svc.cut(role=role)
        assert result.ok is False
        assert "technician" in result.message.lower()

    def test_allowed_for_technician(self):
        svc, a = _svc()
        a.set_preview_input(2)
        result = svc.cut(actor="engineer", role=OperatingMode.TECHNICIAN)
        assert result.ok is True

    def test_no_automatic_retry(self):
        svc, a = _svc()
        a.set_preview_input(2)
        r1 = svc.cut(role=OperatingMode.TECHNICIAN)
        assert r1.ok is True
        # Second cut — same preview (debounced = no program change, but OK)
        r2 = svc.cut(role=OperatingMode.TECHNICIAN)
        assert r2.ok is True

    def test_fails_when_no_preview(self):
        svc, _ = _svc()
        result = svc.cut(role=OperatingMode.TECHNICIAN)
        assert result.ok is False  # no preview set


class TestAuto:
    @pytest.mark.parametrize("role", [OperatingMode.CAMERA_OPERATOR, OperatingMode.BASIC_OPERATOR])
    def test_blocked_for_non_technician(self, role):
        svc, a = _svc()
        a.set_preview_input(3)
        result = svc.auto(role=role)
        assert result.ok is False

    def test_allowed_for_technician(self):
        svc, a = _svc()
        a.set_preview_input(3)
        result = svc.auto(actor="engineer", role=OperatingMode.TECHNICIAN)
        assert result.ok is True

    def test_result_data_has_correlation_id(self):
        svc, a = _svc()
        a.set_preview_input(1)
        result = svc.auto(role=OperatingMode.TECHNICIAN)
        assert result.ok is True
        assert "correlation_id" in result.data
