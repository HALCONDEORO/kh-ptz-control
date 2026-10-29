#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_session_service.py — SessionService unit tests (FlightRecorder wiring)

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch


from application.runtime_state_store import RuntimeStateStore
from application.session_service import SessionService
from core.state import SystemState


# ── Helpers ───────────────────────────────────────────────────────────────────

class _Port:
    """Minimal CameraPort stub for SessionService tests."""

    def __init__(self):
        self.calls: list = []

    def power_on(self, camera_id: str):
        self.calls.append(("power_on", camera_id))

    def standby(self, camera_id: str):
        self.calls.append(("standby", camera_id))

    def home(self, camera_id: str):
        self.calls.append(("home", camera_id))

    def cancel_polls(self, camera_id: str):
        self.calls.append(("cancel_polls", camera_id))


def _make_recorder():
    rec = MagicMock()
    rec.recorded: list[dict] = []
    rec.record_dict.side_effect = lambda d: rec.recorded.append(d)
    return rec


def _svc(recorder=None, system_state=None, runtime_state_store=None) -> tuple[SessionService, _Port]:
    port = _Port()
    svc = SessionService(
        port,
        flight_recorder=recorder,
        system_state=system_state,
        runtime_state_store=runtime_state_store,
    )
    return svc, port


# ── session_id ────────────────────────────────────────────────────────────────

def test_session_id_is_none_before_start():
    svc, _ = _svc()
    assert svc.session_id is None


def test_session_id_set_after_start():
    svc, _ = _svc()
    svc.start()
    assert svc.session_id is not None
    assert len(svc.session_id) > 0


def test_session_id_cleared_after_end():
    svc, _ = _svc()
    svc.start()
    svc.end()
    assert svc.session_id is None


def test_session_id_unique_across_starts():
    svc, _ = _svc()
    svc.start()
    id1 = svc.session_id
    svc.end()
    svc.start()
    id2 = svc.session_id
    assert id1 != id2


def test_session_id_format():
    svc, _ = _svc()
    svc.start()
    assert svc.session_id.startswith("session-")


# ── FlightRecorder events ─────────────────────────────────────────────────────

def test_start_emits_session_started_event():
    rec = _make_recorder()
    svc, _ = _svc(recorder=rec)
    svc.start()
    rec.record_dict.assert_called_once()
    call_arg = rec.recorded[0]
    assert call_arg["event_type"] == "SessionStarted"


def test_end_emits_session_ended_event():
    rec = _make_recorder()
    svc, _ = _svc(recorder=rec)
    svc.start()
    rec.recorded.clear()
    svc.end()
    rec.record_dict.assert_called()
    last = rec.recorded[-1]
    assert last["event_type"] == "SessionEnded"


def test_start_event_has_session_id():
    rec = _make_recorder()
    svc, _ = _svc(recorder=rec)
    svc.start()
    event = rec.recorded[0]
    assert event["session_id"] == svc.session_id or event["session_id"].startswith("session-")


def test_end_event_has_session_id_matching_start():
    rec = _make_recorder()
    svc, _ = _svc(recorder=rec)
    svc.start()
    started_id = svc.session_id
    svc.end()
    end_event = rec.recorded[-1]
    assert end_event["session_id"] == started_id


def test_start_event_has_timestamp():
    rec = _make_recorder()
    svc, _ = _svc(recorder=rec)
    svc.start()
    event = rec.recorded[0]
    assert "timestamp" in event
    assert "Z" in event["timestamp"]


def test_start_event_has_level():
    rec = _make_recorder()
    svc, _ = _svc(recorder=rec)
    svc.start()
    event = rec.recorded[0]
    assert "level" in event


def test_start_event_has_source():
    rec = _make_recorder()
    svc, _ = _svc(recorder=rec)
    svc.start()
    event = rec.recorded[0]
    assert "source" in event


def test_start_event_has_result():
    rec = _make_recorder()
    svc, _ = _svc(recorder=rec)
    svc.start()
    event = rec.recorded[0]
    assert "result" in event


# ── No recorder — graceful no-op ──────────────────────────────────────────────

def test_start_without_recorder_does_not_raise():
    svc, _ = _svc(recorder=None)
    svc.start()  # must not raise


def test_end_without_recorder_does_not_raise():
    svc, _ = _svc(recorder=None)
    svc.start()
    svc.end()  # must not raise


def test_camera_commands_still_sent_without_recorder():
    svc, port = _svc(recorder=None)
    svc.start()
    svc._power_thread.join(timeout=5)
    assert ("power_on", "cam1") in port.calls
    assert ("power_on", "cam2") in port.calls


# ── Recorder error is silently swallowed ──────────────────────────────────────

def test_recorder_error_does_not_block_session_start():
    rec = MagicMock()
    rec.record_dict.side_effect = OSError("disk full")
    svc, port = _svc(recorder=rec)
    svc.start()  # must not raise
    assert svc.active is True
    svc._power_thread.join(timeout=5)
    assert ("power_on", "cam1") in port.calls


def test_recorder_error_does_not_block_session_end():
    rec = MagicMock()
    rec.record_dict.side_effect = OSError("disk full")
    svc, cam = _svc(recorder=rec)
    svc.start()
    rec.record_dict.side_effect = OSError("disk full")
    svc.end()  # must not raise
    assert svc.active is False


# ── bootstrap wiring ──────────────────────────────────────────────────────────

def test_build_app_context_accepts_flight_recorder(monkeypatch):
    """bootstrap.build_app_context accepts flight_recorder kwarg without error."""
    import bootstrap

    class _FakeCameras:
        pass

    rec = _make_recorder()

    monkeypatch.setattr(bootstrap, "PresetService", lambda: MagicMock())
    monkeypatch.setattr(bootstrap, "AsyncEventBus", lambda: MagicMock(start=lambda: None))
    monkeypatch.setattr(bootstrap, "SystemState", lambda: MagicMock())
    monkeypatch.setattr(bootstrap, "Controller", lambda **_: MagicMock())

    captured = {}

    def _fake_session_svc(
        camera_port,
        camera_ids=None,
        flight_recorder=None,
        system_state=None,
        runtime_state_store=None,
    ):
        captured["recorder"] = flight_recorder
        return MagicMock()

    monkeypatch.setattr(bootstrap, "SessionService", _fake_session_svc)

    bootstrap.build_app_context(_FakeCameras(), flight_recorder=rec)
    assert captured["recorder"] is rec


# ── SystemState mirroring ─────────────────────────────────────────────────────

def test_start_sets_system_state_active():
    state = SystemState()
    svc, _ = _svc(system_state=state)
    assert state.session.active is False
    svc.start()
    assert state.session.active is True


def test_end_clears_system_state_active():
    state = SystemState()
    svc, _ = _svc(system_state=state)
    svc.start()
    svc.end()
    assert state.session.active is False


def test_set_chairman_sets_system_state_chairman_name():
    state = SystemState()
    svc, _ = _svc(system_state=state)
    svc.set_chairman("PersonA")
    assert state.session.chairman_name == "PersonA"


def test_end_clears_system_state_chairman_name():
    state = SystemState()
    svc, _ = _svc(system_state=state)
    svc.start()
    svc.set_chairman("PersonA")
    svc.end()
    assert state.session.chairman_name is None


def test_no_system_state_does_not_raise_on_start():
    svc, _ = _svc(system_state=None)
    svc.start()  # must not raise
    assert svc.active is True


def test_no_system_state_does_not_raise_on_end():
    svc, _ = _svc(system_state=None)
    svc.start()
    svc.end()  # must not raise
    assert svc.active is False


def test_no_system_state_does_not_raise_on_set_chairman():
    svc, _ = _svc(system_state=None)
    svc.set_chairman("Charlie")  # must not raise


# ── Espejo en RuntimeStateStore ───────────────────────────────────────────────

def test_start_sets_runtime_state_session_active():
    store = RuntimeStateStore()
    svc, _ = _svc(runtime_state_store=store)

    with patch(f"{_MARKER_MOD}.mark_session_active"):
        svc.start()

    session = store.snapshot().session
    assert session.active is True
    assert session.session_id == svc.session_id
    assert session.started_at is not None


def test_set_chairman_sets_runtime_state_chairman_name():
    store = RuntimeStateStore()
    svc, _ = _svc(runtime_state_store=store)

    svc.set_chairman("PersonA")

    assert store.snapshot().session.chairman_name == "PersonA"


def test_end_clears_runtime_state_session_fields():
    store = RuntimeStateStore()
    svc, _ = _svc(runtime_state_store=store)
    with patch(f"{_MARKER_MOD}.mark_session_active"):
        svc.start()
    svc.set_chairman("PersonA")

    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        svc.end()

    session = store.snapshot().session
    assert session.active is False
    assert session.session_id is None
    assert session.chairman_name is None
    assert session.started_at is None


def test_clear_runtime_state_clears_runtime_state_without_camera_commands():
    store = RuntimeStateStore()
    svc, port = _svc(runtime_state_store=store)
    with patch(f"{_MARKER_MOD}.mark_session_active"):
        svc.start()
    svc.set_chairman("PersonA")
    port.calls.clear()

    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        svc.clear_runtime_state()

    session = store.snapshot().session
    assert session.active is False
    assert session.session_id is None
    assert session.chairman_name is None
    assert session.started_at is None
    assert port.calls == []


# ── session marker management ──────────────────────────────────────────────────

_MARKER_MOD = "application.session_service"


def test_start_calls_mark_session_active():
    svc, _ = _svc()
    with patch(f"{_MARKER_MOD}.mark_session_active") as mock_mark:
        svc.start()
    mock_mark.assert_called_once()


def test_end_calls_clear_session_marker():
    svc, _ = _svc()
    svc.start()
    with patch(f"{_MARKER_MOD}.clear_session_marker") as mock_clear:
        svc.end()
    mock_clear.assert_called_once()


# ── end() reason propagation ───────────────────────────────────────────────────

def test_end_default_reason_is_manual():
    rec = _make_recorder()
    svc, _ = _svc(recorder=rec)
    svc.start()
    rec.recorded.clear()
    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        svc.end()
    end_event = rec.recorded[-1]
    assert end_event.get("reason") == "manual"


def test_end_passes_inactivity_reason():
    rec = _make_recorder()
    svc, _ = _svc(recorder=rec)
    svc.start()
    rec.recorded.clear()
    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        svc.end(reason="inactivity")
    end_event = rec.recorded[-1]
    assert end_event.get("reason") == "inactivity"


def test_end_passes_app_close_reason():
    rec = _make_recorder()
    svc, _ = _svc(recorder=rec)
    svc.start()
    rec.recorded.clear()
    with patch(f"{_MARKER_MOD}.clear_session_marker"):
        svc.end(reason="app_close")
    end_event = rec.recorded[-1]
    assert end_event.get("reason") == "app_close"


def test_marker_error_does_not_block_session_start():
    svc, port = _svc()
    with patch(f"{_MARKER_MOD}.mark_session_active", side_effect=OSError("disk full")):
        svc.start()
    assert svc.active is True
    svc._power_thread.join(timeout=5)
    assert ("power_on", "cam1") in port.calls


def test_marker_error_does_not_block_session_end():
    svc, _ = _svc()
    with patch(f"{_MARKER_MOD}.mark_session_active"):
        svc.start()
    with patch(f"{_MARKER_MOD}.clear_session_marker", side_effect=OSError("disk full")):
        svc.end()
    assert svc.active is False


# ── v7: start() no bloquea el hilo llamante (Qt) ─────────────────────────────

def test_start_does_not_block_on_slow_power_on():
    """Cada power_on confirmado puede tardar segundos; start() se llama desde
    callbacks Qt y debe volver de inmediato, con el encendido en segundo plano."""
    import time as _time

    svc, port = _svc()
    release = threading.Event()
    orig = port.power_on

    def slow_power_on(camera_id):
        release.wait(5)
        return orig(camera_id)

    port.power_on = slow_power_on
    t0 = _time.monotonic()
    svc.start()
    elapsed = _time.monotonic() - t0
    release.set()
    svc._power_thread.join(timeout=5)
    assert elapsed < 1.0
    assert svc.active is True
    assert ("power_on", "cam1") in port.calls
    assert ("power_on", "cam2") in port.calls
