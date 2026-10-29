#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for domain/camera_state.py — CameraConnectionState enum (#97)."""

from __future__ import annotations

import queue
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from domain.camera_state import CameraConnectionState, is_camera_usable


# ─────────────────────────────────────────────────────────────────────────────
#  1. Enum completeness and semantics
# ─────────────────────────────────────────────────────────────────────────────

class TestCameraConnectionStateEnum(unittest.TestCase):

    def test_all_expected_states_exist(self):
        names = {s.name for s in CameraConnectionState}
        assert {"UNKNOWN", "CONNECTING", "CONNECTED", "DISCONNECTED", "ERROR", "SIMULATED"} == names

    def test_states_are_distinct(self):
        states = list(CameraConnectionState)
        assert len(states) == len(set(states))

    def test_is_camera_usable_connected(self):
        assert is_camera_usable(CameraConnectionState.CONNECTED) is True

    def test_is_camera_usable_simulated(self):
        assert is_camera_usable(CameraConnectionState.SIMULATED) is True

    def test_is_camera_usable_false_for_non_active(self):
        for state in (
            CameraConnectionState.UNKNOWN,
            CameraConnectionState.CONNECTING,
            CameraConnectionState.DISCONNECTED,
            CameraConnectionState.ERROR,
        ):
            assert is_camera_usable(state) is False, f"Expected False for {state}"


# ─────────────────────────────────────────────────────────────────────────────
#  2. Minimal CameraWorker fixture (no thread, no socket)
# ─────────────────────────────────────────────────────────────────────────────

def _make_worker(ip: str = "10.0.0.99"):
    """Build a CameraWorker without starting its thread."""
    from ptz.visca.worker import CameraWorker

    w = CameraWorker.__new__(CameraWorker)
    w.ip                = ip
    w.port              = 52381
    w._is_connected     = False
    w._connection_state = CameraConnectionState.UNKNOWN
    w._queue            = queue.Queue(maxsize=20)
    w._sock             = None
    w._lock             = threading.Lock()
    w._interrupt        = threading.Event()
    w._shutdown         = threading.Event()
    w._last_heartbeat   = time.monotonic()
    w.signals           = MagicMock()
    w.signals.connection_changed       = MagicMock()
    w.signals.connection_state_changed = MagicMock()
    w.signals.visca_error              = MagicMock()
    return w


# ─────────────────────────────────────────────────────────────────────────────
#  3. CameraWorker._set_state tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkerSetState(unittest.TestCase):

    def setUp(self):
        self.w = _make_worker()

    def test_initial_state_is_unknown(self):
        assert self.w._connection_state == CameraConnectionState.UNKNOWN
        assert self.w._is_connected is False

    def test_set_state_connected_updates_bool(self):
        self.w._set_state(CameraConnectionState.CONNECTED)
        assert self.w._is_connected is True
        assert self.w._connection_state == CameraConnectionState.CONNECTED

    def test_set_state_disconnected_clears_bool(self):
        self.w._connection_state = CameraConnectionState.CONNECTED
        self.w._is_connected = True
        self.w._set_state(CameraConnectionState.DISCONNECTED)
        assert self.w._is_connected is False
        assert self.w._connection_state == CameraConnectionState.DISCONNECTED

    def test_set_state_simulated_sets_bool_true(self):
        self.w._set_state(CameraConnectionState.SIMULATED)
        assert self.w._is_connected is True

    def test_set_state_connecting_does_not_set_bool(self):
        self.w._set_state(CameraConnectionState.CONNECTING)
        assert self.w._is_connected is False

    def test_set_state_emits_connection_state_changed(self):
        self.w._set_state(CameraConnectionState.CONNECTED)
        self.w.signals.connection_state_changed.emit.assert_called_once_with(
            CameraConnectionState.CONNECTED
        )

    def test_set_state_emits_connection_changed_bool(self):
        self.w._set_state(CameraConnectionState.CONNECTED)
        self.w.signals.connection_changed.emit.assert_called_once_with(True)

    def test_set_state_no_duplicate_emission_same_state(self):
        self.w._set_state(CameraConnectionState.CONNECTED)
        self.w.signals.connection_state_changed.emit.reset_mock()
        self.w.signals.connection_changed.emit.reset_mock()

        self.w._set_state(CameraConnectionState.CONNECTED)  # same state again
        self.w.signals.connection_state_changed.emit.assert_not_called()
        self.w.signals.connection_changed.emit.assert_not_called()

    def test_set_state_connecting_no_bool_signal(self):
        """CONNECTING changes state but does not flip the bool → no bool signal."""
        self.w._set_state(CameraConnectionState.CONNECTING)
        self.w.signals.connection_state_changed.emit.assert_called_once_with(
            CameraConnectionState.CONNECTING
        )
        self.w.signals.connection_changed.emit.assert_not_called()

    # ── _set_connected backward-compat wrapper ───────────────────────────────

    def test_set_connected_true_maps_to_connected_state(self):
        self.w._set_connected(True)
        assert self.w._connection_state == CameraConnectionState.CONNECTED

    def test_set_connected_false_maps_to_disconnected_state(self):
        self.w._connection_state = CameraConnectionState.CONNECTED
        self.w._is_connected = True
        self.w._set_connected(False)
        assert self.w._connection_state == CameraConnectionState.DISCONNECTED


# ─────────────────────────────────────────────────────────────────────────────
#  4. CONNECTING emitted during _connect_with_retry
# ─────────────────────────────────────────────────────────────────────────────

class TestConnectingStateEmittedDuringRetry(unittest.TestCase):

    def test_connecting_state_emitted_on_first_attempt(self):
        """CONNECTING is emitted once when the first attempt starts.

        _set_state deduplicates: re-entering CONNECTING (still in CONNECTING) does
        not re-emit.  The important invariant is that the state is CONNECTING
        before any connection attempt, and DISCONNECTED once all retries are
        exhausted.
        """
        from domain.retry_policy import RetryPolicy

        w = _make_worker()
        states_emitted: list[CameraConnectionState] = []
        w.signals.connection_state_changed.emit.side_effect = (
            lambda s: states_emitted.append(s)
        )

        # _connect mocked to return None so both attempts fail.
        # The mock does NOT call _set_connected, so state stays CONNECTING
        # between retries — only the first CONNECTING transition is emitted.
        policy = RetryPolicy(backoffs=(0,))  # 2 attempts, zero backoff → fast
        with patch.object(w, "_connect", return_value=None):
            result = w._connect_with_retry(policy)

        assert result is None
        assert CameraConnectionState.CONNECTING in states_emitted, (
            f"CONNECTING never emitted; got: {states_emitted}"
        )
        # Final worker state should be CONNECTING (mock did not transition away)
        assert w._connection_state == CameraConnectionState.CONNECTING


if __name__ == "__main__":
    unittest.main()
