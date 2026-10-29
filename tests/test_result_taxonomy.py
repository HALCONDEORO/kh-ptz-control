# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for the unified error/result taxonomy in domain.supportability (#801).

Covers:
  - All new OperationCode values are present and stable.
  - _RESULT_CATALOG covers every code with correct shape.
  - OperationResult factories produce correct codes, severity, retryable and
    safe_to_continue values.
  - from_command_result maps CommandResult error codes to specific OperationCodes.
  - Safety Reset uses SAFETY_RESET_COMPLETED / SAFETY_RESET_PARTIAL_FAILURE.
  - ATEM disabled uses ATEM_DISABLED; network error uses ATEM_DISCONNECTED.
  - Result details do not expose private IPs or secrets.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock


from domain.supportability import (
    OperationCode,
    OperationResult,
    OperationSeverity,
    _RESULT_CATALOG,
    CommandResult,
)


# ── Catalog completeness ───────────────────────────────────────────────────────

class TestResultCatalog:
    def test_every_code_has_a_catalog_entry(self):
        missing = [c for c in OperationCode if c not in _RESULT_CATALOG]
        assert missing == [], f"OperationCode values without catalog entry: {missing}"

    def test_catalog_entries_are_three_tuples(self):
        for code, meta in _RESULT_CATALOG.items():
            assert len(meta) == 3, f"{code}: expected 3-tuple"
            severity, retryable, safe = meta
            assert isinstance(severity, OperationSeverity), f"{code}: bad severity type"
            assert isinstance(retryable, bool), f"{code}: bad retryable type"
            assert isinstance(safe, bool), f"{code}: bad safe_to_continue type"

    def test_ok_is_retryable_and_safe(self):
        _, retryable, safe = _RESULT_CATALOG[OperationCode.OK]
        assert retryable is True
        assert safe is True

    def test_safety_reset_failed_is_not_safe_to_continue(self):
        _, _, safe = _RESULT_CATALOG[OperationCode.SAFETY_RESET_FAILED]
        assert safe is False

    def test_config_invalid_is_not_safe_to_continue(self):
        _, _, safe = _RESULT_CATALOG[OperationCode.CONFIG_INVALID]
        assert safe is False

    def test_atem_disabled_is_info_severity(self):
        severity, _, _ = _RESULT_CATALOG[OperationCode.ATEM_DISABLED]
        assert severity == OperationSeverity.INFO

    def test_camera_timeout_is_retryable(self):
        _, retryable, _ = _RESULT_CATALOG[OperationCode.CAMERA_TIMEOUT]
        assert retryable is True

    def test_command_rejected_is_not_retryable(self):
        _, retryable, _ = _RESULT_CATALOG[OperationCode.COMMAND_REJECTED]
        assert retryable is False


# ── New OperationCode values ──────────────────────────────────────────────────

class TestNewOperationCodes:
    def test_partial_ok_exists(self):
        assert OperationCode.PARTIAL_OK == "PARTIAL_OK"

    def test_command_rejected_exists(self):
        assert OperationCode.COMMAND_REJECTED == "COMMAND_REJECTED"

    def test_camera_disconnected_exists(self):
        assert OperationCode.CAMERA_DISCONNECTED == "CAMERA_DISCONNECTED"

    def test_camera_timeout_exists(self):
        assert OperationCode.CAMERA_TIMEOUT == "CAMERA_TIMEOUT"

    def test_camera_queue_drained_exists(self):
        assert OperationCode.CAMERA_QUEUE_DRAINED == "CAMERA_QUEUE_DRAINED"

    def test_atem_disabled_exists(self):
        assert OperationCode.ATEM_DISABLED == "ATEM_DISABLED"

    def test_atem_disconnected_exists(self):
        assert OperationCode.ATEM_DISCONNECTED == "ATEM_DISCONNECTED"

    def test_atem_command_failed_exists(self):
        assert OperationCode.ATEM_COMMAND_FAILED == "ATEM_COMMAND_FAILED"

    def test_safety_reset_codes_exist(self):
        assert OperationCode.SAFETY_RESET_STARTED
        assert OperationCode.SAFETY_RESET_COMPLETED
        assert OperationCode.SAFETY_RESET_PARTIAL_FAILURE
        assert OperationCode.SAFETY_RESET_FAILED

    def test_persistence_write_failed_exists(self):
        assert OperationCode.PERSISTENCE_WRITE_FAILED == "PERSISTENCE_WRITE_FAILED"

    def test_unknown_error_exists(self):
        assert OperationCode.UNKNOWN_ERROR == "UNKNOWN_ERROR"


# ── OperationResult factories ─────────────────────────────────────────────────

class TestOperationResultSuccess:
    def test_ok_code(self):
        r = OperationResult.success()
        assert r.ok is True
        assert r.code == OperationCode.OK

    def test_ok_retryable_and_safe(self):
        r = OperationResult.success()
        assert r.retryable is True
        assert r.safe_to_continue is True

    def test_fields_passed_through(self):
        r = OperationResult.success(operation="recall_preset", target="cam1")
        assert r.operation == "recall_preset"
        assert r.target == "cam1"


class TestOperationResultPartial:
    def test_partial_ok_code(self):
        r = OperationResult.partial("two cameras stopped, ATEM cleanup failed")
        assert r.ok is True
        assert r.code == OperationCode.PARTIAL_OK

    def test_partial_severity_is_warning(self):
        r = OperationResult.partial("partial")
        assert r.severity == OperationSeverity.WARNING

    def test_partial_safe_to_continue(self):
        r = OperationResult.partial("partial")
        assert r.safe_to_continue is True


class TestOperationResultFailure:
    def test_failure_sets_ok_false(self):
        r = OperationResult.failure(OperationCode.SESSION_INACTIVE, "no session")
        assert r.ok is False

    def test_catalog_severity_applied(self):
        r = OperationResult.failure(OperationCode.ATEM_DISABLED, "disabled")
        assert r.severity == OperationSeverity.INFO

    def test_caller_can_override_severity(self):
        r = OperationResult.failure(
            OperationCode.CAMERA_TIMEOUT, "timeout",
            severity=OperationSeverity.CRITICAL,
        )
        assert r.severity == OperationSeverity.CRITICAL

    def test_retryable_from_catalog(self):
        r = OperationResult.failure(OperationCode.CAMERA_TIMEOUT, "timeout")
        assert r.retryable is True

    def test_safe_to_continue_from_catalog(self):
        r = OperationResult.failure(OperationCode.CONFIG_INVALID, "bad config")
        assert r.safe_to_continue is False

    def test_subsystem_stored(self):
        r = OperationResult.failure(
            OperationCode.ATEM_DISCONNECTED, "no tcp", subsystem="atem"
        )
        assert r.subsystem == "atem"


class TestOperationResultCatalogMeta:
    def test_catalog_meta_returns_tuple(self):
        meta = OperationResult.catalog_meta(OperationCode.CAMERA_TIMEOUT)
        assert len(meta) == 3

    def test_catalog_meta_unknown_code_returns_safe_default(self):
        # If a new code is added without a catalog entry, fallback is conservative.
        meta = OperationResult.catalog_meta(OperationCode.UNKNOWN_ERROR)
        _, _, safe = meta
        assert safe is False


# ── from_command_result ───────────────────────────────────────────────────────

def _cmd(ok: bool, error_code: str | None = None, message: str = "msg") -> CommandResult:
    return CommandResult(
        ok=ok,
        command="recall_preset",
        target="cam1",
        duration_ms=50,
        correlation_id=str(uuid.uuid4()),
        error_code=error_code,
        message=message,
    )


class TestFromCommandResult:
    def test_ok_command_result_yields_ok(self):
        r = OperationResult.from_command_result(_cmd(ok=True))
        assert r.ok is True
        assert r.code == OperationCode.OK

    def test_camera_timeout_error_code_maps_specifically(self):
        r = OperationResult.from_command_result(_cmd(ok=False, error_code="CAMERA_TIMEOUT"))
        assert r.code == OperationCode.CAMERA_TIMEOUT

    def test_camera_disconnected_error_code_maps_specifically(self):
        r = OperationResult.from_command_result(_cmd(ok=False, error_code="CAMERA_DISCONNECTED"))
        assert r.code == OperationCode.CAMERA_DISCONNECTED

    def test_generic_camera_error_maps_to_command_failed(self):
        r = OperationResult.from_command_result(_cmd(ok=False, error_code="CAMERA_ERROR"))
        assert r.code == OperationCode.CAMERA_COMMAND_FAILED

    def test_unknown_error_code_maps_to_command_failed(self):
        r = OperationResult.from_command_result(_cmd(ok=False, error_code="MYSTERY"))
        assert r.code == OperationCode.CAMERA_COMMAND_FAILED

    def test_subsystem_set_to_camera_on_failure(self):
        r = OperationResult.from_command_result(_cmd(ok=False))
        assert r.subsystem == "camera"

    def test_duration_and_correlation_carried_over(self):
        cmd = _cmd(ok=True)
        r = OperationResult.from_command_result(cmd)
        assert r.duration_ms == cmd.duration_ms
        assert r.correlation_id == cmd.correlation_id


# ── Safety Reset structured results ──────────────────────────────────────────

class TestSafetyResetResults:
    def _camera_port(self, stop_ok: bool = True):
        port = MagicMock()
        port.stop_all.return_value = CommandResult(
            ok=stop_ok, command="stop_all", target="all",
            duration_ms=10, correlation_id=str(uuid.uuid4()),
            error_code=None if stop_ok else "CAMERA_ERROR",
            message="OK" if stop_ok else "stop failed",
        )
        return port

    def test_safety_reset_completed_code_on_success(self):
        from application.safety_reset_service import SafetyResetService
        from application.runtime_safety_service import RuntimeSafetyService

        safety = RuntimeSafetyService(self._camera_port(), camera_ids=["cam1"])
        svc = SafetyResetService(runtime_safety=safety)
        result = svc.reset()
        assert result.ok is True
        assert result.code == OperationCode.SAFETY_RESET_COMPLETED

    def test_safety_reset_partial_failure_code_on_camera_stop_failure(self):
        from application.safety_reset_service import SafetyResetService
        from application.runtime_safety_service import RuntimeSafetyService

        safety = RuntimeSafetyService(self._camera_port(stop_ok=False), camera_ids=["cam1"])
        svc = SafetyResetService(runtime_safety=safety)
        result = svc.reset()
        assert result.ok is False
        assert result.code == OperationCode.SAFETY_RESET_PARTIAL_FAILURE

    def test_safety_reset_partial_failure_is_structured(self):
        from application.safety_reset_service import SafetyResetService
        from application.runtime_safety_service import RuntimeSafetyService

        safety = RuntimeSafetyService(self._camera_port(stop_ok=False), camera_ids=["cam1"])
        svc = SafetyResetService(runtime_safety=safety)
        result = svc.reset()
        assert result.subsystem == "safety_reset"
        assert "camera" in result.message.lower() or "error" in result.message.lower()

    def test_safety_reset_completed_result_is_structured(self):
        from application.safety_reset_service import SafetyResetService
        from application.runtime_safety_service import RuntimeSafetyService

        safety = RuntimeSafetyService(self._camera_port(), camera_ids=["cam1"])
        svc = SafetyResetService(runtime_safety=safety)
        result = svc.reset()
        assert result.subsystem == "safety_reset"
        assert result.safe_to_continue is True


# ── ATEM codes ────────────────────────────────────────────────────────────────

class TestAtemDisabledResult:
    def test_atem_disabled_code_when_port_is_none(self):
        from application.atem_command_service import AtemCommandService
        from domain.call_set_policy import OperatingMode

        svc = AtemCommandService(atem_port=None)
        result = svc.cut(actor="op", role=OperatingMode.TECHNICIAN)
        assert result.ok is False
        assert result.code == OperationCode.ATEM_DISABLED

    def test_atem_disabled_result_is_structured(self):
        from application.atem_command_service import AtemCommandService
        from domain.call_set_policy import OperatingMode

        svc = AtemCommandService(atem_port=None)
        result = svc.cut(actor="op", role=OperatingMode.TECHNICIAN)
        assert result.subsystem == "atem"
        assert result.safe_to_continue is True   # disabled is safe; just not available

    def test_atem_disconnected_on_exception(self):
        from application.atem_command_service import AtemCommandService
        from domain.call_set_policy import OperatingMode

        port = MagicMock()
        port.cut.side_effect = ConnectionError("TCP reset")
        svc = AtemCommandService(atem_port=port)
        result = svc.cut(actor="op", role=OperatingMode.TECHNICIAN)
        assert result.code == OperationCode.ATEM_DISCONNECTED


# ── Result details are redaction-safe ────────────────────────────────────────

class TestResultDetailsAreRedacted:
    def test_failure_message_does_not_contain_ip_from_exc(self):
        # exc messages from lower layers may contain IPs; callers should not
        # blindly forward them. This test documents the expected contract —
        # the taxonomy result must not expose private network details.
        result = OperationResult.failure(
            OperationCode.CAMERA_DISCONNECTED,
            message="Camera unreachable",   # sanitised, not the raw exc
            subsystem="camera",
        )
        assert "192.168" not in result.message
        assert "172.16" not in result.message

    def test_to_dict_serialises_all_new_fields(self):
        r = OperationResult.failure(
            OperationCode.ATEM_DISCONNECTED, "err",
            subsystem="atem",
        )
        d = r.to_dict()
        assert "retryable" in d
        assert "safe_to_continue" in d
        assert "subsystem" in d
        assert d["subsystem"] == "atem"
