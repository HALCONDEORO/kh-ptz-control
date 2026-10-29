#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# simulation/sim_worker.py — Fachada de simulación VISCA
#
# Expone la misma interfaz que CameraWorker pero sin hardware real.
# Delegado en hardware_simulator para la implementación del servidor TCP mock.

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def start_simulation(cam1_ip: str, cam2_ip: str) -> tuple[bool, bool]:
    """
    Arranca los servidores VISCA simulados en las IPs dadas.

    Devuelve (ok_cam1, ok_cam2). Llamar antes de que CameraWorker intente conectar.
    """
    try:
        import adapters.hardware_simulator as _sim

        sim_c1 = _sim.SimCamera("CAM1-Platform")
        sim_c2 = _sim.SimCamera("CAM2-Comments")
        ok1 = _sim.ViscaServer(cam1_ip, sim_c1).start()
        ok2 = _sim.ViscaServer(cam2_ip, sim_c2).start()

        if ok1:
            _sim.active_cam1 = sim_c1
        if ok2:
            _sim.active_cam2 = sim_c2

        if not ok1 or not ok2:
            logger.warning("SimVISCA: algún servidor no arrancó (CAM1=%s CAM2=%s)", ok1, ok2)

        return ok1, ok2

    except ImportError as exc:
        logger.exception("simulation: no se puede importar hardware_simulator: %s", exc)
        return False, False


def is_simulation_active() -> bool:
    """True si el archivo de backup de IPs de simulación existe (sim_ip_backup.json)."""
    from adapters.sim_mode import BACKUP
    return BACKUP.exists()
