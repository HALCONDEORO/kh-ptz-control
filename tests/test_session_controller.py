#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_session_controller.py — Unit tests for SessionController in session_mixin.py.

Tests are headless: methods are exercised as unbound functions with a MagicMock
window stub acting as self._w.  Qt stubs are injected before import.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch



# ── Qt stubs ──────────────────────────────────────────────────────────────────

def _ensure_stubs() -> None:
    for mod in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui"):
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)

    qtc = sys.modules["PyQt5.QtCore"]
    for a in ("Qt", "pyqtSignal", "QTimer"):
        if not hasattr(qtc, a):
            setattr(qtc, a, MagicMock())
    if not hasattr(sys.modules["PyQt5"], "QtCore"):
        sys.modules["PyQt5"].QtCore = qtc  # type: ignore[attr-defined]

    qtw = sys.modules["PyQt5.QtWidgets"]
    for a in ("QMessageBox",):
        if not hasattr(qtw, a):
            setattr(qtw, a, MagicMock)
    qmb = qtw.QMessageBox
    if not hasattr(qmb, "Yes"):
        qmb.Yes = 16384
        qmb.No  = 65536


_ensure_stubs()

from ui.session_mixin import SessionController  # noqa: E402
from core.events import EventType               # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ctrl(session_active: bool = False) -> tuple[SessionController, MagicMock]:
    window = MagicMock()
    window.session_active = session_active
    ctrl = SessionController(window)
    return ctrl, window


# ══════════════════════════════════════════════════════════════════════════════
#  Style constants
# ══════════════════════════════════════════════════════════════════════════════

class TestStyleConstants:
    """SessionController style constants must exist and be distinct."""

    def test_off_style_exists(self):
        assert SessionController._STYLE_BTN_OFF

    def test_starting_style_exists(self):
        assert SessionController._STYLE_BTN_STARTING

    def test_on_style_exists(self):
        assert SessionController._STYLE_BTN_ON

    def test_all_three_styles_are_distinct(self):
        styles = {
            SessionController._STYLE_BTN_OFF,
            SessionController._STYLE_BTN_STARTING,
            SessionController._STYLE_BTN_ON,
        }
        assert len(styles) == 3

    def test_off_style_contains_red_color(self):
        assert "#8b1a1a" in SessionController._STYLE_BTN_OFF

    def test_on_style_contains_green_color(self):
        assert "#1a7a1a" in SessionController._STYLE_BTN_ON


# ══════════════════════════════════════════════════════════════════════════════
#  shutdown()
# ══════════════════════════════════════════════════════════════════════════════

class TestShutdown:
    """shutdown() ends session: emits bus event, powers off cameras, resets UI."""

    def _run(self, reason: str = "manual") -> MagicMock:
        ctrl, window = _make_ctrl(session_active=True)
        SessionController.shutdown(ctrl, reason)
        return window

    def test_emits_session_end_event(self):
        w = self._run()
        w._bus.emit.assert_any_call(EventType.SESSION_END, reason="manual")

    def test_reason_passed_to_bus(self):
        ctrl, w = _make_ctrl(session_active=True)
        SessionController.shutdown(ctrl, "inactivity")
        w._bus.emit.assert_any_call(EventType.SESSION_END, reason="inactivity")

    def test_cam1_powered_off(self):
        w = self._run()
        w.Cam1.set_powered.assert_called_with(False)

    def test_cam2_powered_off(self):
        w = self._run()
        w.Cam2.set_powered.assert_called_with(False)

    def test_session_active_set_false(self):
        ctrl, w = _make_ctrl(session_active=True)
        SessionController.shutdown(ctrl)
        assert w.session_active is False

    def test_btn_session_re_enabled(self):
        w = self._run()
        w.BtnSession.setEnabled.assert_called_with(True)

    def test_btn_session_style_set_to_off(self):
        w = self._run()
        w.BtnSession.setStyleSheet.assert_called_with(SessionController._STYLE_BTN_OFF)

    def test_session_status_set_to_off(self):
        w = self._run()
        w.SessionStatus.setText.assert_called_with("OFF")

    def test_controls_visibility_updated(self):
        w = self._run()
        w._update_controls_visibility.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
#  _session_home()
# ══════════════════════════════════════════════════════════════════════════════

class TestSessionHome:
    """_session_home() fires after startup delay: moves cameras, enables button."""

    def test_emits_seat_selected_for_cam1(self):
        ctrl, w = _make_ctrl(session_active=True)
        w._shutting_down = False
        SessionController._session_home(ctrl)
        # Check SEAT_SELECTED was emitted (first call)
        calls = [c for c in w._bus.emit.call_args_list
                 if c.args and c.args[0] == EventType.SEAT_SELECTED]
        assert calls, "SEAT_SELECTED event not emitted"

    def test_emits_camera_home_for_cam2(self):
        ctrl, w = _make_ctrl(session_active=True)
        w._shutting_down = False
        SessionController._session_home(ctrl)
        calls = [c for c in w._bus.emit.call_args_list
                 if c.args and c.args[0] == EventType.CAMERA_HOME]
        assert calls, "CAMERA_HOME event not emitted"

    def test_sets_button_to_on_style(self):
        ctrl, w = _make_ctrl(session_active=True)
        w._shutting_down = False
        SessionController._session_home(ctrl)
        w.BtnSession.setStyleSheet.assert_called_with(SessionController._STYLE_BTN_ON)

    def test_enables_button(self):
        ctrl, w = _make_ctrl(session_active=True)
        w._shutting_down = False
        SessionController._session_home(ctrl)
        w.BtnSession.setEnabled.assert_called_with(True)

    def test_sets_session_status_on(self):
        ctrl, w = _make_ctrl(session_active=True)
        w._shutting_down = False
        SessionController._session_home(ctrl)
        w.SessionStatus.setText.assert_called_with("ON")

    def test_returns_early_when_not_session_active(self):
        ctrl, w = _make_ctrl(session_active=False)
        w._shutting_down = False
        SessionController._session_home(ctrl)
        w._bus.emit.assert_not_called()

    def test_returns_early_when_shutting_down(self):
        ctrl, w = _make_ctrl(session_active=True)
        w._shutting_down = True
        SessionController._session_home(ctrl)
        w._bus.emit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
#  ToggleSession()
# ══════════════════════════════════════════════════════════════════════════════

class TestToggleSession:
    """ToggleSession() switches between starting and ending a session."""

    def test_start_emits_session_start(self):
        ctrl, w = _make_ctrl(session_active=False)
        with patch("ui.session_mixin.QtCore"), \
             patch("adapters.sim_mode.is_active", return_value=True):
            SessionController.ToggleSession(ctrl)
        w._bus.emit.assert_any_call(EventType.SESSION_START)

    def test_start_sets_session_active_true(self):
        ctrl, w = _make_ctrl(session_active=False)
        with patch("ui.session_mixin.QtCore"), \
             patch("adapters.sim_mode.is_active", return_value=True):
            SessionController.ToggleSession(ctrl)
        assert w.session_active is True

    def test_start_powers_on_cam1(self):
        ctrl, w = _make_ctrl(session_active=False)
        with patch("ui.session_mixin.QtCore"), \
             patch("adapters.sim_mode.is_active", return_value=True):
            SessionController.ToggleSession(ctrl)
        w.Cam1.set_powered.assert_called_with(True)

    def test_start_powers_on_cam2(self):
        ctrl, w = _make_ctrl(session_active=False)
        with patch("ui.session_mixin.QtCore"), \
             patch("adapters.sim_mode.is_active", return_value=True):
            SessionController.ToggleSession(ctrl)
        w.Cam2.set_powered.assert_called_with(True)

    def test_start_disables_button_during_startup(self):
        ctrl, w = _make_ctrl(session_active=False)
        with patch("ui.session_mixin.QtCore"), \
             patch("adapters.sim_mode.is_active", return_value=True):
            SessionController.ToggleSession(ctrl)
        w.BtnSession.setEnabled.assert_called_with(False)

    def test_start_sets_starting_style(self):
        ctrl, w = _make_ctrl(session_active=False)
        with patch("ui.session_mixin.QtCore"), \
             patch("adapters.sim_mode.is_active", return_value=True):
            SessionController.ToggleSession(ctrl)
        w.BtnSession.setStyleSheet.assert_called_with(SessionController._STYLE_BTN_STARTING)

    def test_end_confirms_before_shutdown(self):
        ctrl, w = _make_ctrl(session_active=True)
        with patch("ui.session_mixin.QMessageBox") as mock_mb:
            mock_mb.Yes = 16384
            mock_mb.No  = 65536
            mock_mb.question.return_value = mock_mb.No
            SessionController.ToggleSession(ctrl)
        mock_mb.question.assert_called_once()

    def test_end_no_does_not_shutdown(self):
        ctrl, w = _make_ctrl(session_active=True)
        with patch("ui.session_mixin.QMessageBox") as mock_mb:
            mock_mb.Yes = 16384
            mock_mb.No  = 65536
            mock_mb.question.return_value = mock_mb.No
            SessionController.ToggleSession(ctrl)
        # session must still be active
        assert w.session_active is True

    def test_end_yes_calls_shutdown(self):
        ctrl, w = _make_ctrl(session_active=True)
        ctrl.shutdown = MagicMock()
        with patch("ui.session_mixin.QMessageBox") as mock_mb:
            mock_mb.Yes = 16384
            mock_mb.No  = 65536
            mock_mb.question.return_value = mock_mb.Yes
            SessionController.ToggleSession(ctrl)
        ctrl.shutdown.assert_called_once_with("manual")

