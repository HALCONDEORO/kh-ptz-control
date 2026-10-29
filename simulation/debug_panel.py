#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# simulation/debug_panel.py — Simulador de estado de cámara para modo sim
#
# Responsabilidad única: crear y conectar el label de debug de simulación
# (zoom/pan/tilt/cmd) que se añade al panel derecho cuando sim_mode está activo.
#
# Separado de right_panel.py para que la UI de producción no importe
# hardware_simulator directamente.
from __future__ import annotations

import adapters.hardware_simulator as _hw
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QLabel


def attach_sim_debug_panel(layout, main_window) -> None:
    """Add a live sim-state label to *layout* and start its refresh timer.

    Imports hardware_simulator here so production code paths never load it.
    *layout* is a QVBoxLayout. *main_window* must expose Cam1.isChecked().
    """
    layout.addSpacing(8)
    sim_lbl = QLabel("", layout.parentWidget())
    sim_lbl.setAlignment(Qt.AlignCenter)
    sim_lbl.setWordWrap(True)
    sim_lbl.setStyleSheet(
        "font: 700 16px 'IBM Plex Mono', 'Consolas'; color: #222;"
        " background: #E0E0E0; border-radius: 8px; padding: 12px 14px;"
    )
    layout.addWidget(sim_lbl)

    def _refresh():
        cam = _hw.active_cam1 if main_window.Cam1.isChecked() else _hw.active_cam2
        if cam is None:
            return
        with cam._lock:
            z    = int(cam.zoom / 0x4000 * 100)
            p    = int(cam.pan)
            t    = int(cam.tilt)
            ps   = int(cam.pan_spd)
            ts   = int(cam.tilt_spd)
            last = cam.last_cmd or "-"
        sim_lbl.setText(
            f"zoom  {z:3d}%\n"
            f"pan   {p:+7d}   spd {ps:2d}\n"
            f"tilt  {t:+7d}   spd {ts:2d}\n"
            f"cmd   {last}"
        )

    timer = QTimer(layout.parentWidget())
    timer.setInterval(150)
    timer.timeout.connect(_refresh)
    timer.start()
