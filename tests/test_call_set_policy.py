#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_call_set_policy.py — Tests de regresión del contrato CALL/SET (#537)
#
# Cubre todo el contrato definido en #535 e implementado en #536.
# No requiere cámaras reales, Qt ni VISCA: prueba pura de política.

import pytest

from application.call_set_command_policy import CallSetCommandPolicy
from domain.call_set_policy import CallSetAction, InputType, OperatingMode

# ── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def policy():
    return CallSetCommandPolicy()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _call_inputs():
    return [InputType.TAP, InputType.LEFT_CLICK, InputType.SHORT_PRESS]


def _set_inputs():
    return [InputType.RIGHT_CLICK, InputType.LONG_PRESS]


# ── Basic Operator / legacy Operator mode ─────────────────────────────────────

class TestBasicOperatorMode:

    @pytest.mark.parametrize("mode", [OperatingMode.BASIC_OPERATOR, OperatingMode.OPERATOR])
    def test_tap_produces_call(self, policy, mode):
        d = policy.decide(mode, InputType.TAP,
                          session_active=True, camera_available=True)
        assert d.allowed is True
        assert d.action == CallSetAction.CALL
        assert d.requires_confirmation is False

    @pytest.mark.parametrize("mode", [OperatingMode.BASIC_OPERATOR, OperatingMode.OPERATOR])
    @pytest.mark.parametrize("input_type", _set_inputs())
    def test_set_blocked(self, policy, mode, input_type):
        """basic_operator no puede SET; long press no dispara CALL en release."""
        d = policy.decide(mode, input_type,
                          session_active=True, camera_available=True)
        assert d.allowed is False
        assert d.action == CallSetAction.NONE
        assert d.reason_code == "operator_no_set"

    def test_drag_blocked(self, policy):
        d = policy.decide(OperatingMode.BASIC_OPERATOR, InputType.DRAG,
                          session_active=True, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "drag_not_a_camera_action"

    @pytest.mark.parametrize("input_type", _call_inputs())
    def test_session_inactive_blocks_call(self, policy, input_type):
        d = policy.decide(OperatingMode.BASIC_OPERATOR, input_type,
                          session_active=False, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "session_inactive"

    @pytest.mark.parametrize("input_type", _call_inputs())
    def test_camera_unavailable_blocks_call(self, policy, input_type):
        d = policy.decide(OperatingMode.BASIC_OPERATOR, input_type,
                          session_active=True, camera_available=False)
        assert d.allowed is False
        assert d.reason_code == "camera_unavailable"


# ── Camera Operator mode ──────────────────────────────────────────────────────

class TestCameraOperatorMode:

    @pytest.mark.parametrize("input_type", _call_inputs())
    def test_call_inputs_produce_call(self, policy, input_type):
        d = policy.decide(OperatingMode.CAMERA_OPERATOR, input_type,
                          session_active=True, camera_available=True)
        assert d.allowed is True
        assert d.action == CallSetAction.CALL

    @pytest.mark.parametrize("input_type", _set_inputs())
    def test_set_inputs_produce_set_with_confirmation(self, policy, input_type):
        """camera_operator puede SET con confirmación obligatoria."""
        d = policy.decide(OperatingMode.CAMERA_OPERATOR, input_type,
                          session_active=True, camera_available=True)
        assert d.allowed is True
        assert d.action == CallSetAction.SET
        assert d.requires_confirmation is True

    def test_set_requires_confirmation_not_optional(self, policy):
        d = policy.decide(OperatingMode.CAMERA_OPERATOR, InputType.RIGHT_CLICK,
                          session_active=True, camera_available=True)
        assert d.requires_confirmation is True

    def test_drag_blocked(self, policy):
        d = policy.decide(OperatingMode.CAMERA_OPERATOR, InputType.DRAG,
                          session_active=True, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "drag_not_a_camera_action"

    @pytest.mark.parametrize("input_type", _call_inputs())
    def test_session_inactive_blocks(self, policy, input_type):
        d = policy.decide(OperatingMode.CAMERA_OPERATOR, input_type,
                          session_active=False, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "session_inactive"

    @pytest.mark.parametrize("input_type", _set_inputs())
    def test_session_inactive_blocks_set_too(self, policy, input_type):
        d = policy.decide(OperatingMode.CAMERA_OPERATOR, input_type,
                          session_active=False, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "session_inactive"


# ── Technician / legacy Admin Installer mode ──────────────────────────────────

class TestTechnicianMode:

    @pytest.mark.parametrize("mode", [OperatingMode.TECHNICIAN, OperatingMode.ADMIN_INSTALLER])
    @pytest.mark.parametrize("input_type", _call_inputs())
    def test_call_inputs_produce_call(self, policy, mode, input_type):
        d = policy.decide(mode, input_type,
                          session_active=True, camera_available=True)
        assert d.allowed is True
        assert d.action == CallSetAction.CALL

    @pytest.mark.parametrize("mode", [OperatingMode.TECHNICIAN, OperatingMode.ADMIN_INSTALLER])
    @pytest.mark.parametrize("input_type", _set_inputs())
    def test_set_inputs_produce_set_with_confirmation(self, policy, mode, input_type):
        d = policy.decide(mode, input_type,
                          session_active=True, camera_available=True)
        assert d.allowed is True
        assert d.action == CallSetAction.SET
        assert d.requires_confirmation is True

    def test_drag_blocked(self, policy):
        d = policy.decide(OperatingMode.TECHNICIAN, InputType.DRAG,
                          session_active=True, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "drag_not_a_camera_action"

    @pytest.mark.parametrize("input_type", _call_inputs())
    def test_session_inactive_blocks(self, policy, input_type):
        d = policy.decide(OperatingMode.TECHNICIAN, input_type,
                          session_active=False, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "session_inactive"

    @pytest.mark.parametrize("input_type", _call_inputs())
    def test_camera_unavailable_blocks(self, policy, input_type):
        d = policy.decide(OperatingMode.TECHNICIAN, input_type,
                          session_active=True, camera_available=False)
        assert d.allowed is False
        assert d.reason_code == "camera_unavailable"

    @pytest.mark.parametrize("input_type", _set_inputs())
    def test_session_inactive_blocks_set_too(self, policy, input_type):
        d = policy.decide(OperatingMode.TECHNICIAN, input_type,
                          session_active=False, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "session_inactive"


# ── Demo mode ─────────────────────────────────────────────────────────────────

class TestDemoMode:

    @pytest.mark.parametrize("input_type", list(InputType))
    def test_all_inputs_blocked_in_demo(self, policy, input_type):
        """Demo no mueve cámaras reales ni escribe presets reales."""
        d = policy.decide(OperatingMode.DEMO, input_type,
                          session_active=True, camera_available=True)
        assert d.allowed is False
        assert d.action == CallSetAction.NONE
        assert d.reason_code == "demo_mode_no_real_camera"

    def test_demo_blocked_even_session_inactive(self, policy):
        """El motivo de bloqueo es el modo demo, no el estado de sesión."""
        d = policy.decide(OperatingMode.DEMO, InputType.TAP,
                          session_active=False, camera_available=False)
        assert d.reason_code == "demo_mode_no_real_camera"


# ── Support mode ──────────────────────────────────────────────────────────────

class TestSupportMode:

    @pytest.mark.parametrize("input_type", list(InputType))
    def test_all_inputs_blocked_in_support(self, policy, input_type):
        """Soporte no mueve cámaras."""
        d = policy.decide(OperatingMode.SUPPORT, input_type,
                          session_active=True, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "support_mode_no_camera_action"


# ── Names mode ────────────────────────────────────────────────────────────────

class TestNamesMode:

    @pytest.mark.parametrize("input_type", list(InputType))
    def test_all_inputs_blocked_in_names(self, policy, input_type):
        """Names mode: clicks/edits son operaciones de datos, no comandos de cámara."""
        d = policy.decide(OperatingMode.NAMES, input_type,
                          session_active=True, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "names_mode_data_only"


# ── Layout edit mode ──────────────────────────────────────────────────────────

class TestLayoutEditMode:

    @pytest.mark.parametrize("input_type", list(InputType))
    def test_all_inputs_blocked_in_layout_edit(self, policy, input_type):
        """Layout edit: mover/editar asientos no dispara CALL/SET."""
        d = policy.decide(OperatingMode.LAYOUT_EDIT, input_type,
                          session_active=True, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "layout_edit_no_camera_action"


# ── Name edit workspace mode ──────────────────────────────────────────────────

class TestNameEditMode:

    @pytest.mark.parametrize("input_type", list(InputType))
    def test_all_inputs_blocked_in_name_edit(self, policy, input_type):
        """name_edit bloquea acciones de cámara independientemente del rol."""
        d = policy.decide(OperatingMode.NAME_EDIT, input_type,
                          session_active=True, camera_available=True)
        assert d.allowed is False
        assert d.action == CallSetAction.NONE
        assert d.reason_code == "name_edit_no_camera_action"

    @pytest.mark.parametrize("input_type", list(InputType))
    def test_legacy_names_mode_still_blocked(self, policy, input_type):
        """Alias legacy NAMES sigue bloqueando acciones de cámara."""
        d = policy.decide(OperatingMode.NAMES, input_type,
                          session_active=True, camera_available=True)
        assert d.allowed is False
        assert d.reason_code == "names_mode_data_only"


# ── Cross-mode invariants ─────────────────────────────────────────────────────

class TestInvariants:

    def test_cancelled_set_produces_no_action(self, policy):
        """
        Si el llamador NO confirma tras requires_confirmation=True, no envía nada.
        La política devuelve SET+requires_confirmation; es el llamador quien cancela.
        """
        d = policy.decide(OperatingMode.CAMERA_OPERATOR, InputType.LONG_PRESS,
                          session_active=True, camera_available=True)
        assert d.action == CallSetAction.SET
        assert d.requires_confirmation is True

    @pytest.mark.parametrize("mode", [
        OperatingMode.BASIC_OPERATOR,
        OperatingMode.CAMERA_OPERATOR,
        OperatingMode.TECHNICIAN,
        OperatingMode.SYSTEM_ADMIN,
        OperatingMode.OPERATOR,
        OperatingMode.ADMIN_INSTALLER,
    ])
    def test_call_never_requires_confirmation(self, policy, mode):
        d = policy.decide(mode, InputType.TAP,
                          session_active=True, camera_available=True)
        assert d.action == CallSetAction.CALL
        assert d.requires_confirmation is False

    @pytest.mark.parametrize("mode", [
        OperatingMode.BASIC_OPERATOR,
        OperatingMode.CAMERA_OPERATOR,
        OperatingMode.TECHNICIAN,
        OperatingMode.OPERATOR,
        OperatingMode.ADMIN_INSTALLER,
    ])
    def test_blocked_decisions_have_reason_code(self, policy, mode):
        """Toda decisión bloqueada debe tener reason_code para feedback de UI."""
        d = policy.decide(mode, InputType.TAP,
                          session_active=False, camera_available=True)
        assert d.allowed is False
        assert d.reason_code != ""

    def test_allowed_decisions_have_empty_reason_code(self, policy):
        d = policy.decide(OperatingMode.CAMERA_OPERATOR, InputType.TAP,
                          session_active=True, camera_available=True)
        assert d.allowed is True
        assert d.reason_code == ""

    @pytest.mark.parametrize("mode", [
        OperatingMode.DEMO,
        OperatingMode.SUPPORT,
        OperatingMode.NAME_EDIT,
        OperatingMode.NAMES,
        OperatingMode.LAYOUT_EDIT,
        OperatingMode.PRESET_TEST,
    ])
    def test_non_camera_modes_never_return_call_or_set(self, policy, mode):
        for input_type in InputType:
            d = policy.decide(mode, input_type,
                              session_active=True, camera_available=True)
            assert d.action == CallSetAction.NONE
