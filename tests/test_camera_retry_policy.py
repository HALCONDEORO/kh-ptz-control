#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_camera_retry_policy.py — RetryPolicy domain rules + CameraWorker integration
#
# Sections:
#   1. RetryPolicy pure-domain tests (no I/O, no Qt)
#   2. CameraWorker._connect_with_retry integration tests (mock socket)
#   3. ATEMMonitor uses ATEM_RETRY_POLICY (smoke import)

from __future__ import annotations

import queue
import sys
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch

# ── PyQt5 stub (required before importing worker / atem_monitor) ──────────────

_pyqt5_stub    = types.ModuleType("PyQt5")
_qtcore_stub   = types.ModuleType("PyQt5.QtCore")

class _FakeSignal:
    def __init__(self, *a, **kw): pass
    def emit(self, *a):           pass
    def connect(self, *a):        pass

class _FakeQObject:
    def __init__(self, *a, **kw): pass

class _FakeQThread(_FakeQObject):
    def isInterruptionRequested(self): return False
    def requestInterruption(self):     pass

_qtcore_stub.QObject    = _FakeQObject
_qtcore_stub.QThread    = _FakeQThread
_qtcore_stub.pyqtSignal = lambda *a, **kw: _FakeSignal()
_pyqt5_stub.QtCore      = _qtcore_stub
sys.modules.setdefault("PyQt5",        _pyqt5_stub)
sys.modules.setdefault("PyQt5.QtCore", _qtcore_stub)

# Force fresh import of target modules
for _key in list(sys.modules):
    if _key in ("ptz.visca.worker", "domain.retry_policy"):
        del sys.modules[_key]

from domain.retry_policy import RetryPolicy, CAMERA_RETRY_POLICY, ATEM_RETRY_POLICY

sys.modules.pop("ptz.visca.worker", None)
from ptz.visca.worker import CameraWorker


# ── 1. RetryPolicy pure-domain tests ─────────────────────────────────────────

class TestRetryPolicyDomain(unittest.TestCase):

    def test_max_attempts_no_backoffs(self):
        p = RetryPolicy(backoffs=())
        self.assertEqual(p.max_attempts, 1)

    def test_max_attempts_one_backoff(self):
        p = RetryPolicy(backoffs=(5,))
        self.assertEqual(p.max_attempts, 2)

    def test_max_attempts_three_backoffs(self):
        p = RetryPolicy(backoffs=(2, 5, 15))
        self.assertEqual(p.max_attempts, 4)

    def test_frozen_cannot_mutate(self):
        p = RetryPolicy(backoffs=(1, 2))
        with self.assertRaises((AttributeError, TypeError)):
            p.backoffs = (3, 4)  # type: ignore[misc]

    def test_camera_retry_policy_backoffs(self):
        self.assertEqual(CAMERA_RETRY_POLICY.backoffs, (5, 15, 30))

    def test_camera_retry_policy_max_attempts(self):
        self.assertEqual(CAMERA_RETRY_POLICY.max_attempts, 4)

    def test_atem_retry_policy_backoffs(self):
        self.assertEqual(ATEM_RETRY_POLICY.backoffs, (2, 5, 15))

    def test_atem_retry_policy_max_attempts(self):
        self.assertEqual(ATEM_RETRY_POLICY.max_attempts, 4)

    def test_equality(self):
        a = RetryPolicy(backoffs=(1, 2))
        b = RetryPolicy(backoffs=(1, 2))
        self.assertEqual(a, b)

    def test_inequality(self):
        a = RetryPolicy(backoffs=(1, 2))
        b = RetryPolicy(backoffs=(1, 3))
        self.assertNotEqual(a, b)


# ── Minimal CameraWorker fixture (no real thread, no real socket) ─────────────

def _make_worker(ip: str = "10.0.0.99") -> CameraWorker:
    """Build a CameraWorker without starting its background thread."""
    w = CameraWorker.__new__(CameraWorker)
    w.ip             = ip
    w.port           = 52381
    w._is_connected  = False
    w._queue         = queue.Queue(maxsize=20)
    w._sock          = None
    w._lock          = threading.Lock()
    w._interrupt     = threading.Event()
    w._shutdown      = threading.Event()
    w._last_heartbeat = time.monotonic()
    w.signals        = MagicMock()
    w.signals.connection_changed = MagicMock()
    w.signals.visca_error        = MagicMock()
    return w


# ── 2. CameraWorker._connect_with_retry integration tests ────────────────────

class TestConnectWithRetry(unittest.TestCase):

    def setUp(self):
        self.worker = _make_worker()
        self.policy = RetryPolicy(backoffs=(0, 0))  # zero backoff → fast tests

    # ── Success path ──────────────────────────────────────────────────────────

    def test_returns_socket_on_first_success(self):
        mock_sock = MagicMock()
        with patch.object(self.worker, "_connect", return_value=mock_sock) as m:
            result = self.worker._connect_with_retry(self.policy)
        self.assertIs(result, mock_sock)
        m.assert_called_once()

    def test_returns_socket_on_second_attempt(self):
        mock_sock = MagicMock()
        with patch.object(self.worker, "_connect", side_effect=[None, mock_sock]) as m:
            result = self.worker._connect_with_retry(self.policy)
        self.assertIs(result, mock_sock)
        self.assertEqual(m.call_count, 2)

    def test_does_not_call_connect_after_success(self):
        mock_sock = MagicMock()
        # policy has max_attempts=3; success on attempt 1 → only 1 call
        with patch.object(self.worker, "_connect", return_value=mock_sock) as m:
            self.worker._connect_with_retry(self.policy)
        self.assertEqual(m.call_count, 1)

    # ── Failure path ─────────────────────────────────────────────────────────

    def test_returns_none_after_all_attempts_fail(self):
        with patch.object(self.worker, "_connect", return_value=None):
            result = self.worker._connect_with_retry(self.policy)
        self.assertIsNone(result)

    def test_calls_connect_max_attempts_times_on_total_failure(self):
        with patch.object(self.worker, "_connect", return_value=None) as m:
            self.worker._connect_with_retry(self.policy)
        self.assertEqual(m.call_count, self.policy.max_attempts)

    def test_single_attempt_policy_calls_connect_once(self):
        single = RetryPolicy(backoffs=())
        with patch.object(self.worker, "_connect", return_value=None) as m:
            self.worker._connect_with_retry(single)
        m.assert_called_once()

    # ── Interrupt path ────────────────────────────────────────────────────────

    def test_returns_none_immediately_if_already_interrupted(self):
        self.worker._interrupt.set()
        with patch.object(self.worker, "_connect", return_value=None) as m:
            result = self.worker._connect_with_retry(self.policy)
        self.assertIsNone(result)
        m.assert_not_called()

    def test_returns_none_when_interrupted_during_backoff(self):
        # First attempt fails; interrupt fires before the second attempt.
        # Use real backoff (1 s) and set interrupt mid-wait.
        slow_policy = RetryPolicy(backoffs=(1,))
        connect_calls = []

        def _fake_connect():
            connect_calls.append(1)
            return None

        with patch.object(self.worker, "_connect", side_effect=_fake_connect):
            # Set interrupt after a tiny delay so _wait_interruptible picks it up
            threading.Timer(0.05, self.worker._interrupt.set).start()
            result = self.worker._connect_with_retry(slow_policy)

        self.assertIsNone(result)
        self.assertEqual(len(connect_calls), 1)  # interrupted before 2nd attempt

    # ── Default policy ────────────────────────────────────────────────────────

    def test_uses_camera_retry_policy_by_default(self):
        """_connect_with_retry() with no args uses CAMERA_RETRY_POLICY."""
        mock_sock = MagicMock()
        with patch.object(self.worker, "_connect", return_value=mock_sock):
            result = self.worker._connect_with_retry()
        self.assertIs(result, mock_sock)


# ── 3. ATEMMonitor uses ATEM_RETRY_POLICY ────────────────────────────────────

class TestATEMMonitorUsesPolicy(unittest.TestCase):

    def test_atem_monitor_no_hardcoded_backoffs(self):
        """atem_monitor source must not contain the old hardcoded _BACKOFFS variable."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "adapters" / "atem_monitor.py"
        text = src.read_text(encoding="utf-8")
        self.assertNotIn(
            "_BACKOFFS",
            text,
            "atem_monitor._BACKOFFS was removed; use domain.retry_policy.ATEM_RETRY_POLICY",
        )

    def test_atem_monitor_references_atem_retry_policy(self):
        """atem_monitor source must reference ATEM_RETRY_POLICY from domain."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "adapters" / "atem_monitor.py"
        text = src.read_text(encoding="utf-8")
        self.assertIn("ATEM_RETRY_POLICY", text)

    def test_atem_retry_policy_accessible_from_domain(self):
        from domain.retry_policy import ATEM_RETRY_POLICY as p
        self.assertGreater(p.max_attempts, 1)
        self.assertIsInstance(p.backoffs, tuple)


if __name__ == "__main__":
    unittest.main()
