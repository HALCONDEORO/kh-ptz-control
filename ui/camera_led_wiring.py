#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/camera_led_wiring.py — LED ámbar de (re)conexión de cámara
# (extraído de MainWindow — presupuesto anti-god-object).

from __future__ import annotations

from domain.camera_state import CameraConnectionState


def wire_connecting_led(main_window, worker) -> None:
    """LED ámbar mientras el worker intenta (re)conectar con la cámara.

    Se cablea para CADA worker, igual que connection_changed, para que el
    indicador siga al worker actual tras un cambio de IP.
    """
    def _on_state_changed(state, _ip=worker.ip) -> None:
        try:
            cam_key = main_window._cameras.cam_key(_ip)
        except ValueError:
            return
        (main_window.Cam1 if cam_key == 1 else main_window.Cam2).set_connecting(
            state is CameraConnectionState.CONNECTING)

    worker.signals.connection_state_changed.connect(_on_state_changed)
