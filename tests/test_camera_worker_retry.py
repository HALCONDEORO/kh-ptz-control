#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_camera_worker_retry.py — Robustez VISCA: reintentos con backoff,
# watchdog de respuestas y señal de vida del worker
#
# Escenarios:
#   1. Comando normal reintentado con backoff tras respuesta sin trama final
#      (y el watchdog de respuestas se resetea al completar).
#   2. Comando confirmado (fast_connect) NO se reintenta tras respuesta sin
#      trama final: su deadline manda.
#   3. Un STOP entrante aborta el backoff de un comando normal al momento:
#      el STOP mantiene su prioridad y no espera.
#   4. Watchdog: N respuestas consecutivas sin trama final marcan la cámara
#      en ERROR (señal connection_state_changed).
#   5. progress_age(): las esperas interrumpibles refrescan la señal de vida
#      que vigila el Supervisor.

from __future__ import annotations

import queue
import sys
import threading
import time
import types
import unittest
from unittest.mock import MagicMock

# ─── Stubs PyQt5 ─────────────────────────────────────────────────────────────

pyqt5_stub     = types.ModuleType("PyQt5")
qtcore_stub    = types.ModuleType("PyQt5.QtCore")
qtwidgets_stub = types.ModuleType("PyQt5.QtWidgets")

class _FakeSignal:
    def __init__(self, *a, **kw): pass
    def emit(self, *a):           pass
    def connect(self, *a):        pass

class _FakeQObject:
    def __init__(self, *a, **kw): pass

qtcore_stub.QObject    = _FakeQObject
qtcore_stub.pyqtSignal = lambda *a, **kw: _FakeSignal()
pyqt5_stub.QtCore      = qtcore_stub
pyqt5_stub.QtWidgets   = qtwidgets_stub
sys.modules.setdefault("PyQt5",           pyqt5_stub)
sys.modules.setdefault("PyQt5.QtCore",    qtcore_stub)
sys.modules.setdefault("PyQt5.QtWidgets", qtwidgets_stub)

# data_paths / secret_manager stubs (requeridos por config.py → camera_worker)
dp_stub = types.ModuleType("data_paths")
from pathlib import Path
dp_stub.SEAT_NAMES_FILE       = Path("seat_names_test.json")
dp_stub.CHAIRMAN_PRESETS_FILE = Path("chairman_presets_test.json")
dp_stub.SCHEDULE_FILE         = Path("schedule_test.json")
dp_stub.CONFIG_DIR            = Path(".")
dp_stub._DATA_FILES           = (dp_stub.CHAIRMAN_PRESETS_FILE, dp_stub.SEAT_NAMES_FILE, dp_stub.SCHEDULE_FILE)
dp_stub._LEGACY_FILES         = tuple(f.name for f in dp_stub._DATA_FILES)
dp_stub._CONFIG_TXT_FILES     = ("PTZ1IP.txt", "PTZ2IP.txt", "PTZ1ID.txt", "PTZ2ID.txt")
dp_stub._CONFIG_TXT_FILES     = ("PTZ1IP.txt", "PTZ1ID.txt")
dp_stub._LEGACY_FILES         = tuple(f.name for f in dp_stub._DATA_FILES)
sys.modules.setdefault("data_paths", dp_stub)
sm_stub = types.ModuleType("secret_manager")
sys.modules.setdefault("secret_manager", sm_stub)

# Forzar recarga del módulo real en lugar de cualquier stub inyectado por otros tests
sys.modules.pop("ptz.visca.worker", None)
from ptz.visca.worker import CameraWorker, ViscaCommand          # noqa: E402
import ptz.visca.worker as _wmod                                  # noqa: E402
from domain.camera_state import CameraConnectionState             # noqa: E402
from domain.retry_policy import RetryPolicy                       # noqa: E402

MOVE    = bytes.fromhex("8101060101010303FF")   # move normal
PT_STOP = bytes.fromhex("8101060100000303FF")   # pan/tilt stop, cam 1
COMPLETION = bytes([0x90, 0x50, 0xFF])          # trama Completion VISCA


# ─── Worker de test: red controlada, política de conexión sin esperas ────────

class _ControlledWorker(CameraWorker):
    """
    Worker sin red real. Las respuestas VISCA se guionizan con una lista:
    cada llamada a _read_visca_response consume la siguiente respuesta
    (o repite la última si se agotó la lista).
    """
    def __init__(self, responses):
        self.ip              = "10.0.0.77"
        self.port            = 5678
        self._is_connected   = False
        self._connection_state = CameraConnectionState.UNKNOWN
        self._queue          = queue.Queue(maxsize=20)
        self._sock           = None
        self._lock           = threading.Lock()
        self._interrupt      = threading.Event()
        self._shutdown       = threading.Event()
        self._last_heartbeat = time.monotonic()
        self._last_progress  = self._last_heartbeat
        self._consecutive_no_response = 0
        self._lifecycle_lock = threading.Lock()
        self._restart_join_timeout_s = 0.5  # espera acotada corta en tests
        self.signals         = MagicMock()
        self._responses      = list(responses)
        self._read_calls     = 0
        self.first_read_done = threading.Event()
        self.sent_payloads   = []

    def _connect(self):
        sock = MagicMock()
        sock.sendall = MagicMock(side_effect=lambda data: self.sent_payloads.append(data))
        return sock

    def _connect_with_retry(self, policy=None):
        # Conexión inmediata en tests: la política de reconexión ya tiene sus
        # propios tests; aquí se prueba el reintento de COMANDO.
        return super()._connect_with_retry(RetryPolicy(backoffs=()))

    def _read_visca_response(self, sock):
        self._read_calls += 1
        if self._read_calls == 1:
            self.first_read_done.set()
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]

    def _ping(self):
        pass  # sin heartbeats entre asserts

    def _set_connected(self, connected: bool):
        self._is_connected = connected  # sin señales Qt


def _start(worker: CameraWorker, test: unittest.TestCase) -> CameraWorker:
    """Lanza el thread del worker y lo registra para parada limpia."""
    worker._thread = threading.Thread(
        target=worker._run, daemon=True, name=f"Test-{worker.ip}")
    worker._thread.start()
    test.addCleanup(worker.stop)
    return worker


class _BackoffPatch:
    """Sustituye la política de reintento de comandos por backoffs de test."""
    def __init__(self, test: unittest.TestCase, backoffs):
        self._original = _wmod.CAMERA_COMMAND_RETRY_POLICY
        _wmod.CAMERA_COMMAND_RETRY_POLICY = RetryPolicy(backoffs=backoffs)
        test.addCleanup(self._restore)

    def _restore(self):
        _wmod.CAMERA_COMMAND_RETRY_POLICY = self._original


# ─────────────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCommandRetryWithBackoff(unittest.TestCase):
    """Los comandos normales se reintentan con backoff interrumpible."""

    def test_ordinary_command_retried_after_missing_final_frame(self):
        """Respuesta vacía → socket cerrado → reintento que sí completa."""
        _BackoffPatch(self, backoffs=(0,))
        w = _start(_ControlledWorker([b"", COMPLETION]), self)

        done = threading.Event()
        w.send(ViscaCommand(camera=1, payload=MOVE, on_success=done.set))
        self.assertTrue(done.wait(timeout=3.0), "on_success nunca se invocó")
        self.assertEqual(len(w.sent_payloads), 2,
                         "el comando debió enviarse 2 veces (1 intento + 1 reintento)")
        self.assertEqual(w._consecutive_no_response, 0,
                         "el watchdog se resetea tras una Completion")

    def test_confirmed_command_not_retried_after_missing_final_frame(self):
        """Un confirmado (fast_connect) no espera backoffs ni se reenvía:
        su deadline manda — un reintento tardío sería una orden fantasma."""
        _BackoffPatch(self, backoffs=(30,))
        w = _start(_ControlledWorker([b""]), self)

        failed = threading.Event()
        w.send(ViscaCommand(camera=1, payload=MOVE, fast_connect=True,
                            on_failure=failed.set))
        self.assertTrue(failed.wait(timeout=3.0), "on_failure nunca se invocó")
        time.sleep(0.2)
        self.assertEqual(len(w.sent_payloads), 1,
                         "un confirmado jamás se reenvía tras una respuesta sin trama final")

    def test_stop_interrupts_retry_backoff_immediately(self):
        """Un STOP entrante aborta el backoff de un comando normal al momento
        y sale primero: la prioridad de STOP no se degrada por los reintentos."""
        _BackoffPatch(self, backoffs=(30,))
        w = _start(_ControlledWorker([b""]), self)

        move_failed = threading.Event()
        w.send(ViscaCommand(camera=1, payload=MOVE, on_failure=move_failed.set))
        self.assertTrue(w.first_read_done.wait(timeout=3.0),
                        "el primer intento del MOVE no llegó a ejecutarse")

        stop_sent_at = []
        t0 = time.monotonic()
        w.send_priority(ViscaCommand(camera=1, payload=PT_STOP))

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not stop_sent_at:
            if PT_STOP in w.sent_payloads:
                stop_sent_at.append(time.monotonic() - t0)
            else:
                time.sleep(0.01)

        self.assertTrue(stop_sent_at, "el STOP no se envió")
        self.assertLess(stop_sent_at[0], 5.0,
                        "el STOP esperó al backoff del MOVE: prioridad degradada")
        self.assertTrue(move_failed.wait(timeout=3.0),
                        "el MOVE interrumpido no completó con fallo inmediato")
        self.assertEqual(w.sent_payloads.count(MOVE), 1,
                         "el MOVE interrumpido no debe reenviarse")


class TestNoResponseWatchdog(unittest.TestCase):
    """Watchdog: N respuestas sin trama final consecutivas marcan ERROR."""

    def test_error_state_after_consecutive_missing_frames(self):
        # VISCA_NO_RESPONSE_LIMIT = 3 en config; backoffs (0,0) → 3 intentos.
        _BackoffPatch(self, backoffs=(0, 0))
        w = _start(_ControlledWorker([b""]), self)

        failed = threading.Event()
        w.send(ViscaCommand(camera=1, payload=MOVE, on_failure=failed.set))
        self.assertTrue(failed.wait(timeout=5.0), "on_failure nunca se invocó")
        self.assertGreaterEqual(w._consecutive_no_response, 3,
                                "el contador del watchdog no llegó al límite")
        states = [c.args[0] for c in w.signals.connection_state_changed.emit.call_args_list]
        self.assertIn(CameraConnectionState.ERROR, states,
                      "la cámara no se marcó en ERROR tras las respuestas perdidas")

    def test_error_frame_resets_watchdog(self):
        """Una trama Error SÍ es respuesta de la cámara: resetea el contador."""
        _BackoffPatch(self, backoffs=(0, 0))
        w = _start(_ControlledWorker([b"", bytes([0x90, 0x60, 0x02, 0xFF])]), self)

        failed = threading.Event()
        w.send(ViscaCommand(camera=1, payload=MOVE, on_failure=failed.set))
        self.assertTrue(failed.wait(timeout=5.0), "on_failure nunca se invocó")
        self.assertEqual(w._consecutive_no_response, 0,
                         "una trama Error recibida debe resetear el watchdog")


class TestProgressLiveness(unittest.TestCase):
    """progress_age(): señal de vida que vigila el Supervisor."""

    def test_wait_interruptible_refreshes_progress(self):
        w = _ControlledWorker([COMPLETION])
        w._last_progress = time.monotonic() - 40.0
        self.assertGreater(w.progress_age(), 39.0)
        interrupted = w._wait_interruptible(0.3)
        self.assertFalse(interrupted)
        self.assertLess(w.progress_age(), 1.0,
                        "la espera interrumpible no refrescó la señal de vida")

    def test_progress_defaults_to_heartbeat_on_legacy_stubs(self):
        w = _ControlledWorker([COMPLETION])
        del w._last_progress
        w._last_heartbeat = time.monotonic() - 7.0
        self.assertGreater(w.progress_age(), 6.0)


class TestSupervisorRestartRoute(unittest.TestCase):
    """P1: el Supervisor reinicia DE VERDAD un worker vivo pero bloqueado.

    Antes del fix, CameraWorker.restart() devolvía sin hacer nada si el hilo
    seguía vivo, justo el caso que el Supervisor detecta (progress_age viejo).
    """

    def test_supervisor_replaces_live_stuck_thread(self):
        from core.supervisor import Supervisor
        w = _ControlledWorker([COMPLETION])
        _start(w, self)
        old = w._thread
        w._last_progress = time.monotonic() - 999.0  # sin señales de vida
        sup = Supervisor(intervalo=0.05)
        sup.registrar(
            "cam",
            lambda: w._thread.is_alive() and w.progress_age() < 30.0,
            w.restart,
        )
        sup.start()
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and w._thread is old:
            time.sleep(0.02)
        sup.stop()
        self.assertIsNot(w._thread, old,
                         "restart() no hizo nada con el hilo vivo")
        old.join(timeout=3.0)
        self.assertFalse(old.is_alive(),
                         "el hilo viejo debe morir ANTES de crear el nuevo")
        # El worker nuevo procesa comandos: no quedó zombie.
        w.send(ViscaCommand(camera=1, payload=MOVE))
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and MOVE not in w.sent_payloads:
            time.sleep(0.02)
        self.assertIn(MOVE, w.sent_payloads)

    def test_unkillable_thread_marks_error_without_second_consumer(self):
        w = _ControlledWorker([COMPLETION])
        entered = threading.Event()
        gate = threading.Event()
        original_read = w._read_visca_response
        def blocking_read(sock):
            entered.set()
            gate.wait(5.0)  # hilo colgado: ignora _shutdown hasta abrir la puerta
            return original_read(sock)
        w._read_visca_response = blocking_read
        _start(w, self)
        zombie = w._thread
        w.send(ViscaCommand(camera=1, payload=MOVE))
        self.assertTrue(entered.wait(timeout=2.0))
        self.assertFalse(w.restart(),
                         "con el hilo colgado restart() debe informar de fallo")
        self.assertIs(w._thread, zombie,
                      "nunca se crea un segundo consumidor con el viejo vivo")
        self.assertEqual(w._connection_state, CameraConnectionState.ERROR)
        gate.set()
        zombie.join(timeout=3.0)
        self.assertFalse(zombie.is_alive(),
                         "el hilo colgado debe terminar al despertar, sin enviar")
        # Muerto el viejo, el siguiente pase del supervisor sí recupera.
        self.assertTrue(w.restart())
        w.send(ViscaCommand(camera=1, payload=MOVE))
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and w.sent_payloads.count(MOVE) < 2:
            time.sleep(0.02)
        self.assertEqual(w.sent_payloads.count(MOVE), 2,
                         "el zombie no reenvió nada; el worker nuevo sí envía")


class TestSentinelLeakOnFailedRestarts(unittest.TestCase):
    """P1b: reinicios fallidos no dejan sentinels None que maten al relevo."""

    def test_failed_restarts_then_recovery_keeps_new_thread_alive(self):
        w = _ControlledWorker([COMPLETION])
        entered = threading.Event()
        gate = threading.Event()
        original_read = w._read_visca_response
        def blocking_read(sock):
            entered.set()
            gate.wait(5.0)  # hilo colgado hasta abrir la puerta
            return original_read(sock)
        w._read_visca_response = blocking_read
        _start(w, self)
        zombie = w._thread
        w.send(ViscaCommand(camera=1, payload=MOVE))
        self.assertTrue(entered.wait(timeout=2.0))
        self.assertFalse(w.restart())  # intento 1: el hilo no muere
        self.assertFalse(w.restart())  # intento 2: idem
        nones = sum(1 for it in list(w._queue.queue) if it is None)
        self.assertLessEqual(nones, 1,
                             "cada restart fallido añadía otro sentinel None")
        gate.set()
        zombie.join(timeout=3.0)
        self.assertFalse(zombie.is_alive())
        # Recuperación: el hilo nuevo NO debe morir por un sentinel sobrante.
        self.assertTrue(w.restart())
        new_thread = w._thread
        time.sleep(0.3)
        self.assertTrue(new_thread.is_alive(),
                        "un sentinel sobrante mató al hilo recién creado")
        w.send(ViscaCommand(camera=1, payload=MOVE))
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and w.sent_payloads.count(MOVE) < 2:
            time.sleep(0.02)
        self.assertEqual(w.sent_payloads.count(MOVE), 2,
                         "el worker recuperado debe procesar comandos")

    def test_sentinels_drained_without_losing_queued_stops(self):
        w = _ControlledWorker([COMPLETION])
        entered = threading.Event()
        gate = threading.Event()
        original_read = w._read_visca_response
        def blocking_read(sock):
            entered.set()
            gate.wait(5.0)
            return original_read(sock)
        w._read_visca_response = blocking_read
        _start(w, self)
        zombie = w._thread
        w.send(ViscaCommand(camera=1, payload=MOVE))
        self.assertTrue(entered.wait(timeout=2.0))
        self.assertFalse(w.restart())
        self.assertFalse(w.restart())
        # Un STOP encolado durante la avería debe sobrevivir al drenaje.
        w.send_priority(ViscaCommand(camera=1, payload=PT_STOP))
        gate.set()
        zombie.join(timeout=3.0)
        self.assertTrue(w.restart())
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and PT_STOP not in w.sent_payloads:
            time.sleep(0.02)
        self.assertIn(PT_STOP, w.sent_payloads,
                      "el STOP encolado durante la avería se perdió en el relevo")


class TestSingleFailureNotification(unittest.TestCase):
    """P2: on_failure se llama exactamente una vez por comando fallido."""

    def _wait_for_read(self, w, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and w._read_calls < 1:
            time.sleep(0.01)

    def test_once_when_command_expires_during_backoff(self):
        w = _ControlledWorker([b""])  # sin trama final: falla y entra en backoff
        _start(w, self)
        calls = []
        cmd = ViscaCommand(camera=1, payload=MOVE,
                           expires_at=time.monotonic() + 0.7,
                           on_failure=lambda: calls.append(1))
        w.send(cmd)
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and not calls:
            time.sleep(0.02)
        time.sleep(0.4)  # margen para una hipotética segunda llamada (epílogo)
        self.assertEqual(len(calls), 1,
                         "vencer durante el backoff notificaba dos veces")

    def test_once_when_cancelled_during_backoff(self):
        w = _ControlledWorker([b""])
        _start(w, self)
        calls = []
        cmd = ViscaCommand(camera=1, payload=MOVE,
                           on_failure=lambda: calls.append(1))
        w.send(cmd)
        self._wait_for_read(w)  # primer intento hecho; entra en backoff
        cmd.cancelled.set()
        time.sleep(1.6)  # sale del backoff (1 s) + epílogo
        self.assertEqual(len(calls), 1)

    def test_once_when_stop_interrupts_backoff(self):
        w = _ControlledWorker([b""])
        _start(w, self)
        calls = []
        w.send(ViscaCommand(camera=1, payload=MOVE,
                            on_failure=lambda: calls.append(1)))
        self._wait_for_read(w)
        w.send_priority(ViscaCommand(camera=1, payload=PT_STOP))
        time.sleep(0.6)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
