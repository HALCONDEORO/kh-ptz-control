#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_gpio_monitor.py — Tests for adapters/gpio_monitor.py

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# Stub PyQt5 with a *real* QThread base class so GpioMonitor stays a proper
# Python class and its static methods / class body remain accessible.
class _FakeQThread:
    def __init__(self, parent=None):
        pass

    def isInterruptionRequested(self) -> bool:
        return True  # makes any run() loop exit immediately in tests


_fake_qtcore = MagicMock()
_fake_qtcore.QThread = _FakeQThread
_fake_qtcore.pyqtSignal = lambda *a, **kw: MagicMock()

sys.modules.setdefault("PyQt5", MagicMock())
sys.modules.setdefault("PyQt5.QtCore", _fake_qtcore)

import adapters.gpio_monitor as gm  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level constants
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_default_pin_is_17(self):
        assert gm.GPIO_SCREEN_BUTTON_PIN == 17

    def test_debounce_secs(self):
        assert gm._DEBOUNCE_SECS == 0.5

    def test_poll_secs(self):
        assert gm._POLL_SECS == 0.05


# ═══════════════════════════════════════════════════════════════════════════════
# GpioMonitor.is_available()
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsAvailable:
    def test_returns_false_on_non_linux(self, monkeypatch):
        monkeypatch.setattr(gm.platform, "system", lambda: "Windows")
        assert gm.GpioMonitor.is_available() is False

    def test_returns_false_on_macos(self, monkeypatch):
        monkeypatch.setattr(gm.platform, "system", lambda: "Darwin")
        assert gm.GpioMonitor.is_available() is False

    def test_returns_false_on_linux_without_gpio(self, monkeypatch):
        monkeypatch.setattr(gm.platform, "system", lambda: "Linux")
        with patch.dict(sys.modules, {"RPi": None, "RPi.GPIO": None}):
            assert gm.GpioMonitor.is_available() is False

    def test_returns_true_on_linux_with_gpio(self, monkeypatch):
        monkeypatch.setattr(gm.platform, "system", lambda: "Linux")
        mock_gpio = MagicMock()
        with patch.dict(sys.modules, {"RPi": mock_gpio, "RPi.GPIO": mock_gpio}):
            assert gm.GpioMonitor.is_available() is True

    def test_platform_check_happens_before_import(self, monkeypatch):
        monkeypatch.setattr(gm.platform, "system", lambda: "Windows")
        # RPi.GPIO absent; result should still be False (platform checked first)
        with patch.dict(sys.modules, {"RPi": None, "RPi.GPIO": None}):
            assert gm.GpioMonitor.is_available() is False


# ═══════════════════════════════════════════════════════════════════════════════
# GpioMonitor.run() — early exit when RPi.GPIO not importable
# ═══════════════════════════════════════════════════════════════════════════════

class TestRun:
    def _make_monitor(self, pin: int = 17) -> gm.GpioMonitor:
        m = gm.GpioMonitor.__new__(gm.GpioMonitor)
        m._pin = pin
        return m

    def _make_gpio(self) -> MagicMock:
        gpio = MagicMock()
        gpio.HIGH = 1
        gpio.LOW = 0
        gpio.input.return_value = 1
        return gpio

    def test_run_returns_none_without_gpio(self):
        monitor = self._make_monitor()
        with patch.dict(sys.modules, {"RPi": None, "RPi.GPIO": None}):
            result = monitor.run()
        assert result is None

    def test_run_does_not_raise_without_gpio(self):
        monitor = self._make_monitor()
        with patch.dict(sys.modules, {"RPi": None, "RPi.GPIO": None}):
            monitor.run()  # must not raise


# ═══════════════════════════════════════════════════════════════════════════════
# GpioMonitor.run() — optional GPIO failures must never abort the application
#
# Regression tests for #882: on the first real Raspberry Pi install, RPi.GPIO
# imported successfully but GPIO.setup() raised RuntimeError("Not running on a
# RPi!"). The exception escaped the QThread and killed the whole Qt process
# (status=6/ABRT), so the GUI never opened and systemd restart-looped.
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunFailuresAreContained:
    def _make_monitor(self, pin: int = 17) -> gm.GpioMonitor:
        m = gm.GpioMonitor.__new__(gm.GpioMonitor)
        m._pin = pin
        return m

    def _make_gpio(self):
        """Return (gpio, modules) where modules is ready for patch.dict(sys.modules).

        `import RPi.GPIO as GPIO` binds getattr(RPi, "GPIO"), so the parent
        package mock must expose the same child object we assert against.
        """
        gpio = MagicMock()
        gpio.HIGH = 1
        gpio.LOW = 0
        gpio.input.return_value = 1
        parent = MagicMock()
        parent.GPIO = gpio
        return gpio, {"RPi": parent, "RPi.GPIO": gpio}

    def test_setup_runtime_error_does_not_propagate(self):
        """The exact failure seen on the Pi: module imports, setup() rejects."""
        gpio, modules = self._make_gpio()
        gpio.setup.side_effect = RuntimeError("Not running on a RPi!")
        monitor = self._make_monitor()
        with patch.dict(sys.modules, modules):
            assert monitor.run() is None  # must not raise

    def test_setmode_failure_does_not_propagate(self):
        gpio, modules = self._make_gpio()
        gpio.setmode.side_effect = RuntimeError("mode already set")
        monitor = self._make_monitor()
        with patch.dict(sys.modules, modules):
            assert monitor.run() is None

    def test_input_failure_does_not_propagate(self):
        gpio, modules = self._make_gpio()
        gpio.input.side_effect = RuntimeError("pin not configured")
        monitor = self._make_monitor()
        with patch.object(gm.GpioMonitor, "isInterruptionRequested", side_effect=[False, True]):
            with patch.dict(sys.modules, modules):
                assert monitor.run() is None

    def test_cleanup_failure_does_not_propagate(self):
        gpio, modules = self._make_gpio()
        gpio.cleanup.side_effect = RuntimeError("cleanup failed")
        monitor = self._make_monitor()
        with patch.object(gm.GpioMonitor, "isInterruptionRequested", return_value=True):
            with patch.dict(sys.modules, modules):
                assert monitor.run() is None

    def test_import_error_other_than_import_does_not_propagate(self):
        """A backend that raises on import (not just ImportError) is tolerated."""
        monitor = self._make_monitor()

        class _Exploding:
            def __getattr__(self, name):
                raise RuntimeError("broken backend")

        with patch.dict(sys.modules, {"RPi": _Exploding(), "RPi.GPIO": _Exploding()}):
            assert monitor.run() is None

    def test_pin_is_released_when_setup_fails(self):
        gpio, modules = self._make_gpio()
        gpio.setup.side_effect = RuntimeError("Not running on a RPi!")
        monitor = self._make_monitor(pin=17)
        with patch.dict(sys.modules, modules):
            monitor.run()
        gpio.cleanup.assert_called_once_with(17)

    def test_successful_run_still_cleans_up(self):
        gpio, modules = self._make_gpio()
        monitor = self._make_monitor(pin=17)
        with patch.object(gm.GpioMonitor, "isInterruptionRequested", return_value=True):
            with patch.dict(sys.modules, modules):
                monitor.run()
        gpio.setup.assert_called_once()
        gpio.cleanup.assert_called_once_with(17)
