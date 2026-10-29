#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_atem_dispatcher.py — Tests de la capa de seguridad/acciones ATEM

from __future__ import annotations

from unittest.mock import patch

from adapters.atem_dispatcher import ATEMDispatcher
from domain.atem_state import ATEMState


def _dispatcher(
    *,
    session_active: bool = True,
    mapping: dict[str, str] | None = None,
    atem_connected: bool = True,
):
    actions: list[str] = []
    with patch("adapters.atem_dispatcher._load_mapping", return_value=(mapping or {"3->2": "comments_home"}, True)):
        dispatcher = ATEMDispatcher(
            session_provider=lambda: session_active,
            on_action=actions.append,
        )
    if atem_connected:
        dispatcher.on_atem_state_changed(ATEMState.CONNECTED)
    return dispatcher, actions


class TestATEMDispatcherActions:
    def test_default_transition_only_triggers_on_3_to_2(self):
        cases = [
            ([3, 2], ["comments_home"]),
            ([1, 2], []),
            ([2, 2], []),
            ([3, 1, 2], []),
            ([2], []),
        ]

        for inputs, expected in cases:
            dispatcher, actions = _dispatcher()
            dispatcher.set_armed(True)

            for input_id in inputs:
                dispatcher.on_program_changed(input_id)

            assert actions == expected, inputs

    def test_explicit_input_mapping_still_triggers_on_entering_input(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)

        dispatcher.on_program_changed(2)

        assert actions == ["comments_home"]

    def test_duplicate_input_is_deduplicated(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)

        dispatcher.on_program_changed(2)
        dispatcher.on_program_changed(2)

        assert actions == ["comments_home"]

    def test_platform_home_action_is_emitted(self):
        dispatcher, actions = _dispatcher(mapping={"1": "platform_home"})
        dispatcher.set_armed(True)

        dispatcher.on_program_changed(1)

        assert actions == ["platform_home"]


class TestATEMDispatcherBlocks:
    def test_disconnected_atem_blocks_actions(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"}, atem_connected=False)
        dispatcher.set_armed(True)

        dispatcher.on_program_changed(2)

        assert actions == []
        assert "not connected" in dispatcher.get_blocked_reason()

    def test_disarmed_blocks_actions(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})

        dispatcher.on_program_changed(2)

        assert actions == []

    def test_inactive_session_blocks_actions(self):
        dispatcher, actions = _dispatcher(session_active=False, mapping={"2": "comments_home"})
        dispatcher.set_armed(True)

        dispatcher.on_program_changed(2)

        assert actions == []

    def test_manual_cooldown_blocks_actions(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)
        dispatcher.notify_manual_control()

        dispatcher.on_program_changed(2)

        assert actions == []

    def test_reconnect_guard_blocks_until_cleared(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.mark_reconnecting()

        dispatcher.on_program_changed(3)
        dispatcher.on_program_changed(2)
        assert actions == []

        dispatcher.clear_reconnect_guard()
        dispatcher.reset_input_tracking()
        dispatcher.on_program_changed(3)
        dispatcher.on_program_changed(2)
        assert actions == ["comments_home"]

    def test_log_only_blocks_action_emission(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)
        dispatcher.set_log_only(True)

        dispatcher.on_program_changed(2)

        assert actions == []


class TestATEMDispatcherState:
    def test_connected_with_known_previous_input_sets_reconnect_guard(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)
        dispatcher.on_program_changed(1)
        # Simulate a disconnect then reconnect (guard triggers on the transition)
        dispatcher.on_atem_state_changed(ATEMState.DISCONNECTED)
        dispatcher.on_atem_state_changed(ATEMState.CONNECTED)

        assert dispatcher.reconnect_guard is True
        dispatcher.on_program_changed(2)
        assert actions == []

    def test_reset_input_tracking_does_not_clear_reconnect_guard(self):
        dispatcher, _actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.mark_reconnecting()

        dispatcher.reset_input_tracking()

        assert dispatcher.reconnect_guard is True

    def test_mark_reconnecting_only_sets_guard_when_armed(self):
        dispatcher, _actions = _dispatcher()

        dispatcher.mark_reconnecting()
        assert dispatcher.reconnect_guard is False

        dispatcher.set_armed(True)
        dispatcher.mark_reconnecting()
        assert dispatcher.reconnect_guard is True

    def test_dry_run_reports_transition_action(self):
        dispatcher, _actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.on_program_changed(3)

        assert dispatcher.dry_run(2) == "Would trigger: comments_home"


class TestAutomationStateCoverage:
    """Full acceptance-criteria coverage for all five safety layers."""

    # ── on_program_changed signal behaviour ───────────────────────────────────

    def test_disarmed_does_not_emit_action(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        # armed defaults to False

        dispatcher.on_program_changed(2)

        assert actions == []

    def test_session_inactive_blocks_when_armed(self):
        dispatcher, actions = _dispatcher(session_active=False, mapping={"2": "comments_home"})
        dispatcher.set_armed(True)

        dispatcher.on_program_changed(2)

        assert actions == []

    def test_manual_cooldown_active_blocks_when_armed_and_session_active(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)
        dispatcher.notify_manual_control()

        dispatcher.on_program_changed(2)

        assert actions == []

    def test_reconnect_guard_blocks_when_all_else_clear(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)
        dispatcher.mark_reconnecting()

        dispatcher.on_program_changed(2)

        assert actions == []

    def test_log_only_does_not_emit_but_action_would_occur(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)
        dispatcher.set_log_only(True)

        dispatcher.on_program_changed(2)

        assert actions == []

    def test_all_clear_emits_action_triggered(self):
        dispatcher, actions = _dispatcher(mapping={"2": "comments_home"})
        dispatcher.set_armed(True)

        dispatcher.on_program_changed(2)

        assert actions == ["comments_home"]

    # ── get_automation_state() ────────────────────────────────────────────────

    def test_state_when_disarmed(self):
        dispatcher, _ = _dispatcher()

        state = dispatcher.get_automation_state()

        assert state.armed is False
        assert state.log_only is False
        assert state.reconnect_guard is False
        assert state.manual_cooldown_active is False
        assert state.blocked_reason == "automation disarmed"
        assert state.last_input is None

    def test_state_when_session_inactive(self):
        dispatcher, _ = _dispatcher(session_active=False)
        dispatcher.set_armed(True)

        state = dispatcher.get_automation_state()

        assert state.armed is True
        assert state.blocked_reason == "session inactive"

    def test_state_when_manual_cooldown_active(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.notify_manual_control()

        state = dispatcher.get_automation_state()

        assert state.manual_cooldown_active is True
        assert state.blocked_reason == "manual override cooldown"

    def test_state_when_reconnect_guard_active(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.mark_reconnecting()

        state = dispatcher.get_automation_state()

        assert state.reconnect_guard is True
        assert state.blocked_reason == "reconnect guard active"

    def test_state_when_log_only(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.set_log_only(True)

        state = dispatcher.get_automation_state()

        assert state.armed is True
        assert state.log_only is True
        assert state.blocked_reason == ""

    def test_state_all_clear(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.on_program_changed(3)

        state = dispatcher.get_automation_state()

        assert state.armed is True
        assert state.log_only is False
        assert state.reconnect_guard is False
        assert state.manual_cooldown_active is False
        assert state.blocked_reason == ""
        assert state.last_input == 3

    def test_state_is_frozen_dataclass(self):
        """get_automation_state() must return a frozen (immutable) snapshot."""
        import pytest
        from domain.atem_state import AtemAutomationState
        dispatcher, _ = _dispatcher()
        state = dispatcher.get_automation_state()

        assert isinstance(state, AtemAutomationState)
        with pytest.raises(AttributeError):
            state.armed = True  # type: ignore[misc]


class TestDryRunPip:
    """dry_run_pip simulates PiP-triggered actions without executing them."""

    def test_unmapped_pip_on_returns_no_action(self):
        dispatcher, _ = _dispatcher(mapping={})
        result = dispatcher.dry_run_pip(True)
        assert "no action" in result

    def test_unmapped_pip_off_returns_no_action(self):
        dispatcher, _ = _dispatcher(mapping={})
        result = dispatcher.dry_run_pip(False)
        assert "no action" in result

    def test_mapped_pip_on_shows_action(self):
        dispatcher, _ = _dispatcher(mapping={"pip:on": "pip_on"})
        dispatcher.set_armed(True)
        result = dispatcher.dry_run_pip(True)
        assert "pip_on" in result

    def test_mapped_pip_off_shows_action(self):
        dispatcher, _ = _dispatcher(mapping={"pip:off": "pip_off"})
        dispatcher.set_armed(True)
        result = dispatcher.dry_run_pip(False)
        assert "pip_off" in result

    def test_blocked_shows_blocked_reason(self):
        dispatcher, _ = _dispatcher(mapping={"pip:on": "pip_on"})
        # not armed → blocked
        result = dispatcher.dry_run_pip(True)
        assert "Blocked" in result

    def test_log_only_shows_log_only_mode(self):
        dispatcher, _ = _dispatcher(mapping={"pip:on": "pip_on"})
        dispatcher.set_armed(True)
        dispatcher.set_log_only(True)
        result = dispatcher.dry_run_pip(True)
        assert "log-only" in result


class TestDispatchActionHelper:
    """_dispatch_action is the single gating path for both program and PiP events."""

    def test_dispatch_none_action_does_not_emit(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher._dispatch_action("none", "test")
        assert actions == []

    def test_dispatch_emits_when_all_gates_pass(self):
        dispatcher, actions = _dispatcher(mapping={"3->2": "comments_home"})
        dispatcher.set_armed(True)
        dispatcher._dispatch_action("comments_home", "test")
        assert actions == ["comments_home"]

    def test_dispatch_blocked_when_disarmed(self):
        dispatcher, actions = _dispatcher()
        # disarmed by default
        dispatcher._dispatch_action("comments_home", "test")
        assert actions == []

    def test_dispatch_log_only_does_not_emit(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.set_log_only(True)
        dispatcher._dispatch_action("comments_home", "test")
        assert actions == []


class TestPipAutomationEnabled:
    """pip_automation_enabled controls whether PiP events trigger actions."""

    def test_default_pip_automation_enabled_is_true(self):
        dispatcher, _ = _dispatcher()
        assert dispatcher.pip_automation_enabled is True

    def test_set_pip_automation_disabled_suppresses_on_pip_changed(self):
        dispatcher, actions = _dispatcher(mapping={"pip:on": "pip_on"})
        dispatcher.set_armed(True)
        dispatcher.set_pip_automation_enabled(False)
        from domain.atem_state import ATEMPiPState
        dispatcher.on_pip_changed(ATEMPiPState(enabled=True))
        assert actions == []

    def test_pip_automation_re_enabled_allows_action(self):
        dispatcher, actions = _dispatcher(mapping={"pip:on": "pip_on"})
        dispatcher.set_armed(True)
        dispatcher.set_pip_automation_enabled(False)
        dispatcher.set_pip_automation_enabled(True)
        from domain.atem_state import ATEMPiPState
        dispatcher.on_pip_changed(ATEMPiPState(enabled=True))
        assert actions == ["pip_on"]

    def test_set_pip_automation_idempotent(self):
        dispatcher, _ = _dispatcher()
        # Should not raise or produce unexpected side effects
        dispatcher.set_pip_automation_enabled(True)
        dispatcher.set_pip_automation_enabled(True)
        assert dispatcher.pip_automation_enabled is True

    def test_automation_state_snapshot_includes_pip_automation(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_pip_automation_enabled(False)
        state = dispatcher.get_automation_state()
        assert state.pip_automation_enabled is False

    def test_automation_state_snapshot_pip_automation_true_by_default(self):
        dispatcher, _ = _dispatcher()
        state = dispatcher.get_automation_state()
        assert state.pip_automation_enabled is True

    def test_dry_run_pip_reports_disabled_when_pip_automation_off(self):
        dispatcher, _ = _dispatcher(mapping={"pip:on": "pip_on"})
        dispatcher.set_armed(True)
        dispatcher.set_pip_automation_enabled(False)
        result = dispatcher.dry_run_pip(True)
        assert "disabled" in result.lower()

    def test_dry_run_pip_reports_action_when_pip_automation_on(self):
        dispatcher, _ = _dispatcher(mapping={"pip:on": "pip_on"})
        dispatcher.set_armed(True)
        result = dispatcher.dry_run_pip(True)
        assert "pip_on" in result

    def test_update_mapping_does_not_reset_pip_automation(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_pip_automation_enabled(False)
        dispatcher.update_mapping({"pip:on": "pip_on"})
        assert dispatcher.pip_automation_enabled is False


class TestPipAutomationReenableDedup:
    """Re-enabling pip_automation must not silently drop the first PiP event."""

    def test_reenable_resets_dedup_state(self):
        """After disable→enable, the first PiP event MUST fire even if state is unchanged."""
        dispatcher, actions = _dispatcher(mapping={"pip:on": "pip_on", "pip:off": "pip_off"})
        dispatcher.set_armed(True)
        from domain.atem_state import ATEMPiPState

        # PiP turns ON → fires action
        dispatcher.on_pip_changed(ATEMPiPState(enabled=True))
        assert actions == ["pip_on"]
        actions.clear()

        # Disable automation
        dispatcher.set_pip_automation_enabled(False)
        # PiP turns OFF while disabled — tracked but not acted on
        dispatcher.on_pip_changed(ATEMPiPState(enabled=False))
        assert actions == []

        # Re-enable: _last_pip_enabled must be reset to None
        dispatcher.set_pip_automation_enabled(True)
        assert dispatcher._last_pip_enabled is None

        # Now PiP turns ON again — must fire even though state was ON before disable
        dispatcher.on_pip_changed(ATEMPiPState(enabled=True))
        assert actions == ["pip_on"]

    def test_disable_does_not_reset_dedup_state(self):
        """Disabling must NOT reset dedup state (we still track PiP while disabled)."""
        dispatcher, _ = _dispatcher(mapping={"pip:on": "pip_on"})
        dispatcher.set_armed(True)
        from domain.atem_state import ATEMPiPState
        dispatcher.on_pip_changed(ATEMPiPState(enabled=True))
        assert dispatcher._last_pip_enabled is True
        dispatcher.set_pip_automation_enabled(False)
        # After disabling: dedup state preserved (not None)
        assert dispatcher._last_pip_enabled is True


class TestLoadMappingUnknownActions:
    """_load_mapping converts unknown action values to 'none' with a warning."""

    def test_unknown_action_becomes_none(self):
        import json
        import tempfile
        import os
        from unittest.mock import patch
        from adapters.atem_dispatcher import _load_mapping

        data = {"3->2": "not_a_real_action", "pip:on": "pip_on"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            with patch("adapters.atem_dispatcher._mapping_file", return_value=__import__("pathlib").Path(path)):
                mapping, pip_enabled = _load_mapping()
            assert mapping.get("3->2") == "none"       # unknown → "none"
            assert mapping.get("pip:on") == "pip_on"   # known → preserved
            assert pip_enabled is True
        finally:
            os.unlink(path)

    def test_known_actions_preserved(self):
        import json
        import tempfile
        import os
        from unittest.mock import patch
        from adapters.atem_dispatcher import _load_mapping

        data = {"3->2": "comments_home", "pip:off": "pip_off"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            with patch("adapters.atem_dispatcher._mapping_file", return_value=__import__("pathlib").Path(path)):
                mapping, _ = _load_mapping()
            assert mapping["3->2"] == "comments_home"
            assert mapping["pip:off"] == "pip_off"
        finally:
            os.unlink(path)

    def test_pip_automation_key_not_in_mapping(self):
        import json
        import tempfile
        import os
        from unittest.mock import patch
        from adapters.atem_dispatcher import _load_mapping, _PIP_AUTOMATION_KEY

        data = {_PIP_AUTOMATION_KEY: False, "3->2": "comments_home"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            with patch("adapters.atem_dispatcher._mapping_file", return_value=__import__("pathlib").Path(path)):
                mapping, pip_enabled = _load_mapping()
            assert _PIP_AUTOMATION_KEY not in mapping   # meta-key filtered out
            assert pip_enabled is False
        finally:
            os.unlink(path)
