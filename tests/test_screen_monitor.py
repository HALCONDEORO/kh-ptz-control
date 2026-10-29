#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_screen_monitor.py — Tests for adapters/screen_monitor.py

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch


# Stub Qt before importing the module so tests run without PyQt5 installed.
sys.modules.setdefault("PyQt5", MagicMock())
sys.modules.setdefault("PyQt5.QtCore", MagicMock())

import adapters.screen_monitor as sm  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# _is_monitor_on — parses xset output
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsMonitorOn:
    def _run_with_stdout(self, stdout: str):
        fake = MagicMock()
        fake.stdout = stdout
        with patch.object(sm.subprocess, "run", return_value=fake):
            return sm._is_monitor_on()

    def test_monitor_on_returns_true(self):
        output = "Monitor is On\n"
        assert self._run_with_stdout(output) is True

    def test_monitor_off_returns_false(self):
        output = "Monitor is Off\n"
        assert self._run_with_stdout(output) is False

    def test_monitor_standby_returns_false(self):
        output = "Monitor is Standby\n"
        assert self._run_with_stdout(output) is False

    def test_monitor_suspend_returns_false(self):
        output = "Monitor is Suspend\n"
        assert self._run_with_stdout(output) is False

    def test_no_monitor_line_defaults_true(self):
        output = "DPMS (Energy Star):\n  Standby: 600\n"
        assert self._run_with_stdout(output) is True

    def test_multiline_output_finds_monitor_line(self):
        output = (
            "Keyboard Control:\n"
            "  auto repeat:  on\n"
            "DPMS (Energy Star):\n"
            "  Standby: 0\n"
            "Monitor is On\n"
        )
        assert self._run_with_stdout(output) is True

    def test_timeout_error_returns_true(self):
        with patch.object(sm.subprocess, "run", side_effect=subprocess.TimeoutExpired("xset", 2)):
            assert sm._is_monitor_on() is True

    def test_os_error_returns_true(self):
        with patch.object(sm.subprocess, "run", side_effect=OSError("not found")):
            assert sm._is_monitor_on() is True

    def test_empty_output_returns_true(self):
        assert self._run_with_stdout("") is True


# ═══════════════════════════════════════════════════════════════════════════════
# _xset — calls subprocess with xset and given args
# ═══════════════════════════════════════════════════════════════════════════════

class TestXset:
    def test_calls_subprocess_run(self):
        calls = []
        with patch.object(sm.subprocess, "run", lambda cmd, **kw: calls.append(cmd)):
            sm._xset("dpms", "force", "on")
        assert calls == [["xset", "dpms", "force", "on"]]

    def test_oserror_is_swallowed(self):
        with patch.object(sm.subprocess, "run", side_effect=OSError("xset missing")):
            sm._xset("s", "off")  # must not raise

    def test_timeout_is_swallowed(self):
        with patch.object(sm.subprocess, "run", side_effect=subprocess.TimeoutExpired("xset", 2)):
            sm._xset("q")  # must not raise
