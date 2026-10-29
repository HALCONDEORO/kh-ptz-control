#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# core/controller.py — Orquestador central
#
# El Controller es el único componente que:
#   - Suscribe eventos del bus
#   - Llama a los servicios de aplicación
#   - Actualiza SystemState
#
# Ni la UI ni los dispositivos llaman entre sí: todo pasa por aquí.
# Sin Qt. Sin I/O directa.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.events import AsyncEventBus, EventType, Event
from core.state import SystemState

if TYPE_CHECKING:
    from application.preset_service import PresetService
    from application.session_service import SessionService
    from ports.camera_port import CameraPort

logger = logging.getLogger(__name__)


class Controller:

    def __init__(
        self,
        state: SystemState,
        bus: AsyncEventBus,
        preset_svc: 'PresetService',
        session_svc: 'SessionService',
        camera_port: 'CameraPort',
    ) -> None:
        self._state        = state
        self._bus          = bus
        self._camera_port  = camera_port
        self._presets      = preset_svc
        self._session      = session_svc
        self._register()

    def _register(self) -> None:
        self._bus.subscribe(EventType.SEAT_SELECTED,         self._on_seat_selected)
        self._bus.subscribe(EventType.CAMERA_MOVE,           self._on_camera_move)
        self._bus.subscribe(EventType.CAMERA_STOP,           self._on_camera_stop)
        self._bus.subscribe(EventType.CAMERA_ZOOM,           self._on_camera_zoom)
        self._bus.subscribe(EventType.CAMERA_HOME,           self._on_camera_home)
        self._bus.subscribe(EventType.CHAIRMAN_ASSIGNED,     self._on_chairman_assigned)
        self._bus.subscribe(EventType.PRESET_SAVE_REQUESTED, self._on_preset_save_requested)
        self._bus.subscribe(EventType.PRESET_SAVE_SLOT,      self._on_preset_save_slot)
        self._bus.subscribe(EventType.SESSION_START,         self._on_session_start)
        self._bus.subscribe(EventType.SESSION_END,           self._on_session_end)

    # ─────────────────────────────────────────────────────────────────────
    #  Helpers
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _cam_id(cam: int) -> str:
        """Convert integer camera index (1/2) to CameraPort string ID."""
        return f"cam{cam}"

    def _no_session(self, command: str, payload: dict | None = None) -> bool:
        """Return True and warn if no session is active — caller must abort."""
        if not self._state.session.active:
            logger.warning(
                "command blocked (no active session): %s payload=%r",
                command, payload or {},
            )
            return True
        return False

    def _result_ok(self, result) -> bool:
        """Normalise a CameraPort CommandResult or a legacy bool to bool."""
        if hasattr(result, "ok"):
            return bool(result.ok)
        return bool(result)

    def _invalidate_zoom(self, cam: int) -> None:
        if hasattr(self._camera_port, "invalidate_zoom"):
            self._camera_port.invalidate_zoom(cam)

    # ─────────────────────────────────────────────────────────────────────
    #  Handlers
    # ─────────────────────────────────────────────────────────────────────

    def _on_seat_selected(self, event: Event) -> None:
        if self._no_session("seat_selected", event.payload):
            return
        name: str = event.payload.get("name", "")
        cam:  int = event.payload.get("camera", self._state.active_camera)
        # 'preset' is the canonical VISCA slot number.
        # 'seat_number' is kept as a backward-compat alias for callers that
        # have not yet been migrated to send the explicit 'preset' field.
        preset_slot: int = (
            event.payload.get("preset")
            or event.payload.get("seat_number")
            or 0
        )

        preset = self._presets.get_preset_for_name(name) if name else preset_slot

        if preset is None or preset == 0:  # slot==0 o slot inválido (0 es el slot "ninguno")
            logger.warning("seat_selected: preset inválido (slot=%d, name=%r)", preset_slot, name)
            return

        result = self._camera_port.recall_preset(self._cam_id(cam), preset)
        if self._result_ok(result):
            self._state.camera(cam).active_preset = preset
            self._invalidate_zoom(cam)

    def _on_camera_move(self, event: Event) -> None:
        if self._no_session("camera_move", event.payload):
            return
        cam  = event.payload["camera"]
        pan  = event.payload["pan_speed"]
        tilt = event.payload["tilt_speed"]
        self._camera_port.move(self._cam_id(cam), pan, tilt)
        cam_state = self._state.camera(cam)
        cam_state.pan_speed  = pan
        cam_state.tilt_speed = tilt

    def _on_camera_stop(self, event: Event) -> None:
        # stop_move is always safe to send — it should work even without a session
        # (e.g., stop a runaway move after session ends).  No session guard here.
        cam = event.payload["camera"]
        self._camera_port.stop_move(self._cam_id(cam))
        cam_state = self._state.camera(cam)
        cam_state.pan_speed  = 0
        cam_state.tilt_speed = 0

    def _on_camera_zoom(self, event: Event) -> None:
        if self._no_session("camera_zoom", event.payload):
            return
        cam   = event.payload["camera"]
        speed = event.payload["speed"]
        self._camera_port.zoom(self._cam_id(cam), speed)

    def _on_camera_home(self, event: Event) -> None:
        if self._no_session("camera_home", event.payload):
            return
        cam = event.payload["camera"]
        self._camera_port.home(self._cam_id(cam))

    def _on_chairman_assigned(self, event: Event) -> None:
        if self._no_session("chairman_assigned", event.payload):
            return
        name: str = event.payload["name"]
        self._state.session.chairman_name = name
        self._session.set_chairman(name)

        preset = self._presets.get_preset_for_name(name)
        cam = 1  # Chairman siempre controla Cam1 (Platform)
        result = self._camera_port.recall_preset(self._cam_id(cam), preset)
        if self._result_ok(result):
            self._state.camera(cam).active_preset = preset
            self._invalidate_zoom(cam)
        else:
            logger.warning("chairman_assigned: fallo al hacer recall preset %d", preset)

    def _on_preset_save_requested(self, event: Event) -> None:
        if self._no_session("preset_save_requested", event.payload):
            return
        cam:  int = event.payload.get("camera", 1)
        name: str = event.payload["name"]

        slot, is_new = self._presets.assign_slot(name)
        if slot is None:
            logger.error("preset_save: rango de presets agotado para '%s'", name)
            return

        result = self._camera_port.save_preset(self._cam_id(cam), slot)
        ok = self._result_ok(result)
        if ok:
            if is_new:
                persisted = self._presets.persist()
                if not persisted:
                    logger.error(
                        "preset_save: fallo al persistir preset para '%s' slot=%d — "
                        "PRESET_SAVED no emitido", name, slot,
                    )
                    return
            logger.info("Preset %d guardado para '%s' en Cam%d", slot, name, cam)
            self._bus.emit(EventType.PRESET_SAVED, camera=cam, name=name, slot=slot)
        else:
            if is_new:
                self._presets.release_slot(name)
            logger.error("preset_save: fallo VISCA para '%s' slot=%d — %s",
                         name, slot, "slot liberado" if is_new else "slot existente conservado")

    def _on_preset_save_slot(self, event: Event) -> None:
        if self._no_session("preset_save_slot", event.payload):
            return
        cam:  int = event.payload["camera"]
        slot: int = event.payload["slot"]
        result = self._camera_port.save_preset(self._cam_id(cam), slot)
        ok = self._result_ok(result)
        if ok:
            logger.info("Preset slot %d guardado en Cam%d", slot, cam)
        else:
            logger.error("preset_save_slot: fallo VISCA cam%d slot=%d", cam, slot)

    def _on_session_start(self, event: Event) -> None:
        self._session.start()

    def _on_session_end(self, event: Event) -> None:
        reason = event.payload.get("reason", "manual")
        self._session.end(reason=reason)
