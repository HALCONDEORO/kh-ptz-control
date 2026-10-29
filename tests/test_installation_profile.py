#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for domain/installation_profile.py and config/diagnostics integration."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from domain.installation_profile import (
    InstallationProfile,
    KNOWN_PROFILE_VALUES,
    expected_camera_count,
    parse_profile,
)
from config.loader import load_config
from application.diagnostics_service import DiagnosticsService, Status


# ── InstallationProfile enum ──────────────────────────────────────────────────

class TestInstallationProfileEnum:

    def test_all_known_values_parseable(self):
        for value in KNOWN_PROFILE_VALUES:
            assert parse_profile(value) is not None

    def test_unknown_value_returns_none(self):
        assert parse_profile("unknown_profile") is None
        assert parse_profile("") is None

    @pytest.mark.parametrize("value,expected", [
        ("starter_1_camera", InstallationProfile.STARTER_1_CAMERA),
        ("standard_2_camera", InstallationProfile.STANDARD_2_CAMERA),
        ("demo", InstallationProfile.DEMO),
        ("professional_multi_camera", InstallationProfile.PROFESSIONAL_MULTI_CAMERA),
        ("custom", InstallationProfile.CUSTOM),
    ])
    def test_parse_profile_known(self, value, expected):
        assert parse_profile(value) == expected


# ── expected_camera_count ─────────────────────────────────────────────────────

class TestExpectedCameraCount:

    def test_starter_expects_1(self):
        assert expected_camera_count(InstallationProfile.STARTER_1_CAMERA) == 1

    def test_standard_expects_2(self):
        assert expected_camera_count(InstallationProfile.STANDARD_2_CAMERA) == 2

    def test_demo_unrestricted(self):
        assert expected_camera_count(InstallationProfile.DEMO) is None

    def test_professional_unrestricted(self):
        assert expected_camera_count(InstallationProfile.PROFESSIONAL_MULTI_CAMERA) is None

    def test_custom_unrestricted(self):
        assert expected_camera_count(InstallationProfile.CUSTOM) is None


# ── Config loading ────────────────────────────────────────────────────────────

class TestConfigInstallationProfile:

    def _write_config(self, tmp_path: Path, site: dict, cameras: list | None = None) -> Path:
        config = {
            "site": site,
            "cameras": cameras or [
                {"id": "platform", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"}
            ],
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(config), encoding="utf-8")
        return p

    def test_profile_loaded(self, tmp_path):
        p = self._write_config(tmp_path, {"installation_profile": "starter_1_camera"})
        settings = load_config(p)
        assert settings.site.installation_profile == "starter_1_camera"

    def test_profile_defaults_to_empty(self, tmp_path):
        p = self._write_config(tmp_path, {})
        settings = load_config(p)
        assert settings.site.installation_profile == ""

    def test_profile_with_other_site_fields(self, tmp_path):
        p = self._write_config(tmp_path, {
            "name": "Dail Eireann",
            "installation_profile": "standard_2_camera",
        })
        settings = load_config(p)
        assert settings.site.name == "Dail Eireann"
        assert settings.site.installation_profile == "standard_2_camera"


# ── DiagnosticsService profile check ─────────────────────────────────────────

def _make_service(
    tmp_path: Path,
    *,
    profile: str = "starter_1_camera",
    cameras: list | None = None,
    with_config: bool = True,
) -> DiagnosticsService:
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    if with_config:
        config: dict = {
            "site": {"installation_profile": profile},
            "cameras": cameras or [
                {"id": "platform", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"}
            ],
        }
        (install_dir / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")

    return DiagnosticsService(
        install_dir=install_dir,
        data_dir=data_dir,
        config_path=install_dir / "config.yaml",
    )


class TestInstallationProfileCheck:

    def test_starter_with_1_camera_ok(self, tmp_path):
        svc = _make_service(tmp_path, profile="starter_1_camera")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_profile")
        assert check.status == Status.OK
        assert "starter_1_camera" in check.message

    def test_standard_with_2_cameras_ok(self, tmp_path):
        cameras = [
            {"id": "platform", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"},
            {"id": "comments", "role": "comments", "ip": "172.16.1.12", "visca_id": "82"},
        ]
        svc = _make_service(tmp_path, profile="standard_2_camera", cameras=cameras)
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_profile")
        assert check.status == Status.OK

    def test_demo_with_any_camera_count_ok(self, tmp_path):
        svc = _make_service(tmp_path, profile="demo")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_profile")
        assert check.status == Status.OK

    def test_starter_with_2_cameras_warns(self, tmp_path):
        cameras = [
            {"id": "platform", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"},
            {"id": "comments", "role": "comments", "ip": "172.16.1.12", "visca_id": "82"},
        ]
        svc = _make_service(tmp_path, profile="starter_1_camera", cameras=cameras)
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_profile")
        assert check.status == Status.WARNING
        assert "mismatch" in check.message.lower()

    def test_standard_with_1_camera_warns(self, tmp_path):
        svc = _make_service(tmp_path, profile="standard_2_camera")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_profile")
        assert check.status == Status.WARNING

    def test_missing_profile_warns(self, tmp_path):
        svc = _make_service(tmp_path, profile="")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_profile")
        assert check.status == Status.WARNING

    def test_unknown_profile_warns(self, tmp_path):
        svc = _make_service(tmp_path, profile="super_custom_xyz")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_profile")
        assert check.status == Status.WARNING

    def test_no_config_warns(self, tmp_path):
        svc = _make_service(tmp_path, with_config=False)
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_profile")
        assert check.status == Status.WARNING

    def test_professional_multi_camera_ok(self, tmp_path):
        cameras = [
            {"id": "cam1", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"},
            {"id": "cam2", "role": "comments", "ip": "172.16.1.12", "visca_id": "82"},
            {"id": "cam3", "role": "platform",  "ip": "172.16.1.13", "visca_id": "83"},
        ]
        svc = _make_service(tmp_path, profile="professional_multi_camera", cameras=cameras)
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_profile")
        assert check.status == Status.OK

