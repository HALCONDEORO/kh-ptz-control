#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/atem_command_service.py — Manual ATEM write commands with safety guards (#553)
#
# AtemCommandService exposes Phase 1 manual live-switching commands with guards:
#   set_preview(input_id, actor, role)
#   cut(actor, role)
#   auto(actor, role)
#
# Safety rules:
#   - CUT/AUTO require TECHNICIAN role.  Normal operator/camera_operator cannot cut live.
#   - CUT/AUTO never retry automatically — one call, one result.
#   - Commands require ATEM to be connected.
#   - All commands are auditable: correlation_id + actor in result data.
#   - Returns OperationResult.failure when role is insufficient.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.atem_policy import can_live_switch
from domain.call_set_policy import OperatingMode
from domain.supportability import OperationCode, OperationResult, OperationSeverity

if TYPE_CHECKING:
    from ports.atem_port import AtemWritePort

logger = logging.getLogger(__name__)


class AtemCommandService:
    """Manual ATEM live-switching commands with role-based safety guards.

    Parameters
    ----------
    atem_port:
        AtemWritePort implementation (FakeATEM or production adapter).
        Pass None when ATEM is absent/disabled — all methods return failure.
    """

    def __init__(self, atem_port: "AtemWritePort | None" = None) -> None:
        self._port = atem_port

    def set_preview(
        self,
        input_id: int,
        actor: str = "",
        role: OperatingMode = OperatingMode.CAMERA_OPERATOR,
    ) -> OperationResult:
        """Set ATEM preview bus input.

        Any role may set preview — it does not cause an on-air transition.
        """
        if self._port is None:
            return self._disabled("set_preview")
        try:
            result = self._port.set_preview_input(input_id)
            logger.info(
                "[ATEM] set_preview input=%d actor=%r role=%s corr=%s ok=%s",
                input_id, actor, role.value, result.correlation_id, result.ok,
            )
            return self._from_atem_result(result, "set_preview")
        except Exception as exc:
            logger.exception("[ATEM] set_preview error: %s", exc)
            return self._error("set_preview", exc)

    def cut(
        self,
        actor: str = "",
        role: OperatingMode = OperatingMode.CAMERA_OPERATOR,
    ) -> OperationResult:
        """Execute CUT transition — TECHNICIAN role required.

        CUT is never retried automatically.  This method represents one
        deliberate operator action.  No automatic retry is performed on failure.
        """
        if self._port is None:
            return self._disabled("cut")
        if not can_live_switch(role):
            logger.warning("[ATEM] cut blocked: role=%s actor=%r", role.value, actor)
            return OperationResult(
                ok=False,
                code=OperationCode.PERMISSION_DENIED,
                message=f"CUT requires technician role (current: {role.value})",
                severity=OperationSeverity.WARNING,
                operation="atem_cut",
                target="atem",
            )
        try:
            result = self._port.cut()
            logger.warning(
                "[ATEM] CUT executed actor=%r role=%s corr=%s ok=%s",
                actor, role.value, result.correlation_id, result.ok,
            )
            return self._from_atem_result(result, "cut")
        except Exception as exc:
            logger.exception("[ATEM] cut error: %s", exc)
            return self._error("cut", exc)

    def auto(
        self,
        actor: str = "",
        role: OperatingMode = OperatingMode.CAMERA_OPERATOR,
    ) -> OperationResult:
        """Execute AUTO transition — TECHNICIAN role required.

        AUTO is never retried automatically.  This method represents one
        deliberate operator action.  Uses the ATEM's configured transition
        type and rate — the software does not control transition settings.
        """
        if self._port is None:
            return self._disabled("auto")
        if not can_live_switch(role):
            logger.warning("[ATEM] auto blocked: role=%s actor=%r", role.value, actor)
            return OperationResult(
                ok=False,
                code=OperationCode.PERMISSION_DENIED,
                message=f"AUTO requires technician role (current: {role.value})",
                severity=OperationSeverity.WARNING,
                operation="atem_auto",
                target="atem",
            )
        try:
            result = self._port.auto()
            logger.warning(
                "[ATEM] AUTO executed actor=%r role=%s corr=%s ok=%s",
                actor, role.value, result.correlation_id, result.ok,
            )
            return self._from_atem_result(result, "auto")
        except Exception as exc:
            logger.exception("[ATEM] auto error: %s", exc)
            return self._error("auto", exc)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _from_atem_result(self, result, operation: str) -> OperationResult:
        if result.ok:
            return OperationResult.success(
                operation=f"atem_{operation}",
                target="atem",
                message=f"ATEM {operation} OK",
                data={
                    "correlation_id": result.correlation_id,
                    "duration_ms": result.duration_ms,
                    "target": result.target,
                },
            )
        return OperationResult.failure(
            code=OperationCode.ATEM_COMMAND_FAILED,
            message=f"ATEM {operation} failed: {result.error_code} — {result.message}",
            operation=f"atem_{operation}",
            target="atem",
            subsystem="atem",
        )

    def _disabled(self, operation: str) -> OperationResult:
        return OperationResult.failure(
            code=OperationCode.ATEM_DISABLED,
            message="ATEM disabled or not installed",
            operation=f"atem_{operation}",
            target="atem",
            subsystem="atem",
        )

    def _error(self, operation: str, exc: Exception) -> OperationResult:
        return OperationResult.failure(
            code=OperationCode.ATEM_DISCONNECTED,
            message=f"ATEM {operation} error: {exc}",
            operation=f"atem_{operation}",
            target="atem",
            subsystem="atem",
        )
