#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# core/state.py — Única fuente de verdad del estado del sistema
#
# Sin Qt. Sin I/O. Solo datos.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CameraState:
    connected: bool = False
    pan_speed: int = 0
    tilt_speed: int = 0
    zoom_position: Optional[int] = None
    active_preset: Optional[int] = None
    focus_mode: str = 'auto'
    exposure_level: int = 0
    backlight_on: bool = False


@dataclass
class SessionState:
    active: bool = False
    chairman_name: Optional[str] = None


@dataclass
class SystemState:
    cam1: CameraState = field(default_factory=CameraState)
    cam2: CameraState = field(default_factory=CameraState)
    session: SessionState = field(default_factory=SessionState)
    active_camera: int = 1  # 1 = Platform, 2 = Comments

    def camera(self, index: int) -> CameraState:
        if index == 1:
            return self.cam1
        if index == 2:
            return self.cam2
        raise ValueError(f"invalid camera index {index!r}: must be 1 or 2")
