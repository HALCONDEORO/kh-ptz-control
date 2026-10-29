#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# adapters/input/joystick_adapter.py — Traduce eventos del joystick al EventBus
#
# El widget DigitalJoystick llama a handlers con (pan_spd, tilt_spd).
# Este adaptador los convierte en eventos del bus, manteniendo el widget
# sin dependencias de la capa de aplicación.

from __future__ import annotations

from core.events import AsyncEventBus, EventType


class JoystickAdapter:
    """
    Conecta un DigitalJoystick con el AsyncEventBus.

    Uso en main_window:
        adapter = JoystickAdapter(bus, active_camera_fn)
        right_panel.connect_joystick(
            handlers=adapter.handlers(),
            stop_handler=adapter.stop,
        )
    """

    def __init__(self, bus: AsyncEventBus, active_camera_fn) -> None:
        self._bus = bus
        self._get_active_camera = active_camera_fn

    def handlers(self) -> dict:
        """Devuelve el dict de handlers para connect_joystick()."""
        return {
            'up':        lambda ps, ts: self._move(0,   ts),
            'down':      lambda ps, ts: self._move(0,  -ts),
            'left':      lambda ps, ts: self._move(-ps,  0),
            'right':     lambda ps, ts: self._move(ps,   0),
            'upleft':    lambda ps, ts: self._move(-ps,  ts),
            'upright':   lambda ps, ts: self._move(ps,   ts),
            'downleft':  lambda ps, ts: self._move(-ps, -ts),
            'downright': lambda ps, ts: self._move(ps,  -ts),
        }

    def stop(self) -> None:
        self._bus.emit(
            EventType.CAMERA_STOP,
            camera=self._get_active_camera(),
        )

    def _move(self, pan: int, tilt: int) -> None:
        self._bus.emit(
            EventType.CAMERA_MOVE,
            camera=self._get_active_camera(),
            pan_speed=pan,
            tilt_speed=tilt,
        )
