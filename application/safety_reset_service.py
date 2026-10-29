#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/safety_reset_service.py — Safety Reset orchestration (#765, #782).
#
# SafetyResetService executes a full runtime soft-reset:
#   1. Stop all cameras immediately (priority STOP, bypasses session guard).
#   2. Clear volatile session state (chairman, session_id, active flag).
#   3. ATEM transient-state cleanup (#782) — clears cached state, not config.
#   4. Report per-subsystem outcome without raising.
#
# What Safety Reset does NOT do:
#   - Does not send camera standby / power-off.
#   - Does not delete config.yaml, room layout, presets, or names.
#   - Does not restart the app process or reboot the Raspberry Pi.
#   - Does not send destructive ATEM commands.
#
# The reset is idempotent: calling it twice is safe and leaves the system
# in the same known-good state.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.supportability import OperationCode, OperationResult, OperationSeverity

if TYPE_CHECKING:
    from application.runtime_safety_service import RuntimeSafetyService
    from application.session_service import SessionService

logger = logging.getLogger(__name__)


class SafetyResetService:
    """Orchestrates a full runtime Safety Reset without rebooting.

    The reset stops all camera movement, drains command queues (via
    CameraWorker priority STOP), and clears volatile session state.
    Persistent configuration and customer data are preserved.

    Parameters
    ----------
    runtime_safety:
        RuntimeSafetyService — owns the STOP_ALL camera logic.
    session_service:
        SessionService — provides clear_runtime_state() for session cleanup.
    """

    def __init__(
        self,
        runtime_safety: "RuntimeSafetyService",
        session_service: "SessionService | None" = None,
        atem_port=None,  # duck-typed AtemRuntimeSafety: reset_transient_state() + cancel_pending_commands()
    ) -> None:
        self._safety = runtime_safety
        self._session = session_service
        self._atem_port = atem_port

    def reset(self) -> OperationResult:
        """Execute a Safety Reset.

        Sequence:
          1. STOP_ALL cameras (priority, drains queues).
          2. Clear volatile session state (if SessionService is wired).

        Returns a structured OperationResult reporting which subsystems
        succeeded or failed.  Never raises — subsystem errors are captured
        and included in the result message.
        """
        logger.warning("SafetyResetService: Safety Reset initiated")

        failures: list[str] = []

        # Step 1 — Stop all cameras
        try:
            camera_result = self._safety.stop_all_cameras()
            if not camera_result.ok:
                failures.append(f"cameras: {camera_result.message}")
        except Exception as exc:
            logger.exception("SafetyResetService: stop_all_cameras raised: %s", exc)
            failures.append(f"cameras: {exc}")

        # Step 2 — Clear session runtime state (no standby sent)
        if self._session is not None:
            try:
                self._session.clear_runtime_state()
            except Exception as exc:
                logger.exception("SafetyResetService: clear_runtime_state raised: %s", exc)
                failures.append(f"session: {exc}")

        # Step 3 — ATEM transient-state cleanup (#782)
        if self._atem_port is not None:
            try:
                self._atem_port.reset_transient_state()
                self._atem_port.cancel_pending_commands()
            except Exception as exc:
                logger.exception("SafetyResetService: atem cleanup raised: %s", exc)
                failures.append(f"atem: {exc}")

        if failures:
            msg = "Safety Reset completed with errors: " + "; ".join(failures)
            logger.error("SafetyResetService: %s", msg)
            return OperationResult.failure(
                code=OperationCode.SAFETY_RESET_PARTIAL_FAILURE,
                message=msg,
                operation="safety_reset",
                target="runtime",
                subsystem="safety_reset",
            )

        logger.warning("SafetyResetService: Safety Reset complete — system in known-good state")
        return OperationResult(
            ok=True,
            code=OperationCode.SAFETY_RESET_COMPLETED,
            message="Safety Reset complete",
            severity=OperationSeverity.WARNING,
            operation="safety_reset",
            target="runtime",
            subsystem="safety_reset",
            retryable=False,
            safe_to_continue=True,
        )
