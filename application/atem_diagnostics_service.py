#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/atem_diagnostics_service.py — Read-only ATEM diagnostics (#552)
#
# AtemDiagnosticsService wraps an AtemReadPort and exposes safe read operations
# for khptz doctor, status display and support bundles.
#
# Contract:
#   - NEVER calls set_preview, cut or auto.
#   - Returns OperationResult for every call — never raises.
#   - Works when ATEM is absent, disabled or disconnected.
#   - Stale state is marked with is_stale=True in result.data.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from domain.supportability import OperationCode, OperationResult, OperationSeverity

if TYPE_CHECKING:
    from ports.atem_port import AtemReadPort

logger = logging.getLogger(__name__)


class AtemDiagnosticsService:
    """Read-only ATEM diagnostics — safe for any mode or state.

    Parameters
    ----------
    atem_port:
        AtemReadPort implementation.  Pass None when ATEM is absent or
        disabled — all methods return a safe degraded result.
    """

    def __init__(self, atem_port: "AtemReadPort | None" = None) -> None:
        self._port = atem_port

    # ── Public API ────────────────────────────────────────────────────────────

    def read_status(self) -> OperationResult:
        """Return ATEM connection status as OperationResult."""
        if self._port is None:
            return self._disabled_result("read_status")
        try:
            status = self._port.get_status()
            data: dict[str, Any] = {
                "adapter_type": status.adapter_type,
                "connected": status.connected,
                "program_input": status.program_input,
                "preview_input": status.preview_input,
                "transitioning": status.transitioning,
                "automation_mode": status.automation_mode,
                "last_error": status.last_error,
            }
            if status.connected:
                return OperationResult.success(
                    operation="atem_read_status",
                    target="atem",
                    message="ATEM connected",
                    data=data,
                )
            return OperationResult(
                ok=False,
                code=OperationCode.ATEM_UNAVAILABLE,
                message="ATEM disconnected",
                severity=OperationSeverity.WARNING,
                operation="atem_read_status",
                target="atem",
                data=data,
            )
        except Exception as exc:
            logger.exception("AtemDiagnosticsService.read_status error: %s", exc)
            return self._error_result("read_status", exc)

    def read_program_input(self) -> OperationResult:
        """Return current program input as OperationResult."""
        if self._port is None:
            return self._disabled_result("read_program_input")
        try:
            value = self._port.get_program_input()
            data: dict[str, Any] = {"program_input": value, "is_stale": value is None}
            if value is not None:
                return OperationResult.success(
                    operation="atem_read_program", target="atem",
                    message=f"Program input: {value}", data=data,
                )
            return OperationResult(
                ok=False, code=OperationCode.ATEM_UNAVAILABLE,
                message="Program input unknown (no data received)",
                severity=OperationSeverity.WARNING,
                operation="atem_read_program", target="atem", data=data,
            )
        except Exception as exc:
            logger.exception("AtemDiagnosticsService.read_program_input error: %s", exc)
            return self._error_result("read_program_input", exc)

    def read_preview_input(self) -> OperationResult:
        """Return current preview input as OperationResult."""
        if self._port is None:
            return self._disabled_result("read_preview_input")
        try:
            value = self._port.get_preview_input()
            data: dict[str, Any] = {"preview_input": value, "is_stale": value is None}
            if value is not None:
                return OperationResult.success(
                    operation="atem_read_preview", target="atem",
                    message=f"Preview input: {value}", data=data,
                )
            return OperationResult(
                ok=False, code=OperationCode.ATEM_UNAVAILABLE,
                message="Preview input unknown (no data received)",
                severity=OperationSeverity.WARNING,
                operation="atem_read_preview", target="atem", data=data,
            )
        except Exception as exc:
            logger.exception("AtemDiagnosticsService.read_preview_input error: %s", exc)
            return self._error_result("read_preview_input", exc)

    def test_connection(self) -> OperationResult:
        """Test ATEM connectivity and return structured result."""
        if self._port is None:
            return self._disabled_result("test_connection")
        try:
            result = self._port.test_connection()
            if result.ok:
                return OperationResult.success(
                    operation="atem_test_connection", target="atem",
                    message="ATEM connection OK",
                    data={"correlation_id": result.correlation_id, "duration_ms": result.duration_ms},
                )
            return OperationResult(
                ok=False, code=OperationCode.ATEM_UNAVAILABLE,
                message=f"ATEM connection failed: {result.error_code} — {result.message}",
                severity=OperationSeverity.WARNING,
                operation="atem_test_connection", target="atem",
            )
        except Exception as exc:
            logger.exception("AtemDiagnosticsService.test_connection error: %s", exc)
            return self._error_result("test_connection", exc)

    def doctor_check(self) -> dict:
        """Return a doctor-style check dict for khptz doctor ATEM row."""
        if self._port is None:
            return {
                "name": "ATEM",
                "status": "NOT_APPLICABLE",
                "detail": "ATEM disabled or not installed",
            }
        conn_result = self.test_connection()
        if conn_result.ok:
            prog = self._port.get_program_input()
            return {"name": "ATEM", "status": "OK", "detail": f"Connected. Program: {prog}"}
        return {
            "name": "ATEM",
            "status": "WARNING",
            "detail": f"Disconnected or unreachable: {conn_result.message}",
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _disabled_result(self, operation: str) -> OperationResult:
        return OperationResult(
            ok=False, code=OperationCode.ATEM_UNAVAILABLE,
            message="ATEM disabled or not installed",
            severity=OperationSeverity.INFO,
            operation=f"atem_{operation}", target="atem",
        )

    def _error_result(self, operation: str, exc: Exception) -> OperationResult:
        return OperationResult(
            ok=False, code=OperationCode.ATEM_UNAVAILABLE,
            message=f"ATEM diagnostics error: {exc}",
            severity=OperationSeverity.ERROR,
            operation=f"atem_{operation}", target="atem",
        )
