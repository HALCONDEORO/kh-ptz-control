#!/usr/bin/env python3
"""Tests for Raspberry Pi post-provision normalization."""
from pathlib import Path

import pytest
import yaml

from runtime.rpi_post_provision import normalize_config


def _write_config(path: Path, *, camera_count: int = 2, atem_ip: str = "", atem_enabled: bool = False):
    cameras = [
        {
            "id": f"camera_{index}",
            "role": "platform" if index == 1 else "comments",
            "ip": f"172.16.1.{10 + index}",
            "visca_id": f"{0x80 + index:02X}",
        }
        for index in range(1, camera_count + 1)
    ]
    data = {
        "site": {"installation_profile": "wizard"},
        "cameras": cameras,
        "atem": {
            "ip": atem_ip,
            "installed": atem_enabled,
            "enabled": atem_enabled,
        },
        "features": {"atem_enabled": atem_enabled},
        "network": {"profile": "flat_lan"},
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_two_camera_profile_is_normalized(tmp_path: Path):
    config = tmp_path / "config.yaml"
    _write_config(config, camera_count=2)
    advisories = normalize_config(config)
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert raw["site"]["installation_profile"] == "standard_2_camera"
    assert any("isolated AV VLAN" in item for item in advisories)


def test_one_camera_profile_is_normalized(tmp_path: Path):
    config = tmp_path / "config.yaml"
    _write_config(config, camera_count=1)
    normalize_config(config)
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert raw["site"]["installation_profile"] == "starter_1_camera"


def test_enabled_atem_requires_ip(tmp_path: Path):
    config = tmp_path / "config.yaml"
    _write_config(config, atem_enabled=True, atem_ip="")
    with pytest.raises(RuntimeError, match="ATEM is enabled"):
        normalize_config(config)


def test_enabled_atem_flags_are_synchronized(tmp_path: Path):
    config = tmp_path / "config.yaml"
    _write_config(config, atem_enabled=True, atem_ip="172.16.1.50")
    normalize_config(config)
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert raw["atem"]["installed"] is True
    assert raw["atem"]["enabled"] is True
    assert raw["features"]["atem_enabled"] is True
