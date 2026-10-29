#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_camera_worker.py — Tests de robustez de CameraWorker
#
# Escenarios:
#   1. Excepción en on_success no mata el thread del worker
#   2. Excepción en on_failure no mata el thread del worker
#   3. on_success se invoca tras envío exitoso
#   4. on_failure se invoca cuando _connect siempre falla

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
dp_stub._CONFIG_TXT_FILES     = ("PTZ1IP.txt", "PTZ2IP.txt", "Cam1ID.txt", "Cam2ID.txt", "ATEMIP.txt", "Contact.txt")
_prev_data_paths = sys.modules.get("data_paths")
sys.modules.setdefault("data_paths", dp_stub)

sm_stub = types.ModuleType("secret_manager")
sm_stub.decrypt_password = lambda: "test"
sys.modules.setdefault("secret_manager", sm_stub)

# Forzar recarga del módulo real en lugar de cualquier stub inyectado por otros tests
sys.modules.pop("ptz.visca.worker", None)
from ptz.visca.worker import CameraWorker, ViscaCommand

if _prev_data_paths is None:
    sys.modules.pop("data_paths", None)
else:
    sys.modules["data_paths"] = _prev_data_paths


# ─── Subclases de test: sustituyen red real con comportamiento controlado ─────

class _OKWorker(CameraWorker):
    """
    Worker que simula envío exitoso sin abrir sockets reales.
    Sobreescribe _connect para devolver un mock y _read_visca_response
    para devolver una trama Completion VISCA válida.
    """
    def __init__(self):
        # Construir manualmente sin lanzar el thread — lo lanzamos en el test
        self.ip              = "10.0.0.99"
        self.port            = 5678
        self._is_connected   = False
        self._queue          = queue.Queue(maxsize=20)
        self._sock           = None
        self._lock           = threading.Lock()
        self._interrupt      = threading.Event()
        self._shutdown       = threading.Event()
        self._last_heartbeat = time.monotonic()
        self.signals         = MagicMock()
        self.signals.connection_changed = MagicMock()
        self.signals.visca_error        = MagicMock()

    def _connect(self):
        sock = MagicMock()
        sock.send = MagicMock()
        return sock

    def _read_visca_response(self, sock):
        return bytes([0x90, 0x50, 0xFF])  # Completion VISCA

    def _ping(self):
        pass  # Evita heartbeats sobre MagicMock cuando el test deja el hilo vivo.

    def _set_connected(self, connected: bool):
        self._is_connected = connected  # sin señales Qt


class _FailWorker(CameraWorker):
    """
    Worker que simula fallo total de red: _connect siempre devuelve None.
    Tras los intentos fallidos se invoca on_failure.
    """
    def __init__(self):
        self.ip              = "10.0.0.88"
        self.port            = 5678
        self._is_connected   = False
        self._queue          = queue.Queue(maxsize=20)
        self._sock           = None
        self._lock           = threading.Lock()
        self._interrupt      = threading.Event()
        self._shutdown       = threading.Event()
        self._last_heartbeat = time.monotonic()
        self.signals         = MagicMock()
        self.signals.connection_changed = MagicMock()
        self.signals.visca_error        = MagicMock()

    def _connect(self):
        return None  # sin conexión disponible

    def _connect_with_retry(self, policy=None):
        # En tests usamos backoff cero para que on_failure se llame de inmediato
        # sin esperar los segundos reales de CAMERA_RETRY_POLICY.
        from domain.retry_policy import RetryPolicy
        return super()._connect_with_retry(RetryPolicy(backoffs=()))

    def _ping(self):
        pass  # Mantiene el hilo inactivo sin intentar red real entre asserts.

    def _set_connected(self, connected: bool):
        self._is_connected = connected


def _start(worker: CameraWorker, test: unittest.TestCase) -> CameraWorker:
    """Lanza el thread del worker y devuelve el worker listo.

    Registra worker.stop() como cleanup: sin esto el thread queda vivo
    tras el test (daemon=True no lo mata hasta que termina el proceso),
    filtrando threads a los tests siguientes de toda la suite.
    """
    worker._thread = threading.Thread(
        target=worker._run, daemon=True, name=f"Test-{worker.ip}")
    worker._thread.start()
    test.addCleanup(worker.stop)
    return worker


# ─────────────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestCallbackExceptionSafety(unittest.TestCase):
    """Bug A: excepción en on_success / on_failure no debe matar el thread."""

    def test_on_success_exception_does_not_kill_thread(self):
        """
        Si on_success lanza RuntimeError, el worker lo captura, loguea el error
        y continúa procesando comandos. El thread no muere.
        """
        w = _start(_OKWorker(), self)

        raised = threading.Event()
        def _raise():
            raised.set()
            raise RuntimeError("on_success intencional")

        # Comando 1: on_success que lanza
        w.send(ViscaCommand(camera=1,
                            payload=b'\x81\x01\x06\x01\x09\x09\x03\x03\xFF',
                            on_success=_raise))
        raised.wait(timeout=2.0)
        self.assertTrue(raised.is_set(), "on_success no se ejecutó")

        time.sleep(0.05)  # margen para que el worker procese la excepción
        self.assertTrue(w._thread.is_alive(),
                        "Thread murió tras excepción en on_success")

        # Comando 2: debe ejecutarse (worker sigue activo)
        alive = threading.Event()
        w.send(ViscaCommand(camera=1,
                            payload=b'\x81\x01\x06\x01\x09\x09\x03\x03\xFF',
                            on_success=alive.set))
        alive.wait(timeout=2.0)
        self.assertTrue(alive.is_set(),
                        "Segundo comando no procesado — el thread habría muerto sin el fix")

    def test_on_failure_exception_does_not_kill_thread(self):
        """
        Si on_failure lanza RuntimeError, el worker lo captura, loguea el error
        y continúa procesando comandos. El thread no muere.
        """
        w = _start(_FailWorker(), self)

        raised = threading.Event()
        def _raise():
            raised.set()
            raise RuntimeError("on_failure intencional")

        w.send(ViscaCommand(camera=1,
                            payload=b'\x81\x01\x04\x00\x02\xFF',
                            on_failure=_raise))
        raised.wait(timeout=3.0)
        self.assertTrue(raised.is_set(), "on_failure no se ejecutó")

        time.sleep(0.05)
        self.assertTrue(w._thread.is_alive(),
                        "Thread murió tras excepción en on_failure")


class TestCallbackInvocation(unittest.TestCase):
    """Verificar que on_success y on_failure se invocan en los casos correctos."""

    def test_on_success_called_after_successful_send(self):
        w = _start(_OKWorker(), self)

        called = threading.Event()
        w.send(ViscaCommand(camera=1,
                            payload=b'\x81\x01\x04\x00\x02\xFF',
                            on_success=called.set))
        called.wait(timeout=2.0)
        self.assertTrue(called.is_set(), "on_success nunca se invocó")

    def test_on_failure_called_when_connect_fails(self):
        w = _start(_FailWorker(), self)

        called = threading.Event()
        w.send(ViscaCommand(camera=1,
                            payload=b'\x81\x01\x04\x00\x02\xFF',
                            on_failure=called.set))
        called.wait(timeout=3.0)
        self.assertTrue(called.is_set(), "on_failure nunca se invocó")

    def test_no_callback_ok(self):
        """Comando sin callbacks no lanza excepción."""
        w = _start(_OKWorker(), self)
        done = threading.Event()
        # Enviamos dos: el primero sin callback, el segundo con callback para saber cuándo acabó
        w.send(ViscaCommand(camera=1, payload=b'\x81\x01\x04\x00\x02\xFF'))
        w.send(ViscaCommand(camera=1, payload=b'\x81\x01\x04\x00\x02\xFF',
                            on_success=done.set))
        done.wait(timeout=2.0)
        self.assertTrue(done.is_set())


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ─────────────────────────────────────────────────────────────────────────────
#  STOP admission: send_priority nunca descarta el STOP entrante
# ─────────────────────────────────────────────────────────────────────────────

PT_STOP = bytes.fromhex("8101060100000303FF")   # pan/tilt stop, cam 1
Z_STOP  = bytes.fromhex("8101040700FF")         # zoom stop, cam 1
HOME    = bytes.fromhex("81010604FF")           # home (priority, NO es stop)
MOVE    = bytes.fromhex("8101060101010303FF")   # move normal


def _queue_worker(maxsize: int = 20) -> "_OKWorker":
    w = _OKWorker()
    w._queue = queue.Queue(maxsize=maxsize)
    return w


def _drain(q: "queue.Queue") -> list:
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            return items


class TestStopAdmission(unittest.TestCase):
    """Regresión: un STOP nuevo SIEMPRE entra en la cola.

    Cubre el fallo de la primera versión del fix de zoom-stop: conservar
    comandos priority indiscriminadamente podía llenar la cola y descartar
    en silencio el STOP entrante (queue.Full tragado por el except)."""

    def test_stop_pair_survives_second_priority(self):
        """PT-STOP y Z-STOP del mismo stop_move se conservan en orden."""
        w = _queue_worker()
        w.send_priority(ViscaCommand(camera=1, payload=PT_STOP))
        w.send_priority(ViscaCommand(camera=1, payload=Z_STOP))
        payloads = [c.payload for c in _drain(w._queue)]
        self.assertEqual(payloads, [PT_STOP, Z_STOP])

    def test_new_stop_admitted_over_stale_priority_non_stop(self):
        """Cola llena con priority NO-STOP (HOME): el STOP nuevo entra."""
        w = _queue_worker(maxsize=2)
        w._queue.put(ViscaCommand(camera=1, payload=HOME, priority=True))
        w._queue.put(ViscaCommand(camera=1, payload=HOME, priority=True))
        w.send_priority(ViscaCommand(camera=1, payload=PT_STOP))
        payloads = [c.payload for c in _drain(w._queue)]
        self.assertEqual(payloads, [PT_STOP])

    def test_new_stop_never_dropped_when_queue_full_of_stops(self):
        """Cola llena de STOPs: se descarta el MÁS VIEJO, nunca el nuevo."""
        w = _queue_worker(maxsize=3)
        for _ in range(3):
            w._queue.put(ViscaCommand(camera=1, payload=PT_STOP, priority=True))
        w.send_priority(ViscaCommand(camera=1, payload=Z_STOP))
        items = _drain(w._queue)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[-1].payload, Z_STOP)

    def test_coalesced_zoom_stop_replaced_by_priority_pair(self):
        """La carrera real: zoom-stop coalesced pendiente + STOP → par priority."""
        w = _queue_worker()
        w._queue.put(ViscaCommand(camera=1, payload=Z_STOP, coalesce=True))
        w.send_priority(ViscaCommand(camera=1, payload=PT_STOP))
        w.send_priority(ViscaCommand(camera=1, payload=Z_STOP))
        items = _drain(w._queue)
        self.assertEqual([c.payload for c in items], [PT_STOP, Z_STOP])
        self.assertTrue(all(c.priority for c in items))

    def test_is_stop_payload(self):
        self.assertTrue(CameraWorker._is_stop_payload(PT_STOP))
        self.assertTrue(CameraWorker._is_stop_payload(Z_STOP))
        self.assertTrue(CameraWorker._is_stop_payload(bytes.fromhex("8801040700FF")))
        self.assertFalse(CameraWorker._is_stop_payload(HOME))
        self.assertFalse(CameraWorker._is_stop_payload(MOVE))
        self.assertFalse(CameraWorker._is_stop_payload(bytes.fromhex("81040700FF")))
        self.assertFalse(CameraWorker._is_stop_payload(b""))

    def test_home_never_evicts_pending_stops(self):
        """Regresión v3: un priority NO-STOP (HOME) con la cola llena de STOPs
        no desplaza ninguno; el que se descarta es el propio HOME."""
        w = _queue_worker(maxsize=2)
        w._queue.put(ViscaCommand(camera=1, payload=PT_STOP, priority=True))
        w._queue.put(ViscaCommand(camera=1, payload=Z_STOP, priority=True))
        w.send_priority(ViscaCommand(camera=1, payload=HOME))
        payloads = [c.payload for c in _drain(w._queue)]
        self.assertEqual(payloads, [PT_STOP, Z_STOP])

    def test_concurrent_producers_stop_always_admitted(self):
        """Concurrencia: productores saturan la cola con moves mientras otro
        hilo emite STOPs; cada STOP debe acabar admitido y sin interbloqueo."""
        w = _queue_worker(maxsize=10)
        errors = []

        def moves():
            try:
                for _ in range(200):
                    w.send(ViscaCommand(camera=1, payload=MOVE, coalesce=True))
            except Exception as exc:  # noqa: BLE001 - el test debe fallar, no colgar
                errors.append(exc)

        def stops():
            try:
                for _ in range(50):
                    w.send_priority(ViscaCommand(camera=1, payload=PT_STOP))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=moves) for _ in range(4)]
        threads.append(threading.Thread(target=stops))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertFalse(any(t.is_alive() for t in threads), "deadlock en send_priority")
        self.assertEqual(errors, [])
        items = _drain(w._queue)
        self.assertTrue(items, "la cola no debe quedar vacía")
        self.assertTrue(all(CameraWorker._is_stop_payload(c.payload) for c in items),
                        "tras STOPs priority solo quedan STOPs encolados")

    def test_send_priority_preserves_shutdown_sentinel(self):
        """Regresión v4 (Auditoría): el sentinel None de stop() no rompe el
        drain (AttributeError) y sobrevive: la parada del worker no se pierde."""
        w = _queue_worker()
        w._queue.put(None)  # sentinel de stop()
        w.send_priority(ViscaCommand(camera=1, payload=PT_STOP))
        items = _drain(w._queue)
        self.assertEqual(len(items), 2)
        self.assertIsNone(items[0])
        self.assertEqual(items[1].payload, PT_STOP)

    def test_sentinel_survives_eviction_when_queue_full(self):
        """Cola llena [None, STOP] + STOP nuevo: se evicta el STOP viejo,
        nunca el sentinel."""
        w = _queue_worker(maxsize=2)
        w._queue.put(None)
        w._queue.put(ViscaCommand(camera=1, payload=PT_STOP, priority=True))
        w.send_priority(ViscaCommand(camera=1, payload=Z_STOP))
        items = _drain(w._queue)
        self.assertEqual(len(items), 2)
        self.assertIsNone(items[0])
        self.assertEqual(items[1].payload, Z_STOP)

    def test_send_coalesce_ignores_sentinel(self):
        """send() coalesced tras stop(): el sentinel None no rompe el scan."""
        w = _queue_worker()
        w._queue.put(None)
        ok = w.send(ViscaCommand(camera=1, payload=MOVE, coalesce=True))
        self.assertTrue(ok)
        items = _drain(w._queue)
        self.assertIsNone(items[0])
        self.assertEqual(items[1].payload, MOVE)
