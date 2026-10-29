#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/session_service.py — Estado y lógica de ciclo de vida de sesión
#
# Sin Qt. Trackea estado de sesión; la UI (SessionController) gestiona QTimer y diálogos.
# Emite SessionStarted / SessionEnded al FlightRecorder cuando está disponible.

from __future__ import annotations

import logging
import threading
import uuid
from typing import Optional, TYPE_CHECKING

from application.session_marker import clear_session_marker, mark_session_active
from domain.time_utils import utc_now_iso as _utc_now

if TYPE_CHECKING:
    from ports.camera_port import CameraPort
    from core.state import SystemState
    from application.runtime_state_store import RuntimeStateStore

logger = logging.getLogger(__name__)


class SessionService:
    """
    Encapsula el estado de sesión y los comandos de cámara asociados.

    La lógica de QTimer y diálogos permanece en SessionController (capa Qt).
    Esta clase solo gestiona el estado; los detalles VISCA/hardware viven en el adaptador.

    Parameters
    ----------
    camera_port:
        CameraPort adapter for camera commands.
    camera_ids:
        Ordered list of camera IDs to operate on.  Defaults to ["cam1", "cam2"].
    flight_recorder:
        Optional FlightRecorder for emitting SessionStarted / SessionEnded events.
    """

    def __init__(
        self,
        camera_port: 'CameraPort',
        camera_ids: 'list[str] | None' = None,
        flight_recorder=None,
        system_state: 'Optional[SystemState]' = None,
        runtime_state_store: 'Optional[RuntimeStateStore]' = None,
    ) -> None:
        self._port = camera_port
        self._camera_ids: list[str] = camera_ids if camera_ids is not None else ["cam1", "cam2"]
        self._recorder = flight_recorder
        self._system_state = system_state
        self._store = runtime_state_store  # #791 — fuente unica de verdad
        self._active = False
        self._chairman: Optional[str] = None
        self._session_id: Optional[str] = None

    @property
    def active(self) -> bool:
        return self._active

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    # ── SystemState mirror helpers ─────────────────────────────────────────────

    def _sync_active(self, value: bool) -> None:
        if self._system_state is not None:
            self._system_state.session.active = value

    def _sync_chairman(self, value: Optional[str]) -> None:
        if self._system_state is not None:
            self._system_state.session.chairman_name = value

    # ── Helpers de RuntimeStateStore (#791) ───────────────────────────────────

    def _store_session_started(self) -> None:
        if self._store is not None:
            self._store.update_session(
                active=True,
                session_id=self._session_id,
                started_at=_utc_now(),
                clear_chairman=True,
            )

    def _store_session_ended(self) -> None:
        if self._store is not None:
            self._store.update_session(
                active=False,
                clear_session_id=True,
                clear_chairman=True,
                clear_started_at=True,
            )

    def _store_chairman_set(self, name: str) -> None:
        if self._store is not None:
            self._store.update_session(chairman_name=name)

    def _store_chairman_cleared(self) -> None:
        if self._store is not None:
            self._store.update_session(clear_chairman=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_chairman(self, name: str) -> None:
        self._chairman = name
        self._sync_chairman(name)
        self._store_chairman_set(name)
        logger.info("SessionService: chairman = '%s'", name)

    def start(self) -> None:
        """Envía Power ON a todas las cámaras. QTimer para Home lo gestiona SessionController."""
        self._session_id = f"session-{uuid.uuid4().hex[:12]}"
        self._power_thread = self._power_on_all_async()
        self._active = True
        self._sync_active(True)
        self._store_session_started()
        try:
            mark_session_active()
        except OSError:
            logger.warning("SessionService: no se pudo escribir marcador de sesión")
        logger.info("SessionService: sesión iniciada session_id=%s", self._session_id)
        self._record_event("SessionStarted", result="succeeded")

    def _power_on_all(self) -> None:
        """Power ON secuencial de todas las cámaras (logging por fallo)."""
        for cam_id in self._camera_ids:
            result = self._port.power_on(cam_id)
            if result is not None and hasattr(result, "ok") and not result.ok:
                logger.warning(
                    "SessionService: power_on falló en %s: %s",
                    cam_id, getattr(result, "message", "unknown"),
                )

    def _power_on_all_async(self) -> threading.Thread:
        """Lanza _power_on_all en un hilo daemon y lo devuelve.

        start() se llama desde callbacks Qt (ToggleSession): cada power_on es
        un comando confirmado que puede bloquear varios segundos por cámara
        esperando la respuesta VISCA. En el hilo UI eso congela la aplicación
        y, peor, impide que salga un STOP del operador. El arranque de sesión
        no depende de que las cámaras hayan confirmado: la sesión queda activa
        y los encendidos se completan en segundo plano (un STOP los interrumpe
        con fallo inmediato). El thread se devuelve para que los tests puedan
        esperarlo con join().
        """
        t = threading.Thread(
            target=self._power_on_all, daemon=True, name="SessionPowerOn")
        t.start()
        return t

    def home_both(self) -> None:
        """Envía Home a todas las cámaras. Llamar desde QTimer callback en SessionController."""
        for cam_id in self._camera_ids:
            self._port.home(cam_id)

    def end(self, reason: str = "manual") -> None:
        """Envía Standby a todas las cámaras."""
        for cam_id in self._camera_ids:
            self._port.cancel_polls(cam_id)
        for cam_id in self._camera_ids:
            result = self._port.standby(cam_id)
            if result is not None and hasattr(result, "ok") and not result.ok:
                logger.warning(
                    "SessionService: standby falló en %s: %s",
                    cam_id, getattr(result, "message", "unknown"),
                )
        self._active = False
        self._sync_active(False)
        self._chairman = None
        self._sync_chairman(None)
        self._store_session_ended()
        try:
            clear_session_marker()
        except OSError:
            logger.warning("SessionService: no se pudo borrar marcador de sesión")
        logger.info("SessionService: sesión terminada session_id=%s reason=%s", self._session_id, reason)
        self._record_event("SessionEnded", result="succeeded", reason=reason)
        self._session_id = None

    def clear_runtime_state(self) -> None:
        """Clear volatile session state without sending camera commands.

        Called by SafetyResetService during a Safety Reset.  Does not put
        cameras into standby — the reset service has already stopped them.
        Preserves persistent data (config, layout, presets, names).
        """
        self._active = False
        self._sync_active(False)
        self._chairman = None
        self._sync_chairman(None)
        self._store_session_ended()
        try:
            clear_session_marker()
        except OSError:
            logger.warning("SessionService: no se pudo borrar marcador de sesión (safety reset)")
        logger.info("SessionService: runtime state cleared (safety reset)")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _record_event(self, event_type: str, **extra) -> None:
        if self._recorder is None:
            return
        try:
            from domain.blackbox_event import EventLevel, EventResult, EventSource
            self._recorder.record_dict({
                "timestamp": _utc_now(),
                "level": EventLevel.INFO,
                "event_type": event_type,
                "session_id": self._session_id or "none",
                "correlation_id": self._session_id or "none",
                "source": EventSource.OPERATOR_UI,
                "result": extra.pop("result", EventResult.SUCCEEDED),
                **extra,
            })
        except Exception:  # noqa: BLE001
            pass
