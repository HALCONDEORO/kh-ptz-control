#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/connectivity.py — Modo de conectividad y política de red
#
# Sin I/O. Solo constantes y lógica pura de dominio.

from __future__ import annotations

from enum import Enum
from typing import Optional


class ConnectivityMode(str, Enum):
    """Modo de conectividad de la instalación."""
    OFFLINE = "offline"   # Sin internet — modo seguro por defecto para instalaciones cliente
    ONLINE  = "online"    # Con internet — opcional, para futuras funciones online
    HYBRID  = "hybrid"    # Reservado — combinación de ambos modos


# Modo por defecto: offline-first para proteger instalaciones existentes
DEFAULT_CONNECTIVITY_MODE = ConnectivityMode.OFFLINE

KNOWN_MODE_VALUES = {m.value for m in ConnectivityMode}


def parse_connectivity_mode(value: str) -> Optional[ConnectivityMode]:
    """Return ConnectivityMode for *value*, or None if unrecognised."""
    try:
        return ConnectivityMode(value)
    except ValueError:
        return None


def requires_internet(mode: ConnectivityMode) -> bool:
    """Return True only if the mode requires internet access."""
    return mode == ConnectivityMode.ONLINE
