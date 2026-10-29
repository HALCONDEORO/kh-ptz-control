#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_visca_manager.py — Tests de CameraManager: estado, cache y concurrencia

from __future__ import annotations

import sys
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ─── Stubs mínimos para PyQt5 (requerido por ptz.visca.worker) ───────────────

_pyqt5      = types.ModuleType("PyQt5")
_qtcore     = types.ModuleType("PyQt5.QtCore")
_qtwidgets  = types.ModuleType("PyQt5.QtWidgets")
_qtcore.QObject    = object
_qtcore.pyqtSignal = lambda *a, **kw: None
_pyqt5.QtCore      = _qtcore
_pyqt5.QtWidgets   = _qtwidgets
sys.modules.setdefault("PyQt5",           _pyqt5)
sys.modules.setdefault("PyQt5.QtCore",    _qtcore)
sys.modules.setdefault("PyQt5.QtWidgets", _qtwidgets)

_sm = types.ModuleType("secret_manager")
_sm.decrypt_password = lambda: "test"
sys.modules.setdefault("secret_manager", _sm)

_dp = types.ModuleType("data_paths")
_dp.SEAT_NAMES_FILE       = Path("seat_names_test.json")
_dp.CHAIRMAN_PRESETS_FILE = Path("chairman_presets_test.json")
_dp.SCHEDULE_FILE         = Path("schedule_test.json")
_dp.CONFIG_DIR            = Path(".")
sys.modules.setdefault("data_paths", _dp)

# ─── Importar módulos reales ──────────────────────────────────────────────────
# Forzar recarga del módulo real aunque test_preset_poll.py haya inyectado un
# stub en sys.modules["ptz.visca.manager"] antes de que este archivo se ejecute.
sys.modules.pop("ptz.visca.manager", None)
sys.modules.pop("ptz.visca.worker",  None)

from config import CAM1, CAM2, CameraConfig
from ptz.visca.manager import CameraManager
import ptz.visca.manager as _manager_mod  # referencia real; inmune a override posterior de sys.modules

IP1 = CAM1.ip
IP2 = CAM2.ip

_CFG1 = CameraConfig(ip='10.1.1.1', cam_id='81')
_CFG2 = CameraConfig(ip='10.1.1.2', cam_id='82')


def _mgr(**kw) -> CameraManager:
    return CameraManager(_CFG1, _CFG2, **kw)


# ─────────────────────────────────────────────────────────────────────────────
#  cam_key
# ─────────────────────────────────────────────────────────────────────────────

class TestCamKey(unittest.TestCase):
    def test_cam1_ip_returns_1(self):
        m = _mgr()
        self.assertEqual(m.cam_key(_CFG1.ip), 1)

    def test_cam2_ip_returns_2(self):
        m = _mgr()
        self.assertEqual(m.cam_key(_CFG2.ip), 2)

    def test_unknown_ip_raises(self):
        m = _mgr()
        with self.assertRaises(ValueError):
            m.cam_key('0.0.0.0')


# ─────────────────────────────────────────────────────────────────────────────
#  worker(): creación y caché
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkerCreation(unittest.TestCase):

    @patch.object(_manager_mod, 'CameraWorker')
    def test_worker_created_on_first_call(self, MockCW):
        mock_w = MagicMock()
        MockCW.return_value = mock_w
        m = _mgr()
        result = m.worker(_CFG1.ip)
        MockCW.assert_called_once_with(_CFG1.ip)
        self.assertIs(result, mock_w)

    @patch.object(_manager_mod, 'CameraWorker')
    def test_worker_cached_on_second_call(self, MockCW):
        MockCW.return_value = MagicMock()
        m = _mgr()
        w1 = m.worker(_CFG1.ip)
        w2 = m.worker(_CFG1.ip)
        MockCW.assert_called_once()   # una sola creación
        self.assertIs(w1, w2)

    @patch.object(_manager_mod, 'CameraWorker')
    def test_two_cameras_get_independent_workers(self, MockCW):
        MockCW.side_effect = [MagicMock(), MagicMock()]
        m = _mgr()
        w1 = m.worker(_CFG1.ip)
        w2 = m.worker(_CFG2.ip)
        self.assertIsNot(w1, w2)
        self.assertEqual(MockCW.call_count, 2)

    @patch.object(_manager_mod, 'CameraWorker')
    def test_on_worker_ready_callback_invoked(self, MockCW):
        ready_calls = []
        mock_w = MagicMock()
        MockCW.return_value = mock_w
        m = _mgr(on_worker_ready=ready_calls.append)
        m.worker(_CFG1.ip)
        self.assertEqual(ready_calls, [mock_w])

    @patch.object(_manager_mod, 'CameraWorker')
    def test_on_worker_ready_not_called_on_cache_hit(self, MockCW):
        ready_calls = []
        MockCW.return_value = MagicMock()
        m = _mgr(on_worker_ready=ready_calls.append)
        m.worker(_CFG1.ip)
        m.worker(_CFG1.ip)  # cache hit
        self.assertEqual(len(ready_calls), 1)

    @patch.object(_manager_mod, 'CameraWorker')
    def test_concurrent_first_access_creates_single_worker(self, MockCW):
        """Accesos concurrentes a la misma IP no crean workers duplicados (TOCTOU)."""
        MockCW.side_effect = lambda ip: MagicMock(name=f"worker-{ip}")
        m = _mgr()
        results = []
        barrier = threading.Barrier(8)

        def _get():
            barrier.wait()
            results.append(m.worker(_CFG1.ip))

        threads = [threading.Thread(target=_get) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(1.0)

        self.assertEqual(MockCW.call_count, 1, "se crearon workers duplicados")
        self.assertEqual(len({id(w) for w in results}), 1, "se devolvieron instancias distintas")


# ─────────────────────────────────────────────────────────────────────────────
#  Zoom cache
# ─────────────────────────────────────────────────────────────────────────────

class TestZoomCache(unittest.TestCase):
    def setUp(self):
        self.m = _mgr()

    def test_initial_zoom_is_none(self):
        self.assertIsNone(self.m.get_zoom(_CFG1.ip))
        self.assertIsNone(self.m.get_zoom(_CFG2.ip))

    def test_set_zoom_updates_cache(self):
        self.m.set_zoom(_CFG1.ip, 42)
        self.assertEqual(self.m.get_zoom(_CFG1.ip), 42)

    def test_set_zoom_cam1_does_not_affect_cam2(self):
        self.m.set_zoom(_CFG1.ip, 75)
        self.assertIsNone(self.m.get_zoom(_CFG2.ip))

    def test_invalidate_zoom_clears_cache(self):
        self.m.set_zoom(_CFG1.ip, 55)
        self.m.invalidate_zoom(_CFG1.ip)
        self.assertIsNone(self.m.get_zoom(_CFG1.ip))

    def test_invalidate_zoom_cam1_does_not_affect_cam2(self):
        self.m.set_zoom(_CFG1.ip, 30)
        self.m.set_zoom(_CFG2.ip, 70)
        self.m.invalidate_zoom(_CFG1.ip)
        self.assertEqual(self.m.get_zoom(_CFG2.ip), 70)

    def test_set_zoom_overwrites(self):
        self.m.set_zoom(_CFG1.ip, 10)
        self.m.set_zoom(_CFG1.ip, 90)
        self.assertEqual(self.m.get_zoom(_CFG1.ip), 90)


# ─────────────────────────────────────────────────────────────────────────────
#  zoom_query_try_acquire / zoom_query_release
# ─────────────────────────────────────────────────────────────────────────────

class TestZoomQueryInflight(unittest.TestCase):
    def setUp(self):
        self.m = _mgr()

    def test_first_acquire_returns_true(self):
        self.assertTrue(self.m.zoom_query_try_acquire(_CFG1.ip))

    def test_second_acquire_returns_false(self):
        self.m.zoom_query_try_acquire(_CFG1.ip)
        self.assertFalse(self.m.zoom_query_try_acquire(_CFG1.ip))

    def test_release_allows_reacquire(self):
        self.m.zoom_query_try_acquire(_CFG1.ip)
        self.m.zoom_query_release(_CFG1.ip)
        self.assertTrue(self.m.zoom_query_try_acquire(_CFG1.ip))

    def test_cam1_and_cam2_independent(self):
        self.assertTrue(self.m.zoom_query_try_acquire(_CFG1.ip))
        self.assertTrue(self.m.zoom_query_try_acquire(_CFG2.ip))

    def test_atomic_under_concurrency(self):
        """Solo uno de dos threads concurrentes puede adquirir el slot (TOCTOU)."""
        results = []
        barrier = threading.Barrier(2)

        def _try():
            barrier.wait()
            results.append(self.m.zoom_query_try_acquire(_CFG1.ip))

        t1 = threading.Thread(target=_try)
        t2 = threading.Thread(target=_try)
        t1.start()
        t2.start()
        t1.join(1.0)
        t2.join(1.0)

        self.assertEqual(sorted(results), [False, True],
                         "Ambos threads adquirieron el slot (TOCTOU no protegido)")


# ─────────────────────────────────────────────────────────────────────────────
#  ae_query_try_acquire / ae_query_release
# ─────────────────────────────────────────────────────────────────────────────

class TestAEQueryInflight(unittest.TestCase):
    def setUp(self):
        self.m = _mgr()

    def test_first_acquire_returns_true(self):
        self.assertTrue(self.m.ae_query_try_acquire(_CFG1.ip))

    def test_second_acquire_returns_false(self):
        self.m.ae_query_try_acquire(_CFG1.ip)
        self.assertFalse(self.m.ae_query_try_acquire(_CFG1.ip))

    def test_release_allows_reacquire(self):
        self.m.ae_query_try_acquire(_CFG1.ip)
        self.m.ae_query_release(_CFG1.ip)
        self.assertTrue(self.m.ae_query_try_acquire(_CFG1.ip))

    def test_ae_and_zoom_slots_independent(self):
        """Los slots de AE y zoom son independientes: uno no bloquea al otro."""
        self.assertTrue(self.m.zoom_query_try_acquire(_CFG1.ip))
        self.assertTrue(self.m.ae_query_try_acquire(_CFG1.ip))

    def test_atomic_under_concurrency(self):
        results = []
        barrier = threading.Barrier(2)

        def _try():
            barrier.wait()
            results.append(self.m.ae_query_try_acquire(_CFG1.ip))

        t1 = threading.Thread(target=_try)
        t2 = threading.Thread(target=_try)
        t1.start()
        t2.start()
        t1.join(1.0)
        t2.join(1.0)

        self.assertEqual(sorted(results), [False, True])


# ─────────────────────────────────────────────────────────────────────────────
#  Estado per-cámara (backlight, focus, exposure, ae_mode)
# ─────────────────────────────────────────────────────────────────────────────

class TestCameraState(unittest.TestCase):
    def setUp(self):
        self.m = _mgr()

    def test_initial_backlight_false(self):
        self.assertFalse(self.m.backlight_on[1])
        self.assertFalse(self.m.backlight_on[2])

    def test_initial_focus_auto(self):
        self.assertEqual(self.m.focus_mode[1], 'auto')
        self.assertEqual(self.m.focus_mode[2], 'auto')

    def test_initial_exposure_zero(self):
        self.assertEqual(self.m.exposure_level[1], 0)
        self.assertEqual(self.m.exposure_level[2], 0)

    def test_initial_ae_mode_auto(self):
        self.assertEqual(self.m.ae_mode[1], 'auto')
        self.assertEqual(self.m.ae_mode[2], 'auto')

    def test_state_write_cam1_does_not_affect_cam2(self):
        self.m.backlight_on[1] = True
        self.assertFalse(self.m.backlight_on[2])

        self.m.exposure_level[1] = 5
        self.assertEqual(self.m.exposure_level[2], 0)

        self.m.ae_mode[1] = 'manual'
        self.assertEqual(self.m.ae_mode[2], 'auto')


if __name__ == '__main__':
    unittest.main(verbosity=2)
