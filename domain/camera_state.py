#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/camera_state.py — Estado explícito de conexión de cámara PTZ

from __future__ import annotations

from enum import Enum, auto


class CameraConnectionState(Enum):
    UNKNOWN      = auto()  # estado inicial / aún no se ha intentado conectar
    CONNECTING   = auto()  # intento TCP en curso
    CONNECTED    = auto()  # socket abierto y respondiendo
    DISCONNECTED = auto()  # desconexión limpia o reintentos agotados
    ERROR        = auto()  # excepción inesperada durante operación
    SIMULATED    = auto()  # conectado al simulador de hardware


def is_camera_usable(state: CameraConnectionState) -> bool:
    """Devuelve True si la cámara está operativa (real o simulada)."""
    return state in (CameraConnectionState.CONNECTED, CameraConnectionState.SIMULATED)
