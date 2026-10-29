#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_runtime_audit_log.py — RuntimeAuditLog unit tests

from __future__ import annotations


from application.runtime_audit_log import RuntimeAuditLog, AuditEntry
from domain.runtime_state import (
    AtemRuntimeState,
    CameraRuntimeState,
    LifecycleState,
    OperationsState,
    RuntimeState,
    SessionRuntimeState,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _state(**kwargs) -> RuntimeState:
    """Build a RuntimeState, merging kwargs into defaults."""
    return RuntimeState(**{k: v for k, v in kwargs.items()})


def _session(active=False, session_id=None, chairman_name=None) -> SessionRuntimeState:
    return SessionRuntimeState(active=active, session_id=session_id, chairman_name=chairman_name)


def _camera(camera_id: str, connected=False, movement_state="unknown") -> CameraRuntimeState:
    return CameraRuntimeState(camera_id=camera_id, connected=connected, movement_state=movement_state)


def _operations(safety_reset=False, action=None) -> OperationsState:
    return OperationsState(safety_reset_in_progress=safety_reset, active_operator_action=action)


def _atem(connection_state="disconnected") -> AtemRuntimeState:
    return AtemRuntimeState(connection_state=connection_state)


def _lifecycle(startup_complete=False, shutdown_in_progress=False) -> LifecycleState:
    return LifecycleState(startup_complete=startup_complete, shutdown_in_progress=shutdown_in_progress)


def _event_names(log: RuntimeAuditLog) -> list[str]:
    return [e.event for e in log.entries()]


# ── AuditEntry ────────────────────────────────────────────────────────────────

def test_audit_entry_has_timestamp():
    entry = AuditEntry("test_event")
    assert entry.timestamp
    assert "Z" in entry.timestamp


def test_audit_entry_to_dict_contains_required_keys():
    entry = AuditEntry("test_event", {"key": "value"})
    d = entry.to_dict()
    assert d["event"] == "test_event"
    assert d["details"] == {"key": "value"}
    assert "timestamp" in d


def test_audit_entry_defaults_empty_details():
    entry = AuditEntry("test_event")
    assert entry.details == {}


# ── Manual recording ──────────────────────────────────────────────────────────

def test_record_adds_entry():
    log = RuntimeAuditLog()
    log.record("manual_event", {"reason": "test"})
    assert len(log.entries()) == 1
    assert log.entries()[0].event == "manual_event"


def test_record_details_stored():
    log = RuntimeAuditLog()
    log.record("x", {"foo": "bar"})
    assert log.entries()[0].details == {"foo": "bar"}


def test_entries_returns_copy():
    log = RuntimeAuditLog()
    log.record("a")
    copy = log.entries()
    copy.append(AuditEntry("injected"))
    assert len(log.entries()) == 1


# ── to_dict_list ─────────────────────────────────────────────────────────────

def test_to_dict_list_serializes_all_entries():
    log = RuntimeAuditLog()
    log.record("event_1")
    log.record("event_2")
    result = log.to_dict_list()
    assert len(result) == 2
    assert result[0]["event"] == "event_1"
    assert result[1]["event"] == "event_2"


# ── clear ─────────────────────────────────────────────────────────────────────

def test_clear_empties_all_entries():
    log = RuntimeAuditLog()
    log.record("x")
    log.clear()
    assert log.entries() == []


def test_clear_resets_previous_snapshot():
    log = RuntimeAuditLog()
    state = _state()
    log.on_state_change(state)
    log.clear()
    # After clear, first on_state_change call should re-emit runtime_state_initialized
    log.on_state_change(state)
    assert "runtime_state_initialized" in _event_names(log)


# ── on_state_change: first call ───────────────────────────────────────────────

def test_first_state_change_emits_initialized():
    log = RuntimeAuditLog()
    log.on_state_change(_state())
    assert "runtime_state_initialized" in _event_names(log)


def test_initialized_includes_camera_ids():
    log = RuntimeAuditLog()
    state = _state(cameras={"cam1": _camera("cam1"), "cam2": _camera("cam2")})
    log.on_state_change(state)
    entry = next(e for e in log.entries() if e.event == "runtime_state_initialized")
    assert set(entry.details["cameras"]) == {"cam1", "cam2"}


# ── Session transitions ───────────────────────────────────────────────────────

def test_session_started_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(session=_session(active=False)))
    log.on_state_change(_state(session=_session(active=True, session_id="sid-1")))
    assert "session_started" in _event_names(log)
    entry = next(e for e in log.entries() if e.event == "session_started")
    assert entry.details["session_id"] == "sid-1"


def test_session_ended_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(session=_session(active=True, session_id="sid-1")))
    log.on_state_change(_state(session=_session(active=False)))
    assert "session_ended" in _event_names(log)
    entry = next(e for e in log.entries() if e.event == "session_ended")
    assert entry.details["previous_session_id"] == "sid-1"


# ── Chairman transitions ──────────────────────────────────────────────────────

def test_chairman_assigned_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(session=_session()))
    log.on_state_change(_state(session=_session(chairman_name="PersonA")))
    assert "chairman_assigned" in _event_names(log)


def test_chairman_name_not_stored_in_event_details():
    log = RuntimeAuditLog()
    log.on_state_change(_state(session=_session()))
    log.on_state_change(_state(session=_session(chairman_name="PersonA")))
    entry = next(e for e in log.entries() if e.event == "chairman_assigned")
    assert "PersonA" not in str(entry.details)


def test_chairman_cleared_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(session=_session(chairman_name="PersonA")))
    log.on_state_change(_state(session=_session(chairman_name=None)))
    assert "chairman_cleared" in _event_names(log)


# ── Safety Reset transitions ──────────────────────────────────────────────────

def test_safety_reset_initiated_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(operations=_operations(safety_reset=False)))
    log.on_state_change(_state(operations=_operations(safety_reset=True)))
    assert "safety_reset_initiated" in _event_names(log)


def test_safety_reset_complete_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(operations=_operations(safety_reset=True)))
    log.on_state_change(_state(operations=_operations(safety_reset=False)))
    assert "safety_reset_complete" in _event_names(log)


# ── Operator action transitions ───────────────────────────────────────────────

def test_operator_action_started_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(operations=_operations(action=None)))
    log.on_state_change(_state(operations=_operations(action="recall_preset")))
    assert "operator_action_started" in _event_names(log)
    entry = next(e for e in log.entries() if e.event == "operator_action_started")
    assert entry.details["action"] == "recall_preset"


def test_operator_action_ended_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(operations=_operations(action="recall_preset")))
    log.on_state_change(_state(operations=_operations(action=None)))
    assert "operator_action_ended" in _event_names(log)
    entry = next(e for e in log.entries() if e.event == "operator_action_ended")
    assert entry.details["action"] == "recall_preset"


# ── Camera transitions ────────────────────────────────────────────────────────

def test_camera_registered_event_when_new_camera_appears():
    log = RuntimeAuditLog()
    log.on_state_change(_state(cameras={}))
    log.on_state_change(_state(cameras={"cam1": _camera("cam1")}))
    assert "camera_registered" in _event_names(log)


def test_camera_connected_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(cameras={"cam1": _camera("cam1", connected=False)}))
    log.on_state_change(_state(cameras={"cam1": _camera("cam1", connected=True)}))
    assert "camera_connected" in _event_names(log)


def test_camera_disconnected_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(cameras={"cam1": _camera("cam1", connected=True)}))
    log.on_state_change(_state(cameras={"cam1": _camera("cam1", connected=False)}))
    assert "camera_disconnected" in _event_names(log)


def test_camera_movement_state_changed_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(cameras={"cam1": _camera("cam1", movement_state="idle")}))
    log.on_state_change(_state(cameras={"cam1": _camera("cam1", movement_state="moving")}))
    events = [e for e in log.entries() if e.event == "camera_movement_state_changed"]
    assert events
    assert events[-1].details["from"] == "idle"
    assert events[-1].details["to"] == "moving"


# ── ATEM transitions ──────────────────────────────────────────────────────────

def test_atem_state_changed_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(atem=_atem("not_configured")))
    log.on_state_change(_state(atem=_atem("connected")))
    assert "atem_state_changed" in _event_names(log)
    entry = next(e for e in log.entries() if e.event == "atem_state_changed")
    assert entry.details["from"] == "not_configured"
    assert entry.details["to"] == "connected"


# ── Lifecycle transitions ─────────────────────────────────────────────────────

def test_startup_complete_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(lifecycle=_lifecycle(startup_complete=False)))
    log.on_state_change(_state(lifecycle=_lifecycle(startup_complete=True)))
    assert "startup_complete" in _event_names(log)


def test_shutdown_initiated_event():
    log = RuntimeAuditLog()
    log.on_state_change(_state(lifecycle=_lifecycle(shutdown_in_progress=False)))
    log.on_state_change(_state(lifecycle=_lifecycle(shutdown_in_progress=True)))
    assert "shutdown_initiated" in _event_names(log)


# ── Ring buffer ───────────────────────────────────────────────────────────────

def test_ring_buffer_discards_oldest_when_full():
    log = RuntimeAuditLog(max_entries=3)
    for i in range(5):
        log.record(f"event_{i}")
    names = _event_names(log)
    assert len(names) == 3
    assert "event_0" not in names
    assert "event_4" in names


def test_ring_buffer_default_capacity_is_large_enough_for_typical_use():
    log = RuntimeAuditLog()
    for i in range(200):
        log.record(f"e_{i}")
    assert len(log.entries()) == 200

