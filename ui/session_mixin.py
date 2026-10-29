#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# session_mixin.py — Mixin de gestión de sesión
#
# Responsabilidad única: controlar el ciclo de vida de la sesión:
# encender cámaras, esperar arranque de motores, ir a Home, apagar.
#
# CAMBIOS RESPECTO A VERSIÓN ANTERIOR:
#   - REDUNDANCIA ELIMINADA: el CSS de BtnSession se repetía 3 veces
#     (estado OFF, estado Starting, estado ON) con strings literales idénticos
#     dentro de ToggleSession() y _session_home().
#     Ahora son constantes de clase _STYLE_BTN_OFF, _STYLE_BTN_STARTING,
#     _STYLE_BTN_ON. Un solo lugar para cambiar el estilo.
#   - MOTIVO: si se cambia el radio del botón (actualmente 25px) o el color
#     base, antes había que modificar 3 strings en 2 métodos distintos.
#     Con constantes, un solo cambio lo afecta todo.

import logging

from PyQt5 import QtCore
from PyQt5.QtWidgets import QMessageBox

from core.events import EventType
from domain.preset import PRESET_CHAIRMAN_GENERIC

logger = logging.getLogger(__name__)


class SessionController:

    # ── Estilos del botón de sesión ────────────────────────────────────────
    # Extraídos como constantes de clase para evitar duplicación.
    # Antes estaban inline en ToggleSession() y _session_home() como strings
    # repetidos — cualquier cambio de color/radio requería 3 ediciones.

    _STYLE_BTN_OFF = (
        "QPushButton{background-color: #8b1a1a; border: 2px solid #5a0d0d;"
        " font: bold 26px; color: white; border-radius: 25px}"
        "QPushButton:pressed{background-color: #5a0d0d}"
    )

    _STYLE_BTN_STARTING = (
        # Gris: indica que el botón está temporalmente deshabilitado
        # mientras las cámaras inicializan los motores (8 segundos).
        "QPushButton{background-color: #555; border: 2px solid #333;"
        " font: bold 26px; color: #aaa; border-radius: 25px}"
    )

    _STYLE_BTN_ON = (
        "QPushButton{background-color: #1a7a1a; border: 2px solid #0d4d0d;"
        " font: bold 26px; color: white; border-radius: 25px}"
        "QPushButton:pressed{background-color: #0d4d0d}"
    )

    def __init__(self, window):
        self._w = window

    def ToggleSession(self):
        """
        Botón ⏻: alterna entre iniciar y terminar la sesión.

        INICIO DE SESIÓN:
          1. Envía Power ON a ambas cámaras (01 04 00 02 FF).
          2. Deshabilita el botón durante 8 s: las cámaras PTZ necesitan
             ese tiempo para inicializar los motores antes de aceptar movimiento.
          3. Tras 8 s, _session_home() mueve ambas a Home y reactiva el botón.

        FIN DE SESIÓN:
          1. Pide confirmación para evitar apagados accidentales.
          2. Envía Standby (01 04 00 03 FF) a ambas cámaras.
          3. Actualiza UI a estado OFF.
        """
        if not self._w.session_active:
            # ── Arrancar sesión ───────────────────────────────────────────
            self._w.session_active = True
            self._w._record_activity()       # resetea el contador de inactividad
            self._w._reset_watchdog_state()  # restaura caps y reintentos

            # Deshabilitar botón mientras las cámaras arrancan
            self._w.BtnSession.setEnabled(False)
            self._w.BtnSession.setStyleSheet(self._STYLE_BTN_STARTING)  # gris: en proceso
            self._w.SessionStatus.setText('Starting...')
            self._w.SessionStatus.setStyleSheet("font: bold 12px; color: #888")

            # Power ON via bus → Controller → SessionService.start()
            self._w._bus.emit(EventType.SESSION_START)
            self._w.Cam1.set_powered(True)
            self._w.Cam2.set_powered(True)
            self._w._update_controls_visibility()

            # Esperar antes de enviar Home: los motores PTZ necesitan tiempo
            # para inicializarse. En sim las cámaras son falsas → 1 s es suficiente.
            import adapters.sim_mode as _sm
            delay_ms = 1000 if _sm.is_active() else 8000
            QtCore.QTimer.singleShot(delay_ms, self._session_home)

        else:
            # ── Terminar sesión ───────────────────────────────────────────
            reply = QMessageBox.question(
                self._w, 'End Session',
                'Power off both cameras and end the session?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.shutdown("manual")

    def shutdown(self, reason: str = "manual") -> None:
        """Cancel preset polls, power off cameras, and update session state/UI.

        Single shutdown path shared by manual End Session and inactivity auto
        power-off (#194). reason is logged so operators can distinguish the two.
        """
        logger.info("Session shutdown: reason=%s", reason)

        # Standby via bus → Controller → SessionService.end(reason)
        self._w._bus.emit(EventType.SESSION_END, reason=reason)

        self._w.Cam1.set_powered(False)
        self._w.Cam2.set_powered(False)
        self._w.session_active = False
        self._w._update_controls_visibility()
        self._w.BtnSession.setEnabled(True)  # re-enable if ended during startup window
        self._w.BtnSession.setStyleSheet(self._STYLE_BTN_OFF)
        self._w.BtnSession.setToolTip('Start Session: Power ON both cameras and go Home')
        self._w.SessionStatus.setText('OFF')
        self._w.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")

    def _session_home(self):
        """
        Llamado por QTimer 8 s después del Power ON.
        Cam1 → posición chairman (preset 1). Cam2 → Home.
        """
        if not self._w.session_active or getattr(self._w, "_shutting_down", False):
            return

        # Cam1 → chairman generic preset, Cam2 → mechanical home via bus
        self._w._bus.emit(
            EventType.SEAT_SELECTED,
            preset=PRESET_CHAIRMAN_GENERIC,       # canonical VISCA slot
            seat_number=PRESET_CHAIRMAN_GENERIC,  # backward compat alias
            camera=1,
            name="",
        )
        self._w._bus.emit(EventType.CAMERA_HOME, camera=2)

        self._w.BtnSession.setStyleSheet(self._STYLE_BTN_ON)  # verde: sesión activa
        self._w.BtnSession.setToolTip('End Session: Power OFF (standby) both cameras')
        self._w.BtnSession.setEnabled(True)
        self._w.SessionStatus.setText('ON')
        self._w.SessionStatus.setStyleSheet("font: bold 12px; color: #1a7a1a")
