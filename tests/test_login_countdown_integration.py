#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_login_countdown_integration.py — Real-Qt integration tests for the operator
auto-entry countdown.

Unlike test_login_screen_password_warning.py (which drives unbound methods with a
MagicMock self), these tests build a *real* LoginScreen on an offscreen
QApplication, so they exercise the actual widget wiring:

  • default boot mode is Operator (never a stale persisted Admin role)
  • Operator ALWAYS shows the countdown, with no password field and "Start now"
  • pressing "Start now" (or the countdown reaching 0) logs in as CAMERA_OPERATOR
  • switching to Admin cancels the countdown and reveals the password field

Run isolated (the full Qt suite segfaults under Py3.14 offscreen):
    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_login_countdown_integration.py
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from conftest import ensure_real_qt, is_poisoned_by_qt_stub  # noqa: E402
from domain.call_set_policy import OperatingMode  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _real_qt():
    """Ensure the real PyQt5 is in sys.modules (drop any collection-time stub)."""
    ensure_real_qt()


@pytest.fixture
def qapp(_real_qt):
    # Function-scoped, not module-scoped: under pytest-forked each test runs in
    # its own forked child, so a QApplication built once and shared across
    # tests in this module would be inherited across fork() boundaries from
    # whichever test happened to build it first — Qt does not support that and
    # aborts the next child that touches it. conftest.py's autouse
    # _qapp_available fixture already guarantees one exists in *this* process.
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def login(qapp):
    from ui.login_screen import LoginScreen
    if is_poisoned_by_qt_stub(LoginScreen):
        pytest.skip("ui.login_screen was imported under a PyQt5 stub by another "
                    "test module — run this file in isolation")
    widget = LoginScreen()
    widget._set_mode("operator")
    yield widget
    widget.deleteLater()


class TestBootDefaultsToOperator:
    def test_init_login_mode_starts_in_operator(self, login):
        login._init_login_mode()
        assert login._mode == "operator"


class TestOperatorAlwaysShowsCountdown:
    """Operator entry needs no password: the countdown is always shown."""

    def test_operator_auto_is_true(self, login):
        assert login._operator_auto is True

    def test_password_field_hidden(self, login):
        assert login.password_input.isHidden()

    def test_countdown_timer_running(self, login):
        assert login._countdown_timer is not None
        assert login._countdown_timer.isActive()

    def test_button_shows_start_now_with_seconds(self, login):
        assert "Start now" in login.login_btn.text()
        assert "s" in login.login_btn.text()  # "Start now  ·  10s"

    def test_start_now_logs_in_as_operator(self, login):
        received: list[bool] = []
        login.login_successful.connect(lambda: received.append(True))
        login._on_primary_action()  # press "Start now"
        assert received == [True]
        assert login.authenticated is True
        assert login.authenticated_role == OperatingMode.CAMERA_OPERATOR

    def test_countdown_tick_reaches_login(self, login):
        received: list[bool] = []
        login.login_successful.connect(lambda: received.append(True))
        login._countdown_remaining = 1
        login._tick_countdown()  # 1 → 0 → auto-enter
        assert received == [True]
        assert login.authenticated_role == OperatingMode.CAMERA_OPERATOR

    def test_countdown_decrements_button(self, login):
        login._countdown_remaining = 8
        login._tick_countdown()  # 8 → 7, still above zero
        assert login._countdown_remaining == 7
        assert "7s" in login.login_btn.text()


class TestSwitchToAdminCancelsCountdown:
    def test_switch_to_admin_stops_countdown_and_shows_password(self, login):
        assert login._countdown_timer.isActive()
        login._set_mode("admin")
        assert login._mode == "admin"
        assert login._operator_auto is False
        assert not login._countdown_timer.isActive()
        assert not login.password_input.isHidden()

    def test_switch_back_to_operator_restarts_countdown(self, login):
        login._set_mode("admin")
        login._set_mode("operator")
        assert login._operator_auto is True
        assert login._countdown_timer.isActive()
        assert login.password_input.isHidden()
