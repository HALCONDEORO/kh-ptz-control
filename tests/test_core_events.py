#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_core_events.py - Tests del bus asincrono de eventos.

Estos tests cubren la logica pura de core.events: suscripcion, publicacion,
orden de despacho, baja de handlers y ciclo de vida del worker.
"""

import logging
import threading

import pytest

from core.events import AsyncEventBus, Event, EventType


def _drain(bus: AsyncEventBus, timeout: float = 1.0) -> None:
    """Espera a que el worker procese los eventos sin poder colgar el test."""
    done = threading.Event()
    waiter = threading.Thread(target=lambda: (bus._queue.join(), done.set()), daemon=True)
    waiter.start()
    if not done.wait(timeout):
        pytest.fail("AsyncEventBus no dreno la cola de eventos a tiempo")


class TestEvent:

    def test_event_stores_type_and_payload(self):
        event = Event(EventType.CAMERA_MOVE, {"camera": 1, "pan_speed": 5})

        assert event.type is EventType.CAMERA_MOVE
        assert event.payload == {"camera": 1, "pan_speed": 5}


class TestAsyncEventBusLifecycle:

    def test_stop_before_start_is_safe(self):
        bus = AsyncEventBus()

        bus.stop()

        assert bus._worker is None

    def test_start_is_idempotent_while_worker_is_alive(self):
        bus = AsyncEventBus()
        try:
            bus.start()
            first_worker = bus._worker

            bus.start()

            assert bus._worker is first_worker
            assert first_worker is not None
            assert first_worker.is_alive()
        finally:
            bus.stop()

    def test_emit_before_start_is_processed_after_start(self):
        bus = AsyncEventBus()
        seen = []

        bus.subscribe(EventType.SESSION_START, lambda event: seen.append(event.type))
        bus.emit(EventType.SESSION_START)

        try:
            bus.start()
            _drain(bus)
        finally:
            bus.stop()

        assert seen == [EventType.SESSION_START]


class TestAsyncEventBusDispatch:

    def test_dispatches_payload_to_subscriber(self):
        bus = AsyncEventBus()
        seen = []

        bus.subscribe(EventType.SEAT_SELECTED, lambda event: seen.append(event.payload))
        try:
            bus.start()
            bus.emit(EventType.SEAT_SELECTED, camera=2, seat_number=7, name="PersonA")
            _drain(bus)
        finally:
            bus.stop()

        assert seen == [{"camera": 2, "seat_number": 7, "name": "PersonA"}]

    def test_dispatch_order_is_fifo(self):
        bus = AsyncEventBus()
        seen = []

        bus.subscribe(EventType.CAMERA_ZOOM, lambda event: seen.append(event.payload["speed"]))
        try:
            bus.start()
            for speed in [1, 3, -2, 0]:
                bus.emit(EventType.CAMERA_ZOOM, camera=1, speed=speed)
            _drain(bus)
        finally:
            bus.stop()

        assert seen == [1, 3, -2, 0]

    def test_only_matching_event_type_handlers_run(self):
        bus = AsyncEventBus()
        seen = []

        bus.subscribe(EventType.CAMERA_MOVE, lambda event: seen.append("move"))
        bus.subscribe(EventType.CAMERA_STOP, lambda event: seen.append("stop"))
        try:
            bus.start()
            bus.emit(EventType.CAMERA_STOP, camera=1)
            _drain(bus)
        finally:
            bus.stop()

        assert seen == ["stop"]

    def test_multiple_subscribers_run_in_subscription_order(self):
        bus = AsyncEventBus()
        seen = []

        bus.subscribe(EventType.SESSION_END, lambda event: seen.append("first"))
        bus.subscribe(EventType.SESSION_END, lambda event: seen.append("second"))
        try:
            bus.start()
            bus.emit(EventType.SESSION_END)
            _drain(bus)
        finally:
            bus.stop()

        assert seen == ["first", "second"]

    def test_handler_exception_is_logged_and_does_not_stop_later_handlers(self, caplog):
        bus = AsyncEventBus()
        seen = []

        def broken(_event):
            raise RuntimeError("boom")

        bus.subscribe(EventType.PRESET_SAVED, broken)
        bus.subscribe(EventType.PRESET_SAVED, lambda event: seen.append(event.payload["slot"]))

        try:
            bus.start()
            with caplog.at_level(logging.ERROR, logger="core.events"):
                bus.emit(EventType.PRESET_SAVED, camera=1, name="PersonA", slot=10)
                _drain(bus)
        finally:
            bus.stop()

        assert seen == [10]
        records = [record for record in caplog.records if record.exc_info]
        assert records
        assert records[0].exc_info[0] is RuntimeError
        assert "PRESET_SAVED" in records[0].getMessage()


class TestAsyncEventBusUnsubscribe:

    def test_unsubscribe_removes_handler(self):
        bus = AsyncEventBus()
        seen = []

        def handler(event):
            seen.append(event.payload["camera"])

        bus.subscribe(EventType.CONNECTION_CHANGED, handler)
        bus.unsubscribe(EventType.CONNECTION_CHANGED, handler)

        try:
            bus.start()
            bus.emit(EventType.CONNECTION_CHANGED, camera=1, connected=True)
            _drain(bus)
        finally:
            bus.stop()

        assert seen == []

    def test_unsubscribe_unknown_handler_is_noop(self):
        bus = AsyncEventBus()
        seen = []

        def handler(event):
            seen.append(event.payload["camera"])

        def other(_event):
            pass

        bus.subscribe(EventType.CAMERA_STOP, handler)
        bus.unsubscribe(EventType.CAMERA_STOP, other)

        try:
            bus.start()
            bus.emit(EventType.CAMERA_STOP, camera=2)
            _drain(bus)
        finally:
            bus.stop()

        assert seen == [2]

    def test_unsubscribe_one_of_multiple_keeps_the_rest(self):
        bus = AsyncEventBus()
        seen = []

        def first(_event):
            seen.append("first")

        def second(_event):
            seen.append("second")

        bus.subscribe(EventType.SESSION_START, first)
        bus.subscribe(EventType.SESSION_START, second)
        bus.unsubscribe(EventType.SESSION_START, first)

        try:
            bus.start()
            bus.emit(EventType.SESSION_START)
            _drain(bus)
        finally:
            bus.stop()

        assert seen == ["second"]
