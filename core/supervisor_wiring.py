#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# core/supervisor_wiring.py — Cableado del Supervisor de threads de la app
# (extraído de MainWindow para mantener ui/main_window.py dentro de su
# presupuesto anti-god-object, ver tests/test_ui_god_object_budget.py).

from __future__ import annotations

from config import WORKER_STUCK_TIMEOUT_S
from core.supervisor import Supervisor


def build_supervisor(main_window) -> Supervisor:
    """Registra los workers de cámara y el monitor ATEM y arranca el supervisor.

    Los lambdas capturan el objeto worker (no la variable local), así que
    seguirán apuntando al mismo worker aunque esta función ya haya retornado.

    Salud = hilo vivo Y con señales de vida recientes: un hilo bloqueado
    (p.ej. un callback que no retorna) también se reinicia. Si el hilo
    colgado no termina en la espera acotada, CameraWorker.restart() no
    crea otro hilo (nunca dos workers por cámara) y marca la cámara ERROR.
    """
    sup = Supervisor()
    cam1 = main_window._cameras.worker(main_window._cameras.ip_for_key(1))
    cam2 = main_window._cameras.worker(main_window._cameras.ip_for_key(2))
    sup.registrar(
        "camera_worker_cam1",
        lambda: cam1._thread.is_alive() and cam1.progress_age() < WORKER_STUCK_TIMEOUT_S,
        cam1.restart,
    )
    sup.registrar(
        "camera_worker_cam2",
        lambda: cam2._thread.is_alive() and cam2.progress_age() < WORKER_STUCK_TIMEOUT_S,
        cam2.restart,
    )
    # El lambda evalúa main_window._atem_monitor en tiempo de ejecución, por lo
    # que siempre comprueba la instancia activa incluso tras un reinicio.
    sup.registrar(
        "atem_monitor",
        main_window._atem_monitor_is_healthy,
        main_window._restart_atem_monitor,
    )
    sup.start()
    return sup
