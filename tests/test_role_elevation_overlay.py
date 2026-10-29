#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_role_elevation_overlay.py — Unit tests for RoleElevationOverlay._try_login
and ._cancel.

Methods are exercised as unbound functions with a MagicMock stub.
Qt stubs are injected before import; no QApplication is needed.
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
    for a in ("Qt",):
        if not hasattr(qtc, a):
            setattr(qtc, a, MagicMock())

    qtw = sys.modules["PyQt5.QtWidgets"]
    for a in ("QWidget", "QFrame", "QGraphicsDropShadowEffect", "QHBoxLayout",
              "QLabel", "QLineEdit", "QPushButton", "QVBoxLayout"):
        if not hasattr(qtw, a):
            setattr(qtw, a, MagicMock)

    qtg = sys.modules["PyQt5.QtGui"]
    for a in ("QColor", "QFont", "QPainter"):
        if not hasattr(qtg, a):
            setattr(qtg, a, MagicMock)
    if not hasattr(qtg, "QFont"):
        class _FF:
            Bold = 75
            Normal = 50
            def __init__(self, *a, **k): pass
        qtg.QFont = _FF  # type: ignore[attr-defined]
    else:
        if not hasattr(qtg.QFont, "Bold"):
            qtg.QFont.Bold = 75


_ensure_stubs()

import ui.role_elevation_overlay as _reo  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _stub(pwd_text: str = "", attempts: int = 0) -> MagicMock:
    stub = MagicMock()
    stub._pwd_input.text.return_value = pwd_text
    stub._attempts = attempts
    stub._on_success = MagicMock()
    stub._on_cancel  = MagicMock()
    return stub


# ══════════════════════════════════════════════════════════════════════════════
#  _try_login()
# ══════════════════════════════════════════════════════════════════════════════

class TestTryLogin:
    """_try_login() consults application.authentication.verify_admin and calls
    on_success or shows an error. Elevation requires the ADMIN password (with the
    documented migration fallback inside verify_admin)."""

    def test_empty_password_shows_error(self):
        stub = _stub(pwd_text="")
        _reo.RoleElevationOverlay._try_login(stub)
        stub._lbl_err.setText.assert_called_once()
        msg = stub._lbl_err.setText.call_args[0][0]
        assert "password" in msg.lower() or "enter" in msg.lower()

    def test_empty_password_does_not_call_on_success(self):
        stub = _stub(pwd_text="")
        _reo.RoleElevationOverlay._try_login(stub)
        stub._on_success.assert_not_called()

    def test_wrong_password_shows_error(self):
        stub = _stub(pwd_text="wrong")
        with patch("application.authentication.verify_admin", return_value=False):
            _reo.RoleElevationOverlay._try_login(stub)
        stub._lbl_err.setText.assert_called_once()
        stub._on_success.assert_not_called()

    def test_wrong_password_increments_attempts(self):
        stub = _stub(pwd_text="wrong", attempts=0)
        with patch("application.authentication.verify_admin", return_value=False):
            _reo.RoleElevationOverlay._try_login(stub)
        assert stub._attempts == 1

    def test_wrong_password_clears_input(self):
        stub = _stub(pwd_text="wrong")
        with patch("application.authentication.verify_admin", return_value=False):
            _reo.RoleElevationOverlay._try_login(stub)
        stub._pwd_input.clear.assert_called_once()

    def test_correct_password_calls_on_success(self):
        stub = _stub(pwd_text="secret")
        with patch("application.authentication.verify_admin", return_value=True):
            _reo.RoleElevationOverlay._try_login(stub)
        stub._on_success.assert_called_once()

    def test_correct_password_hides_overlay(self):
        stub = _stub(pwd_text="secret")
        with patch("application.authentication.verify_admin", return_value=True):
            _reo.RoleElevationOverlay._try_login(stub)
        stub.hide.assert_called_once()

    def test_correct_password_does_not_show_error(self):
        stub = _stub(pwd_text="secret")
        with patch("application.authentication.verify_admin", return_value=True):
            _reo.RoleElevationOverlay._try_login(stub)
        stub._lbl_err.setText.assert_not_called()

    def test_rejected_password_does_not_elevate(self):
        # verify_admin returns False when no password matches (incl. nothing
        # configured) — the overlay treats it as a wrong password and stays put.
        stub = _stub(pwd_text="anything")
        with patch("application.authentication.verify_admin", return_value=False):
            _reo.RoleElevationOverlay._try_login(stub)
        stub._lbl_err.setText.assert_called_once()
        stub._on_success.assert_not_called()

    def test_attempts_counter_accumulates(self):
        stub = _stub(pwd_text="wrong", attempts=2)
        with patch("application.authentication.verify_admin", return_value=False):
            _reo.RoleElevationOverlay._try_login(stub)
        assert stub._attempts == 3

    def test_error_message_includes_attempt_count(self):
        stub = _stub(pwd_text="wrong", attempts=0)
        with patch("application.authentication.verify_admin", return_value=False):
            _reo.RoleElevationOverlay._try_login(stub)
        msg = stub._lbl_err.setText.call_args[0][0]
        assert "1" in msg  # attempt number shown


# ══════════════════════════════════════════════════════════════════════════════
#  _cancel()
# ══════════════════════════════════════════════════════════════════════════════

class TestCancel:
    """_cancel() hides the overlay and fires on_cancel."""

    def test_calls_on_cancel(self):
        stub = _stub()
        _reo.RoleElevationOverlay._cancel(stub)
        stub._on_cancel.assert_called_once()

    def test_hides_overlay(self):
        stub = _stub()
        _reo.RoleElevationOverlay._cancel(stub)
        stub.hide.assert_called_once()

    def test_does_not_call_on_success(self):
        stub = _stub()
        _reo.RoleElevationOverlay._cancel(stub)
        stub._on_success.assert_not_called()

