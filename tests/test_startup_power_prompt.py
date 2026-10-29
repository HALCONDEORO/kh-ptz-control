#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for the startup "power on cameras?" prompt (MainWindow._maybe_prompt_power_on).

The lifecycle contract forbids AUTOMATIC session start on boot but allows an
explicit operator action via a confirmed dialog. These tests exercise the
method's decision logic without constructing a full MainWindow or a real Qt
event loop: the method is called with a lightweight fake ``self`` and
``QMessageBox`` is replaced with a stub that returns a chosen button.
"""

from __future__ import annotations


import pytest

from ui.main_window import MainWindow


class _FakeSession:
    def __init__(self):
        self.toggled = 0

    def ToggleSession(self):
        self.toggled += 1


class _FakeSelf:
    """Minimal stand-in exposing only what _maybe_prompt_power_on touches."""

    def __init__(self, session_active=False):
        self.session_active = session_active
        self._session = _FakeSession()


class _StubButton:
    def __init__(self, role):
        self.role = role


class _StubMessageBox:
    """Records construction and returns a preset clicked button from exec_()."""

    Question = 4
    AcceptRole = 0
    RejectRole = 1

    # Which role the operator "clicks"; set by each test before exec_.
    click_role = AcceptRole

    def __init__(self, *_a, **_kw):
        self._buttons = {}
        self._clicked = None

    def setIcon(self, *_a):
        pass

    def setWindowTitle(self, *_a):
        pass

    def setText(self, *_a):
        pass

    def setInformativeText(self, *_a):
        pass

    def addButton(self, _label, role):
        btn = _StubButton(role)
        self._buttons[role] = btn
        return btn

    def setDefaultButton(self, *_a):
        pass

    def exec_(self):
        self._clicked = self._buttons.get(type(self).click_role)

    def clickedButton(self):
        return self._clicked


@pytest.fixture
def patched_config(monkeypatch):
    """Provide controllable CAM1/CAM2 IPs and a real is_valid_ip via config."""
    import config

    def _set(cam1_ip, cam2_ip):
        monkeypatch.setattr(config.CAM1, "ip", cam1_ip, raising=False)
        monkeypatch.setattr(config.CAM2, "ip", cam2_ip, raising=False)

    return _set


def _run(monkeypatch, fake_self, click_role):
    _StubMessageBox.click_role = click_role
    monkeypatch.setattr("PyQt5.QtWidgets.QMessageBox", _StubMessageBox)
    MainWindow._maybe_prompt_power_on(fake_self)


def test_no_prompt_when_no_camera_configured(monkeypatch, patched_config):
    patched_config("", "")  # no valid IPs → nothing to power on
    fake = _FakeSelf()
    _run(monkeypatch, fake, _StubMessageBox.AcceptRole)
    assert fake._session.toggled == 0


def test_no_prompt_when_session_already_active(monkeypatch, patched_config):
    patched_config("172.16.1.11", "172.16.1.12")
    fake = _FakeSelf(session_active=True)
    _run(monkeypatch, fake, _StubMessageBox.AcceptRole)
    assert fake._session.toggled == 0


def test_accept_powers_on(monkeypatch, patched_config):
    patched_config("172.16.1.11", "")  # one valid camera is enough
    fake = _FakeSelf()
    _run(monkeypatch, fake, _StubMessageBox.AcceptRole)
    assert fake._session.toggled == 1


def test_decline_leaves_cameras_off(monkeypatch, patched_config):
    patched_config("172.16.1.11", "172.16.1.12")
    fake = _FakeSelf()
    _run(monkeypatch, fake, _StubMessageBox.RejectRole)
    assert fake._session.toggled == 0
