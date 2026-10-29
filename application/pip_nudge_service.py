#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/pip_nudge_service.py — Desplazamiento lateral de cámara sincronizado con PiP ATEM.
#
# Cuando el PiP del ATEM se activa, desplaza la cámara configurada una cantidad
# ajustable hacia un lado.  Al desactivarse, invierte el movimiento para volver
# a la posición previa.
#
# PUNTOS DE ENTRADA:
#   on_pip_changed(pip_state) — para señal ATEMMonitor.pip_changed (producción).
#                               Comprueba sesión activa antes de actuar.
#   on_pip_on() / on_pip_off() — llamada directa desde el panel demo.
#                                Sin comprobación de sesión (útil en modo demo).
#   update(pan_speed, direction, duration_ms) — actualización en vivo desde la UI.
#
# THREADING: los puntos de entrada se invocan desde varios hilos:
#   - on_pip_changed/on_pip_on/on_pip_off: hilo del ATEMMonitor (la señal
#     pip_changed se conecta directamente a este servicio, que no es QObject,
#     por lo que Qt usa DirectConnection) o el hilo Qt principal (panel demo).
#   - cancel(): hilo worker del AsyncEventBus (suscrito vía bus.subscribe).
#   - _stop_camera(): hilo del threading.Timer.
# Todo el estado mutable (_nudge_active, _pending_stop, _generation) se protege
# con _lock.  Además el contador _generation evita stops tardíos: cada _apply()
# lo incrementa; _stop_camera() solo detiene la cámara si no ha cambiado desde
# que se lanzó.
#
# Dependencias: CameraPort (via ports/), threading.  Sin PyQt5.

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from config.settings import PiPNudgeSettings
    from ports.camera_port import CameraPort

logger = logging.getLogger(__name__)


class PiPNudgeService:
    """Desplaza la cámara platform cuando el PiP del ATEM se activa/desactiva.

    Uso básico (demo/test):
        svc = PiPNudgeService(camera_port, "cam1", settings)
        svc.on_pip_on()   # llamar al activar PiP
        svc.on_pip_off()  # llamar al desactivar PiP
        svc.cancel()      # llamar si control manual interrumpe el nudge

    Uso producción (conectado a ATEMMonitor.pip_changed):
        svc = PiPNudgeService(..., session_provider=lambda: mw.session_active)
        atem_monitor.pip_changed.connect(svc.on_pip_changed)
    """

    def __init__(
        self,
        camera_port: "CameraPort",
        camera_id: str,
        settings: "PiPNudgeSettings",
        session_provider: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._port = camera_port
        self._camera_id = camera_id
        self._cfg = settings
        self._session_provider = session_provider or (lambda: True)
        self._nudge_active = False
        self._pending_stop: threading.Timer | None = None
        self._generation = 0  # incrementado en cada _apply(); evita stop tardío
        # Reentrante: _apply() se invoca desde on_pip_on/off que ya tienen el lock.
        self._lock = threading.RLock()

    # ── API pública ───────────────────────────────────────────────────────────

    def on_pip_changed(self, pip_state) -> None:
        """Punto de entrada para ATEMMonitor.pip_changed (modo producción).

        Comprueba que la sesión esté activa antes de actuar.
        """
        if not self._session_provider():
            logger.debug("[PiPNudge] pip_changed ignorado: sesión inactiva")
            return
        if pip_state.enabled:
            self.on_pip_on()
        else:
            self.on_pip_off()

    def on_pip_on(self) -> None:
        """Aplica el desplazamiento lateral al activarse el PiP."""
        with self._lock:
            if self._cfg.pan_speed == 0 or self._cfg.duration_ms == 0:
                return
            pan = self._cfg.pan_speed
            if self._cfg.direction == "left":
                pan = -pan
            self._nudge_active = True   # antes de _apply para que pip_off no lo ignore
            self._apply(pan, label="ON")

    def on_pip_off(self) -> None:
        """Invierte el desplazamiento al desactivarse el PiP."""
        with self._lock:
            if not self._nudge_active:
                return
            self._nudge_active = False
            pan = self._cfg.pan_speed
            if self._cfg.direction == "right":
                pan = -pan   # fue a la derecha → vuelve a la izquierda
            self._apply(pan, label="OFF")

    def cancel(self) -> None:
        """Cancela cualquier desplazamiento pendiente (control manual).

        No envía stop_move: el comando manual ya está en la cola VISCA y
        se ejecutará inmediatamente después del nudge en curso.
        """
        with self._lock:
            self._cancel_pending_stop()
            self._nudge_active = False

    def update(self, pan_speed: int, direction: str, duration_ms: int) -> None:
        """Actualización en vivo desde la UI — efectiva en el próximo pip_on/off."""
        with self._lock:
            self._cfg.pan_speed = pan_speed
            self._cfg.direction = direction
            self._cfg.duration_ms = duration_ms
        logger.debug(
            "[PiPNudge] settings updated: pan_speed=%d direction=%s duration_ms=%d",
            pan_speed, direction, duration_ms,
        )

    def describe(self) -> str:
        """Devuelve una descripción legible del nudge configurado (para dry-run / UI)."""
        if self._cfg.pan_speed == 0 or self._cfg.duration_ms == 0:
            return "sin nudge (valores en 0)"
        return (
            f"pan {self._cfg.direction}  velocidad={self._cfg.pan_speed}  "
            f"duración={self._cfg.duration_ms} ms"
        )

    # ── Internos ──────────────────────────────────────────────────────────────

    def _apply(self, pan_speed: int, label: str) -> None:
        self._cancel_pending_stop()
        self._generation += 1
        gen = self._generation
        self._port.move(self._camera_id, pan_speed, 0)
        logger.info(
            "[PiPNudge] PiP %s → pan %+d durante %d ms (cam=%s)",
            label, pan_speed, self._cfg.duration_ms, self._camera_id,
        )
        t = threading.Timer(
            self._cfg.duration_ms / 1000.0,
            self._stop_camera,
            args=(gen,),
        )
        t.daemon = True
        t.start()
        self._pending_stop = t

    def _cancel_pending_stop(self) -> None:
        if self._pending_stop is not None:
            self._pending_stop.cancel()
            self._pending_stop = None

    def _stop_camera(self, gen: int) -> None:
        with self._lock:
            if gen != self._generation:
                return  # un _apply() posterior ya tomó el control
            self._pending_stop = None
        # stop_move() fuera del lock: solo encola un comando VISCA, pero así
        # evitamos retener el lock durante la llamada al puerto.
        self._port.stop_move(self._camera_id)
