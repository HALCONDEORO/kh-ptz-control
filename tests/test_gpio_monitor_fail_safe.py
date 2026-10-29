#!/usr/bin/env python3
"""Regression tests for issue #882: optional GPIO must never abort HALLPTZ."""

from __future__ import annotations

import sys
import types

from adapters.gpio_monitor import GpioMonitor


def _fake_gpio(monkeypatch, *, setup_error=None, input_error=None):
    package = types.ModuleType("RPi")
    gpio = types.ModuleType("RPi.GPIO")
    calls = {"setmode": 0, "setup": 0, "input": 0, "cleanup": 0}

    gpio.BCM = 11
    gpio.IN = 1
    gpio.PUD_UP = 22
    gpio.HIGH = 1
    gpio.LOW = 0

    def setmode(_mode):
        calls["setmode"] += 1

    def setup(_pin, _direction, *, pull_up_down):
        assert pull_up_down == gpio.PUD_UP
        calls["setup"] += 1
        if setup_error is not None:
            raise setup_error

    def input_(_pin):
        calls["input"] += 1
        if input_error is not None:
            raise input_error
        return gpio.HIGH

    def cleanup(_pin):
        calls["cleanup"] += 1

    gpio.setmode = setmode
    gpio.setup = setup
    gpio.input = input_
    gpio.cleanup = cleanup
    package.GPIO = gpio

    monkeypatch.setitem(sys.modules, "RPi", package)
    monkeypatch.setitem(sys.modules, "RPi.GPIO", gpio)
    return calls


def test_setup_runtime_error_is_non_fatal(monkeypatch, caplog):
    calls = _fake_gpio(
        monkeypatch,
        setup_error=RuntimeError("Not running on a RPi!"),
    )

    # Run synchronously so any exception escaping QThread.run fails this test.
    GpioMonitor(pin=17).run()

    assert calls["setmode"] == 1
    assert calls["setup"] == 1
    # A half-completed setup() can leave the pin partially claimed, so the
    # monitor always attempts a release; _safe_cleanup tolerates a backend that
    # never initialised.
    assert calls["cleanup"] == 1
    assert "monitor disabled" in caplog.text


def test_polling_error_is_non_fatal_and_cleans_up(monkeypatch, caplog):
    calls = _fake_gpio(
        monkeypatch,
        input_error=OSError("GPIO device unavailable"),
    )

    GpioMonitor(pin=17).run()

    assert calls["setup"] == 1
    assert calls["input"] == 1
    assert calls["cleanup"] == 1
    assert "monitor disabled" in caplog.text


def test_unexpected_gpio_exception_is_contained(monkeypatch, caplog):
    calls = _fake_gpio(
        monkeypatch,
        input_error=Exception("unexpected backend failure"),
    )

    GpioMonitor(pin=17).run()

    assert calls["cleanup"] == 1
    assert "unexpected GPIO failure" in caplog.text

