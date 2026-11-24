#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# core/events.py — Bus de eventos y tipos de evento
#
# Sin Qt en tiempo de importación. Sin I/O. La única dependencia de Qt
# está en _QtDispatchProxy, cargada de forma perezosa mediante subscribe_qt(),
# para mantener el núcleo desacoplado de la interfaz gráfica.

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventType(Enum):
    # ── Entrada de asientos ──────────────────────────────────
    SEAT_SELECTED        = auto()   # payload: name, camera, preset, seat_id
                                            # seat_number kept for backward compat

    # ── Movimiento de cámara ─────────────────────────────────
    CAMERA_MOVE          = auto()   # payload: camera, pan_speed, tilt_speed
    CAMERA_STOP          = auto()   # payload: camera
    CAMERA_ZOOM          = auto()   # payload: camera, speed

    # ── Presets ──────────────────────────────────────────────
    CHAIRMAN_ASSIGNED     = auto()   # payload: name
    PRESET_SAVE_REQUESTED = auto()   # payload: camera, name  (name-based slot assignment)
    PRESET_SAVE_SLOT      = auto()   # payload: camera, slot  (direct slot save, known slot)
    PRESET_SAVED          = auto()   # payload: camera, name, slot

    # ── Movimiento especial ───────────────────────────────────
    CAMERA_HOME           = auto()   # payload: camera  (PTZ mechanical home, or saved Comments home on Cam2)
    COMMENTS_HOME_SAVE    = auto()   # payload: camera  (save current position as editable Comments home)

    # ── Sesión ───────────────────────────────────────────────
    SESSION_START        = auto()
    SESSION_END          = auto()

    # ── Conexión ─────────────────────────────────────────────
    CONNECTION_CHANGED   = auto()   # payload: camera, connected
    CAMERA_ZOOM_INVALIDATED = auto()  # payload: camera; confirmed preset changed zoom


@dataclass
class Event:
    type: EventType
    payload: Dict[str, Any]
    _preset_superseded: bool = False


class _QtDispatchProxy:
    """
    Reenvía llamadas al handler al hilo principal de Qt mediante una señal
    con QueuedConnection. El QObject se crea en el hilo principal (subscribe_qt
    siempre se llama desde constructores de widgets), por lo que Qt enruta
    automáticamente la señal al hilo correcto sin importar desde qué hilo
    se llame a dispatch().
    """

    def __init__(self, handler: Callable[[Event], None]) -> None:
        from PyQt5.QtCore import QObject, pyqtSignal, Qt  # importación perezosa

        class _Emitter(QObject):
            fired = pyqtSignal(object)

        self._emitter = _Emitter()
        self._emitter.fired.connect(handler, Qt.QueuedConnection)

    def dispatch(self, event: Event) -> None:
        self._emitter.fired.emit(event)


class AsyncEventBus:
    """
    Bus de eventos asíncrono y thread-safe.

    emit() encola el evento y retorna inmediatamente; no bloquea la UI.
    Un único hilo worker daemon desencola y despacha los handlers en orden.

    Ciclo de vida:
        bus = AsyncEventBus()
        bus.start()   # lanza el hilo worker
        ...
        bus.stop()    # envía centinela, drena la cola y une el hilo

    Para handlers que accedan a widgets Qt usar subscribe_qt(); el proxy
    entrega la llamada en el hilo principal mediante QueuedConnection.
    """

    def __init__(self) -> None:
        self._queue: queue.Queue[Optional[Event]] = queue.Queue()
        self._subscribers: Dict[EventType, List[Callable[[Event], None]]] = {}
        self._lock = threading.RLock()
        self._worker: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()
        self._stop_requested = False
        # Only not-yet-dispatched recalls may be replaced. Admission and worker
        # claim share the lifecycle lock; in-flight handlers are never retired.
        self._pending_presets: Dict[Any, Event] = {}
        # One explicit queue-only STOP subscriber; ordinary handlers stay serial.
        self._safety_prepare = None
        self._safety_stop = None
        self._safety_cancel = None
        self._emergency_active = None
        self._emergency = {}
        self._emergency_condition = threading.Condition()
        self._emergency_stopping = False
        self._emergency_worker = None

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    def start(self) -> None:
        with self._lifecycle_lock:
            if any(w is not None and w.is_alive() for w in
                   (self._worker, self._emergency_worker)):
                return  # Includes a worker still finishing a timed-out stop.
            self._stop_requested = False
            with self._emergency_condition:
                self._emergency_stopping = False
            self._emergency_worker = threading.Thread(
                target=self._run_emergency, name="AsyncEventBus-STOP", daemon=True,
            )
            self._emergency_worker.start()
            self._worker = threading.Thread(
                target=self._run,
                name="AsyncEventBus-worker",
                daemon=True,
            )
            self._worker.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            worker = self._worker
            if worker is None:
                with self._emergency_condition:
                    self._cancel_emergency_barriers()
                return
            if not self._stop_requested:
                self._queue.put(None)
                self._stop_requested = True
                with self._emergency_condition:
                    self._emergency_stopping = True
                    self._emergency_condition.notify_all()
        # A handler may request stop itself. Let it return and consume the
        # sentinel rather than trying to join its own thread.
        if worker is threading.current_thread():
            return
        worker.join(timeout=2.0)
        emergency = self._emergency_worker
        if emergency is not None and emergency is not threading.current_thread():
            emergency.join(timeout=2.0)
        with self._emergency_condition:
            self._cancel_emergency_barriers()
        with self._lifecycle_lock:
            if self._worker is worker and not worker.is_alive():
                self._worker = None

    # ── Suscripción ──────────────────────────────────────────────────────────

    def subscribe(self, event_type: EventType,
                  handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

    def subscribe_qt(self, event_type: EventType,
                     handler: Callable[[Event], None]) -> None:
        """Registra un handler que se ejecutará en el hilo principal de Qt."""
        proxy = _QtDispatchProxy(handler)

        def _despachar(event: Event) -> None:
            proxy.dispatch(event)

        _despachar._original = handler  # type: ignore[attr-defined]
        self.subscribe(event_type, _despachar)

    def unsubscribe(self, event_type: EventType,
                    handler: Callable[[Event], None]) -> None:
        with self._lock:
            handlers = self._subscribers.get(event_type, [])
            to_remove = [
                h for h in handlers
                if h is handler or getattr(h, '_original', None) is handler
            ]
            for h in to_remove:
                handlers.remove(h)

    # ── Publicación ──────────────────────────────────────────────────────────

    def emit(self, event_type: EventType, **payload: Any) -> None:
        event = Event(type=event_type, payload=payload)
        # Serialize admission with the shutdown sentinel. Preserve first-start
        # buffering, but never carry post-stop commands into a later run.
        # Preparation only captures/retires epochs. No port calls or user handlers.
        with self._lifecycle_lock, self._emergency_condition:
            if self._safety_prepare is not None:
                key = self._safety_prepare(event)
                if event_type is EventType.CAMERA_STOP:
                    if self._worker is None or self._stop_requested:
                        if self._safety_cancel is not None:
                            self._safety_cancel(event)
                        return
                    self._emergency[key] = event
                    self._emergency_condition.notify()
                    return
            if self._stop_requested:
                logger.debug("Discarding event after stop: %s", event_type)
                return
            if event_type in (EventType.SESSION_START, EventType.SESSION_END):
                # Do not merge intents across an explicit session boundary.
                self._pending_presets.clear()
            if event_type is EventType.SEAT_SELECTED:
                # Controller preparation resolves the active camera at emit time.
                camera = event.payload.get("camera")
                previous = self._pending_presets.get(camera)
                if previous is not None:
                    previous._preset_superseded = True
                self._pending_presets[camera] = event
            self._queue.put(event)

    def register_motion_safety(self, prepare, stop_handler, cancel_handler=None) -> None:
        """Register the controller's sole STOP lane before starting the bus.

        prepare must be bounded, memory-only; stop_handler must only admit STOP.
        This is deliberately not a general parallel subscription API.
        """
        with self._lifecycle_lock:
            if self._safety_prepare is not None or self._worker is not None:
                raise RuntimeError("motion safety must be registered once before start")
            self._safety_prepare = prepare
            self._safety_stop = stop_handler
            self._safety_cancel = cancel_handler

    def _cancel_emergency_barriers(self):
        # Called under the emergency condition. Never mark cancellation as STOP
        # success: the endpoint stays closed until a new live STOP is admitted.
        if self._safety_cancel is not None:
            events = list(self._emergency.values())
            if self._emergency_active is not None:
                events.append(self._emergency_active)
            for event in events:
                self._safety_cancel(event)

    def _run_emergency(self) -> None:
        while True:
            with self._emergency_condition:
                self._emergency_condition.wait_for(
                    lambda: self._emergency or self._emergency_stopping
                )
                if not self._emergency:
                    return
                key = next(iter(self._emergency))
                event = self._emergency.pop(key)
                self._emergency_active = event
            try:
                self._safety_stop(event)
            except Exception:
                logger.exception("Emergency STOP admission failed")
            finally:
                with self._emergency_condition:
                    self._emergency_active = None
            # Serialize observer admission with the shutdown sentinel. A late
            # STOP callback must not leave a notification for the next run.
            with self._lifecycle_lock:
                if not self._stop_requested:
                    self._queue.put(event)

    # ── Worker interno ───────────────────────────────────────────────────────

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            try:
                if event is None:  # centinela de parada
                    break
                with self._lifecycle_lock:
                    if event.type is EventType.SEAT_SELECTED:
                        if event._preset_superseded:
                            continue
                        camera = event.payload.get("camera")
                        if self._pending_presets.get(camera) is event:
                            del self._pending_presets[camera]
                with self._lock:
                    handlers = list(self._subscribers.get(event.type, []))
                for handler in handlers:
                    try:
                        handler(event)
                    except Exception:
                        logger.exception(
                            "Excepción en handler %r para %s",
                            handler, event.type,
                        )
            finally:
                self._queue.task_done()
