#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# gpio_monitor.py — Physical screen button listener via Raspberry Pi GPIO

from __future__ import annotations

import logging
import os
import platform
import time

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

# BCM pin number for the physical screen power button.
# Override via environment variable: HALLPTZ_GPIO_SCREEN_BTN_PIN=<pin>
GPIO_SCREEN_BUTTON_PIN: int = int(os.getenv("HALLPTZ_GPIO_SCREEN_BTN_PIN", "17"))

# Minimum seconds between two button-press events (debounce)
_DEBOUNCE_SECS = 0.5
_POLL_SECS = 0.05


class GpioMonitor(QThread):
    """Poll a GPIO pin and emit ``button_pressed`` on an active-low press.

    GPIO is an optional appliance integration. A missing/unsupported GPIO
    library, insufficient OS permissions, or hardware initialisation failure
    must never abort the main Qt application.
    """

    button_pressed = pyqtSignal()

    def __init__(self, pin: int = GPIO_SCREEN_BUTTON_PIN, parent=None):
        super().__init__(parent)
        self._pin = pin

    def run(self) -> None:
        """Poll the button pin until interrupted.

        The GPIO button is optional hardware. Every failure mode here — missing
        module, a backend that imports but cannot drive real pins, a pin already
        claimed by another process — must disable only this monitor. Nothing may
        propagate out of run(), because an exception escaping a QThread aborts
        the whole Qt process and takes the application down with it (#882).
        """
        try:
            import RPi.GPIO as GPIO
        except Exception as exc:  # ImportError, but also broken/partial backends
            logger.warning("[GpioMonitor] RPi.GPIO not available (%s) — GPIO monitor disabled", exc)
            return

        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        except Exception as exc:
            # e.g. RuntimeError("Not running on a RPi!") on non-Pi or restricted hardware
            logger.warning(
                "[GpioMonitor] could not initialise GPIO%d (%s) — monitor disabled",
                self._pin,
                exc,
            )
            self._safe_cleanup(GPIO)
            return

        logger.info("[GpioMonitor] monitoring GPIO%d for screen button", self._pin)

        last_state = GPIO.HIGH
        last_press_time = 0.0

        try:
            while not self.isInterruptionRequested():
                state = GPIO.input(self._pin)
                now = time.monotonic()
                if (
                    last_state == GPIO.HIGH
                    and state == GPIO.LOW
                    and (now - last_press_time) >= _DEBOUNCE_SECS
                ):
                    logger.info("[GpioMonitor] screen button pressed (GPIO%d)", self._pin)
                    self.button_pressed.emit()
                    last_press_time = now
                last_state = state
                time.sleep(_POLL_SECS)
        except (RuntimeError, OSError, ValueError) as exc:
            # The expected hardware failures: pin revoked, device unplugged,
            # permissions withdrawn mid-run. A one-line warning is enough.
            logger.warning(
                "[GpioMonitor] GPIO%d polling stopped (%s) — monitor disabled",
                self._pin,
                exc,
            )
        except Exception:
            # Anything else is a bug rather than a hardware condition, so keep
            # an actionable traceback in the service log — but still fail closed
            # instead of taking down the operator UI.
            logger.exception("[GpioMonitor] unexpected GPIO failure — monitor disabled")
        finally:
            self._safe_cleanup(GPIO)

    def _safe_cleanup(self, GPIO) -> None:
        """Release the pin, tolerating a backend that never initialised."""
        try:
            GPIO.cleanup(self._pin)
        except Exception as exc:
            logger.debug("[GpioMonitor] GPIO%d cleanup failed (%s)", self._pin, exc)
        else:
            logger.info("[GpioMonitor] GPIO%d cleaned up", self._pin)

    @staticmethod
    def is_available() -> bool:
        """Best-effort check that a usable GPIO backend is present.

        A successful import is not proof the pins can be driven, so run() stays
        defensive regardless of what this returns.
        """
        if platform.system() != "Linux":
            return False
        try:
            import RPi.GPIO  # noqa: F401
            return True
        except Exception:
            # Broad on purpose: a partially-installed backend can raise almost
            # anything on import, and "GPIO unavailable" is always the right
            # answer here.
            return False
