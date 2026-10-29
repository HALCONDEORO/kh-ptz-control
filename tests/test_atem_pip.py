#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_atem_pip.py — Tests de detección y despacho de Picture-in-Picture ATEM

from __future__ import annotations

import sys
from unittest.mock import patch

from PyQt5.QtCore import QCoreApplication, Qt

if not QCoreApplication.instance():
    _app = QCoreApplication(sys.argv)

from adapters.atem_dispatcher import ATEMDispatcher, _PIP_KEY_OFF, _PIP_KEY_ON
from domain.atem_state import ATEMPiPState


# ── Helpers ────────────────────────────────────────────────────────────────────

def _dispatcher(
    *,
    session_active: bool = True,
    mapping: dict[str, str] | None = None,
    atem_connected: bool = True,
) -> tuple[ATEMDispatcher, list[str]]:
    from domain.atem_state import ATEMState

    default_pip_mapping: dict[str, str] = {
        "pip:on":  "pip_on",
        "pip:off": "pip_off",
    }
    used_mapping = mapping if mapping is not None else default_pip_mapping
    actions: list[str] = []
    with patch("adapters.atem_dispatcher._load_mapping", return_value=(used_mapping, True)):
        dispatcher = ATEMDispatcher(
            session_provider=lambda: session_active,
            on_action=actions.append,
        )
    if atem_connected:
        dispatcher.on_atem_state_changed(ATEMState.CONNECTED)
    return dispatcher, actions


def _pip(enabled: bool, source: int | None = None) -> ATEMPiPState:
    return ATEMPiPState(enabled=enabled, source=source)


# ── ATEMPiPState — dominio ─────────────────────────────────────────────────────

class TestATEMPiPStateDomain:
    def test_pip_state_enabled_with_source(self):
        state = ATEMPiPState(enabled=True, source=2)
        assert state.enabled is True
        assert state.source == 2

    def test_pip_state_disabled(self):
        state = ATEMPiPState(enabled=False)
        assert state.enabled is False
        assert state.source is None

    def test_pip_state_is_frozen(self):
        import pytest
        state = ATEMPiPState(enabled=True, source=1)
        with pytest.raises((AttributeError, TypeError)):
            state.enabled = False  # type: ignore[misc]

    def test_pip_on_and_off_are_different(self):
        on  = ATEMPiPState(enabled=True,  source=1)
        off = ATEMPiPState(enabled=False, source=None)
        assert on != off


# ── ATEMDispatcher — on_pip_changed ───────────────────────────────────────────

class TestATEMDispatcherPiPActions:
    def test_pip_on_triggers_pip_on_action_when_armed(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)

        dispatcher.on_pip_changed(_pip(True, source=2))

        assert actions == ["pip_on"]

    def test_pip_off_triggers_pip_off_action_when_armed(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        # Primero activar para que el toggle funcione
        dispatcher.on_pip_changed(_pip(True))
        actions.clear()

        dispatcher.on_pip_changed(_pip(False))

        assert actions == ["pip_off"]

    def test_pip_on_then_off_sequence(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)

        dispatcher.on_pip_changed(_pip(True,  source=3))
        dispatcher.on_pip_changed(_pip(False))

        assert actions == ["pip_on", "pip_off"]

    def test_pip_duplicate_state_does_not_retrigger(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)

        dispatcher.on_pip_changed(_pip(True))
        dispatcher.on_pip_changed(_pip(True))  # mismo estado → ignorar

        assert actions == ["pip_on"]

    def test_pip_source_does_not_affect_deduplication(self):
        """Cambiar la fuente del PiP sin cambiar enabled no retrigger."""
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)

        dispatcher.on_pip_changed(_pip(True, source=1))
        dispatcher.on_pip_changed(_pip(True, source=2))  # source distinto, enabled igual

        assert actions == ["pip_on"]


class TestATEMDispatcherPiPBlocks:
    def test_pip_blocked_when_disarmed(self):
        dispatcher, actions = _dispatcher()
        # armed = False por defecto

        dispatcher.on_pip_changed(_pip(True))

        assert actions == []

    def test_pip_blocked_when_session_inactive(self):
        dispatcher, actions = _dispatcher(session_active=False)
        dispatcher.set_armed(True)

        dispatcher.on_pip_changed(_pip(True))

        assert actions == []

    def test_pip_blocked_during_manual_cooldown(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.notify_manual_control()

        dispatcher.on_pip_changed(_pip(True))

        assert actions == []

    def test_pip_blocked_during_reconnect_guard(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.mark_reconnecting()

        dispatcher.on_pip_changed(_pip(True))

        assert actions == []

    def test_pip_log_only_does_not_emit(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.set_log_only(True)

        dispatcher.on_pip_changed(_pip(True))

        assert actions == []


class TestATEMDispatcherPiPMapping:
    def test_pip_on_without_mapping_entry_emits_nothing(self):
        dispatcher, actions = _dispatcher(mapping={"3->2": "comments_home"})
        dispatcher.set_armed(True)

        dispatcher.on_pip_changed(_pip(True))

        assert actions == []

    def test_pip_off_without_mapping_entry_emits_nothing(self):
        dispatcher, actions = _dispatcher(mapping={"3->2": "comments_home"})
        dispatcher.set_armed(True)
        # seed state so off-transition is recognised
        dispatcher.on_pip_changed(_pip(True))  # not mapped → no action
        actions.clear()

        dispatcher.on_pip_changed(_pip(False))

        assert actions == []

    def test_pip_on_mapped_to_comments_home(self):
        dispatcher, actions = _dispatcher(mapping={"pip:on": "comments_home"})
        dispatcher.set_armed(True)

        dispatcher.on_pip_changed(_pip(True))

        assert actions == ["comments_home"]

    def test_pip_mapping_keys_are_valid(self):
        from adapters.atem_dispatcher import _is_valid_mapping_key
        assert _is_valid_mapping_key("pip:on")  is True
        assert _is_valid_mapping_key("pip:off") is True

    def test_pip_keys_are_accepted_by_load_mapping(self):
        """update_mapping acepta pip:on y pip:off sin warnings."""
        dispatcher, _ = _dispatcher(mapping={})
        # No debe levantar excepción ni ignorar las claves
        dispatcher.update_mapping({"pip:on": "pip_on", "pip:off": "pip_off"})
        assert dispatcher.mapping[_PIP_KEY_ON]  == "pip_on"
        assert dispatcher.mapping[_PIP_KEY_OFF] == "pip_off"


# ── ATEMMonitor — simulación PiP ──────────────────────────────────────────────

class TestATEMMonitorPiPSimulation:
    """Tests del método _handle_sim_pip_event sin arrancar el hilo."""

    def _make_monitor(self):
        from adapters.atem_monitor import ATEMMonitor
        with patch("adapters.atem_monitor._sim_is_active", return_value=True):
            monitor = ATEMMonitor(ip="")
        return monitor

    def test_pip_on_event_emits_pip_changed_enabled(self):
        monitor = self._make_monitor()
        received: list[ATEMPiPState] = []
        monitor.pip_changed.connect(received.append, Qt.DirectConnection)

        monitor._handle_sim_pip_event("pip_on")

        assert len(received) == 1
        assert received[0].enabled is True
        assert received[0].source is None

    def test_pip_on_with_source_parses_source(self):
        monitor = self._make_monitor()
        received: list[ATEMPiPState] = []
        monitor.pip_changed.connect(received.append, Qt.DirectConnection)

        monitor._handle_sim_pip_event("pip_on:2")

        assert received[0].source == 2

    def test_pip_off_event_emits_pip_changed_disabled(self):
        monitor = self._make_monitor()
        received: list[ATEMPiPState] = []
        monitor.pip_changed.connect(received.append, Qt.DirectConnection)

        monitor._handle_sim_pip_event("pip_on")   # primero on
        monitor._handle_sim_pip_event("pip_off")  # luego off

        assert received[1].enabled is False
        assert received[1].source is None

    def test_pip_duplicate_on_does_not_re_emit(self):
        monitor = self._make_monitor()
        received: list[ATEMPiPState] = []
        monitor.pip_changed.connect(received.append, Qt.DirectConnection)

        monitor._handle_sim_pip_event("pip_on")
        monitor._handle_sim_pip_event("pip_on")

        assert len(received) == 1

    def test_pip_unknown_event_is_ignored(self):
        monitor = self._make_monitor()
        received: list[ATEMPiPState] = []
        monitor.pip_changed.connect(received.append, Qt.DirectConnection)

        monitor._handle_sim_pip_event("bogus_event")

        assert received == []

    def test_pip_on_with_invalid_source_defaults_to_none(self):
        monitor = self._make_monitor()
        received: list[ATEMPiPState] = []
        monitor.pip_changed.connect(received.append, Qt.DirectConnection)

        monitor._handle_sim_pip_event("pip_on:abc")

        assert received[0].enabled is True
        assert received[0].source is None


# ── ATEMDispatcher — pip_automation_enabled ───────────────────────────────────

class TestPiPAutomationEnabled:
    """set_pip_automation_enabled / pip_automation_enabled property."""

    def test_pip_automation_enabled_is_true_by_default(self):
        dispatcher, _ = _dispatcher()
        assert dispatcher.pip_automation_enabled is True

    def test_pip_automation_disabled_blocks_on_pip_changed(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.set_pip_automation_enabled(False)

        dispatcher.on_pip_changed(_pip(True))

        assert actions == []

    def test_pip_automation_disabled_tracks_state_but_no_action(self):
        """While disabled: state is tracked but no actions are emitted."""
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.set_pip_automation_enabled(False)

        dispatcher.on_pip_changed(_pip(True))
        dispatcher.on_pip_changed(_pip(True))  # duplicate — deduplicated

        assert actions == []  # no actions while disabled

    def test_re_enabling_pip_automation_resets_dedup_state(self):
        """Re-enabling PiP automation resets _last_pip_enabled to None.

        This means the next PiP event always fires after re-enable, even if
        the physical PiP state hasn't changed, ensuring cameras move to the
        correct position when automation is restored after a manual override.
        """
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.set_pip_automation_enabled(False)
        dispatcher.on_pip_changed(_pip(True))   # state tracked as True, no action
        assert actions == []

        dispatcher.set_pip_automation_enabled(True)  # resets dedup state

        # Even though PiP was already True, the event fires again
        dispatcher.on_pip_changed(_pip(True))
        assert actions == ["pip_on"]

    def test_re_enabling_pip_automation_restores_dispatch(self):
        """Re-enabling restores dispatch — no need to manually reset dedup state."""
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.set_pip_automation_enabled(False)
        dispatcher.on_pip_changed(_pip(True))   # disabled → no action
        actions.clear()

        # set_pip_automation_enabled(True) resets _last_pip_enabled internally
        dispatcher.set_pip_automation_enabled(True)
        dispatcher.on_pip_changed(_pip(True))

        assert actions == ["pip_on"]

    def test_set_pip_automation_enabled_idempotent(self):
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.set_pip_automation_enabled(True)   # already True
        dispatcher.set_pip_automation_enabled(True)   # no-op

        dispatcher.on_pip_changed(_pip(True))

        assert actions == ["pip_on"]

    def test_pip_automation_enabled_persists_to_mapping(self):
        """set_pip_automation_enabled(False) calls _save_mapping with the flag."""
        dispatcher, _ = _dispatcher(mapping={})
        with patch("adapters.atem_dispatcher._save_mapping") as mock_save:
            dispatcher.set_pip_automation_enabled(False)
            mock_save.assert_called_once()
            _, kwargs = mock_save.call_args
            assert kwargs.get("pip_automation_enabled") is False

    def test_load_mapping_reads_pip_automation_key(self, tmp_path):
        """_load_mapping returns False when pip_automation_enabled is False in JSON."""
        import json as _json
        from adapters.atem_dispatcher import _load_mapping
        mapping_file = tmp_path / "atem_mapping.json"
        mapping_file.write_text(
            _json.dumps({"pip_automation_enabled": False, "3->2": "comments_home"}),
            encoding="utf-8",
        )
        with patch("adapters.atem_dispatcher._mapping_file", return_value=mapping_file):
            mapping, pip_enabled = _load_mapping()
        assert pip_enabled is False
        assert "3->2" in mapping
        assert "pip_automation_enabled" not in mapping  # meta-key filtered out

    def test_load_mapping_defaults_pip_automation_to_true(self, tmp_path):
        """When key absent, pip_automation_enabled defaults to True."""
        import json as _json
        from adapters.atem_dispatcher import _load_mapping
        mapping_file = tmp_path / "atem_mapping.json"
        mapping_file.write_text(
            _json.dumps({"3->2": "comments_home"}),
            encoding="utf-8",
        )
        with patch("adapters.atem_dispatcher._mapping_file", return_value=mapping_file):
            _, pip_enabled = _load_mapping()
        assert pip_enabled is True


# ── dry_run_pip deduplication ─────────────────────────────────────────────────

class TestDryRunPip:
    """dry_run_pip() must mirror on_pip_changed() exactly, including deduplication."""

    def test_dry_run_pip_on_with_no_prior_state(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_armed(True)
        # _last_pip_enabled is None → state IS a change
        result = dispatcher.dry_run_pip(True)
        assert "Would trigger" in result

    def test_dry_run_pip_reports_no_change_when_already_on(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_armed(True)
        # Seed state as already ON
        dispatcher.on_pip_changed(_pip(True))
        result = dispatcher.dry_run_pip(True)
        assert "no change" in result
        assert "already ON" in result

    def test_dry_run_pip_reports_no_change_when_already_off(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_armed(True)
        # Seed state as OFF (from None → ON → OFF sequence)
        dispatcher.on_pip_changed(_pip(True))
        dispatcher.on_pip_changed(_pip(False))
        result = dispatcher.dry_run_pip(False)
        assert "no change" in result
        assert "already OFF" in result

    def test_dry_run_pip_reports_automation_disabled(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.set_pip_automation_enabled(False)
        result = dispatcher.dry_run_pip(True)
        assert "pip automation disabled" in result

    def test_dry_run_pip_automation_disabled_takes_precedence_over_mapping(self):
        """Even with pip:on mapped, disabled automation means no action."""
        dispatcher, _ = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.set_pip_automation_enabled(False)
        result = dispatcher.dry_run_pip(True)
        assert "Would trigger" not in result

    def test_dry_run_pip_reports_not_mapped(self):
        dispatcher, _ = _dispatcher(mapping={"3->2": "comments_home"})
        dispatcher.set_armed(True)
        result = dispatcher.dry_run_pip(True)
        assert "not mapped" in result

    def test_dry_run_pip_reports_blocked_reason(self):
        dispatcher, _ = _dispatcher()
        # armed=False → blocked
        result = dispatcher.dry_run_pip(True)
        assert "Blocked" in result

    def test_dry_run_pip_is_consistent_with_real_dispatch(self):
        """dry_run_pip and on_pip_changed must agree: if dry_run says trigger, real does too."""
        dispatcher, actions = _dispatcher()
        dispatcher.set_armed(True)

        dry = dispatcher.dry_run_pip(True)
        dispatcher.on_pip_changed(_pip(True))

        if "Would trigger" in dry:
            assert len(actions) == 1
        else:
            assert len(actions) == 0


# ── AtemAutomationState snapshot ─────────────────────────────────────────────

class TestAutomationStateSnapshot:
    """get_automation_state() must expose all fields for diagnostics."""

    def test_snapshot_includes_pip_automation_enabled(self):
        dispatcher, _ = _dispatcher()
        state = dispatcher.get_automation_state()
        assert state.pip_automation_enabled is True

    def test_snapshot_pip_automation_false_when_disabled(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_pip_automation_enabled(False)
        state = dispatcher.get_automation_state()
        assert state.pip_automation_enabled is False

    def test_snapshot_last_pip_enabled_none_initially(self):
        dispatcher, _ = _dispatcher()
        state = dispatcher.get_automation_state()
        assert state.last_pip_enabled is None

    def test_snapshot_last_pip_enabled_reflects_on_pip_changed(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.on_pip_changed(_pip(True))

        state = dispatcher.get_automation_state()
        assert state.last_pip_enabled is True

    def test_snapshot_last_pip_enabled_false_after_pip_off(self):
        dispatcher, _ = _dispatcher()
        dispatcher.set_armed(True)
        dispatcher.on_pip_changed(_pip(True))
        dispatcher.on_pip_changed(_pip(False))

        state = dispatcher.get_automation_state()
        assert state.last_pip_enabled is False

    def test_snapshot_last_pip_enabled_updated_even_when_automation_disabled(self):
        """State tracking continues even when pip automation is off."""
        dispatcher, _ = _dispatcher()
        dispatcher.set_pip_automation_enabled(False)
        dispatcher.on_pip_changed(_pip(True))

        state = dispatcher.get_automation_state()
        assert state.last_pip_enabled is True

    def test_snapshot_is_frozen_dataclass(self):
        import pytest
        from domain.atem_state import AtemAutomationState
        dispatcher, _ = _dispatcher()
        state = dispatcher.get_automation_state()
        assert isinstance(state, AtemAutomationState)
        with pytest.raises((AttributeError, TypeError)):
            state.armed = True  # type: ignore[misc]
