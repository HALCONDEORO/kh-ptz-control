#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tests del orquestador central core.controller.
"""

from core.controller import Controller
from core.events import AsyncEventBus, EventType
from core.state import SystemState


def _drain(bus: AsyncEventBus) -> None:
    bus._queue.join()


class _CameraPort:
    """Minimal CameraPort-compatible fake for controller tests.

    Returns plain booleans so _result_ok() handles both CommandResult and bool.
    """

    def __init__(self):
        self.calls = []
        self.recall_ok = True
        self.save_ok = True

    def recall_preset(self, camera, preset):
        self.calls.append(("recall_preset", camera, preset))
        return self.recall_ok

    def save_preset(self, camera, slot):
        self.calls.append(("save_preset", camera, slot))
        return self.save_ok

    def invalidate_zoom(self, camera):
        self.calls.append(("invalidate_zoom", camera))

    def move(self, camera, pan, tilt):
        self.calls.append(("move", camera, pan, tilt))

    def stop_move(self, camera):
        self.calls.append(("stop", camera))

    def zoom(self, camera, speed):
        self.calls.append(("zoom", camera, speed))

    def home(self, camera):
        self.calls.append(("home", camera))


class _PresetSvc:
    def __init__(self):
        self.map = {"PersonA": 10}
        self.assign_result = (12, True)
        self.persist_ok = True
        self.calls = []

    def get_preset_for_name(self, name):
        self.calls.append(("get_preset_for_name", name))
        return self.map.get(name, 1)

    def assign_slot(self, name):
        self.calls.append(("assign_slot", name))
        slot, is_new = self.assign_result
        if slot is not None and is_new:
            self.map[name] = slot
        return self.assign_result

    def persist(self):
        self.calls.append(("persist",))
        return self.persist_ok

    def release_slot(self, name):
        self.calls.append(("release_slot", name))
        self.map.pop(name, None)


class _SessionSvc:
    def __init__(self, state=None):
        self.calls = []
        self._state = state

    def set_chairman(self, name):
        self.calls.append(("set_chairman", name))

    def start(self):
        self.calls.append(("start",))
        if self._state is not None:
            self._state.session.active = True

    def end(self, reason: str = "manual"):
        self.calls.append(("end",))
        if self._state is not None:
            self._state.session.active = False


class _Harness:
    def __init__(self, *, session_active: bool = True):
        self.state = SystemState()
        self.state.session.active = session_active
        self.bus = AsyncEventBus()
        self.camera = _CameraPort()
        self.presets = _PresetSvc()
        self.session = _SessionSvc(state=self.state)
        self.saved_events = []
        self.bus.subscribe(EventType.PRESET_SAVED, lambda event: self.saved_events.append(event.payload))
        self.controller = Controller(
            self.state, self.bus, self.presets, self.session,
            camera_port=self.camera,
        )

    def __enter__(self):
        self.bus.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.bus.stop()

    def emit(self, event_type, **payload):
        self.bus.emit(event_type, **payload)
        _drain(self.bus)


class TestControllerSeatSelection:

    def test_named_seat_uses_personal_preset_and_invalidates_zoom_on_success(self):
        with _Harness() as h:
            h.emit(EventType.SEAT_SELECTED, name="PersonA", camera=2, seat_number=7)

        assert h.camera.calls == [("recall_preset", "cam2", 10), ("invalidate_zoom", 2)]
        assert h.state.cam2.active_preset == 10

    def test_unnamed_seat_uses_preset_field_as_visca_slot(self):
        # New canonical form: explicit 'preset' field.
        with _Harness() as h:
            h.emit(EventType.SEAT_SELECTED, name="", camera=1, preset=7)

        assert h.camera.calls == [("recall_preset", "cam1", 7), ("invalidate_zoom", 1)]
        assert h.state.cam1.active_preset == 7

    def test_unnamed_seat_falls_back_to_seat_number_when_preset_absent(self):
        # Backward-compat: callers that only send 'seat_number' still work.
        with _Harness() as h:
            h.emit(EventType.SEAT_SELECTED, name="", camera=1, seat_number=7)

        assert h.camera.calls == [("recall_preset", "cam1", 7), ("invalidate_zoom", 1)]
        assert h.state.cam1.active_preset == 7

    def test_seat_selection_defaults_to_active_camera_when_payload_omits_camera(self):
        with _Harness() as h:
            h.state.active_camera = 2
            h.emit(EventType.SEAT_SELECTED, name="", seat_number=8)

        assert h.camera.calls == [("recall_preset", "cam2", 8), ("invalidate_zoom", 2)]
        assert h.state.cam2.active_preset == 8

    def test_invalid_seat_zero_does_not_call_camera(self):
        with _Harness() as h:
            h.emit(EventType.SEAT_SELECTED, name="", camera=1, seat_number=0)

        assert h.camera.calls == []
        assert h.state.cam1.active_preset is None

    def test_failed_recall_does_not_update_active_preset_or_invalidate_zoom(self):
        with _Harness() as h:
            h.camera.recall_ok = False
            h.emit(EventType.SEAT_SELECTED, name="PersonA", camera=1, seat_number=7)

        assert h.camera.calls == [("recall_preset", "cam1", 10)]
        assert h.state.cam1.active_preset is None


class TestControllerCameraCommands:

    def test_camera_move_delegates_and_updates_state(self):
        with _Harness() as h:
            h.emit(EventType.CAMERA_MOVE, camera=2, pan_speed=-3, tilt_speed=4)

        assert h.camera.calls == [("move", "cam2", -3, 4)]
        assert h.state.cam2.pan_speed == -3
        assert h.state.cam2.tilt_speed == 4

    def test_camera_stop_delegates_and_resets_motion_state(self):
        with _Harness() as h:
            h.state.cam1.pan_speed = 5
            h.state.cam1.tilt_speed = -2
            h.emit(EventType.CAMERA_STOP, camera=1)

        assert h.camera.calls == [("stop", "cam1")]
        assert h.state.cam1.pan_speed == 0
        assert h.state.cam1.tilt_speed == 0

    def test_camera_zoom_delegates_without_state_mutation(self):
        with _Harness() as h:
            h.emit(EventType.CAMERA_ZOOM, camera=1, speed=-4)

        assert h.camera.calls == [("zoom", "cam1", -4)]


class TestControllerChairmanAndPresets:

    def test_chairman_assigned_updates_session_and_recalls_cam1(self):
        with _Harness() as h:
            h.emit(EventType.CHAIRMAN_ASSIGNED, name="PersonA")

        assert h.session.calls == [("set_chairman", "PersonA")]
        assert h.state.session.chairman_name == "PersonA"
        assert h.camera.calls == [("recall_preset", "cam1", 10), ("invalidate_zoom", 1)]
        assert h.state.cam1.active_preset == 10

    def test_chairman_recall_failure_keeps_assignment_but_does_not_update_camera_state(self):
        with _Harness() as h:
            h.camera.recall_ok = False
            h.emit(EventType.CHAIRMAN_ASSIGNED, name="PersonA")

        assert h.session.calls == [("set_chairman", "PersonA")]
        assert h.state.session.chairman_name == "PersonA"
        assert h.camera.calls == [("recall_preset", "cam1", 10)]
        assert h.state.cam1.active_preset is None

    def test_preset_save_new_slot_persists_and_emits_saved_event(self):
        with _Harness() as h:
            h.presets.assign_result = (12, True)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=2, name="PersonB")

        assert h.camera.calls == [("save_preset", "cam2", 12)]
        assert h.presets.calls == [("assign_slot", "PersonB"), ("persist",)]
        assert h.saved_events == [{"camera": 2, "name": "PersonB", "slot": 12}]

    def test_saved_new_preset_can_be_recalled_by_later_seat_selection(self):
        with _Harness() as h:
            h.presets.assign_result = (12, True)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=2, name="PersonB")
            h.emit(EventType.SEAT_SELECTED, name="PersonB", camera=2, seat_number=4)

        assert h.camera.calls == [
            ("save_preset", "cam2", 12),
            ("recall_preset", "cam2", 12),
            ("invalidate_zoom", 2),
        ]
        assert h.presets.calls == [
            ("assign_slot", "PersonB"),
            ("persist",),
            ("get_preset_for_name", "PersonB"),
        ]
        assert h.state.cam2.active_preset == 12
        assert h.saved_events == [{"camera": 2, "name": "PersonB", "slot": 12}]

    def test_preset_save_existing_slot_does_not_persist_again(self):
        with _Harness() as h:
            h.presets.assign_result = (10, False)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="PersonA")

        assert h.camera.calls == [("save_preset", "cam1", 10)]
        assert h.presets.calls == [("assign_slot", "PersonA")]
        assert h.saved_events == [{"camera": 1, "name": "PersonA", "slot": 10}]

    def test_preset_save_failure_rolls_back_new_slot_and_emits_nothing(self):
        with _Harness() as h:
            h.camera.save_ok = False
            h.presets.assign_result = (12, True)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="PersonB")

        assert h.camera.calls == [("save_preset", "cam1", 12)]
        assert h.presets.calls == [("assign_slot", "PersonB"), ("release_slot", "PersonB")]
        assert h.saved_events == []

    def test_preset_save_failure_for_existing_slot_does_not_release_slot(self):
        with _Harness() as h:
            h.camera.save_ok = False
            h.presets.assign_result = (10, False)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="PersonA")

        assert h.camera.calls == [("save_preset", "cam1", 10)]
        assert h.presets.calls == [("assign_slot", "PersonA")]
        assert h.saved_events == []

    def test_preset_save_range_exhausted_does_not_call_camera(self):
        with _Harness() as h:
            h.presets.assign_result = (None, False)
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="PersonB")

        assert h.camera.calls == []
        assert h.saved_events == []

    def test_preset_save_persist_failure_suppresses_saved_event(self):
        """PRESET_SAVED must not be emitted when persist() returns False (#212)."""
        with _Harness() as h:
            h.presets.assign_result = (12, True)
            h.presets.persist_ok = False
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="PersonB")

        assert h.camera.calls == [("save_preset", "cam1", 12)]
        assert ("persist",) in h.presets.calls
        assert h.saved_events == []

    def test_preset_save_persist_failure_does_not_release_slot(self):
        """In-memory slot is kept even when persist fails — camera already holds it (#212)."""
        with _Harness() as h:
            h.presets.assign_result = (12, True)
            h.presets.persist_ok = False
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="PersonB")

        assert ("release_slot", "PersonB") not in h.presets.calls

    def test_preset_save_existing_slot_persist_not_called_and_event_emitted(self):
        """Existing slot: persist() is never called; PRESET_SAVED is still emitted (#212)."""
        with _Harness() as h:
            h.presets.assign_result = (10, False)
            h.presets.persist_ok = False  # irrelevant — persist is not called
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="PersonA")

        assert ("persist",) not in h.presets.calls
        assert h.saved_events == [{"camera": 1, "name": "PersonA", "slot": 10}]


class TestControllerSession:

    def test_session_start_updates_state_and_starts_service(self):
        with _Harness(session_active=False) as h:
            h.emit(EventType.SESSION_START)

        assert h.state.session.active is True
        assert h.session.calls == [("start",)]

    def test_session_end_updates_state_and_ends_service(self):
        with _Harness(session_active=True) as h:
            h.emit(EventType.SESSION_END)

        assert h.state.session.active is False
        assert h.session.calls == [("end",)]


class TestControllerSessionGuard:
    """Camera commands are silently dropped when no session is active."""

    def test_seat_selected_blocked_without_session(self):
        with _Harness(session_active=False) as h:
            h.emit(EventType.SEAT_SELECTED, name="PersonA", camera=1, seat_number=7)
        assert h.camera.calls == []
        assert h.state.cam1.active_preset is None

    def test_camera_move_blocked_without_session(self):
        with _Harness(session_active=False) as h:
            h.emit(EventType.CAMERA_MOVE, camera=1, pan_speed=5, tilt_speed=0)
        assert h.camera.calls == []

    def test_camera_stop_passes_through_without_session(self):
        """STOP must never be blocked — it is a safety command."""
        with _Harness(session_active=False) as h:
            h.emit(EventType.CAMERA_STOP, camera=1)
        assert ("stop", "cam1") in h.camera.calls

    def test_camera_zoom_blocked_without_session(self):
        with _Harness(session_active=False) as h:
            h.emit(EventType.CAMERA_ZOOM, camera=1, speed=3)
        assert h.camera.calls == []

    def test_camera_home_blocked_without_session(self):
        with _Harness(session_active=False) as h:
            h.emit(EventType.CAMERA_HOME, camera=1)
        assert h.camera.calls == []

    def test_chairman_assigned_blocked_without_session(self):
        with _Harness(session_active=False) as h:
            h.emit(EventType.CHAIRMAN_ASSIGNED, name="PersonA")
        assert h.camera.calls == []
        assert h.session.calls == []

    def test_preset_save_requested_blocked_without_session(self):
        with _Harness(session_active=False) as h:
            h.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name="PersonA")
        assert h.camera.calls == []
        assert h.saved_events == []

    def test_preset_save_slot_blocked_without_session(self):
        with _Harness(session_active=False) as h:
            h.emit(EventType.PRESET_SAVE_SLOT, camera=1, slot=5)
        assert h.camera.calls == []

    def test_commands_execute_once_session_becomes_active(self):
        """Guard lifts as soon as session.active is set True."""
        with _Harness(session_active=False) as h:
            h.emit(EventType.CAMERA_MOVE, camera=1, pan_speed=5, tilt_speed=0)
            assert h.camera.calls == []
            h.state.session.active = True
            h.emit(EventType.CAMERA_MOVE, camera=1, pan_speed=5, tilt_speed=0)
        assert ("move", "cam1", 5, 0) in h.camera.calls

    def test_session_start_is_never_blocked(self):
        with _Harness(session_active=False) as h:
            h.emit(EventType.SESSION_START)
        assert h.state.session.active is True
        assert h.session.calls == [("start",)]

    def test_session_end_is_never_blocked(self):
        with _Harness(session_active=True) as h:
            h.emit(EventType.SESSION_END)
        assert h.state.session.active is False
        assert h.session.calls == [("end",)]


# ── Bug regression tests ─────────────────────────────────────────────────────

class TestControllerBugRegressions:
    """Regression tests for bugs found in audit rounds."""

    def test_preset_slot_truthy_falsy_fix(self):
        """preset=0 used to pass 'if not preset:' guard incorrectly — now blocked."""
        with _Harness() as h:
            # slot=0 is not a valid VISCA preset; should be blocked
            h.emit(EventType.SEAT_SELECTED, name="", camera=1, seat_number=0, preset=0)
        assert h.camera.calls == []

    def test_preset_slot_1_is_valid_and_not_blocked(self):
        """slot=1 must pass the guard (was not affected, regression guard)."""
        with _Harness() as h:
            h.emit(EventType.SEAT_SELECTED, name="", camera=1, seat_number=1, preset=1)
        assert any("recall_preset" in str(c) for c in h.camera.calls)

    def test_camera_stop_allowed_without_session(self):
        """CAMERA_STOP is a safety command — must never require an active session."""
        with _Harness(session_active=False) as h:
            h.state.cam1.pan_speed = 10
            h.emit(EventType.CAMERA_STOP, camera=1)
        assert ("stop", "cam1") in h.camera.calls
        assert h.state.cam1.pan_speed == 0


class TestSystemStateValidation:
    """SystemState.camera() raises ValueError for invalid indices."""

    def test_camera_1_returns_cam1(self):
        from core.state import SystemState
        s = SystemState()
        assert s.camera(1) is s.cam1

    def test_camera_2_returns_cam2(self):
        from core.state import SystemState
        s = SystemState()
        assert s.camera(2) is s.cam2

    def test_camera_invalid_index_raises(self):
        import pytest
        from core.state import SystemState
        s = SystemState()
        with pytest.raises(ValueError, match="invalid camera index"):
            s.camera(0)

    def test_camera_index_3_raises(self):
        import pytest
        from core.state import SystemState
        s = SystemState()
        with pytest.raises(ValueError):
            s.camera(3)
