#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/app_controller.py — Controlador de aplicación (capa de orquestación)
#
# ApplicationController es el único punto de entrada de la UI para acciones
# de runtime. Coordina la política CALL/SET, SessionService y el bus de eventos.
# No construye bytes VISCA, no lee YAML, no escribe JSON, no toca widgets Qt.

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING

from domain.call_set_policy import CallSetAction, InputType, OperatingMode
from domain.supportability import CommandResult

if TYPE_CHECKING:
    from application.call_set_command_policy import CallSetCommandPolicy
    from application.session_service import SessionService
    from core.events import AsyncEventBus

from core.events import EventType

logger = logging.getLogger(__name__)


class ApplicationController:
    """
    Single application boundary for UI-initiated runtime actions.

    The UI calls methods here; this class coordinates policy, services and bus
    events. It never builds VISCA bytes, parses YAML, writes JSON or owns Qt
    widgets.

    Responsibilities
    ----------------
    - Apply CallSetCommandPolicy before any camera action.
    - Emit bus events that drive the Controller → CameraPort path.
    - Return a CommandResult so the UI can react without duplicating policy.

    Actions not yet migrated here (tracked per issue):
    - Session power / home lifecycle          (#684)
    - Focus / AE / backlight / zoom adjust    (#739)
    - Diagnostic VISCA test in config dialog  (#683 follow-up)
    """

    def __init__(
        self,
        session_svc: "SessionService",
        call_set_policy: "CallSetCommandPolicy",
        bus: "AsyncEventBus",
    ) -> None:
        self._session = session_svc
        self._policy = call_set_policy
        self._bus = bus

    # ── Public API ────────────────────────────────────────────────────────────

    def recall_seat(
        self,
        seat_id: "int | str",
        input_type: InputType,
        cam: int,
        mode: OperatingMode,
        session_active: bool,
        camera_available: bool,
        preset: "int | None" = None,
    ) -> CommandResult:
        """
        Route a seat recall (CALL) through policy validation and emit
        SEAT_SELECTED on the bus.

        SET actions are intentionally not handled here: they require a
        confirmation dialog owned by the UI layer. The caller can detect
        a SET decision via ``error_code == "set_action"``.

        Parameters
        ----------
        seat_id:
            Stable seat identity (string ID from room_layout, or legacy int).
            Used for logging and policy targeting; not sent to the camera.
        preset:
            VISCA slot number to recall.  When omitted, defaults to int(seat_id)
            for backward compatibility with callers that use preset-as-identity.
        input_type:
            The gesture that initiated the action (TAP, LONG_PRESS, etc.).
        cam:
            Camera index (1 or 2) selected in the UI.
        mode:
            Current operating mode from the UI.
        session_active:
            Whether a session is currently active (from the UI's perspective).
        camera_available:
            Whether the selected camera is connected and ready.
        """
        t0 = time.monotonic()
        cid = str(uuid.uuid4())[:8]
        # Resolve VISCA preset slot: explicit 'preset' param wins; fall back to
        # int(seat_id) for callers that still use preset-as-identity (legacy).
        _preset: int = int(preset) if preset is not None else int(seat_id)
        target = f"seat:{seat_id}/cam:{cam}"

        decision = self._policy.decide(
            mode=mode,
            input_type=input_type,
            session_active=session_active,
            camera_available=camera_available,
        )

        if not decision.allowed:
            logger.debug(
                "recall_seat blocked: seat=%s reason=%s [%s]",
                seat_id, decision.reason_code, cid,
            )
            return CommandResult(
                ok=False,
                command="recall_seat",
                target=target,
                duration_ms=int((time.monotonic() - t0) * 1000),
                correlation_id=cid,
                error_code=decision.reason_code,
                message=f"recall blocked: {decision.reason_code}",
            )

        if decision.action == CallSetAction.CALL:
            self._bus.emit(
                EventType.SEAT_SELECTED,
                seat_id=str(seat_id),   # stable seat identity (future: str ID from layout)
                preset=_preset,          # canonical VISCA slot
                seat_number=_preset,     # backward compat alias — remove once all callers migrate
                camera=cam,
                name="",
            )
            logger.info(
                "recall_seat dispatched: seat=%s preset=%d cam=%d [%s]",
                seat_id, _preset, cam, cid,
            )
            return CommandResult(
                ok=True,
                command="recall_seat",
                target=target,
                duration_ms=int((time.monotonic() - t0) * 1000),
                correlation_id=cid,
                error_code=None,
                message="seat recall dispatched",
            )

        # SET is allowed but handled by the UI layer (confirmation dialog).
        return CommandResult(
            ok=False,
            command="recall_seat",
            target=target,
            duration_ms=int((time.monotonic() - t0) * 1000),
            correlation_id=cid,
            error_code="set_action",
            message="SET action must be confirmed and handled by UI layer",
        )

    def start_session(self) -> CommandResult:
        """
        Emit SESSION_START.

        Full camera power / home lifecycle is tracked in #684. Until that
        migration is complete, the session_mixin QTimer and VISCA power
        commands remain in the UI layer.
        """
        cid = str(uuid.uuid4())[:8]
        self._bus.emit(EventType.SESSION_START)
        logger.info("start_session dispatched [%s]", cid)
        return CommandResult(
            ok=True,
            command="start_session",
            target=None,
            duration_ms=0,
            correlation_id=cid,
            error_code=None,
            message="session start dispatched",
        )

    def end_session(self) -> CommandResult:
        """
        Emit SESSION_END.

        Full camera power-down lifecycle is tracked in #684. Until that
        migration is complete, the session_mixin shutdown path (including
        cancel_preset_polls) remains in the UI layer.
        """
        cid = str(uuid.uuid4())[:8]
        self._bus.emit(EventType.SESSION_END)
        logger.info("end_session dispatched [%s]", cid)
        return CommandResult(
            ok=True,
            command="end_session",
            target=None,
            duration_ms=0,
            correlation_id=cid,
            error_code=None,
            message="session end dispatched",
        )
