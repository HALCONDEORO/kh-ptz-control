# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for OperationResult and OperationCode."""
from domain.supportability import (
    CommandResult,
    OperationCode,
    OperationResult,
    OperationSeverity,
)


def test_success_result():
    r = OperationResult.success(operation="recall_seat", target="seat:1")
    assert r.ok is True
    assert r.code == OperationCode.OK
    assert r.severity == OperationSeverity.INFO


def test_failure_result():
    r = OperationResult.failure(
        code=OperationCode.CAMERA_UNAVAILABLE,
        message="Camera not reachable",
        target="cam1",
    )
    assert r.ok is False
    assert r.code == OperationCode.CAMERA_UNAVAILABLE
    assert r.severity == OperationSeverity.ERROR


def test_warning_result():
    r = OperationResult.failure(
        code=OperationCode.SESSION_INACTIVE,
        message="No active session",
        severity=OperationSeverity.WARNING,
    )
    assert not r.ok
    assert r.severity == OperationSeverity.WARNING


def test_from_command_result_success():
    cmd = CommandResult(
        ok=True,
        command="recall_preset",
        target="cam1",
        duration_ms=45,
        correlation_id="abc123",
        error_code=None,
        message="OK",
    )
    r = OperationResult.from_command_result(cmd, operation="recall_seat")
    assert r.ok is True
    assert r.code == OperationCode.OK
    assert r.target == "cam1"
    assert r.correlation_id == "abc123"


def test_from_command_result_failure():
    cmd = CommandResult(
        ok=False,
        command="recall_preset",
        target="cam2",
        duration_ms=None,
        correlation_id="xyz",
        error_code="TIMEOUT",
        message="Camera timeout",
    )
    r = OperationResult.from_command_result(cmd)
    assert r.ok is False
    assert r.code == OperationCode.CAMERA_COMMAND_FAILED
    assert r.severity == OperationSeverity.ERROR


def test_all_codes_are_strings():
    for code in OperationCode:
        assert isinstance(code.value, str)


def test_to_dict_serialisable():
    r = OperationResult.success(operation="test")
    d = r.to_dict()
    assert d["ok"] is True
    assert d["code"] == "OK"
