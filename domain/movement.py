#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/movement.py — Camera movement state model
#
# Pure domain model — no I/O, no Qt, no threading.
# Runtime state only: not persisted to layout or config.

from __future__ import annotations

from enum import Enum


class MovementState(str, Enum):
    IDLE              = "idle"
    MOVING_TO_PRESET  = "moving_to_preset"
    MANUAL_ACTIVE     = "manual_control_active"
    ERROR             = "error"
