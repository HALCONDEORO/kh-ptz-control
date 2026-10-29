#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_admin_settings_hotspot.py — Hidden top-left hotspot that opens Settings in
administrator mode (production only).

The hotspot is a fully transparent QPushButton built by
``MainWindow._build_admin_hotspot``; clicking it runs ``_open_admin_settings``,
which reuses the existing RoleElevationOverlay + ConfigDialog flow rather than a
separate admin path.

Tests are headless: methods are exercised as unbound functions with NS/MagicMock
stubs acting as self. The import is skipped when another test module has already
injected partial Qt stubs (same guard as test_atem_signal_bindings.py).
"""

from __future__ import annotations

from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest


def _load_main_window():
    try:
        from ui.main_window import MainWindow
    except ImportError as exc:  # Qt stubbed by another test module → skip
        pytest.skip(f"ui.main_window not importable in this run: {exc}")
    return MainWindow


def _open_settings_stub(mode):
    """Minimal self with the collaborators _open_admin_settings reads."""
    return NS(
        _access_mode_svc=NS(mode=mode),
        _open_config_dialog=MagicMock(),
        _on_admin_settings_elevation_success=MagicMock(),
    )


# ── Build guard: production only ──────────────────────────────────────────────


class TestBuildHotspotGuard:
    def test_skipped_outside_production(self, monkeypatch):
        MainWindow = _load_main_window()
        monkeypatch.setenv("HALLPTZ_PROFILE", "demo")
        stub = MagicMock()
        with patch("ui.main_window.QPushButton") as mock_btn:
            MainWindow._build_admin_hotspot(stub)
        mock_btn.assert_not_called()

    def test_built_in_production(self, monkeypatch):
        MainWindow = _load_main_window()
        monkeypatch.setenv("HALLPTZ_PROFILE", "production")
        stub = MagicMock()
        with patch("ui.main_window.QPushButton") as mock_btn:
            MainWindow._build_admin_hotspot(stub)
        mock_btn.assert_called_once()
        # The hotspot's click is wired to the admin-settings entry point.
        mock_btn.return_value.clicked.connect.assert_called_once_with(
            stub._open_admin_settings
        )
        # Stacked under the session button so it never steals its clicks.
        mock_btn.return_value.stackUnder.assert_called_once_with(stub.BtnSession)

    def test_default_profile_is_production(self, monkeypatch):
        MainWindow = _load_main_window()
        monkeypatch.delenv("HALLPTZ_PROFILE", raising=False)
        stub = MagicMock()
        with patch("ui.main_window.QPushButton") as mock_btn:
            MainWindow._build_admin_hotspot(stub)
        mock_btn.assert_called_once()


# ── _open_admin_settings: role-dependent behaviour ────────────────────────────


class TestOpenAdminSettings:
    def test_already_admin_opens_settings_directly(self):
        MainWindow = _load_main_window()
        from domain.call_set_policy import OperatingMode

        stub = _open_settings_stub(OperatingMode.TECHNICIAN)
        MainWindow._open_admin_settings(stub)
        stub._open_config_dialog.assert_called_once()
        # No elevation overlay needed when the role already has settings access.
        assert not hasattr(stub, "_admin_settings_overlay")

    def test_operator_with_password_shows_overlay(self):
        MainWindow = _load_main_window()
        from domain.call_set_policy import OperatingMode

        stub = _open_settings_stub(OperatingMode.CAMERA_OPERATOR)
        with patch("runtime.secret_manager.password_is_configured", return_value=True), \
             patch("ui.role_elevation_overlay.RoleElevationOverlay") as mock_overlay:
            MainWindow._open_admin_settings(stub)

        # Built once with the elevate-then-open-settings success callback.
        mock_overlay.assert_called_once()
        kwargs = mock_overlay.call_args.kwargs
        assert kwargs["parent"] is stub
        assert kwargs["on_success"] is stub._on_admin_settings_elevation_success
        mock_overlay.return_value.show_overlay.assert_called_once()
        stub._open_config_dialog.assert_not_called()

    def test_operator_without_password_warns(self):
        MainWindow = _load_main_window()
        from domain.call_set_policy import OperatingMode

        stub = _open_settings_stub(OperatingMode.CAMERA_OPERATOR)
        with patch("runtime.secret_manager.password_is_configured", return_value=False), \
             patch("ui.main_window.QMessageBox") as mock_mb, \
             patch("ui.role_elevation_overlay.RoleElevationOverlay") as mock_overlay:
            MainWindow._open_admin_settings(stub)

        mock_mb.warning.assert_called_once()
        mock_overlay.assert_not_called()
        assert not hasattr(stub, "_admin_settings_overlay")

    def test_overlay_reused_on_second_open(self):
        MainWindow = _load_main_window()
        from domain.call_set_policy import OperatingMode

        stub = _open_settings_stub(OperatingMode.CAMERA_OPERATOR)
        with patch("runtime.secret_manager.password_is_configured", return_value=True), \
             patch("ui.role_elevation_overlay.RoleElevationOverlay") as mock_overlay:
            MainWindow._open_admin_settings(stub)
            MainWindow._open_admin_settings(stub)

        # Overlay constructed once; second open just re-shows it.
        mock_overlay.assert_called_once()
        assert mock_overlay.return_value.show_overlay.call_count == 2


# ── _on_admin_settings_elevation_success ──────────────────────────────────────


class TestElevationSuccess:
    def test_elevates_then_opens_settings(self):
        MainWindow = _load_main_window()
        stub = NS(
            _on_role_elevation_success=MagicMock(),
            _open_config_dialog=MagicMock(),
        )
        MainWindow._on_admin_settings_elevation_success(stub)
        stub._on_role_elevation_success.assert_called_once()
        stub._open_config_dialog.assert_called_once()
