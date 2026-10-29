#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_runtime_state_safety_reset.py
#
# Issue: #797 — Epic #787 (validate RuntimeState clean-state after Safety Reset)
#
# Tests that RuntimeStateStore reaches the expected clean state after:
#   - Safety Reset
#   - Session End
#   - Shutdown
#   - App start (initial state)
#
# Also verifies the RuntimeAuditLog records the right transitions.

from __future__ import annotations


from application.runtime_state_store import RuntimeStateStore
from application.runtime_audit_log import RuntimeAuditLog


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _active_store(camera_ids=None) -> RuntimeStateStore:
    """Return a store in a typical mid-session state."""
    store = RuntimeStateStore(camera_ids=camera_ids or ["cam1", "cam2"])
    store.update_lifecycle(startup_complete=True)
    store.update_session(active=True, session_id="s-test", chairman_name="Someone")
    store.update_camera("cam1", connected=True, movement_state="moving", active_preset=3)
    store.update_camera("cam2", connected=True, movement_state="idle", active_preset=1)
    store.update_atem(enabled=True, connection_state="connected", program_input=2)
    store.begin_operation("preset_recall")
    return store


# ─────────────────────────────────────────────────────────────────────────────
#  Clean state after Safety Reset
# ─────────────────────────────────────────────────────────────────────────────

class TestSafetyResetCleanState:
    """After begin_safety_reset() + apply_safety_reset_clean_state()."""

    def test_session_inactive_after_reset(self):
        store = _active_store()
        store.begin_safety_reset()
        store.apply_safety_reset_clean_state()
        assert store.snapshot().session.active is False

    def test_session_id_cleared_after_reset(self):
        store = _active_store()
        store.apply_safety_reset_clean_state()
        assert store.snapshot().session.session_id is None

    def test_chairman_cleared_after_reset(self):
        store = _active_store()
        store.apply_safety_reset_clean_state()
        assert store.snapshot().session.chairman_name is None

    def test_safety_reset_in_progress_false_after_reset(self):
        store = _active_store()
        store.begin_safety_reset()
        assert store.snapshot().operations.safety_reset_in_progress is True
        store.apply_safety_reset_clean_state()
        assert store.snapshot().operations.safety_reset_in_progress is False

    def test_active_operator_action_none_after_reset(self):
        store = _active_store()
        store.apply_safety_reset_clean_state()
        assert store.snapshot().operations.active_operator_action is None

    def test_camera_movement_unknown_after_reset(self):
        store = _active_store()
        store.apply_safety_reset_clean_state()
        snap = store.snapshot()
        assert snap.cameras["cam1"].movement_state == "unknown"
        assert snap.cameras["cam2"].movement_state == "unknown"

    def test_camera_active_preset_cleared_after_reset(self):
        store = _active_store()
        store.apply_safety_reset_clean_state()
        snap = store.snapshot()
        assert snap.cameras["cam1"].active_preset is None
        assert snap.cameras["cam2"].active_preset is None

    def test_camera_connected_preserved_after_reset(self):
        """Safety Reset does NOT disconnect cameras — hardware status unchanged."""
        store = _active_store()
        store.apply_safety_reset_clean_state()
        snap = store.snapshot()
        assert snap.cameras["cam1"].connected is True
        assert snap.cameras["cam2"].connected is True

    def test_atem_state_preserved_after_reset(self):
        """Safety Reset does NOT send commands to ATEM — connection state unchanged."""
        store = _active_store()
        store.apply_safety_reset_clean_state()
        snap = store.snapshot()
        assert snap.atem.connection_state == "connected"
        assert snap.atem.program_input == 2

    def test_lifecycle_preserved_after_reset(self):
        """Lifecycle flags are not touched by Safety Reset."""
        store = _active_store()
        store.apply_safety_reset_clean_state()
        assert store.snapshot().lifecycle.startup_complete is True


# ─────────────────────────────────────────────────────────────────────────────
#  Clean state after Session End (normal flow)
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionEndCleanState:
    """After update_session(active=False, clear_session_id=True, clear_chairman=True)."""

    def test_session_inactive_after_end(self):
        store = _active_store()
        store.update_session(active=False, clear_session_id=True, clear_chairman=True)
        assert store.snapshot().session.active is False

    def test_session_id_cleared_after_end(self):
        store = _active_store()
        store.update_session(active=False, clear_session_id=True)
        assert store.snapshot().session.session_id is None

    def test_chairman_cleared_after_end(self):
        store = _active_store()
        store.update_session(active=False, clear_chairman=True)
        assert store.snapshot().session.chairman_name is None


# ─────────────────────────────────────────────────────────────────────────────
#  Clean state after app start (initial state)
# ─────────────────────────────────────────────────────────────────────────────

class TestInitialCleanState:
    """Immediately after RuntimeStateStore creation — represents known-good start."""

    def test_initial_session_inactive(self):
        store = RuntimeStateStore(camera_ids=["cam1"])
        assert store.snapshot().session.active is False

    def test_initial_no_safety_reset(self):
        store = RuntimeStateStore()
        assert store.snapshot().operations.safety_reset_in_progress is False

    def test_initial_no_operator_action(self):
        store = RuntimeStateStore()
        assert store.snapshot().operations.active_operator_action is None

    def test_initial_cameras_configured_not_connected(self):
        store = RuntimeStateStore(camera_ids=["cam1", "cam2"])
        snap = store.snapshot()
        for cam in snap.cameras.values():
            assert cam.configured is True
            assert cam.connected is False
            assert cam.movement_state == "unknown"

    def test_initial_lifecycle_not_complete(self):
        store = RuntimeStateStore()
        assert store.snapshot().lifecycle.startup_complete is False


# ─────────────────────────────────────────────────────────────────────────────
#  Clean state after shutdown initiated
# ─────────────────────────────────────────────────────────────────────────────

class TestShutdownCleanState:
    """Shutdown sets lifecycle.shutdown_in_progress without affecting other state."""

    def test_shutdown_flag_set(self):
        store = RuntimeStateStore()
        store.update_lifecycle(shutdown_in_progress=True)
        assert store.snapshot().lifecycle.shutdown_in_progress is True

    def test_shutdown_flag_does_not_affect_session(self):
        store = _active_store()
        store.update_lifecycle(shutdown_in_progress=True)
        # Session should remain as-is — shutdown doesn't auto-end session
        assert store.snapshot().session.active is True

    def test_shutdown_after_safety_reset_is_clean(self):
        store = _active_store()
        store.begin_safety_reset()
        store.apply_safety_reset_clean_state()
        store.update_lifecycle(shutdown_in_progress=True)
        snap = store.snapshot()
        assert snap.session.active is False
        assert snap.operations.safety_reset_in_progress is False
        assert snap.lifecycle.shutdown_in_progress is True


# ─────────────────────────────────────────────────────────────────────────────
#  Audit log transitions
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditLogTransitions:
    """RuntimeAuditLog records the expected events for key lifecycle transitions."""

    def test_session_start_recorded(self):
        store = RuntimeStateStore()
        log = RuntimeAuditLog()
        store.subscribe(log.on_state_change)
        store.update_session(active=True, session_id="s-abc")
        events = [e.event for e in log.entries()]
        assert "session_started" in events

    def test_session_end_recorded(self):
        store = RuntimeStateStore()
        log = RuntimeAuditLog()
        store.subscribe(log.on_state_change)
        store.update_session(active=True, session_id="s-abc")
        store.update_session(active=False, clear_session_id=True)
        events = [e.event for e in log.entries()]
        assert "session_ended" in events

    def test_safety_reset_initiated_recorded(self):
        store = RuntimeStateStore()
        log = RuntimeAuditLog()
        store.subscribe(log.on_state_change)
        store.begin_safety_reset()
        events = [e.event for e in log.entries()]
        assert "safety_reset_initiated" in events

    def test_safety_reset_complete_recorded(self):
        store = RuntimeStateStore()
        log = RuntimeAuditLog()
        store.subscribe(log.on_state_change)
        store.begin_safety_reset()
        store.apply_safety_reset_clean_state()
        events = [e.event for e in log.entries()]
        assert "safety_reset_complete" in events

    def test_camera_connected_recorded(self):
        store = RuntimeStateStore(camera_ids=["cam1"])
        log = RuntimeAuditLog()
        store.subscribe(log.on_state_change)
        store.update_camera("cam1", connected=True)
        events = [e.event for e in log.entries()]
        assert "camera_connected" in events

    def test_camera_disconnected_recorded(self):
        store = RuntimeStateStore(camera_ids=["cam1"])
        log = RuntimeAuditLog()
        store.subscribe(log.on_state_change)
        store.update_camera("cam1", connected=True)
        store.update_camera("cam1", connected=False)
        events = [e.event for e in log.entries()]
        assert "camera_disconnected" in events

    def test_atem_state_changed_recorded(self):
        store = RuntimeStateStore()
        log = RuntimeAuditLog()
        store.subscribe(log.on_state_change)
        store.update_atem(connection_state="connected")
        events = [e.event for e in log.entries()]
        assert "atem_state_changed" in events

    def test_chairman_assigned_not_storing_name(self):
        """Audit log must not store chairman names — PII."""
        store = RuntimeStateStore()
        log = RuntimeAuditLog()
        store.subscribe(log.on_state_change)
        store.update_session(chairman_name="Secret Name")
        # Find the chairman_assigned entry
        for e in log.entries():
            if e.event == "chairman_assigned":
                assert "Secret Name" not in str(e.details)
                return
        # Either chairman_assigned was recorded without PII, or no entry — pass either way.

    def test_audit_log_to_dict_list(self):
        store = RuntimeStateStore()
        log = RuntimeAuditLog()
        store.subscribe(log.on_state_change)
        store.update_session(active=True, session_id="s-1")
        result = log.to_dict_list()
        assert isinstance(result, list)
        assert all("timestamp" in e and "event" in e for e in result)

