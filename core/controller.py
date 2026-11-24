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
from functools import wraps
from core.motion_admission import MotionAdmission
from typing import TYPE_CHECKING

from core.events import AsyncEventBus, EventType, Event
from core.state import SystemState

if TYPE_CHECKING:
    from application.preset_service import PresetService
    from application.session_service import SessionService
    from ports.camera_port import CameraPort

logger = logging.getLogger(__name__)


def _motion_handler(handler):
    @wraps(handler)
    def guarded(self, event):
        ticket = getattr(event, '_motion_ticket', None)
        if ticket is None:  # Direct handler callers (legacy/tests).
            self._prepare_motion(event)
            ticket = event._motion_ticket
        with self._motion.lock:
            if not self._motion.current(ticket):
                return
        with self._motion.intent(ticket):
            return handler(self, event)
    return guarded


class Controller:

    def __init__(
        self,
        state: SystemState,
        bus: AsyncEventBus,
        preset_svc: 'PresetService',
        session_svc: 'SessionService',
        camera_port: 'CameraPort',
        comments_home_svc=None,
    ) -> None:
        self._state        = state
        self._bus          = bus
        self._camera_port  = camera_port
        self._presets      = preset_svc
        self._session      = session_svc
        if comments_home_svc is None:
            from application.comments_home import CommentsHomeService
            comments_home_svc = CommentsHomeService()
        self._comments_home = comments_home_svc
        # Camera-confirmed slots survive a disk failure, but are not durable
        # until a later retry persists them. Track stable slots, not mutable names.
        self._pending_preset_persistence: set[int] = set()
        fence = getattr(camera_port, "_motion_admission", None)
        self._motion = fence if isinstance(fence, MotionAdmission) else MotionAdmission(lambda cid: cid)
        self._bus.register_motion_safety(
            self._prepare_motion, self._emergency_stop, self._cancel_emergency_stop
        )
        self._register()

    def _register(self) -> None:
        self._bus.subscribe(EventType.SEAT_SELECTED,         self._on_seat_selected)
        self._bus.subscribe(EventType.CAMERA_MOVE,           self._on_camera_move)
        self._bus.subscribe(EventType.CAMERA_ZOOM,           self._on_camera_zoom)
        self._bus.subscribe(EventType.CAMERA_HOME,           self._on_camera_home)
        self._bus.subscribe(EventType.CHAIRMAN_ASSIGNED,     self._on_chairman_assigned)
        self._bus.subscribe(EventType.PRESET_SAVE_REQUESTED, self._on_preset_save_requested)
        self._bus.subscribe(EventType.PRESET_SAVE_SLOT,      self._on_preset_save_slot)
        self._bus.subscribe(EventType.COMMENTS_HOME_SAVE,    self._on_comments_home_save)
        self._bus.subscribe(EventType.SESSION_START,         self._on_session_start)
        self._bus.subscribe(EventType.SESSION_END,           self._on_session_end)

    # ─────────────────────────────────────────────────────────────────────
    #  Helpers
    # ─────────────────────────────────────────────────────────────────────

    _MOTION_EVENTS = frozenset({
        EventType.SEAT_SELECTED, EventType.CAMERA_MOVE, EventType.CAMERA_ZOOM,
        EventType.CAMERA_HOME, EventType.CHAIRMAN_ASSIGNED,
    })

    def _prepare_motion(self, event):
        if event.type not in self._MOTION_EVENTS and event.type is not EventType.CAMERA_STOP:
            return None
        cam = (1 if event.type is EventType.CHAIRMAN_ASSIGNED else
               event.payload.get("camera", self._state.active_camera))
        event.payload = dict(event.payload, camera=cam)
        camera_id = self._cam_id(cam)
        ticket = (self._motion.retire(camera_id) if event.type is EventType.CAMERA_STOP
                  else self._motion.capture(camera_id))
        event._motion_ticket = ticket
        return cam  # Two logical slots bound the pending emergency lane.

    def _cancel_emergency_stop(self, event):
        self._motion.cancel(event._motion_ticket)

    def _emergency_stop(self, event):
        ticket = event._motion_ticket
        try:
            with self._motion.intent(ticket):
                self._on_camera_stop(event)
        finally:
            ticket.ready.set()  # Failure must not strand future admissions.

    def _commit_motion(self, event, update):
        return self._motion.commit(event._motion_ticket, update)

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
            self._bus.emit(EventType.CAMERA_ZOOM_INVALIDATED, camera=cam)

    # ─────────────────────────────────────────────────────────────────────
    #  Handlers
    # ─────────────────────────────────────────────────────────────────────

    @_motion_handler
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
            def update():
                self._state.camera(cam).active_preset = preset
            if self._commit_motion(event, update):
                self._invalidate_zoom(cam)

    @_motion_handler
    def _on_camera_move(self, event: Event) -> None:
        if self._no_session("camera_move", event.payload):
            return
        cam  = event.payload["camera"]
        pan  = event.payload["pan_speed"]
        tilt = event.payload["tilt_speed"]
        result = self._camera_port.move(self._cam_id(cam), pan, tilt)
        if not self._result_ok(result):
            return
        def update():
            cam_state = self._state.camera(cam)
            cam_state.pan_speed = pan
            cam_state.tilt_speed = tilt
        self._commit_motion(event, update)

    def _on_camera_stop(self, event: Event) -> None:
        # stop_move is always safe to send — it should work even without a session
        # (e.g., stop a runaway move after session ends).  No session guard here.
        if not hasattr(event, '_motion_ticket'):
            self._prepare_motion(event)
        cam = event.payload["camera"]
        def update():
            # Clear every logical view of the stopped physical endpoint.
            endpoint = event._motion_ticket.endpoint
            for logical in (1, 2):
                try:
                    matches = self._motion.endpoint(self._cam_id(logical)) == endpoint
                except ValueError:
                    matches = False
                if matches:
                    cam_state = self._state.camera(logical)
                    cam_state.pan_speed = 0
                    cam_state.tilt_speed = 0
        self._commit_motion(event, update)
        self._camera_port.stop_move(self._cam_id(cam))

    @_motion_handler
    def _on_camera_zoom(self, event: Event) -> None:
        if self._no_session("camera_zoom", event.payload):
            return
        cam   = event.payload["camera"]
        speed = event.payload["speed"]
        self._camera_port.zoom(self._cam_id(cam), speed)

    @_motion_handler
    def _on_camera_home(self, event: Event) -> None:
        if self._no_session("camera_home", event.payload):
            return
        cam = event.payload["camera"]
        # Cam2 con posición personalizada guardada → recall del slot dedicado;
        # si nunca se guardó (o el archivo falta), home mecánico como siempre.
        slot = self._comments_home.saved_slot() if cam == 2 else None
        if slot is not None:
            result = self._camera_port.recall_preset(self._cam_id(cam), slot)
        else:
            result = self._camera_port.home(self._cam_id(cam))
        # Home admission is not completion. Re-read observed zoom without
        # assuming a target value or changing the queued motion semantics.
        if self._result_ok(result) and self._commit_motion(event, lambda: None):
            self._invalidate_zoom(cam)

    @_motion_handler
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
            def update():
                self._state.camera(cam).active_preset = preset
            if self._commit_motion(event, update):
                self._invalidate_zoom(cam)
        else:
            logger.warning("chairman_assigned: fallo al hacer recall preset %r", preset)

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
                self._pending_preset_persistence.add(slot)
            if slot in self._pending_preset_persistence:
                persisted = self._presets.persist()
                if not persisted:
                    logger.error(
                        "preset_save: fallo al persistir preset para '%s' slot=%d — "
                        "PRESET_SAVED no emitido", name, slot,
                    )
                    return
                self._pending_preset_persistence.discard(slot)
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

    def _on_comments_home_save(self, event: Event) -> None:
        """Pulsación larga (5 s) en Comments → Home: guarda el encuadre actual.

        Solo Cam2 tiene home editable. Tras un save_preset confirmado se
        persiste el slot para que CAMERA_HOME lo invoque a partir de entonces.
        """
        if self._no_session("comments_home_save", event.payload):
            return
        cam: int = event.payload.get("camera", 2)
        if cam != 2:
            logger.warning("comments_home_save: solo Cam2 tiene home editable (cam=%r)", cam)
            return
        from domain.preset import PRESET_COMMENTS_HOME
        result = self._camera_port.save_preset(self._cam_id(cam), PRESET_COMMENTS_HOME)
        if self._result_ok(result):
            if self._comments_home.set_slot(PRESET_COMMENTS_HOME):
                logger.info("Comments home personalizado guardado en Cam%d slot %d",
                            cam, PRESET_COMMENTS_HOME)
        else:
            logger.error("comments_home_save: fallo VISCA cam%d slot=%d",
                         cam, PRESET_COMMENTS_HOME)

    def _on_session_start(self, event: Event) -> None:
        self._session.start()

    def _on_session_end(self, event: Event) -> None:
        reason = event.payload.get("reason", "manual")
        if event.payload.get("power_off", True):
            self._session.end(reason=reason)
        else:
            self._session.end(reason=reason, power_off=False)
