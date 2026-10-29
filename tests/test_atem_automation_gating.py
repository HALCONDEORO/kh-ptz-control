#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_atem_automation_gating.py — ATEM automation is disabled when no switcher is
configured.

Covers the helper logic added for the "disable ATEM automation when ATEM IP is
empty" behaviour:
  - AtemAdminPanel._atem_is_configured / _refresh_pip_status / _set_pip_automation
    (floating panel PiP automation toggle)
  - MainWindow._atem_is_configured (the provider wired into the panel)

Tests are headless: methods are exercised as unbound functions with NS/MagicMock
stubs. AtemAdminPanel is importable without a real Qt (it falls back to object).
"""

from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock

import pytest

from ui.atem_admin_panel import AtemAdminPanel


# ── _atem_is_configured ───────────────────────────────────────────────────────


class TestPanelConfiguredHelper:
    def test_none_provider_defaults_true(self):
        stub = NS(_atem_configured_provider=None)
        assert AtemAdminPanel._atem_is_configured(stub) is True

    def test_provider_false(self):
        stub = NS(_atem_configured_provider=lambda: False)
        assert AtemAdminPanel._atem_is_configured(stub) is False

    def test_provider_true(self):
        stub = NS(_atem_configured_provider=lambda: True)
        assert AtemAdminPanel._atem_is_configured(stub) is True

    def test_provider_raises_defaults_true(self):
        def _boom():
            raise RuntimeError("config unreadable")

        stub = NS(_atem_configured_provider=_boom)
        assert AtemAdminPanel._atem_is_configured(stub) is True


# ── _refresh_pip_status ───────────────────────────────────────────────────────


def _pip_stub(*, configured: bool, automation_on: bool):
    return NS(
        _lbl_pip_status=MagicMock(),
        _pip_automation_provider=(lambda: automation_on),
        _atem_is_configured=(lambda: configured),
        _btn_pip_enable=MagicMock(),
        _btn_pip_disable=MagicMock(),
    )


class TestRefreshPipStatus:
    def test_not_configured_disables_both_buttons(self):
        stub = _pip_stub(configured=False, automation_on=False)
        AtemAdminPanel._refresh_pip_status(stub)
        stub._btn_pip_enable.setEnabled.assert_called_with(False)
        stub._btn_pip_disable.setEnabled.assert_called_with(False)
        stub._lbl_pip_status.setText.assert_called_with("PiP Auto: no ATEM")

    def test_configured_and_off_enables_enable_button(self):
        stub = _pip_stub(configured=True, automation_on=False)
        AtemAdminPanel._refresh_pip_status(stub)
        stub._btn_pip_enable.setEnabled.assert_called_with(True)
        stub._btn_pip_disable.setEnabled.assert_called_with(False)
        stub._lbl_pip_status.setText.assert_called_with("PiP Auto: OFF")

    def test_configured_and_on_enables_disable_button(self):
        stub = _pip_stub(configured=True, automation_on=True)
        AtemAdminPanel._refresh_pip_status(stub)
        stub._btn_pip_enable.setEnabled.assert_called_with(False)
        stub._btn_pip_disable.setEnabled.assert_called_with(True)
        stub._lbl_pip_status.setText.assert_called_with("PiP Auto: ON")


# ── _set_pip_automation ───────────────────────────────────────────────────────


class TestSetPipAutomation:
    def test_noop_when_not_configured(self):
        setter = MagicMock()
        stub = NS(
            _atem_is_configured=(lambda: False),
            _pip_automation_setter=setter,
            _refresh_pip_status=MagicMock(),
        )
        AtemAdminPanel._set_pip_automation(stub, True)
        setter.assert_not_called()
        stub._refresh_pip_status.assert_not_called()

    def test_applies_when_configured(self):
        setter = MagicMock()
        stub = NS(
            _atem_is_configured=(lambda: True),
            _pip_automation_setter=setter,
            _refresh_pip_status=MagicMock(),
        )
        AtemAdminPanel._set_pip_automation(stub, True)
        setter.assert_called_once_with(True)
        stub._refresh_pip_status.assert_called_once()


# ── MainWindow._atem_is_configured (the wired provider) ───────────────────────


def _load_main_window():
    try:
        from ui.main_window import MainWindow
    except ImportError as exc:  # Qt stubbed by another test module → skip
        pytest.skip(f"ui.main_window not importable in this run: {exc}")
    return MainWindow


class TestMainWindowProvider:
    def test_reflects_atem_ip(self, monkeypatch):
        MainWindow = _load_main_window()
        import config

        monkeypatch.setattr(config.ATEM, "ip", "192.168.1.50", raising=False)
        assert MainWindow._atem_is_configured(NS()) is True

        monkeypatch.setattr(config.ATEM, "ip", "", raising=False)
        assert MainWindow._atem_is_configured(NS()) is False
