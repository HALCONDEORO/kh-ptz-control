#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/call_set_policy.py — Tipos del contrato CALL/SET (#535)

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OperatingMode(str, Enum):
    """Modo de operación del producto en el momento de la acción.

    Roles persistentes (quién es el usuario):
      basic_operator   — solo CALL, sin SET ni movimiento manual.
      camera_operator  — CALL, SET con confirmación, movimiento PTZ, editar nombres.
                         Rol por defecto en una instalación limpia.
      technician       — todo lo de camera_operator + layout, configuración, diagnóstico.
      system_admin     — control total: usuarios, seguridad, backup, reset.
      support          — solo diagnóstico/lectura; sin acciones reales de cámara.
      demo             — operación simulada; nunca toca hardware real.

    Modos de trabajo temporales (tarea en curso, no persistida):
      name_edit    — edición de nombres; bloquea acciones de cámara.
      layout_edit  — edición de layout; bloquea acciones de cámara.
      preset_test  — validación de presets; requiere advertencia antes de mover cámaras.

    Aliases de compatibilidad (valores antiguos persistidos):
      operator        → basic_operator
      admin_installer → technician
      names           → name_edit
    """
    # ── Roles persistentes ────────────────────────────────────────────────
    BASIC_OPERATOR  = "basic_operator"
    CAMERA_OPERATOR = "camera_operator"
    TECHNICIAN      = "technician"
    SYSTEM_ADMIN    = "system_admin"
    SUPPORT         = "support"
    DEMO            = "demo"

    # ── Modos de trabajo temporales ───────────────────────────────────────
    NAME_EDIT   = "name_edit"
    LAYOUT_EDIT = "layout_edit"
    PRESET_TEST = "preset_test"

    # ── Aliases de compatibilidad (backward-compat) ───────────────────────
    OPERATOR        = "operator"         # → basic_operator
    ADMIN_INSTALLER = "admin_installer"  # → technician
    NAMES           = "names"            # → name_edit


class InputType(str, Enum):
    """Tipo de entrada del operador sobre un asiento o preset."""
    TAP         = "tap"
    LEFT_CLICK  = "left_click"
    SHORT_PRESS = "short_press"
    RIGHT_CLICK = "right_click"
    LONG_PRESS  = "long_press"
    DRAG        = "drag"


class CallSetAction(str, Enum):
    """Acción de cámara resultante de la decisión de política."""
    CALL = "call"
    SET  = "set"
    NONE = "none"


@dataclass(frozen=True)
class PolicyDecision:
    """
    Resultado de la decisión CALL/SET para una combinación de modo + entrada.

    allowed=True  → la acción puede ejecutarse.
    allowed=False → la acción está bloqueada; reason_code explica por qué.
    requires_confirmation=True → el llamador debe pedir confirmación al usuario
                                 antes de enviar el comando (solo SET admin).
    reason_code="" cuando allowed=True.
    """
    action:                CallSetAction
    allowed:               bool
    requires_confirmation: bool
    reason_code:           str
