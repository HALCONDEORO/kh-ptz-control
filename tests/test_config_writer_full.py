#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for config.writer.write_full_config — the inverse of load_config.

Hardware-free: no sockets, no Qt. Underpins the setup wizard, which creates
config.yaml from scratch (patch_config_yaml can only edit an existing file).
"""

from __future__ import annotations

import os
import stat

import pytest

from config.loader import load_config
from config.settings import (
    AppSettings,
    ATEMSettings,
    CameraSettings,
    FeaturesSettings,
    NetworkSettings,
    RuntimeSettings,
    SiteSettings,
)
from config.writer import write_full_config


def _sample_settings() -> AppSettings:
    return AppSettings(
        site=SiteSettings(
            name="Test Hall",
            contact="IT Support",
            installation_profile="starter_1_camera",
            installation_id="KHPTZ-2026-7F3A",
        ),
        cameras=[
            CameraSettings(
                id="platform", role="platform", ip="172.16.1.11",
                visca_id="81", name="Main Platform",
            ),
            CameraSettings(
                id="comments", role="comments", ip="172.16.1.12",
                visca_id="82", name="Comments Desk",
            ),
        ],
        atem=ATEMSettings(ip="172.16.1.50"),
        runtime=RuntimeSettings(data_dir="/var/lib/khptz"),
        features=FeaturesSettings(),
        network=NetworkSettings(profile="flat_lan"),
    )


class TestRoundTrip:
    """write_full_config → load_config preserves every field the loader reads."""

    def test_full_round_trip_is_identity(self, tmp_path):
        original = _sample_settings()
        path = tmp_path / "config.yaml"
        write_full_config(original, path)
        assert load_config(path) == original

    def test_camera_name_survives(self, tmp_path):
        original = _sample_settings()
        path = tmp_path / "config.yaml"
        write_full_config(original, path)
        loaded = load_config(path)
        assert [c.name for c in loaded.cameras] == ["Main Platform", "Comments Desk"]

    def test_atem_enabled_round_trip(self, tmp_path):
        original = _sample_settings()
        original.atem = ATEMSettings(ip="172.16.1.50", installed=True, enabled=True)
        original.features = FeaturesSettings(atem_enabled=True)
        path = tmp_path / "config.yaml"
        write_full_config(original, path)
        assert load_config(path) == original


class TestSafety:

    def test_no_python_object_tags(self, tmp_path):
        path = tmp_path / "config.yaml"
        write_full_config(_sample_settings(), path)
        text = path.read_text(encoding="utf-8")
        assert "!!python" not in text, "safe_dump must never emit executable object tags"

    def test_header_present(self, tmp_path):
        path = tmp_path / "config.yaml"
        write_full_config(_sample_settings(), path)
        assert path.read_text(encoding="utf-8").startswith("# KH PTZ Control")

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
    def test_mode_applied(self, tmp_path):
        path = tmp_path / "config.yaml"
        write_full_config(_sample_settings(), path, mode=0o640)
        assert stat.S_IMODE(path.stat().st_mode) == 0o640
