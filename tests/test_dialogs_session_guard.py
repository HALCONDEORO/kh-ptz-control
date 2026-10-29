#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_dialogs_session_guard.py — Tests for session-active guard in _change_config (#167).

Verifies that PTZ IP and VISCA ID change dialogs are blocked when a session
is active and allowed when the session is off, without requiring real Qt dialogs.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch



# ── Qt stubs ─────────────────────────────────────────────────────────────────

def _ensure_qt_stubs() -> None:
    for mod in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui"):
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)

    qtc = sys.modules["PyQt5.QtCore"]
    for name in ("Qt",):
        if not hasattr(qtc, name):
            setattr(qtc, name, MagicMock())

    qtw = sys.modules["PyQt5.QtWidgets"]
    for name in (
        "QMessageBox", "QInputDialog",
        "QVBoxLayout", "QFormLayout", "QHBoxLayout",
        "QLabel", "QLineEdit", "QPushButton",
    ):
        if not hasattr(qtw, name):
            setattr(qtw, name, MagicMock())

    # QDialog must be a plain Python class so ScheduleDialog and other
    # widgets that inherit from it remain real Python classes in tests.
    if not hasattr(qtw, "QDialog"):
        class _FakeQDialog:
            Accepted = 1
            def exec_(self):
                return self.Accepted
        qtw.QDialog = _FakeQDialog

    qtw.QMessageBox.Ok     = 1024
    qtw.QMessageBox.Cancel = 4194304
    qtw.QMessageBox.warning = MagicMock(return_value=qtw.QMessageBox.Ok)

    if not hasattr(qtw, "QDialog"):
        qtw.QDialog = MagicMock()
    qtw.QDialog.Accepted = 1


_ensure_qt_stubs()

# Config stubs
if "config" not in sys.modules:
    cfg = types.ModuleType("config")
    cfg.CAM1 = MagicMock(ip="172.16.1.11", cam_id="81")
    cfg.CAM2 = MagicMock(ip="172.16.1.12", cam_id="82")
    cfg.Contact = "Support: example@example.com"
    cfg.is_valid_ip    = lambda s: len(s) > 0
    cfg.is_valid_cam_id = lambda s: len(s) > 0
    sys.modules["config"] = cfg

if "secret_manager" not in sys.modules:
    sm = types.ModuleType("secret_manager")
    sm.decrypt_password = MagicMock(return_value="test")
    sm.encrypt_password = MagicMock()
    sys.modules["secret_manager"] = sm

sys.modules.pop("dialogs_mixin", None)
import ui.dialogs_mixin as dm  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_window(session_active: bool = False):
    w = MagicMock()
    w.session_active = session_active
    return w


# ── Tests: session guard blocks changes when session is active ────────────────

class TestChangeConfigSessionGuard:

    def test_blocks_ip_change_when_session_active(self):
        w = _make_window(session_active=True)
        ctrl = dm.DialogsController(w)
        from PyQt5.QtWidgets import QMessageBox

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok) as mock_warn:
            ctrl._change_config(1, 'ip')

        # Should show "Session is active" warning and not proceed to confirmation
        calls = mock_warn.call_args_list
        assert any("Session" in str(c) for c in calls), \
            "Expected session-active warning to be shown"

    def test_blocks_id_change_when_session_active(self):
        w = _make_window(session_active=True)
        ctrl = dm.DialogsController(w)
        from PyQt5.QtWidgets import QMessageBox

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok) as mock_warn:
            ctrl._change_config(1, 'id')

        calls = mock_warn.call_args_list
        assert any("Session" in str(c) for c in calls)

    def test_does_not_write_config_file_when_session_active(self):
        """Guard must return before writing to disk — open() must not be called."""
        w = _make_window(session_active=True)
        ctrl = dm.DialogsController(w)
        from PyQt5.QtWidgets import QMessageBox

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok):
            with patch("builtins.open") as mock_open:
                ctrl._change_config(1, 'ip')

        mock_open.assert_not_called()

    def test_allows_ip_change_when_session_inactive(self):
        w = _make_window(session_active=False)
        ctrl = dm.DialogsController(w)
        from PyQt5.QtWidgets import QMessageBox

        # Cancel at the confirmation step so we don't go further
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.Cancel):
            ctrl._change_config(1, 'ip')  # must not raise

    def test_allows_id_change_when_session_inactive(self):
        w = _make_window(session_active=False)
        ctrl = dm.DialogsController(w)
        from PyQt5.QtWidgets import QMessageBox

        with patch.object(QMessageBox, "warning", return_value=QMessageBox.Cancel):
            ctrl._change_config(2, 'id')  # must not raise

    def test_session_guard_checked_before_confirmation(self):
        """Guard fires before the 'Do you want to change…' dialog."""
        w = _make_window(session_active=True)
        ctrl = dm.DialogsController(w)
        from PyQt5.QtWidgets import QMessageBox

        confirmation_shown = []

        def _track_warning(parent, title, text, *args, **kwargs):
            confirmation_shown.append(text)
            return QMessageBox.Ok

        with patch.object(QMessageBox, "warning", side_effect=_track_warning):
            ctrl._change_config(1, 'ip')

        # Only the session-guard message should appear, not the "Do you want to change" message
        assert len(confirmation_shown) == 1
        assert "Session is active" in confirmation_shown[0]

    def test_ptz1address_wrapper_blocked_during_session(self):
        w = _make_window(session_active=True)
        ctrl = dm.DialogsController(w)
        from PyQt5.QtWidgets import QMessageBox
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok):
            ctrl.PTZ1Address()  # must not raise or proceed

    def test_ptz1idchange_wrapper_blocked_during_session(self):
        w = _make_window(session_active=True)
        ctrl = dm.DialogsController(w)
        from PyQt5.QtWidgets import QMessageBox
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok):
            ctrl.PTZ1IDchange()  # must not raise or proceed

