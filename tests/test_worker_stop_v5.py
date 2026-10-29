#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_worker_stop_v5.py — Fiabilidad del STOP y comandos confirmados (v5)
#
# Conversión de los fixtures independientes del servidor (probes de revisión):
#   1. Un STOP no gasta el presupuesto largo de reconexión (backoffs 5/15/30).
#   2. Un MOVE obsoleto no se envía si llegó un STOP durante la conexión.
#   3. Las dos mitades del STOP (PT y zoom) salen aunque se interrumpan.
#   4. Un STOP interrumpido durante la lectura se reencola, no se pierde.
#   5. Un comando confirmado usa la sesión del worker (una sola TCP).
#   6. Un confirmado con respuesta VISCA Error devuelve False.
#   7. Un confirmado sin respuesta agota su timeout y devuelve False.

from __future__ import annotations

import socket
import threading
import time
import unittest
from unittest.mock import MagicMock

from tests.test_camera_worker import _OKWorker
from ptz.visca.worker import CameraWorker, ViscaCommand

PT_STOP = bytes.fromhex("8101060100000303ff")
ZOOM_STOP = bytes.fromhex("8101040700ff")
MOVE = bytes.fromhex("8101060101010201ff")


class _ManualWorker(CameraWorker):
    """Worker real (connect/read) con init manual y señales falsas: sin Qt."""
    def __init__(self, ip="127.0.0.1", port=5678):
        import queue as _q
        self.ip = ip
        self.port = port
        self._is_connected = False
        self._queue = _q.Queue(maxsize=20)
        self._sock = None
        self._lock = threading.Lock()
        self._interrupt = threading.Event()
        self._shutdown = threading.Event()
        self._last_heartbeat = time.monotonic()
        self.signals = MagicMock()

    def _ping(self):
        pass


class TestStopRetryBudget(unittest.TestCase):
    def test_stop_uses_immediate_retries_not_long_backoff(self):
        w = _OKWorker()
        attempts, waits = [], []
        w._connect = lambda: attempts.append(1) and None
        w._wait_interruptible = lambda n: (waits.append(n), False)[1]
        w._queue.put(ViscaCommand(1, PT_STOP, priority=True))
        w._queue.put(None)
        w._run()
        self.assertEqual(len(attempts), 3, "STOP: 3 intentos inmediatos")
        self.assertTrue(all(x < 1 for x in waits), f"STOP sin backoffs largos: {waits}")


class TestStaleMoveNotSent(unittest.TestCase):
    def test_move_dropped_when_stop_arrives_during_connect(self):
        w = _OKWorker()
        entered, release = threading.Event(), threading.Event()
        sent = []
        sock = MagicMock()
        sock.sendall.side_effect = lambda payload: sent.append(bytes(payload))

        def connect():
            entered.set()
            release.wait(2)
            return sock

        w._connect = connect
        w._queue.put(ViscaCommand(1, MOVE))
        w._thread = threading.Thread(target=w._run, daemon=True)
        w._thread.start()
        self.assertTrue(entered.wait(1))
        w.send_priority(ViscaCommand(1, PT_STOP))
        release.set()
        end = time.monotonic() + 2
        while time.monotonic() < end and not sent:
            time.sleep(0.005)
        w.stop()
        self.assertNotIn(MOVE, sent, "el MOVE obsoleto NO debe salir tras pedir STOP")
        self.assertIn(PT_STOP, sent)


class TestStopHalvesSurviveInterrupt(unittest.TestCase):
    def test_pt_and_zoom_stop_both_sent_when_interrupted_mid_reconnect(self):
        w = _OKWorker()
        entered, release = threading.Event(), threading.Event()
        sent, calls = [], []
        sock = MagicMock()
        sock.sendall.side_effect = lambda payload: sent.append(bytes(payload))

        def connect():
            calls.append(1)
            if len(calls) == 1:
                entered.set()
                release.wait(2)
                return None  # 1er intento (PT STOP) falla tras ser interrumpido
            return sock

        w._connect = connect
        w.send_priority(ViscaCommand(1, PT_STOP))
        w._thread = threading.Thread(target=w._run, daemon=True)
        w._thread.start()
        self.assertTrue(entered.wait(1))
        w.send_priority(ViscaCommand(1, ZOOM_STOP))
        release.set()
        end = time.monotonic() + 3
        while time.monotonic() < end and len(sent) < 2:
            time.sleep(0.005)
        w.stop()
        self.assertIn(PT_STOP, sent, "la mitad PT del STOP no debe perderse")
        self.assertIn(ZOOM_STOP, sent, "la mitad zoom del STOP debe salir")

    def test_stop_interrupted_during_read_is_requeued(self):
        w = _OKWorker()
        sent = []
        sock = MagicMock()
        sock.sendall.side_effect = lambda payload: sent.append(bytes(payload))
        w._connect = lambda: sock
        reading, release = threading.Event(), threading.Event()

        def read(_sock):
            reading.set()
            release.wait(2)
            return b""

        w._read_visca_response = read
        w.send_priority(ViscaCommand(1, PT_STOP))
        w._thread = threading.Thread(target=w._run, daemon=True)
        w._thread.start()
        self.assertTrue(reading.wait(1))
        w.send_priority(ViscaCommand(1, ZOOM_STOP))  # interrumpe la lectura del PT STOP
        release.set()
        end = time.monotonic() + 3
        while time.monotonic() < end and not (PT_STOP in sent and ZOOM_STOP in sent):
            time.sleep(0.005)
        w.stop()
        self.assertIn(PT_STOP, sent)
        self.assertIn(ZOOM_STOP, sent)


class TestConfirmedViaWorker(unittest.TestCase):
    def test_confirmed_command_uses_single_worker_session(self):
        """Fixture TCP loopback del servidor: MOVE + power_on = 1 sola sesión."""
        from adapters.visca_camera_adapter import ViscaCameraAdapter

        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen()
        port = srv.getsockname()[1]
        accepted, frames = [], []

        def session(conn, n):
            conn.settimeout(3)
            try:
                while True:
                    data = conn.recv(64)
                    if not data:
                        return
                    frames.append((n, bytes(data).hex()))
                    conn.sendall(bytes.fromhex("9050ff"))  # Completion
            except OSError:
                pass
            finally:
                conn.close()

        def accept():
            while True:
                try:
                    c, _ = srv.accept()
                except OSError:
                    return
                accepted.append(1)
                threading.Thread(target=session, args=(c, len(accepted)), daemon=True).start()

        threading.Thread(target=accept, daemon=True).start()
        w = _ManualWorker("127.0.0.1", port)
        w._thread = threading.Thread(target=w._run, daemon=True)
        w._thread.start()

        class M:
            def worker(self, ip):
                return w

        adapter = ViscaCameraAdapter(M(), cam_configs={1: ("127.0.0.1", "81")})
        w.send(ViscaCommand(1, MOVE))
        end = time.monotonic() + 3
        while time.monotonic() < end and not frames:
            time.sleep(0.005)
        self.assertTrue(frames, "el MOVE debe llegar por la sesión del worker")

        self.assertTrue(adapter.power_on("cam1"), "power_on confirmado por el worker")
        w.stop()
        srv.close()

        self.assertEqual(len(accepted), 1, "una sola sesión TCP: la del worker")
        sessions = {n for n, _ in frames}
        self.assertEqual(sessions, {1})
        self.assertIn((1, MOVE.hex()), frames)
        self.assertIn((1, "8101040002ff"), frames)

    def test_send_confirmed_false_on_visca_error(self):
        w = _OKWorker()
        w._read_visca_response = lambda sock: bytes([0x90, 0x60, 0x02, 0xFF])  # Error
        w._thread = threading.Thread(target=w._run, daemon=True)
        w._thread.start()
        try:
            self.assertFalse(w.send_confirmed(ViscaCommand(1, MOVE), timeout=5))
        finally:
            w.stop()

    def test_send_confirmed_timeout_without_response(self):
        w = _OKWorker()

        def slow_read(_sock):
            time.sleep(1.0)
            return b""

        w._read_visca_response = slow_read
        w._thread = threading.Thread(target=w._run, daemon=True)
        w._thread.start()
        try:
            t0 = time.monotonic()
            self.assertFalse(w.send_confirmed(ViscaCommand(1, MOVE), timeout=0.3))
            self.assertLess(time.monotonic() - t0, 1.0)
        finally:
            w.stop()


class TestInterruptedPickupFailsConfirmed(unittest.TestCase):
    def test_interrupted_pickup_fails_confirmed_caller(self):
        """Fixture de Auditoría: confirmado ya extraído de la cola cuando el
        STOP activa _interrupt — el drain ya no lo ve; recibe fallo inmediato."""
        w = _OKWorker()
        done = threading.Event()
        box = {}
        cmd = ViscaCommand(1, bytes.fromhex("81043f0201ff"))
        cmd.on_failure = lambda: (box.__setitem__("ok", False), done.set())
        w._queue.put(cmd)
        w._interrupt.set()  # STOP llega antes de que el worker despache
        w._queue.put(None)
        t = threading.Thread(target=w._run, daemon=True)
        t.start()
        self.assertTrue(done.wait(1), "el confirmado descartado en pickup falla YA")
        self.assertEqual(box.get("ok"), False)
        t.join(2)


if __name__ == "__main__":
    unittest.main()


# ── v6: cancelación/deadline de confirmados y fallo inmediato en drain ────────

class TestConfirmedCancellation(unittest.TestCase):
    def test_timed_out_confirmed_is_never_executed(self):
        """Fixture del servidor: timeout con el worker sin arrancar; el comando
        cancelado NO debe salir cuando el worker arranca después."""
        w = _OKWorker()
        sent = []
        sock = MagicMock()
        sock.sendall.side_effect = lambda p: sent.append(bytes(p).hex())
        w._connect = lambda: sock
        cmd = ViscaCommand(1, bytes.fromhex("81043f0201ff"))  # preset recall
        result = w.send_confirmed(cmd, 0.02)
        self.assertFalse(result)
        w._queue.put(None)
        w._run()
        self.assertNotIn(cmd.payload.hex(), sent, "un confirmado vencido nunca se ejecuta")

    def test_stop_drain_fails_confirmed_immediately(self):
        """Un STOP que drena un confirmado pendiente lo completa YA con fallo,
        no tras el timeout entero."""
        w = _OKWorker()
        result, done = [], threading.Event()
        cmd = ViscaCommand(1, bytes.fromhex("81043f0201ff"))

        def call():
            result.append(w.send_confirmed(cmd, 5.0))
            done.set()

        t = threading.Thread(target=call)
        t.start()
        end = time.monotonic() + 1
        while time.monotonic() < end and w._queue.empty():
            time.sleep(0.001)
        t0 = time.monotonic()
        w.send_priority(ViscaCommand(1, PT_STOP))
        self.assertTrue(done.wait(1), "el confirmado drenado debe completar de inmediato")
        self.assertLess(time.monotonic() - t0, 1.0)
        t.join(2)
        self.assertEqual(result, [False])

    def test_expired_queued_command_fails_without_sending(self):
        """Un comando que vence esperando en cola falla hacia su llamante y
        nunca se envía."""
        w = _OKWorker()
        sent, failed = [], threading.Event()
        sock = MagicMock()
        sock.sendall.side_effect = lambda p: sent.append(bytes(p).hex())
        w._connect = lambda: sock
        cmd = ViscaCommand(1, MOVE)
        cmd.expires_at = time.monotonic() - 1  # ya vencido
        cmd.on_failure = failed.set
        w._queue.put(cmd)
        w._queue.put(None)
        w._run()
        self.assertTrue(failed.is_set(), "el llamante del vencido recibe fallo")
        self.assertEqual(sent, [])