#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# atem_state.py — Estado explícito del switcher ATEM

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class ATEMState(Enum):
    NOT_CONFIGURED     = auto()   # IP vacía o archivo ATEMIP.txt ausente
    DEPENDENCY_MISSING = auto()   # PyATEMMax no instalado
    CONNECTING         = auto()   # intento de conexión en curso
    CONNECTED          = auto()   # conexión activa y funcionando
    DISCONNECTED       = auto()   # timeout o pérdida de conexión limpia
    ERROR              = auto()   # excepción inesperada durante operación
    RECONNECTING       = auto()   # reintento de conexión tras desconexión


ATEM_SUPERVISOR_TERMINAL_OK = frozenset({
    ATEMState.NOT_CONFIGURED,
    ATEMState.DEPENDENCY_MISSING,
    ATEMState.DISCONNECTED,
})


@dataclass(frozen=True)
class ATEMPiPState:
    """Estado instantáneo del Picture-in-Picture del ATEM.

    enabled  — True mientras el PiP esté activo en el switcher.
    source   — Número de input ATEM visible en la ventana PiP (None = desconocido).
    """
    enabled: bool
    source: int | None = None


@dataclass(frozen=True)
class AtemAutomationState:
    """Snapshot del estado de la automatización ATEM para UI/diagnósticos.

    Campos de deduplicación (last_input, last_pip_enabled) reflejan el
    último estado conocido en el dispatcher.  None significa «nunca visto».
    Útil para diagnosticar por qué un evento fue ignorado (deduplicado).
    """
    armed: bool
    log_only: bool
    reconnect_guard: bool
    manual_cooldown_active: bool
    blocked_reason: str               # "" cuando no bloqueado
    last_input: int | None
    pip_automation_enabled: bool = True   # False → PiP tracked but not acted on
    last_pip_enabled: bool | None = None  # último estado PiP visto por el dispatcher


def is_atem_supervisor_healthy(
    *,
    is_running: bool,
    restart_pending: bool,
    state: ATEMState | None,
) -> bool:
    """Devuelve si el supervisor debe considerar sano el monitor ATEM."""
    if is_running or restart_pending:
        return True
    return state in ATEM_SUPERVISOR_TERMINAL_OK
