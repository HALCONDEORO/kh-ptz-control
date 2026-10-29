#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ptz/visca/types.py — Enums y constantes VISCA puras (sin dependencias externas)

from enum import IntEnum


class PanDir(IntEnum):
    LEFT  = 0x01
    RIGHT = 0x02
    STOP  = 0x03


class TiltDir(IntEnum):
    UP   = 0x01
    DOWN = 0x02
    STOP = 0x03


ZOOM_MAX: int = 0x4000  # 16384 — valor VISCA máximo de zoom (wide=0, tele=0x4000)
