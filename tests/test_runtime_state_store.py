#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_runtime_state_store.py — RuntimeStateStore unit tests

from __future__ import annotations

import threading
from unittest.mock import MagicMock


from application.runtime_state_store import RuntimeStateStore
from domain.runtime_state import RuntimeState


# ── Helpers ───────────────────────────────────────────────────────────────────

def _store(*camera_ids: str) -> RuntimeStateStore:
    return RuntimeStateStore(camera_ids=list(camera_ids))


# ── Initial state ─────────────────────────────────────────────────────────────

def test_initial_snapshot_is_clean():
    store = _store()
    s = store.snapshot()
    assert not s.lifecycle.startup_complete
    assert not s.session.active
    assert s.cameras == {}


def test_initial_cameras_are_configured_but_not_connected():
    store = _store("cam1", "cam2")
    s = store.snapshot()
    assert set(s.cameras.keys()) == {"cam1", "cam2"}
    assert s.cameras["cam1"].configured
    assert not s.cameras["cam1"].connected


# ── Subscription ──────────────────────────────────────────────────────────────

def test_subscriber_called_after_mutation():
    store = _store()
    received = []
    store.subscribe(received.append)
    store.update_lifecycle(startup_complete=True)
    assert len(received) == 1
    assert received[0].lifecycle.startup_complete


def test_subscriber_receives_snapshot_not_stale():
    store = _store()
    snapshots = []
    store.subscribe(snapshots.append)
    store.update_lifecycle(startup_complete=True)
    store.update_lifecycle(shutdown_in_progress=True)
    assert snapshots[0].lifecycle.startup_complete
    assert snapshots[1].lifecycle.shutdown_in_progress


def test_unsubscribe_stops_notifications():
    store = _store()
    received = []
    store.subscribe(received.append)
    store.unsubscribe(received.append)
    store.update_lifecycle(startup_complete=True)
    assert received == []


def test_unsubscribe_unknown_callback_is_silent():
    store = _store()
    store.unsubscribe(lambda s: None)  # should not raise


def test_subscriber_exception_does_not_crash_store():
    store = _store()

    def bad(_):
        raise RuntimeError("boom")

    good = MagicMock()
    store.subscribe(bad)
    store.subscribe(good)
    store.update_lifecycle(startup_complete=True)
    good.assert_called_once()


def test_multiple_subscribers_all_notified():
    store = _store()
    a, b = MagicMock(), MagicMock()
    store.subscribe(a)
    store.subscribe(b)
    store.update_lifecycle(startup_complete=True)
    a.assert_called_once()
    b.assert_called_once()


# ── update_lifecycle ──────────────────────────────────────────────────────────

def test_update_lifecycle_startup_complete():
    store = _store()
    store.update_lifecycle(startup_complete=True)
    assert store.snapshot().lifecycle.startup_complete


def test_update_lifecycle_shutdown():
    store = _store()
    store.update_lifecycle(shutdown_in_progress=True)
    assert store.snapshot().lifecycle.shutdown_in_progress


def test_update_lifecycle_last_error():
    store = _store()
    store.update_lifecycle(last_error="config missing")
    assert store.snapshot().lifecycle.last_error == "config missing"


def test_update_lifecycle_clear_error():
    store = _store()
    store.update_lifecycle(last_error="oops")
    store.update_lifecycle(clear_error=True)
    assert store.snapshot().lifecycle.last_error is None


def test_update_lifecycle_partial_does_not_clobber_other_fields():
    store = _store()
    store.update_lifecycle(startup_complete=True)
    store.update_lifecycle(last_error="x")
    s = store.snapshot()
    assert s.lifecycle.startup_complete
    assert s.lifecycle.last_error == "x"


# ── update_session ────────────────────────────────────────────────────────────

def test_update_session_active():
    store = _store()
    store.update_session(active=True, session_id="sid-1")
    s = store.snapshot()
    assert s.session.active
    assert s.session.session_id == "sid-1"


def test_update_session_clear_chairman():
    store = _store()
    store.update_session(chairman_name="PersonA")
    store.update_session(clear_chairman=True)
    assert store.snapshot().session.chairman_name is None


def test_update_session_clear_session_id():
    store = _store()
    store.update_session(session_id="sid-1")
    store.update_session(clear_session_id=True)
    assert store.snapshot().session.session_id is None


def test_update_session_clear_started_at():
    store = _store()
    store.update_session(started_at="2026-01-01T10:00:00Z")
    store.update_session(clear_started_at=True)
    assert store.snapshot().session.started_at is None


def test_update_session_partial_does_not_clobber_other_fields():
    store = _store()
    store.update_session(active=True, session_id="sid-1", chairman_name="PersonB")
    store.update_session(active=False)
    s = store.snapshot()
    assert not s.session.active
    assert s.session.session_id == "sid-1"
    assert s.session.chairman_name == "PersonB"


# ── update_camera ─────────────────────────────────────────────────────────────

def test_update_camera_connected():
    store = _store("cam1")
    store.update_camera("cam1", connected=True)
    assert store.snapshot().cameras["cam1"].connected


def test_update_camera_movement_state():
    store = _store("cam1")
    store.update_camera("cam1", movement_state="moving")
    assert store.snapshot().cameras["cam1"].movement_state == "moving"


def test_update_camera_active_preset():
    store = _store("cam1")
    store.update_camera("cam1", active_preset=5)
    assert store.snapshot().cameras["cam1"].active_preset == 5


def test_update_camera_clear_preset():
    store = _store("cam1")
    store.update_camera("cam1", active_preset=5)
    store.update_camera("cam1", clear_preset=True)
    assert store.snapshot().cameras["cam1"].active_preset is None


def test_update_camera_last_error_and_clear():
    store = _store("cam1")
    store.update_camera("cam1", last_error="timeout")
    assert store.snapshot().cameras["cam1"].last_error == "timeout"
    store.update_camera("cam1", clear_error=True)
    assert store.snapshot().cameras["cam1"].last_error is None


def test_update_camera_touch_last_seen_sets_timestamp():
    store = _store("cam1")
    store.update_camera("cam1", touch_last_seen=True)
    assert store.snapshot().cameras["cam1"].last_seen_at is not None


def test_update_camera_unknown_id_creates_entry():
    store = _store()
    store.update_camera("new_cam", connected=True)
    assert "new_cam" in store.snapshot().cameras
    assert store.snapshot().cameras["new_cam"].connected


def test_update_camera_does_not_clobber_other_cameras():
    store = _store("cam1", "cam2")
    store.update_camera("cam1", connected=True)
    assert not store.snapshot().cameras["cam2"].connected


# ── update_atem ───────────────────────────────────────────────────────────────

def test_update_atem_enabled():
    store = _store()
    store.update_atem(enabled=True)
    assert store.snapshot().atem.enabled


def test_update_atem_connection_state():
    store = _store()
    store.update_atem(connection_state="connected")
    assert store.snapshot().atem.connection_state == "connected"


def test_update_atem_program_input():
    store = _store()
    store.update_atem(program_input=3)
    assert store.snapshot().atem.program_input == 3


def test_update_atem_clear_error():
    store = _store()
    store.update_atem(last_error="connection refused")
    store.update_atem(clear_error=True)
    assert store.snapshot().atem.last_error is None


# ── begin/end_operation ───────────────────────────────────────────────────────

def test_begin_operation_sets_action():
    store = _store()
    store.begin_operation("recall_preset")
    assert store.snapshot().operations.active_operator_action == "recall_preset"


def test_end_operation_clears_action():
    store = _store()
    store.begin_operation("recall_preset")
    store.end_operation()
    assert store.snapshot().operations.active_operator_action is None


def test_end_operation_preserves_safety_reset_flag():
    store = _store()
    store.begin_safety_reset()
    store.end_operation()
    assert store.snapshot().operations.safety_reset_in_progress


# ── begin_safety_reset ────────────────────────────────────────────────────────

def test_begin_safety_reset_sets_flag():
    store = _store()
    store.begin_safety_reset()
    assert store.snapshot().operations.safety_reset_in_progress


def test_begin_safety_reset_preserves_active_action():
    store = _store()
    store.begin_operation("some_action")
    store.begin_safety_reset()
    s = store.snapshot()
    assert s.operations.safety_reset_in_progress
    assert s.operations.active_operator_action == "some_action"


# ── apply_safety_reset_clean_state ────────────────────────────────────────────

def test_apply_safety_reset_clears_session():
    store = _store("cam1")
    store.update_session(active=True, session_id="sid-1", chairman_name="PersonA")
    store.begin_safety_reset()
    store.apply_safety_reset_clean_state()
    s = store.snapshot()
    assert not s.session.active
    assert s.session.session_id is None
    assert s.session.chairman_name is None


def test_apply_safety_reset_resets_camera_movement():
    store = _store("cam1", "cam2")
    store.update_camera("cam1", movement_state="moving", active_preset=3)
    store.begin_safety_reset()
    store.apply_safety_reset_clean_state()
    cam = store.snapshot().cameras["cam1"]
    assert cam.movement_state == "unknown"
    assert cam.active_preset is None
    assert cam.last_error is None


def test_apply_safety_reset_preserves_camera_hw_status():
    store = _store("cam1")
    store.update_camera("cam1", configured=True, connected=True)
    store.begin_safety_reset()
    store.apply_safety_reset_clean_state()
    cam = store.snapshot().cameras["cam1"]
    assert cam.configured
    assert cam.connected


def test_apply_safety_reset_clears_operations_flags():
    store = _store()
    store.begin_safety_reset()
    store.begin_operation("test_action")
    store.apply_safety_reset_clean_state()
    ops = store.snapshot().operations
    assert not ops.safety_reset_in_progress
    assert ops.active_operator_action is None


def test_apply_safety_reset_does_not_touch_lifecycle():
    store = _store()
    store.update_lifecycle(startup_complete=True)
    store.apply_safety_reset_clean_state()
    assert store.snapshot().lifecycle.startup_complete


# ── update_diagnostics ────────────────────────────────────────────────────────

def test_update_diagnostics_degraded():
    store = _store()
    store.update_diagnostics(degraded=True, degraded_reason="camera offline")
    s = store.snapshot()
    assert s.diagnostics.degraded
    assert s.diagnostics.degraded_reason == "camera offline"


def test_update_diagnostics_clear_reason():
    store = _store()
    store.update_diagnostics(degraded=True, degraded_reason="x")
    store.update_diagnostics(clear_reason=True)
    assert store.snapshot().diagnostics.degraded_reason is None


# ── Thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_updates_do_not_corrupt_state():
    store = _store("cam1")
    errors = []

    def worker(i):
        try:
            store.update_lifecycle(startup_complete=(i % 2 == 0))
            store.update_camera("cam1", movement_state=f"state_{i}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # snapshot() must always return a valid RuntimeState
    s = store.snapshot()
    assert isinstance(s, RuntimeState)

