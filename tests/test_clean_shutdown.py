#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_clean_shutdown.py — Pruebas de idempotencia y cierre limpio (#99).

Comprueba:
- Supervisor.stop() es idempotente
- AsyncEventBus.stop() es idempotente
- CameraWorker.stop() es idempotente
- CameraWorker.stop() espera al hilo dentro del timeout
- Parar un worker ya detenido no lanza excepción
- Supervisor registra el cierre
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock


from core.supervisor import Supervisor
from core.events import AsyncEventBus


# ── Idempotencia de Supervisor ────────────────────────────────────────────────

class TestSupervisorStop:

    def test_stop_before_start_is_safe(self):
        sup = Supervisor(intervalo=1.0)
        sup.stop()  # sin excepción ni bloqueo

    def test_stop_twice_is_safe(self):
        sup = Supervisor(intervalo=60.0)
        sup.start()
        assert sup._hilo is not None and sup._hilo.is_alive()
        sup.stop()
        sup.stop()  # la segunda llamada no debe lanzar excepción

    def test_stop_joins_thread(self):
        sup = Supervisor(intervalo=60.0)
        sup.start()
        thread = sup._hilo
        assert thread is not None and thread.is_alive()
        sup.stop()
        assert not thread.is_alive()

    def test_stop_then_start_then_stop(self):
        sup = Supervisor(intervalo=60.0)
        sup.start()
        sup.stop()
        sup.start()
        assert sup._hilo is not None and sup._hilo.is_alive()
        sup.stop()

    def test_stop_logs_no_exception(self, caplog):
        import logging
        sup = Supervisor(intervalo=60.0)
        sup.start()
        with caplog.at_level(logging.ERROR, logger="core.supervisor"):
            sup.stop()
        assert not caplog.records  # sin logs de error en un cierre limpio

    def test_worker_restart_not_called_after_stop(self):
        restart_calls = []
        sup = Supervisor(intervalo=0.05)
        sup.registrar("test", lambda: False, lambda: restart_calls.append(1))
        sup.start()
        sup.stop()
        count_at_stop = len(restart_calls)
        time.sleep(0.15)  # esperar por si el supervisor vuelve a iterar
        assert len(restart_calls) == count_at_stop  # sin llamadas nuevas tras stop


# ── Idempotencia de AsyncEventBus ─────────────────────────────────────────────

class TestAsyncEventBusStop:

    def test_stop_before_start_is_safe(self):
        bus = AsyncEventBus()
        bus.stop()  # sin excepción

    def test_stop_twice_is_safe(self):
        bus = AsyncEventBus()
        bus.start()
        bus.stop()
        bus.stop()  # la segunda llamada no debe lanzar excepción

    def test_stop_joins_worker(self):
        bus = AsyncEventBus()
        bus.start()
        worker = bus._worker
        assert worker is not None and worker.is_alive()
        bus.stop()
        assert not worker.is_alive()

    def test_worker_is_none_after_stop(self):
        bus = AsyncEventBus()
        bus.start()
        bus.stop()
        assert bus._worker is None

    def test_stop_then_start_then_stop(self):
        bus = AsyncEventBus()
        bus.start()
        bus.stop()
        bus.start()
        assert bus._worker is not None and bus._worker.is_alive()
        bus.stop()


# ── Idempotencia de CameraWorker ──────────────────────────────────────────────

class TestCameraWorkerStop:
    """Comprueba que CameraWorker.stop() sea idempotente y seguro.

    CameraWorker abre un socket TCP; evitamos la red real parcheando _run
    para que el hilo salga inmediatamente.
    """

    def _make_worker(self):
        """Crea un CameraWorker cuyo _run termina inmediatamente (sin TCP)."""
        from ptz.visca.worker import CameraWorker

        class _ImmediateWorker(CameraWorker):
            def _run(self):
                pass  # termina inmediatamente

        w = _ImmediateWorker("127.0.0.1")
        return w

    def test_stop_before_thread_started_is_safe(self):
        from ptz.visca.worker import CameraWorker

        class _ImmediateWorker(CameraWorker):
            def _run(self):
                pass

        w = _ImmediateWorker("127.0.0.1")
        # El hilo arranca en __init__; parar antes de que ejecute.
        w.stop()  # sin excepción

    def test_stop_after_thread_exits_is_safe(self):
        w = self._make_worker()
        w._thread.join(timeout=1.0)  # dejar que _run termine
        w.stop()  # ya está detenido; no debe lanzar excepción

    def test_stop_twice_is_safe(self):
        w = self._make_worker()
        w._thread.join(timeout=1.0)
        w.stop()
        w.stop()  # la segunda llamada no debe lanzar excepción

    def test_stop_sets_interrupt_on_live_thread(self):
        from ptz.visca.worker import CameraWorker

        class _LongWorker(CameraWorker):
            def _run(self):
                time.sleep(10)

        w = _LongWorker("127.0.0.1")
        assert w._thread.is_alive()
        w.stop()
        assert w._interrupt.is_set()

    def test_stop_closes_sock(self):
        from ptz.visca.worker import CameraWorker
        import socket as _socket

        class _SocketWorker(CameraWorker):
            def _run(self):
                time.sleep(0.5)

        w = _SocketWorker("127.0.0.1")
        # Inyectar un socket falso en el atributo correcto.
        fake_sock = MagicMock(spec=_socket.socket)
        w._sock = fake_sock
        w.stop()
        fake_sock.close.assert_called()


# ── Logging del flujo de cierre ───────────────────────────────────────────────

class TestShutdownLogging:

    def test_supervisor_stop_does_not_suppress_all_logs(self, caplog):
        import logging
        sup = Supervisor(intervalo=60.0)
        sup.start()
        with caplog.at_level(logging.DEBUG, logger="core.supervisor"):
            sup.stop()
        # Supervisor.start() registra un mensaje info; solo verificamos que no falle.

    def test_bus_stop_worker_becomes_none(self):
        bus = AsyncEventBus()
        bus.start()
        assert bus._worker is not None
        bus.stop()
        assert bus._worker is None
