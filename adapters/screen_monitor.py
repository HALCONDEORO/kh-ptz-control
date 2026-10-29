#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# screen_monitor.py — DPMS screen state monitor for camera auto-off prompt

from __future__ import annotations

import logging
import os
import platform
import subprocess
import time

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 2  # seconds between xset q polls


class ScreenMonitor(QThread):
    """Polls DPMS state every 2 s; emits screen_turned_off on On → Off/Standby/Suspend transition.

    Only meaningful on Linux with an active DISPLAY. Use is_available() before creating.
    """

    screen_turned_off = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_was_on = True

    def run(self):
        while not self.isInterruptionRequested():
            is_on = _is_monitor_on()
            if self._last_was_on and not is_on:
                logger.info("[ScreenMonitor] display went off — emitting screen_turned_off")
                self.screen_turned_off.emit()
            self._last_was_on = is_on
            time.sleep(_POLL_INTERVAL)

    @staticmethod
    def is_available() -> bool:
        return platform.system() == "Linux" and bool(os.getenv("DISPLAY"))

    @staticmethod
    def wake() -> None:
        _xset("dpms", "force", "on")

    @staticmethod
    def sleep() -> None:
        _xset("dpms", "force", "off")


def _xset(*args: str) -> None:
    try:
        subprocess.run(
            ["xset", *args],
            capture_output=True, timeout=2,
            env={**os.environ},
        )
    except Exception as exc:
        logger.warning("xset %s failed: %s", " ".join(args), exc)


def _is_monitor_on() -> bool:
    """Returns True if monitor reports On; False if Off/Standby/Suspend.
    Returns True on any error so we never spam the dialog on xset failure."""
    try:
        result = subprocess.run(
            ["xset", "q"],
            capture_output=True, text=True, timeout=2,
            env={**os.environ},
        )
        for line in result.stdout.splitlines():
            if "Monitor is" in line:
                return "On" in line
    except Exception:
        logger.debug("screen_monitor: xset query failed, assuming monitor On")
    return True
