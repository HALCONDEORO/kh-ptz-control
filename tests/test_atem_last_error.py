#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_atem_last_error.py — Tests for ATEMMonitor.last_error property (#174).

Verifies that last_error is populated on connection failure, cleared on
successful connection, and initially empty.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QCoreApplication

if not QCoreApplication.instance():
    _app = QCoreApplication(sys.argv)

from adapters.atem_monitor import ATEMMonitor


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock(*, connect_raises=None, wait_ok=False):
    instance = MagicMock()
    instance.waitForConnection.return_value = wait_ok
    if connect_raises:
        instance.connect.side_effect = connect_raises
    mock_module = MagicMock()
    mock_module.ATEMMax.return_value = instance
    return mock_module, instance


def _run_monitor(monitor, timeout_ms=5000):
    with patch("adapters.atem_monitor._sim_is_active", return_value=False):
        try:
            monitor.start()
            monitor.wait(timeout_ms)
        finally:
            if monitor.isRunning():
                monitor.requestInterruption()
                monitor.wait(2000)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestLastError:

    def test_last_error_initially_empty(self):
        mon = ATEMMonitor("192.168.1.1")
        assert mon.last_error == ""

    def test_last_error_set_on_timeout(self):
        mock_module, instance = _make_mock(wait_ok=False)
        instance.connect.side_effect = None  # connect succeeds; waitForConnection times out

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(ATEMMonitor, "_wait_interruptible", return_value=False):
            mon = ATEMMonitor("192.168.1.1")
            _run_monitor(mon)

        assert mon.last_error != "", "Expected last_error to be set after timeout"
        assert "192.168.1.1" in mon.last_error or "attempt" in mon.last_error

    def test_last_error_set_on_connection_exception(self):
        mock_module, instance = _make_mock(connect_raises=OSError("Connection refused"))

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(ATEMMonitor, "_wait_interruptible", return_value=False):
            mon = ATEMMonitor("192.168.1.1")
            _run_monitor(mon)

        assert "Connection refused" in mon.last_error

    def test_last_error_cleared_on_successful_connection(self):
        mock_module, instance = _make_mock(wait_ok=True)
        instance.connect.side_effect = None

        # Simulate one poll then interrupt

        def _fake_poll(self, atem):
            self.requestInterruption()

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(ATEMMonitor, "_poll_loop", _fake_poll):
            mon = ATEMMonitor("192.168.1.1")
            mon.last_error = "previous error"
            _run_monitor(mon)

        assert mon.last_error == "", "last_error should be cleared after successful connection"

    def test_last_error_not_set_when_not_configured(self):
        mon = ATEMMonitor("")
        _run_monitor(mon)
        assert mon.last_error == ""

    def test_last_error_not_set_on_missing_dependency(self):
        with patch.dict(sys.modules, {"PyATEMMax": None}):
            mon = ATEMMonitor("192.168.1.1")
            _run_monitor(mon)
        assert mon.last_error == ""
