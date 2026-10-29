#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/shutdown_intent.py — Shutdown intent contract (#766).

from enum import Enum


class ShutdownIntent(Enum):
    """Operator's explicit choice at app-exit time.

    CANCEL                     — do not close the app.
    EXIT_KEEP_CAMERAS_ON       — close app; send no standby/power-off to cameras.
    EXIT_AND_POWER_OFF_CAMERAS — close app and send standby to all cameras.
    """
    CANCEL = "cancel"
    EXIT_KEEP_CAMERAS_ON = "exit_keep_cameras_on"
    EXIT_AND_POWER_OFF_CAMERAS = "exit_and_power_off_cameras"
