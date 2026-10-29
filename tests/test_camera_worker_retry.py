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


if __name__ == "__main__":
    unittest.main(verbosity=2)
