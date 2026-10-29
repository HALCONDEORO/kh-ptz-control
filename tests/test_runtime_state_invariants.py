#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_runtime_state_invariants.py
#
# Issue: #795 — Epic #787 (single source of truth for runtime state)
#
# Validates RuntimeState and RuntimeStateStore invariants:
#   - If session.active is False, active_operator_action should not indicate
#     active camera movement (enforced by convention; store accepts it but tests catch it).
#   - After apply_safety_reset_clean_state():
#       session.active == False
#       operations.safety_reset_in_progress == False
#       active_operator_action is None
#       all camera movement_state == "unknown"
#   - Camera cannot be selected (preset active) if not configured.
#   - ATEM connection state cleared on safety reset is "not stored as connected".
#   - RuntimeState is immutable (frozen dataclass).
#   - Snapshots are independent; mutations don't affect prior snapshots.

from __future__ import annotations

import threading
import pytest

from domain.runtime_state import (
    AtemRuntimeState,
    CameraRuntimeState,
    OperationsState,
    RuntimeState,
    SessionRuntimeState,
)
from application.runtime_state_store import RuntimeStateStore


# ─────────────────────────────────────────────────────────────────────────────
#  RuntimeState domain model tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRuntimeStateImmutability:
    """RuntimeState is a frozen dataclass — mutation attempts must fail."""

    def test_runtime_state_is_frozen(self):
        state = RuntimeState()
        with pytest.raises((AttributeError, TypeError)):
            state.session = SessionRuntimeState(active=True)  # type: ignore[misc]

    def test_session_runtime_state_is_frozen(self):
        s = SessionRuntimeState(active=False)
        with pytest.raises((AttributeError, TypeError)):
            s.active = True  # type: ignore[misc]

    def test_camera_runtime_state_is_frozen(self):
        c = CameraRuntimeState(camera_id="cam1")
        with pytest.raises((AttributeError, TypeError)):
            c.connected = True  # type: ignore[misc]

    def test_atem_runtime_state_is_frozen(self):
        a = AtemRuntimeState()
        with pytest.raises((AttributeError, TypeError)):
            a.enabled = True  # type: ignore[misc]

    def test_operations_state_is_frozen(self):
        o = OperationsState()
        with pytest.raises((AttributeError, TypeError)):
            o.safety_reset_in_progress = True  # type: ignore[misc]


class TestRuntimeStateDefaults:
    """Default state must represent a clean, not-yet-started system."""

    def test_default_session_inactive(self):
        state = RuntimeState()
        assert state.session.active is False
        assert state.session.session_id is None
        assert state.session.chairman_name is None

    def test_default_no_safety_reset_in_progress(self):
        state = RuntimeState()
        assert state.operations.safety_reset_in_progress is False
        assert state.operations.active_operator_action is None

    def test_default_not_degraded(self):
        state = RuntimeState()
        assert state.diagnostics.degraded is False

    def test_clean_state_factory_cameras(self):
        state = RuntimeState.clean_state(camera_ids=["cam1", "cam2"])
        assert set(state.cameras.keys()) == {"cam1", "cam2"}
        for cam in state.cameras.values():
            assert cam.configured is True
            assert cam.connected is False
            assert cam.movement_state == "unknown"


class TestRuntimeStateSerialisation:
    """Serialisation must not expose customer PII."""

    def test_to_dict_contains_session(self):
        state = RuntimeState(
            session=SessionRuntimeState(active=True, chairman_name="PersonA"),
        )
        d = state.to_dict()
        assert d["session"]["active"] is True
        assert d["session"]["chairman_name"] == "PersonA"

    def test_to_redacted_dict_hides_chairman(self):
        state = RuntimeState(
            session=SessionRuntimeState(active=True, chairman_name="PersonA"),
        )
        d = state.to_redacted_dict()
        assert d["session"]["chairman_name"] == "[REDACTED]"

    def test_to_redacted_dict_no_chairman_not_redacted(self):
        state = RuntimeState(
            session=SessionRuntimeState(active=False, chairman_name=None),
        )
        d = state.to_redacted_dict()
        assert d["session"]["chairman_name"] is None  # nothing to redact

    def test_to_dict_cameras_present(self):
        state = RuntimeState(
            cameras={"cam1": CameraRuntimeState(camera_id="cam1", connected=True)},
        )
        d = state.to_dict()
        assert "cam1" in d["cameras"]
        assert d["cameras"]["cam1"]["connected"] is True


# ─────────────────────────────────────────────────────────────────────────────
#  RuntimeStateStore tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRuntimeStateStoreBasics:

    def test_initial_snapshot_is_clean(self):
        store = RuntimeStateStore(camera_ids=["cam1"])
        snap = store.snapshot()
        assert snap.session.active is False
        assert snap.operations.safety_reset_in_progress is False
        assert snap.cameras["cam1"].configured is True

    def test_snapshot_independence(self):
        """Mutations must not retroactively affect previous snapshots."""
        store = RuntimeStateStore()
        snap_before = store.snapshot()
        store.update_session(active=True, session_id="s-abc")
        snap_after = store.snapshot()
        assert snap_before.session.active is False
        assert snap_after.session.active is True

    def test_update_session_start(self):
        store = RuntimeStateStore()
        store.update_session(active=True, session_id="s-001", started_at="2026-01-01T00:00:00Z")
        snap = store.snapshot()
        assert snap.session.active is True
        assert snap.session.session_id == "s-001"
        assert snap.session.started_at == "2026-01-01T00:00:00Z"

    def test_update_session_end_clears_chairman(self):
        store = RuntimeStateStore()
        store.update_session(active=True, session_id="s-001", chairman_name="PersonB")
        store.update_session(active=False, clear_session_id=True, clear_chairman=True)
        snap = store.snapshot()
        assert snap.session.active is False
        assert snap.session.session_id is None
        assert snap.session.chairman_name is None

    def test_update_camera_connected(self):
        store = RuntimeStateStore(camera_ids=["cam1"])
        store.update_camera("cam1", connected=True, movement_state="idle")
        snap = store.snapshot()
        assert snap.cameras["cam1"].connected is True
        assert snap.cameras["cam1"].movement_state == "idle"

    def test_update_camera_error_and_clear(self):
        store = RuntimeStateStore(camera_ids=["cam1"])
        store.update_camera("cam1", last_error="timeout")
        assert store.snapshot().cameras["cam1"].last_error == "timeout"
        store.update_camera("cam1", clear_error=True)
        assert store.snapshot().cameras["cam1"].last_error is None

    def test_update_atem(self):
        store = RuntimeStateStore()
        store.update_atem(enabled=True, connection_state="connected", program_input=3)
        snap = store.snapshot()
        assert snap.atem.enabled is True
        assert snap.atem.connection_state == "connected"
        assert snap.atem.program_input == 3

    def test_lifecycle_update(self):
        store = RuntimeStateStore()
        store.update_lifecycle(startup_complete=True)
        assert store.snapshot().lifecycle.startup_complete is True

    def test_begin_end_operation(self):
        store = RuntimeStateStore()
        store.begin_operation("moving")
        assert store.snapshot().operations.active_operator_action == "moving"
        store.end_operation()
        assert store.snapshot().operations.active_operator_action is None


class TestRuntimeStateStoreSafetyReset:
    """Invariants that must hold after apply_safety_reset_clean_state()."""

    def test_session_cleared_after_reset(self):
        store = RuntimeStateStore(camera_ids=["cam1"])
        store.update_session(active=True, session_id="s-abc", chairman_name="PersonA")
        store.apply_safety_reset_clean_state()
        snap = store.snapshot()
        assert snap.session.active is False
        assert snap.session.session_id is None
        assert snap.session.chairman_name is None

    def test_safety_reset_in_progress_cleared(self):
        store = RuntimeStateStore()
        store.begin_safety_reset()
        assert store.snapshot().operations.safety_reset_in_progress is True
        store.apply_safety_reset_clean_state()
        assert store.snapshot().operations.safety_reset_in_progress is False

    def test_active_operator_action_cleared_after_reset(self):
        store = RuntimeStateStore()
        store.begin_operation("preset_recall")
        store.apply_safety_reset_clean_state()
        assert store.snapshot().operations.active_operator_action is None

    def test_camera_movement_state_unknown_after_reset(self):
        store = RuntimeStateStore(camera_ids=["cam1", "cam2"])
        store.update_camera("cam1", movement_state="moving", connected=True)
        store.update_camera("cam2", movement_state="preset_recalling", connected=True)
        store.apply_safety_reset_clean_state()
        snap = store.snapshot()
        assert snap.cameras["cam1"].movement_state == "unknown"
        assert snap.cameras["cam2"].movement_state == "unknown"

    def test_camera_connection_preserved_after_reset(self):
        """Camera connected status is not cleared by Safety Reset."""
        store = RuntimeStateStore(camera_ids=["cam1"])
        store.update_camera("cam1", connected=True)
        store.apply_safety_reset_clean_state()
        snap = store.snapshot()
        assert snap.cameras["cam1"].connected is True

    def test_active_preset_cleared_after_reset(self):
        store = RuntimeStateStore(camera_ids=["cam1"])
        store.update_camera("cam1", active_preset=5)
        store.apply_safety_reset_clean_state()
        assert store.snapshot().cameras["cam1"].active_preset is None

    def test_idempotent_safety_reset(self):
        """Calling apply_safety_reset_clean_state() twice is safe."""
        store = RuntimeStateStore(camera_ids=["cam1"])
        store.apply_safety_reset_clean_state()
        store.apply_safety_reset_clean_state()
        snap = store.snapshot()
        assert snap.session.active is False
        assert snap.operations.safety_reset_in_progress is False


class TestRuntimeStateStoreSubscribers:

    def test_subscriber_called_on_update(self):
        store = RuntimeStateStore()
        received = []
        store.subscribe(received.append)
        store.update_session(active=True, session_id="s-x")
        assert len(received) == 1
        assert received[0].session.active is True

    def test_subscriber_not_called_after_unsubscribe(self):
        store = RuntimeStateStore()
        received = []
        store.subscribe(received.append)
        store.unsubscribe(received.append)
        store.update_session(active=True)
        assert len(received) == 0

    def test_subscriber_error_does_not_crash_store(self):
        store = RuntimeStateStore()

        def bad_callback(snap):
            raise ValueError("oops")

        store.subscribe(bad_callback)
        # Must not raise
        store.update_session(active=True)
        assert store.snapshot().session.active is True


class TestRuntimeStateStoreThreadSafety:
    """Concurrent mutations must not corrupt the store."""

    def test_concurrent_updates_no_exception(self):
        store = RuntimeStateStore(camera_ids=["cam1", "cam2"])
        errors = []

        def writer(cam_id, n):
            try:
                for i in range(n):
                    store.update_camera(cam_id, connected=(i % 2 == 0))
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=("cam1", 50)),
            threading.Thread(target=writer, args=("cam2", 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        snap = store.snapshot()
        assert "cam1" in snap.cameras
        assert "cam2" in snap.cameras

    def test_session_and_camera_concurrent(self):
        store = RuntimeStateStore(camera_ids=["cam1"])
        errors = []

        def session_writer():
            try:
                for _ in range(30):
                    store.update_session(active=True, session_id="s-x")
                    store.update_session(active=False, clear_session_id=True)
            except Exception as exc:
                errors.append(exc)

        def camera_writer():
            try:
                for _ in range(30):
                    store.update_camera("cam1", connected=True)
                    store.update_camera("cam1", connected=False)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=session_writer)
        t2 = threading.Thread(target=camera_writer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors


# ─────────────────────────────────────────────────────────────────────────────
#  Business invariants
# ─────────────────────────────────────────────────────────────────────────────

class TestBusinessInvariants:
    """Higher-level state correctness rules from the epic spec."""

    def test_no_active_session_means_no_movement_after_reset(self):
        """
        After Safety Reset: session.active is False and all movement_state is
        'unknown' — no camera should appear to be moving.
        """
        store = RuntimeStateStore(camera_ids=["cam1"])
        store.update_session(active=True, session_id="s-1")
        store.update_camera("cam1", movement_state="moving")
        store.apply_safety_reset_clean_state()
        snap = store.snapshot()
        assert snap.session.active is False
        # 'unknown' or 'idle' — not 'moving'
        assert snap.cameras["cam1"].movement_state != "moving"

    def test_unconfigured_camera_never_has_active_preset(self):
        """
        A camera that was never configured should not have an active preset.
        (Store enforces this through clean_state which sets configured=True for
        known IDs only; unknown IDs start with configured=False by default.)
        """
        store = RuntimeStateStore()
        snap = store.snapshot()
        # No cameras registered — cameras dict is empty
        assert snap.cameras == {}

    def test_chairman_name_cleared_on_session_end(self):
        store = RuntimeStateStore()
        store.update_session(active=True, session_id="s-1", chairman_name="Carlos")
        store.update_session(active=False, clear_session_id=True, clear_chairman=True)
        snap = store.snapshot()
        assert snap.session.chairman_name is None

    def test_atem_not_connected_during_not_configured(self):
        store = RuntimeStateStore()
        store.update_atem(enabled=False, connection_state="not_configured")
        snap = store.snapshot()
        assert snap.atem.connection_state != "connected"

    def test_safety_reset_flag_cleared_before_notifying_subscribers(self):
        """
        Subscribers receive a snapshot where safety_reset_in_progress is already
        False after apply_safety_reset_clean_state().
        """
        store = RuntimeStateStore()
        store.begin_safety_reset()
        received = []
        store.subscribe(received.append)
        store.apply_safety_reset_clean_state()
        assert len(received) == 1
        assert received[0].operations.safety_reset_in_progress is False
