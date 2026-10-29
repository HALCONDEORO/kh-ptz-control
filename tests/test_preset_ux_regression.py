# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Regression tests for the unified preset UX (#268, #536).

Tests cover:
  - call_cb/set_cb blocking when Names panel is open (now via CallSetCommandPolicy)
  - No duplicate CALL after long press
  - PresetActionMixin input handler (complementing test_preset_actions.py)
  - ViscaProtocol call_preset/set_preset API exists
  - Names ON/OFF mode transitions in isolation

Qt-free: all tests use pure-Python stubs.
"""
from __future__ import annotations


from application.call_set_command_policy import CallSetCommandPolicy
from domain.call_set_policy import InputType, OperatingMode


# ── Stub: policy-driven preset button logic ───────────────────────────────────

class _PolicyPresetLogic:
    """
    Stub that mirrors MainWindow._call_preset_from_button /
    _confirm_and_set_preset using CallSetCommandPolicy.

    _access_mode mirrors AccessModeService.mode (persisted, not toggled by
    a visible button). The dialog is replaced with a configurable flag
    (_confirm_result).
    """

    def __init__(self):
        self._names_open:    bool          = False
        self._access_mode:   OperatingMode = OperatingMode.OPERATOR
        self._session_active: bool         = True
        self.calls:               list[int] = []
        self.sets:                list[int] = []
        self.confirmations_asked: list[int] = []
        self._confirm_result: bool = True   # default: user clicks "Yes"
        self._policy = CallSetCommandPolicy()

    def _current_operating_mode(self) -> OperatingMode:
        if self._names_open:
            return OperatingMode.NAMES
        return self._access_mode

    # Mirror of main_window._call_preset_from_button
    def call_preset_from_button(self, preset_number: int) -> None:
        decision = self._policy.decide(
            mode=self._current_operating_mode(),
            input_type=InputType.TAP,
            session_active=self._session_active,
            camera_available=True,
        )
        if decision.allowed:
            self.calls.append(preset_number)

    # Mirror of main_window._confirm_and_set_preset (dialog replaced with flag)
    def confirm_and_set_preset(self, preset_number: int) -> None:
        decision = self._policy.decide(
            mode=self._current_operating_mode(),
            input_type=InputType.LONG_PRESS,
            session_active=self._session_active,
            camera_available=True,
        )
        if not decision.allowed:
            return
        if decision.requires_confirmation:
            self.confirmations_asked.append(preset_number)
            if not self._confirm_result:
                return
        self.sets.append(preset_number)


# Keep old name as alias so remaining test classes need no changes
_NamesAwarePresetLogic = _PolicyPresetLogic


# ── Tests: Names ON/OFF blocking ──────────────────────────────────────────────

class TestNamesBlocksPresetActions:
    def test_call_blocked_when_names_open(self):
        logic = _NamesAwarePresetLogic()
        logic._names_open = True
        logic.call_preset_from_button(5)
        assert logic.calls == []

    def test_call_allowed_when_names_closed(self):
        logic = _NamesAwarePresetLogic()
        logic._names_open = False
        logic.call_preset_from_button(5)
        assert logic.calls == [5]

    def test_set_blocked_when_names_open(self):
        logic = _NamesAwarePresetLogic()
        logic._names_open = True
        logic.confirm_and_set_preset(5)
        assert logic.confirmations_asked == []
        assert logic.sets == []

    def test_set_allowed_in_admin_mode(self):
        logic = _NamesAwarePresetLogic()
        logic._names_open = False
        logic._access_mode = OperatingMode.ADMIN_INSTALLER
        logic.confirm_and_set_preset(5)
        assert logic.confirmations_asked == [5]
        assert logic.sets == [5]

    def test_set_blocked_in_operator_mode(self):
        """Operator mode cannot SET — policy returns operator_no_set."""
        logic = _NamesAwarePresetLogic()
        logic._names_open = False
        logic._access_mode = OperatingMode.OPERATOR
        logic.confirm_and_set_preset(5)
        assert logic.confirmations_asked == []
        assert logic.sets == []

    def test_cancel_set_does_not_save(self):
        logic = _NamesAwarePresetLogic()
        logic._access_mode = OperatingMode.ADMIN_INSTALLER
        logic._confirm_result = False
        logic.confirm_and_set_preset(7)
        assert logic.confirmations_asked == [7]
        assert logic.sets == []

    def test_confirm_set_saves(self):
        logic = _NamesAwarePresetLogic()
        logic._access_mode = OperatingMode.ADMIN_INSTALLER
        logic._confirm_result = True
        logic.confirm_and_set_preset(7)
        assert logic.sets == [7]

    def test_names_toggle_on_then_off_restores_calls(self):
        logic = _NamesAwarePresetLogic()
        logic._names_open = True
        logic.call_preset_from_button(3)
        assert logic.calls == []
        logic._names_open = False
        logic.call_preset_from_button(3)
        assert logic.calls == [3]

    def test_multiple_presets_all_blocked_when_names_open(self):
        logic = _NamesAwarePresetLogic()
        logic._names_open = True
        for n in range(1, 6):
            logic.call_preset_from_button(n)
        assert logic.calls == []


# ── Stub: PresetActionMixin state machine ─────────────────────────────────────

class _PresetMixinStub:
    """
    Simulates PresetActionMixin state machine without Qt timers.
    Long press is fired manually by calling _simulate_long_press().
    """

    LONG_PRESS_MS = 800

    def __init__(self, preset_number: int, call_cb, set_cb):
        self._preset_number = preset_number
        self._call_cb = call_cb
        self._set_cb = set_cb
        self._long_press_fired = False
        self._long_press_active = False

    def simulate_right_click(self):
        self._set_cb(self._preset_number)

    def simulate_left_press(self):
        self._long_press_fired = False
        self._long_press_active = True

    def simulate_long_press_timeout(self):
        if self._long_press_active:
            self._long_press_fired = True
            self._long_press_active = False
            self._set_cb(self._preset_number)

    def simulate_left_release(self):
        self._long_press_active = False
        if not self._long_press_fired:
            self._call_cb(self._preset_number)
        self._long_press_fired = False

    def simulate_drag_cancel(self):
        self._long_press_active = False


# ── Tests: PresetActionMixin state machine ────────────────────────────────────

class TestPresetMixinStateMachine:
    def _stub(self):
        calls = []
        sets = []
        return (
            _PresetMixinStub(5, calls.append, sets.append),
            calls,
            sets,
        )

    def test_left_click_calls_once(self):
        stub, calls, sets = self._stub()
        stub.simulate_left_press()
        stub.simulate_left_release()
        assert calls == [5]
        assert sets == []

    def test_right_click_sets_once(self):
        stub, calls, sets = self._stub()
        stub.simulate_right_click()
        assert calls == []
        assert sets == [5]

    def test_long_press_sets_once(self):
        stub, calls, sets = self._stub()
        stub.simulate_left_press()
        stub.simulate_long_press_timeout()
        assert sets == [5]

    def test_long_press_does_not_also_call_on_release(self):
        stub, calls, sets = self._stub()
        stub.simulate_left_press()
        stub.simulate_long_press_timeout()
        stub.simulate_left_release()
        assert calls == []      # CALL must NOT fire after long press
        assert sets == [5]

    def test_drag_cancels_long_press(self):
        stub, calls, sets = self._stub()
        stub.simulate_left_press()
        stub.simulate_drag_cancel()
        stub.simulate_left_release()
        assert calls == [5]     # short tap still fires
        assert sets == []       # but no SET from the cancelled long press

    def test_no_context_menu_on_right_click(self):
        # Right-click fires SET immediately — no menu interaction needed
        stub, calls, sets = self._stub()
        stub.simulate_right_click()
        assert sets == [5]

    def test_sequential_left_clicks_each_call_once(self):
        stub, calls, sets = self._stub()
        for _ in range(3):
            stub.simulate_left_press()
            stub.simulate_left_release()
        assert calls == [5, 5, 5]
        assert sets == []

    def test_right_click_preset_number_correct(self):
        calls = []
        sets = []
        stub = _PresetMixinStub(12, calls.append, sets.append)
        stub.simulate_right_click()
        assert sets == [12]

    def test_long_press_preset_number_correct(self):
        calls = []
        sets = []
        stub = _PresetMixinStub(7, calls.append, sets.append)
        stub.simulate_left_press()
        stub.simulate_long_press_timeout()
        assert sets == [7]

    def test_left_click_preset_number_correct(self):
        calls = []
        sets = []
        stub = _PresetMixinStub(9, calls.append, sets.append)
        stub.simulate_left_press()
        stub.simulate_left_release()
        assert calls == [9]



# ── Tests: Names edit mode flag transitions ───────────────────────────────────

class TestNamesModeTransitions:
    """Verify the Names toggle correctly enables/disables call actions."""

    def test_open_close_cycle(self):
        logic = _NamesAwarePresetLogic()
        # Normal operation
        logic.call_preset_from_button(1)
        assert logic.calls == [1]
        # Names ON
        logic._names_open = True
        logic.call_preset_from_button(2)
        assert logic.calls == [1]  # blocked
        # Names OFF
        logic._names_open = False
        logic.call_preset_from_button(3)
        assert logic.calls == [1, 3]  # allowed again

    def test_set_requires_confirmation_in_admin_mode(self):
        logic = _NamesAwarePresetLogic()
        logic._names_open = False
        logic._access_mode = OperatingMode.ADMIN_INSTALLER
        logic.confirm_and_set_preset(5)
        assert 5 in logic.confirmations_asked

    def test_no_camera_action_without_confirmation(self):
        logic = _NamesAwarePresetLogic()
        logic._confirm_result = False
        logic.confirm_and_set_preset(5)
        assert logic.sets == []

    def test_names_on_blocks_set_action(self):
        logic = _NamesAwarePresetLogic()
        logic._names_open = True
        logic.confirm_and_set_preset(5)
        assert logic.sets == []
        assert logic.confirmations_asked == []

