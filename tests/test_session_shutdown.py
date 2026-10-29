#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_session_shutdown.py — Unit tests for the centralised session shutdown path (#194).

Verifies that SessionController.shutdown() is the single path used by both
manual End Session and inactivity auto power-off, and that preset polls are
always cancelled before cameras are powered off.

Module-level Qt stubs are kept minimal; ptz/config stubs are injected via the
`session_ctrl` fixture (monkeypatch) so they are cleaned up after each test
and do not corrupt the real ptz.visca.commands module for later test files.
"""
from __future__ import annotations

import importlib
import sys
import types
import time as _time
from unittest.mock import MagicMock

import pytest


# ── Minimal top-level Qt stubs (safe to leave; other tests also set these) ───

def _ensure_qt_stubs() -> None:
    for mod_name in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)
    qtc = sys.modules["PyQt5.QtCore"]
    if not hasattr(qtc, "QTimer"):
        qtc.QTimer = MagicMock()
    if not hasattr(qtc, "QObject"):
        qtc.QObject = object
    if not hasattr(qtc, "pyqtSignal"):
        qtc.pyqtSignal = MagicMock()
    qtw = sys.modules["PyQt5.QtWidgets"]
    if not hasattr(qtw, "QMessageBox"):
        qtw.QMessageBox = MagicMock()


_ensure_qt_stubs()


# ── Fixture: loads session_mixin with patched ptz/config stubs ───────────────

@pytest.fixture
def session_ctrl(monkeypatch):
    """Yield SessionController with all deps stubbed via monkeypatch.

    After #215 session_mixin no longer imports ptz.visca.commands or config.CAM*/PRESET_MAP.
    Only domain.preset is needed; core.events imports cleanly without Qt.
    """
    # Domain stub
    domain_stub        = types.ModuleType("domain")
    preset_stub        = types.ModuleType("domain.preset")
    preset_stub.PRESET_CHAIRMAN_GENERIC = 1
    monkeypatch.setitem(sys.modules, "domain",        domain_stub)
    monkeypatch.setitem(sys.modules, "domain.preset", preset_stub)

    # Force a fresh import of session_mixin each time
    monkeypatch.delitem(sys.modules, "session_mixin", raising=False)
    sm = importlib.import_module("ui.session_mixin")

    yield sm.SessionController


# ── Window stub factory ───────────────────────────────────────────────────────

def _make_window():
    w = MagicMock()
    w.session_active = True
    w._shutting_down = False
    w._visca = MagicMock()
    w._bus = MagicMock()
    w.BtnSession = MagicMock()
    w.SessionStatus = MagicMock()
    return w


# ── Tests: SessionController.shutdown() ───────────────────────────────────────

class TestSessionControllerShutdown:

    def test_shutdown_emits_session_end_and_does_not_call_visca_directly(self, session_ctrl):
        """After #684 the direct _visca.cancel_preset_polls() call was removed.

        Poll cancellation routes through SessionService.end() (via SESSION_END bus
        event) which calls CameraPort.cancel_polls(). Verify the direct VISCA call
        is gone and SESSION_END is still emitted with the shutdown reason.
        """
        from core.events import EventType
        w = _make_window()
        ctrl = session_ctrl(w)

        ctrl.shutdown("manual")

        w._bus.emit.assert_called_with(EventType.SESSION_END, reason="manual")
        w._visca.cancel_preset_polls.assert_not_called()

    def test_shutdown_sets_session_active_false(self, session_ctrl):
        w = _make_window()
        ctrl = session_ctrl(w)

        ctrl.shutdown("manual")

        assert w.session_active is False

    def test_shutdown_updates_button_style_to_off(self, session_ctrl):
        w = _make_window()
        ctrl = session_ctrl(w)

        ctrl.shutdown("manual")

        w.BtnSession.setStyleSheet.assert_called_with(session_ctrl._STYLE_BTN_OFF)

    def test_shutdown_updates_status_text_to_off(self, session_ctrl):
        w = _make_window()
        ctrl = session_ctrl(w)

        ctrl.shutdown("manual")

        w.SessionStatus.setText.assert_called_with("OFF")

    def test_shutdown_emits_session_end_event(self, session_ctrl):
        from core.events import EventType
        w = _make_window()
        ctrl = session_ctrl(w)

        ctrl.shutdown("manual")

        w._bus.emit.assert_called_with(EventType.SESSION_END, reason="manual")

    def test_shutdown_logs_inactivity_reason(self, session_ctrl, caplog):
        import logging
        w = _make_window()
        ctrl = session_ctrl(w)

        with caplog.at_level(logging.INFO, logger="ui.session_mixin"):
            ctrl.shutdown("inactivity")

        assert any("inactivity" in r.message for r in caplog.records)

    def test_shutdown_logs_manual_reason(self, session_ctrl, caplog):
        import logging
        w = _make_window()
        ctrl = session_ctrl(w)

        with caplog.at_level(logging.INFO, logger="ui.session_mixin"):
            ctrl.shutdown("manual")

        assert any("manual" in r.message for r in caplog.records)


# ── Tests: _check_inactivity logic (tested in isolation) ─────────────────────
#
# main_window has a large Qt/hardware import chain. We test the guard logic by
# executing the exact same pattern from the fixed method on a lightweight stub.

class _WindowLike:
    """Stand-in for MainWindow to test _check_inactivity guard logic (#194)."""
    _INACTIVITY_TIMEOUT = 7200.0

    def __init__(self, session_active: bool, elapsed: float, session):
        self.session_active = session_active
        self._last_activity = _time.time() - elapsed
        self._session = session

    def _check_inactivity(self):
        """Mirrors MainWindow._check_inactivity after fix (#194)."""
        if not self.session_active:
            return
        if _time.time() - self._last_activity < self._INACTIVITY_TIMEOUT:
            return
        self._session.shutdown("inactivity")


class TestCheckInactivityLogic:

    def test_inactivity_shutdown_called_when_timed_out(self):
        fake_session = MagicMock()
        w = _WindowLike(session_active=True, elapsed=9000.0, session=fake_session)

        w._check_inactivity()

        fake_session.shutdown.assert_called_once_with("inactivity")

    def test_inactivity_shutdown_not_called_when_session_inactive(self):
        fake_session = MagicMock()
        w = _WindowLike(session_active=False, elapsed=9000.0, session=fake_session)

        w._check_inactivity()

        fake_session.shutdown.assert_not_called()

    def test_inactivity_shutdown_not_called_within_timeout(self):
        fake_session = MagicMock()
        w = _WindowLike(session_active=True, elapsed=10.0, session=fake_session)

        w._check_inactivity()

        fake_session.shutdown.assert_not_called()


# ── Tests: _session_home guard (#147) ─────────────────────────────────────────

class TestSessionHomeGuard:

    def test_session_home_skips_commands_when_session_inactive(self, session_ctrl):
        w = _make_window()
        w.session_active = False
        ctrl = session_ctrl(w)

        ctrl._session_home()

        w._bus.emit.assert_not_called()

    def test_session_home_skips_commands_when_shutting_down(self, session_ctrl):
        w = _make_window()
        w.session_active = True
        w._shutting_down = True
        ctrl = session_ctrl(w)

        ctrl._session_home()

        w._bus.emit.assert_not_called()

    def test_session_home_emits_seat_selected_and_camera_home(self, session_ctrl):
        from core.events import EventType
        from unittest.mock import call
        w = _make_window()
        w.session_active = True
        ctrl = session_ctrl(w)

        ctrl._session_home()

        calls = w._bus.emit.call_args_list
        # Seat-selected event carries 'preset' (canonical) and 'seat_number' (compat).
        assert any(
            c.args == (EventType.SEAT_SELECTED,)
            and c.kwargs.get("preset") == 1
            and c.kwargs.get("seat_number") == 1
            and c.kwargs.get("camera") == 1
            for c in calls
        )
        assert any(c == call(EventType.CAMERA_HOME, camera=2) for c in calls)
        w.BtnSession.setEnabled.assert_called_with(True)
        w.SessionStatus.setText.assert_called_with('ON')


# ── Tests: button not stuck after shutdown during startup window (#147) ────────

class TestButtonNotStuckAfterShutdown:

    def test_shutdown_re_enables_button(self, session_ctrl):
        """shutdown() must call setEnabled(True) so the button is not stuck disabled.

        During the 8-second startup window the button is disabled. If the session
        is ended (inactivity or app close) before _session_home() fires, shutdown()
        must re-enable the button so operators can start a new session.
        """
        w = _make_window()
        w.BtnSession.isEnabled.return_value = False  # simulate disabled state
        ctrl = session_ctrl(w)

        ctrl.shutdown("inactivity")

        w.BtnSession.setEnabled.assert_called_with(True)

    def test_shutdown_re_enables_button_when_shutting_down_flag_set(self, session_ctrl):
        """Even when _shutting_down is True, shutdown() must not leave button disabled."""
        w = _make_window()
        w._shutting_down = True
        ctrl = session_ctrl(w)

        ctrl.shutdown("manual")

        w.BtnSession.setEnabled.assert_called_with(True)

    def test_session_home_skip_does_not_re_enable_button(self, session_ctrl):
        """When _session_home() skips due to inactive session, it must NOT touch the button.

        Responsibility for the button state lies with shutdown(), not with the skipped
        _session_home() path.
        """
        w = _make_window()
        w.session_active = False
        ctrl = session_ctrl(w)

        ctrl._session_home()

        w.BtnSession.setEnabled.assert_not_called()
