#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tests that the Starter and Standard default config templates load and
validate successfully through load_config().

Hardware-free: reads bundled YAML files only, no sockets.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config.loader import load_config
from config.settings import AppSettings

DEFAULTS_DIR = Path(__file__).parent.parent / "config" / "defaults"


class TestStarterTemplate:

    @pytest.fixture()
    def settings(self):
        return load_config(DEFAULTS_DIR / "starter.yaml")

    # ── issue #663 regression: starter must have all doctor-expected fields ──

    def test_has_installation_profile(self, settings):
        """starter.yaml must have site.installation_profile set (not empty)."""
        assert settings.site.installation_profile != ""

    def test_has_network_section(self, settings):
        """starter.yaml must have a network: section so doctor does not warn about missing schema."""
        assert settings.network is not None

    def test_doctor_does_not_warn_about_missing_installation_profile(self, tmp_path, settings):
        """Doctor must not warn 'installation_profile not set' for the starter config."""
        import shutil
        from application.diagnostics_service import DiagnosticsService, Status
        config_path = tmp_path / "config.yaml"
        shutil.copy(DEFAULTS_DIR / "starter.yaml", config_path)
        install_dir = tmp_path / "app"
        install_dir.mkdir()
        (install_dir / "VERSION").write_text("0.0.0", encoding="utf-8")
        svc = DiagnosticsService(install_dir=install_dir, data_dir=tmp_path, config_path=config_path)
        report = svc.run()
        profile_check = next((c for c in report.checks if c.name == "installation_profile"), None)
        assert profile_check is not None
        assert profile_check.status != Status.FAIL, (
            f"Doctor reports FAIL for installation_profile on starter config: {profile_check.message}"
        )

    def test_doctor_does_not_warn_about_missing_network_section(self, tmp_path):
        """Doctor must not warn 'network profile not configured' for the starter config."""
        import shutil
        from application.diagnostics_service import DiagnosticsService
        config_path = tmp_path / "config.yaml"
        shutil.copy(DEFAULTS_DIR / "starter.yaml", config_path)
        install_dir = tmp_path / "app"
        install_dir.mkdir()
        (install_dir / "VERSION").write_text("0.0.0", encoding="utf-8")
        svc = DiagnosticsService(install_dir=install_dir, data_dir=tmp_path, config_path=config_path)
        report = svc.run()
        net_check = next((c for c in report.checks if c.name == "network_profile"), None)
        assert net_check is not None
        # Network profile warning is acceptable (flat_lan is a security advisory, not a schema error)
        # But it must NOT say "not configured" (missing section) — the section must be present
        assert "not configured" not in net_check.message.lower(), (
            f"Doctor reports missing network section on starter config: {net_check.message}"
        )

    def test_loads_as_app_settings(self, settings):
        assert isinstance(settings, AppSettings)

    def test_has_one_camera(self, settings):
        assert len(settings.cameras) == 1

    def test_camera_id_platform(self, settings):
        assert settings.cameras[0].id == "platform"

    def test_camera_role_platform(self, settings):
        assert settings.cameras[0].role == "platform"

    def test_camera_ip_set(self, settings):
        assert settings.cameras[0].ip != ""

    def test_camera_visca_id_set(self, settings):
        assert settings.cameras[0].visca_id != ""

    def test_atem_disabled(self, settings):
        assert settings.features.atem_enabled is False

    def test_simulation_off(self, settings):
        assert settings.features.simulation is False

    def test_no_real_secrets(self, settings):
        content = (DEFAULTS_DIR / "starter.yaml").read_text()
        assert "password" not in content.lower()
        assert "secret" not in content.lower()
        assert "token" not in content.lower()


class TestStandardTemplate:

    @pytest.fixture()
    def settings(self):
        return load_config(DEFAULTS_DIR / "standard.yaml")

    def test_loads_as_app_settings(self, settings):
        assert isinstance(settings, AppSettings)

    def test_has_two_cameras(self, settings):
        assert len(settings.cameras) == 2

    def test_has_platform_camera(self, settings):
        ids = [c.id for c in settings.cameras]
        assert "platform" in ids

    def test_has_comments_camera(self, settings):
        ids = [c.id for c in settings.cameras]
        assert "comments" in ids

    def test_no_duplicate_camera_ids(self, settings):
        ids = [c.id for c in settings.cameras]
        assert len(ids) == len(set(ids))

    def test_all_cameras_have_ip(self, settings):
        assert all(c.ip != "" for c in settings.cameras)

    def test_all_cameras_have_visca_id(self, settings):
        assert all(c.visca_id != "" for c in settings.cameras)

    def test_atem_enabled(self, settings):
        assert settings.features.atem_enabled is True

    def test_atem_ip_set(self, settings):
        assert settings.atem.ip != ""

    def test_simulation_off(self, settings):
        assert settings.features.simulation is False

    def test_no_real_secrets(self, settings):
        content = (DEFAULTS_DIR / "standard.yaml").read_text()
        assert "password" not in content.lower()
        assert "secret" not in content.lower()
        assert "token" not in content.lower()
