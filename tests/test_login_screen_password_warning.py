#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_login_screen_password_warning.py — Tests for issue #88.

Verifies that LoginScreen shows a clear visible warning when no password is
configured, disables the login form, and does NOT reveal the password or fall
back to a default.

All tests call LoginScreen methods as unbound functions with a MagicMock stub as
self, avoiding a real QApplication.  The Qt modules are stubbed so the import
succeeds headlessly.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch


# ── Qt stubs (must come before importing ui.login_screen) ─────────────────────

def _ensure_qt_stubs() -> None:
    """Inject minimal Qt symbol stubs so login_screen can be imported headlessly."""
    for mod_name in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    qtc = sys.modules["PyQt5.QtCore"]
    for attr in ("Qt", "pyqtSignal", "QTimer"):
        if not hasattr(qtc, attr):
            setattr(qtc, attr, MagicMock())

    qtw = sys.modules["PyQt5.QtWidgets"]
    for attr in (
        "QWidget", "QVBoxLayout", "QHBoxLayout", "QLabel", "QLineEdit",
        "QPushButton", "QMessageBox", "QFrame", "QGraphicsDropShadowEffect",
    ):
        if not hasattr(qtw, attr):
            setattr(qtw, attr, MagicMock)

    qtg = sys.modules["PyQt5.QtGui"]
    for attr in ("QFont", "QColor", "QPalette"):
        if not hasattr(qtg, attr):
            setattr(qtg, attr, MagicMock)


_ensure_qt_stubs()

import ui.login_screen as _ls  # noqa: E402  (must follow stub setup)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_stub() -> MagicMock:
    """
    Return a MagicMock that acts as `self` for LoginScreen unbound method calls.

    Captures _set_status calls so tests can inspect the (text, variant) pairs.
    """
    stub = MagicMock()
    stub._status_calls: list[tuple[str, str]] = []

    def _capture_set_status(text: str, variant: str) -> None:
        stub._status_calls.append((text, variant))

    stub._set_status = _capture_set_status
    return stub


# ── Tests: _check_password_configured ────────────────────────────────────────

class TestPasswordWarningWhenNotConfigured:
    """LoginScreen must show a clear error when no password is configured."""

    def _run(self) -> MagicMock:
        stub = _make_stub()
        with patch("ui.login_screen.password_is_configured", return_value=False):
            _ls.LoginScreen._check_password_configured(stub)
        return stub

    def test_warning_is_shown(self):
        """A visible 'error' status must be set when no password is configured."""
        stub = self._run()
        assert len(stub._status_calls) == 1, (
            f"Expected exactly one _set_status call; got {stub._status_calls}"
        )
        _, variant = stub._status_calls[0]
        assert variant == "error", f"Expected 'error' variant, got '{variant}'"

    def test_warning_message_mentions_setup_password(self):
        """The warning text must tell the operator which command to run."""
        stub = self._run()
        text, _ = stub._status_calls[0]
        assert "setup_password.py" in text, (
            f"Warning must mention setup_password.py; got: {text!r}"
        )

    def test_warning_message_does_not_contain_a_password_value(self):
        """The warning must never embed or reveal any credential value."""
        stub = self._run()
        text, _ = stub._status_calls[0]
        # The test password from conftest is "pytest-password"; it must not appear.
        assert "pytest-password" not in text

    def test_password_input_is_disabled(self):
        """The password field must be disabled when no password is configured."""
        stub = self._run()
        stub.password_input.setEnabled.assert_called_with(False)

    def test_login_button_is_disabled(self):
        """The ACCESS button must be disabled when no password is configured."""
        stub = self._run()
        stub.login_btn.setEnabled.assert_called_with(False)


class TestNoWarningWhenPasswordConfigured:
    """LoginScreen must NOT show the warning when a password is configured."""

    def _run(self) -> MagicMock:
        stub = _make_stub()
        with patch("ui.login_screen.password_is_configured", return_value=True):
            _ls.LoginScreen._check_password_configured(stub)
        return stub

    def test_no_status_update_when_configured(self):
        """_check_password_configured must not call _set_status when a password exists."""
        stub = self._run()
        assert stub._status_calls == [], (
            f"No status update expected when password is configured; got: {stub._status_calls}"
        )

    def test_password_input_stays_enabled(self):
        """setEnabled must not be called on the password field when configured."""
        stub = self._run()
        stub.password_input.setEnabled.assert_not_called()

    def test_login_button_stays_enabled(self):
        """setEnabled must not be called on the ACCESS button when configured."""
        stub = self._run()
        stub.login_btn.setEnabled.assert_not_called()


class TestVerifyPasswordCatchesLateNotConfiguredError:
    """
    _verify_password must also guard against PasswordNotConfiguredError at
    attempt time (e.g. if password.enc is deleted between app start and first
    login attempt).
    """

    def _run(self) -> MagicMock:
        stub = _make_stub()
        stub.is_locked = False
        stub.password_input.text.return_value = "any_text"

        with patch("ui.login_screen.password_is_configured", return_value=False):
            _ls.LoginScreen._verify_password(stub)
        return stub

    def test_form_is_disabled_on_late_not_configured_error(self):
        """Both the input and button must be disabled on PasswordNotConfiguredError."""
        stub = self._run()
        stub.password_input.setEnabled.assert_called_with(False)
        stub.login_btn.setEnabled.assert_called_with(False)

    def test_error_status_is_shown_on_late_not_configured_error(self):
        """An 'error' status must be shown when PasswordNotConfiguredError is raised."""
        stub = self._run()
        assert len(stub._status_calls) == 1
        _, variant = stub._status_calls[0]
        assert variant == "error"

    def test_no_login_signal_emitted_on_not_configured_error(self):
        """login_successful must NOT be emitted when password is not configured."""
        stub = self._run()
        stub.login_successful.emit.assert_not_called()


# ── Tests: login mode → role mapping ──────────────────────────────────────────

from domain.call_set_policy import OperatingMode  # noqa: E402


class TestLoginRoleMapping:
    """The role granted on success must match the login mode used."""

    def _success(self, mode: str) -> MagicMock:
        stub = _make_stub()
        stub._mode = mode
        stub.attempts = 0
        _ls.LoginScreen._on_login_success(stub)
        return stub

    def test_operator_mode_grants_camera_operator(self):
        stub = self._success("operator")
        assert stub.authenticated_role == OperatingMode.CAMERA_OPERATOR
        assert stub.authenticated is True

    def test_admin_mode_grants_system_admin(self):
        stub = self._success("admin")
        assert stub.authenticated_role == OperatingMode.SYSTEM_ADMIN

    def test_supercore_mode_grants_system_admin(self):
        stub = self._success("supercore")
        assert stub.authenticated_role == OperatingMode.SYSTEM_ADMIN


class TestSupercoreVerifyDispatch:
    """In supercore mode, _verify_password must use verify_supercore."""

    def _run(self, user: str, pwd: str, ok: bool) -> MagicMock:
        stub = _make_stub()
        stub._mode = "supercore"
        stub.is_locked = False
        stub.username_input.text.return_value = user
        stub.password_input.text.return_value = pwd
        with patch("ui.login_screen.verify_supercore", return_value=ok) as vs:
            _ls.LoginScreen._verify_password(stub)
        stub._verify_supercore_mock = vs
        return stub

    def test_calls_verify_supercore_with_username_and_password(self):
        stub = self._run("supercore", "secret", ok=True)
        stub._verify_supercore_mock.assert_called_once_with("supercore", "secret")

    def test_success_triggers_login(self):
        stub = self._run("supercore", "secret", ok=True)
        stub._on_login_success.assert_called_once()

    def test_failure_does_not_login(self):
        stub = self._run("supercore", "bad", ok=False)
        stub._on_login_success.assert_not_called()
        stub._on_login_failure.assert_called_once()

    def test_empty_username_is_rejected_without_verifying(self):
        stub = self._run("", "secret", ok=True)
        stub._verify_supercore_mock.assert_not_called()
        stub._on_login_success.assert_not_called()


class TestOperatorCountdown:
    """When the schedule marks operator auto-entry, a countdown auto-enters and
    'Start now' enters immediately — without asking for a password. In any other
    case the credential is verified."""

    def test_primary_action_in_operator_auto_enters_operator(self):
        stub = _make_stub()
        stub._mode = "operator"
        stub._operator_auto = True
        _ls.LoginScreen._on_primary_action(stub)
        stub._enter_operator.assert_called_once()
        stub._verify_password.assert_not_called()

    def test_primary_action_in_operator_manual_verifies_password(self):
        """Operator with NO schedule bypass must type a password (verify)."""
        stub = _make_stub()
        stub._mode = "operator"
        stub._operator_auto = False
        _ls.LoginScreen._on_primary_action(stub)
        stub._verify_password.assert_called_once()
        stub._enter_operator.assert_not_called()

    def test_primary_action_in_admin_mode_verifies_password(self):
        stub = _make_stub()
        stub._mode = "admin"
        stub._operator_auto = False
        _ls.LoginScreen._on_primary_action(stub)
        stub._verify_password.assert_called_once()
        stub._enter_operator.assert_not_called()

    def test_enter_operator_forces_operator_mode_and_logs_in(self):
        stub = _make_stub()
        stub._mode = "admin"  # even if switched, _enter_operator must reset it
        _ls.LoginScreen._enter_operator(stub)
        assert stub._mode == "operator"
        stub._cancel_countdown.assert_called_once()
        stub._on_login_success.assert_called_once()

    def test_countdown_tick_enters_operator_at_zero(self):
        stub = _make_stub()
        stub._countdown_remaining = 1
        _ls.LoginScreen._tick_countdown(stub)
        stub._enter_operator.assert_called_once()

    def test_countdown_tick_above_zero_does_not_enter(self):
        stub = _make_stub()
        stub._countdown_remaining = 5
        _ls.LoginScreen._tick_countdown(stub)
        stub._enter_operator.assert_not_called()
        stub._update_start_button.assert_called_once()
        assert stub._countdown_remaining == 4
