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
    CAMERA_HOME           = auto()   # payload: camera  (PTZ mechanical home)

    # ── Sesión ───────────────────────────────────────────────
    SESSION_START        = auto()
    SESSION_END          = auto()

    # ── Conexión ─────────────────────────────────────────────
    CONNECTION_CHANGED   = auto()   # payload: camera, connected


@dataclass
class Event:
    type: EventType
    payload: Dict[str, Any]


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

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return  # idempotente: no arranca un segundo worker
        self._worker = threading.Thread(
            target=self._run,
            name="AsyncEventBus-worker",
            daemon=True,
        )
        self._worker.start()

    def stop(self) -> None:
        if self._worker is None:
            return
        self._queue.put(None)  # centinela: ordena al worker que termine
        self._worker.join(timeout=2.0)
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
        self._queue.put(Event(type=event_type, payload=payload))

    # ── Worker interno ───────────────────────────────────────────────────────

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            try:
                if event is None:  # centinela de parada
                    break
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
