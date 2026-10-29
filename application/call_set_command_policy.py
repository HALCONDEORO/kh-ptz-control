#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/call_set_command_policy.py — Servicio de política CALL/SET (#536)
#
# Único punto de decisión para acciones CALL/SET en el producto.
# Sin Qt, sin VISCA, sin efectos secundarios: recibe contexto, devuelve decisión.
#
# Contrato definido en #535. Tests en tests/test_call_set_policy.py.

from __future__ import annotations

from domain.call_set_policy import (
    CallSetAction,
    InputType,
    OperatingMode,
    PolicyDecision,
)

# Entradas que representan "intención de acción directa" → CALL
_CALL_INPUTS: frozenset[InputType] = frozenset({
    InputType.TAP,
    InputType.LEFT_CLICK,
    InputType.SHORT_PRESS,
})

# Entradas que representan "intención de configuración" → SET (solo admin/installer)
_SET_INPUTS: frozenset[InputType] = frozenset({
    InputType.RIGHT_CLICK,
    InputType.LONG_PRESS,
})

# Modos de trabajo y roles que bloquean toda acción de cámara real.
_ALWAYS_BLOCKED: dict[OperatingMode, str] = {
    OperatingMode.DEMO:        "demo_mode_no_real_camera",
    OperatingMode.SUPPORT:     "support_mode_no_camera_action",
    # Modos de trabajo temporales
    OperatingMode.NAME_EDIT:   "name_edit_no_camera_action",
    OperatingMode.NAMES:       "names_mode_data_only",       # alias legacy
    OperatingMode.LAYOUT_EDIT: "layout_edit_no_camera_action",
    OperatingMode.PRESET_TEST: "preset_test_no_direct_action",
}

# Roles que pueden hacer SET (con confirmación obligatoria).
_SET_ALLOWED_ROLES: frozenset[OperatingMode] = frozenset({
    OperatingMode.CAMERA_OPERATOR,
    OperatingMode.TECHNICIAN,
    OperatingMode.SYSTEM_ADMIN,
    OperatingMode.ADMIN_INSTALLER,  # alias legacy de technician
})

# Roles que solo pueden hacer CALL (sin SET).
_CALL_ONLY_ROLES: frozenset[OperatingMode] = frozenset({
    OperatingMode.BASIC_OPERATOR,
    OperatingMode.OPERATOR,         # alias legacy de basic_operator
})


class CallSetCommandPolicy:
    """
    Decide si una acción CALL o SET está permitida dadas las condiciones actuales.

    Jerarquía de roles (#718 #719):
      basic_operator / operator  → solo CALL.
      camera_operator            → CALL + SET con confirmación.
      technician / admin_installer → CALL + SET con confirmación.
      system_admin               → CALL + SET con confirmación.
      support                    → bloqueado (sin acciones reales de cámara).
      demo                       → bloqueado (sin hardware real).

    Modos de trabajo temporales (name_edit, layout_edit, preset_test):
      Bloquean todas las acciones de cámara independientemente del rol.
    """

    def decide(
        self,
        mode: OperatingMode,
        input_type: InputType,
        session_active: bool,
        camera_available: bool,
    ) -> PolicyDecision:

        # 1. Roles/modos que bloquean siempre (independientemente del estado)
        if mode in _ALWAYS_BLOCKED:
            return PolicyDecision(
                action=CallSetAction.NONE,
                allowed=False,
                requires_confirmation=False,
                reason_code=_ALWAYS_BLOCKED[mode],
            )

        # 2. Precondiciones de estado (roles operativos)
        if not session_active:
            return PolicyDecision(
                action=CallSetAction.NONE,
                allowed=False,
                requires_confirmation=False,
                reason_code="session_inactive",
            )

        if not camera_available:
            return PolicyDecision(
                action=CallSetAction.NONE,
                allowed=False,
                requires_confirmation=False,
                reason_code="camera_unavailable",
            )

        # 3. Drag nunca es acción de cámara
        if input_type == InputType.DRAG:
            return PolicyDecision(
                action=CallSetAction.NONE,
                allowed=False,
                requires_confirmation=False,
                reason_code="drag_not_a_camera_action",
            )

        # 4. Entradas CALL → permitido para todos los roles operativos
        if input_type in _CALL_INPUTS:
            return PolicyDecision(
                action=CallSetAction.CALL,
                allowed=True,
                requires_confirmation=False,
                reason_code="",
            )

        # 5. Entradas SET
        if input_type in _SET_INPUTS:
            if mode in _CALL_ONLY_ROLES:
                # basic_operator / operator: no pueden SET
                return PolicyDecision(
                    action=CallSetAction.NONE,
                    allowed=False,
                    requires_confirmation=False,
                    reason_code="operator_no_set",
                )
            if mode in _SET_ALLOWED_ROLES:
                # camera_operator / technician / system_admin: SET con confirmación
                return PolicyDecision(
                    action=CallSetAction.SET,
                    allowed=True,
                    requires_confirmation=True,
                    reason_code="",
                )
            # Rol desconocido en entradas SET → bloquear por seguridad
            return PolicyDecision(
                action=CallSetAction.NONE,
                allowed=False,
                requires_confirmation=False,
                reason_code="role_no_set",
            )

        # Entrada desconocida (no debería ocurrir con el enum completo)
        return PolicyDecision(
            action=CallSetAction.NONE,
            allowed=False,
            requires_confirmation=False,
            reason_code="unknown_input",
        )
