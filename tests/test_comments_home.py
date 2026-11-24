#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tests for the editable Comments → Home position.

Covers:
- CommentsHomeService persistence (missing/invalid/roundtrip).
- Controller branching: CAMERA_HOME recalls the saved slot on Cam2 only when
  one was saved; COMMENTS_HOME_SAVE stores the position in the camera memory
  and persists the slot.
- CommentsHomeButton input handling: tap → tapped, 5 s hold → held,
  interrupted gestures cancel the hold.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from application.comments_home import CommentsHomeService
from domain.preset import PRESET_COMMENTS_HOME


# ── CommentsHomeService persistence ─────────────────────────────────────────

class TestCommentsHomeService:

    def test_missing_file_means_no_saved_position(self, tmp_path):
        svc = CommentsHomeService(tmp_path / "comments_home.json")
        assert svc.saved_slot() is None

    def test_set_slot_persists_across_instances(self, tmp_path):
        path = tmp_path / "comments_home.json"
        svc = CommentsHomeService(path)
        assert svc.set_slot(PRESET_COMMENTS_HOME) is True
        assert svc.saved_slot() == PRESET_COMMENTS_HOME
        # A fresh instance (e.g. after an app restart) sees the saved slot.
        assert CommentsHomeService(path).saved_slot() == PRESET_COMMENTS_HOME

    def test_invalid_content_falls_back_to_none(self, tmp_path):
        path = tmp_path / "comments_home.json"
        path.write_text('{"slot": "not-a-number"}', encoding="utf-8")
        assert CommentsHomeService(path).saved_slot() is None
        path.write_text('[1, 2, 3]', encoding="utf-8")
        assert CommentsHomeService(path).saved_slot() is None

    def test_other_valid_preset_slot_is_rejected(self, tmp_path):
        # Un slot de asiento (12) es válido VISCA pero nunca es Comments Home:
        # un archivo equivocado no puede redirigir el botón Home a un asiento.
        path = tmp_path / "comments_home.json"
        path.write_text('{"slot": 12}', encoding="utf-8")
        assert CommentsHomeService(path).saved_slot() is None

    def test_bool_is_not_a_slot(self, tmp_path):
        path = tmp_path / "comments_home.json"
        svc = CommentsHomeService(path)
        assert svc.set_slot(True) is False  # bool hereda de int pero no es slot
        assert svc.saved_slot() is None
        assert not path.exists()

    def test_slot_outside_preset_map_is_rejected(self, tmp_path):
        path = tmp_path / "comments_home.json"
        svc = CommentsHomeService(path)
        assert svc.set_slot(9999) is False
        assert svc.set_slot(12) is False  # slot de asiento, no el dedicado
        assert svc.saved_slot() is None
        assert not path.exists()


# ── Controller branching ────────────────────────────────────────────────────

from core.controller import Controller
from core.events import AsyncEventBus, EventType
from core.state import SystemState


def _drain(bus: AsyncEventBus) -> None:
    bus._queue.join()


class _CameraPort:
    def __init__(self):
        self.calls = []
        self.save_ok = True

    def recall_preset(self, camera, preset):
        self.calls.append(("recall_preset", camera, preset))
        return True

    def save_preset(self, camera, slot):
        self.calls.append(("save_preset", camera, slot))
        return self.save_ok

    def invalidate_zoom(self, camera):
        self.calls.append(("invalidate_zoom", camera))

    def stop_move(self, camera):
        self.calls.append(("stop", camera))

    def home(self, camera):
        self.calls.append(("home", camera))
        return True


class _PresetSvc:
    def get_preset_for_name(self, name):
        return 1


class _SessionSvc:
    def set_chairman(self, name):
        pass


class _Harness:
    def __init__(self, tmp_path, *, session_active: bool = True):
        self.state = SystemState()
        self.state.session.active = session_active
        self.bus = AsyncEventBus()
        self.camera = _CameraPort()
        self.home_svc = CommentsHomeService(tmp_path / "comments_home.json")
        self.outcome_events = []
        self.bus.subscribe(
            EventType.COMMENTS_HOME_SAVED,
            lambda e: self.outcome_events.append((e.type, dict(e.payload))))
        self.bus.subscribe(
            EventType.COMMENTS_HOME_SAVE_FAILED,
            lambda e: self.outcome_events.append((e.type, dict(e.payload))))
        self.controller = Controller(
            self.state, self.bus, _PresetSvc(), _SessionSvc(),
            camera_port=self.camera, comments_home_svc=self.home_svc,
        )

    def __enter__(self):
        self.bus.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.bus.stop()

    def emit(self, event_type, **payload):
        self.bus.emit(event_type, **payload)
        _drain(self.bus)


class TestControllerCommentsHome:

    def test_home_without_saved_position_uses_mechanical_home(self, tmp_path):
        with _Harness(tmp_path) as h:
            h.emit(EventType.CAMERA_HOME, camera=2)
        assert ("home", "cam2") in h.camera.calls
        assert not any(c[0] == "recall_preset" for c in h.camera.calls)

    def test_home_with_saved_position_recalls_dedicated_slot(self, tmp_path):
        with _Harness(tmp_path) as h:
            h.home_svc.set_slot(PRESET_COMMENTS_HOME)
            h.emit(EventType.CAMERA_HOME, camera=2)
        assert ("recall_preset", "cam2", PRESET_COMMENTS_HOME) in h.camera.calls
        assert ("home", "cam2") not in h.camera.calls

    def test_platform_camera_always_uses_mechanical_home(self, tmp_path):
        with _Harness(tmp_path) as h:
            h.home_svc.set_slot(PRESET_COMMENTS_HOME)
            h.emit(EventType.CAMERA_HOME, camera=1)
        assert ("home", "cam1") in h.camera.calls

    def test_save_stores_position_and_switches_future_home_calls(self, tmp_path):
        with _Harness(tmp_path) as h:
            h.emit(EventType.COMMENTS_HOME_SAVE, camera=2)
            assert ("save_preset", "cam2", PRESET_COMMENTS_HOME) in h.camera.calls
            assert h.home_svc.saved_slot() == PRESET_COMMENTS_HOME
            h.emit(EventType.CAMERA_HOME, camera=2)
        assert ("recall_preset", "cam2", PRESET_COMMENTS_HOME) in h.camera.calls

    def test_save_success_emits_saved_event_for_ui_feedback(self, tmp_path):
        with _Harness(tmp_path) as h:
            h.emit(EventType.COMMENTS_HOME_SAVE, camera=2)
        assert (EventType.COMMENTS_HOME_SAVED,
                {"camera": 2, "slot": PRESET_COMMENTS_HOME}) in h.outcome_events
        assert not any(t == EventType.COMMENTS_HOME_SAVE_FAILED
                       for t, _ in h.outcome_events)

    def test_save_blocked_without_session(self, tmp_path):
        with _Harness(tmp_path, session_active=False) as h:
            h.emit(EventType.COMMENTS_HOME_SAVE, camera=2)
        assert h.camera.calls == []
        assert h.home_svc.saved_slot() is None
        assert h.outcome_events == []

    def test_save_rejected_for_platform_camera(self, tmp_path):
        with _Harness(tmp_path) as h:
            h.emit(EventType.COMMENTS_HOME_SAVE, camera=1)
        assert not any(c[0] == "save_preset" for c in h.camera.calls)
        assert h.home_svc.saved_slot() is None
        assert h.outcome_events == []

    def test_failed_visca_save_does_not_persist_slot(self, tmp_path):
        with _Harness(tmp_path) as h:
            h.camera.save_ok = False
            h.emit(EventType.COMMENTS_HOME_SAVE, camera=2)
        assert h.home_svc.saved_slot() is None
        types = [t for t, _ in h.outcome_events]
        assert EventType.COMMENTS_HOME_SAVE_FAILED in types
        assert EventType.COMMENTS_HOME_SAVED not in types

    def test_failed_disk_persist_emits_failure_not_saved(self, tmp_path, monkeypatch):
        monkeypatch.setattr("application.comments_home.save_json",
                            lambda *a, **k: False)
        with _Harness(tmp_path) as h:
            h.emit(EventType.COMMENTS_HOME_SAVE, camera=2)
        assert h.home_svc.saved_slot() is None
        types = [t for t, _ in h.outcome_events]
        assert EventType.COMMENTS_HOME_SAVE_FAILED in types
        assert EventType.COMMENTS_HOME_SAVED not in types


# ── CommentsHomeButton input handling (real Qt, forked child) ───────────────

pytest.importorskip("PyQt5")

# The whole suite imports Qt stubs and real widgets during collection. Forking
# preserves that process state; exec a clean interpreter so these regressions
# always exercise real Qt without skipping poisoned classes or changing CI.
# Mirrors tests/test_preset_interrupted_gesture.py.


@pytest.fixture(autouse=True)
def _fresh_qt_process(request):
    if os.environ.get("KHPTZ_COMMENTS_HOME_QT_CHILD") == "1":
        return
    env = dict(os.environ, KHPTZ_COMMENTS_HOME_QT_CHILD="1", QT_QPA_PLATFORM="offscreen")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", request.node.nodeid],
        cwd=Path(__file__).resolve().parents[1], env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    request.node._comments_home_child_passed = True


from conftest import ensure_real_qt


@pytest.fixture
def home_button(request):
    if getattr(request.node, "_comments_home_child_passed", False):
        yield None
        return
    ensure_real_qt()
    from PyQt5.QtWidgets import QApplication
    from ui.widgets import CommentsHomeButton
    app = QApplication.instance() or QApplication([])
    tapped, held = [], []
    button = CommentsHomeButton('Comments → Home')
    button._hold_timer.setInterval(20)  # hold threshold shortened for the test
    button.tapped.connect(lambda: tapped.append(1))
    button.held.connect(lambda: held.append(1))
    button.show()
    app.processEvents()
    yield app, button, tapped, held
    button.close()


def _only_in_child(test):
    from functools import wraps

    @wraps(test)
    def wrapped(home_button, *args, **kwargs):
        if home_button is not None:
            return test(home_button, *args, **kwargs)
    return wrapped


@_only_in_child
def test_short_tap_emits_tapped_not_held(home_button):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    app, button, tapped, held = home_button
    QTest.mousePress(button, Qt.LeftButton, pos=QPoint(5, 5))
    QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(5, 5))
    app.processEvents()
    assert tapped == [1]
    assert held == []


@_only_in_child
def test_five_second_hold_emits_held_not_tapped(home_button):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    app, button, tapped, held = home_button
    QTest.mousePress(button, Qt.LeftButton, pos=QPoint(5, 5))
    QTest.qWait(100)  # over the (shortened) hold threshold
    QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(5, 5))
    app.processEvents()
    assert held == [1]
    assert tapped == []


@_only_in_child
def test_hide_during_hold_cancels_set(home_button):
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    app, button, tapped, held = home_button
    QTest.mousePress(button, Qt.LeftButton, pos=QPoint(5, 5))
    button.hide()
    QTest.qWait(100)
    app.processEvents()
    assert held == []
    assert tapped == []


@_only_in_child
def test_drag_out_of_button_cancels_hold(home_button):
    # Regresión: sacar el puntero del botón durante la pulsación cancela el SET.
    # QTest.mouseMove con pos fuera del widget despacha por posición (no llega
    # al botón), así que el move se entrega directo al botón.
    from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
    from PyQt5.QtGui import QMouseEvent
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication
    app, button, tapped, held = home_button
    QTest.mousePress(button, Qt.LeftButton, pos=QPoint(5, 5))
    outside = QPoint(250, 100)
    move = QMouseEvent(QEvent.MouseMove, QPointF(outside), Qt.NoButton,
                       Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(button, move)
    QTest.qWait(100)  # sobre el umbral (acortado) de hold
    app.processEvents()
    assert held == []
    QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(5, 5))
    app.processEvents()
    assert tapped == []  # el gesto quedó cancelado: ni SET ni CALL


@_only_in_child
def test_programmatic_click_after_hold_still_recalls(home_button):
    # Regresión: un click nuevo (programático/accesibilidad) tras un hold no
    # debe quedar bloqueado por el gesto consumido anterior.
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtTest import QTest
    app, button, tapped, held = home_button
    QTest.mousePress(button, Qt.LeftButton, pos=QPoint(5, 5))
    QTest.qWait(100)
    QTest.mouseRelease(button, Qt.LeftButton, pos=QPoint(5, 5))
    app.processEvents()
    assert held == [1]
    assert tapped == []  # el release del hold no dispara CALL
    button.click()
    app.processEvents()
    assert tapped == [1]
