#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tests for config/loader.py — load_config() and ConfigError validation.

Hardware-free: no sockets, no Qt, no production files.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config.loader import ConfigError, load_config
from config.settings import AppSettings, CameraSettings


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_yaml(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return p


MINIMAL_CAMERA = {
    "id": "platform",
    "role": "platform",
    "ip": "172.16.1.11",
    "visca_id": "81",
}

VALID_CONFIG = {
    "site": {"name": "Test Hall", "contact": "IT Support"},
    "cameras": [
        MINIMAL_CAMERA,
        {"id": "comments", "role": "comments", "ip": "172.16.1.12", "visca_id": "82"},
    ],
    "atem": {"ip": "192.168.1.240"},
    "runtime": {"data_dir": "/tmp/data"},
    "features": {"atem_enabled": True, "simulation": False},
}


# ── Valid config ───────────────────────────────────────────────────────────────

class TestValidConfig:

    def test_returns_app_settings(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_CONFIG)
        result = load_config(path)
        assert isinstance(result, AppSettings)

    def test_site_name(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_CONFIG)
        result = load_config(path)
        assert result.site.name == "Test Hall"

    def test_site_contact(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_CONFIG)
        result = load_config(path)
        assert result.site.contact == "IT Support"

    def test_cameras_count(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_CONFIG)
        result = load_config(path)
        assert len(result.cameras) == 2

    def test_camera_fields(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_CONFIG)
        cam = load_config(path).cameras[0]
        assert isinstance(cam, CameraSettings)
        assert cam.id == "platform"
        assert cam.role == "platform"
        assert cam.ip == "172.16.1.11"
        assert cam.visca_id == "81"

    def test_atem_ip(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_CONFIG)
        result = load_config(path)
        assert result.atem.ip == "192.168.1.240"

    def test_runtime_data_dir(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_CONFIG)
        result = load_config(path)
        assert result.runtime.data_dir == "/tmp/data"

    def test_features_atem_enabled(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_CONFIG)
        result = load_config(path)
        assert result.features.atem_enabled is True

    def test_features_simulation_false(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_CONFIG)
        result = load_config(path)
        assert result.features.simulation is False

    def test_optional_sections_have_defaults(self, tmp_path):
        minimal = {"cameras": [MINIMAL_CAMERA]}
        path = _write_yaml(tmp_path, minimal)
        result = load_config(path)
        assert result.site.name == ""
        assert result.atem.ip == ""
        assert result.runtime.data_dir == ""
        assert result.features.atem_enabled is False


# ── Optional camera name ──────────────────────────────────────────────────────

class TestCameraName:
    """The optional `name` field: respected when present, derived from role when absent."""

    def test_explicit_name_is_kept(self, tmp_path):
        camera = {**MINIMAL_CAMERA, "name": "Main Platform"}
        path = _write_yaml(tmp_path, {"cameras": [camera]})
        cam = load_config(path).cameras[0]
        assert cam.name == "Main Platform"

    def test_missing_name_derives_from_known_role(self, tmp_path):
        # MINIMAL_CAMERA has role "platform" and no name → "Platform".
        path = _write_yaml(tmp_path, {"cameras": [MINIMAL_CAMERA]})
        cam = load_config(path).cameras[0]
        assert cam.name == "Platform"

    def test_blank_name_derives_from_role(self, tmp_path):
        camera = {**MINIMAL_CAMERA, "name": "   "}
        path = _write_yaml(tmp_path, {"cameras": [camera]})
        cam = load_config(path).cameras[0]
        assert cam.name == "Platform"

    def test_comments_role_derives_comments(self, tmp_path):
        camera = {"id": "comments", "role": "comments", "ip": "172.16.1.12", "visca_id": "82"}
        path = _write_yaml(tmp_path, {"cameras": [camera]})
        cam = load_config(path).cameras[0]
        assert cam.name == "Comments"

    def test_unknown_role_derives_presentable_name(self, tmp_path):
        camera = {"id": "aux", "role": "wide_shot", "ip": "172.16.1.13", "visca_id": "83"}
        path = _write_yaml(tmp_path, {"cameras": [camera]})
        cam = load_config(path).cameras[0]
        assert cam.name == "Wide Shot"


# ── Missing required fields ───────────────────────────────────────────────────

class TestMissingRequiredFields:

    @pytest.mark.parametrize("missing_key", ["id", "role", "ip", "visca_id"])
    def test_missing_camera_field_raises(self, tmp_path, missing_key):
        camera = {k: v for k, v in MINIMAL_CAMERA.items() if k != missing_key}
        data = {"cameras": [camera]}
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ConfigError, match=missing_key):
            load_config(path)

    def test_empty_cameras_list_raises(self, tmp_path):
        path = _write_yaml(tmp_path, {"cameras": []})
        with pytest.raises(ConfigError, match="vacío"):
            load_config(path)

    def test_missing_cameras_section_raises(self, tmp_path):
        path = _write_yaml(tmp_path, {"site": {"name": "x"}})
        with pytest.raises(ConfigError):
            load_config(path)

    def test_empty_ip_raises(self, tmp_path):
        camera = {**MINIMAL_CAMERA, "ip": ""}
        path = _write_yaml(tmp_path, {"cameras": [camera]})
        with pytest.raises(ConfigError, match="ip"):
            load_config(path)

    def test_empty_visca_id_raises(self, tmp_path):
        camera = {**MINIMAL_CAMERA, "visca_id": ""}
        path = _write_yaml(tmp_path, {"cameras": [camera]})
        with pytest.raises(ConfigError, match="visca_id"):
            load_config(path)


# ── Duplicate camera IDs ───────────────────────────────────────────────────────

class TestDuplicateCameraIds:

    def test_duplicate_id_raises(self, tmp_path):
        data = {
            "cameras": [
                MINIMAL_CAMERA,
                {**MINIMAL_CAMERA, "ip": "172.16.1.99"},
            ]
        }
        path = _write_yaml(tmp_path, data)
        with pytest.raises(ConfigError, match="duplicado"):
            load_config(path)

    def test_unique_ids_accepted(self, tmp_path):
        data = {
            "cameras": [
                MINIMAL_CAMERA,
                {"id": "comments", "role": "comments", "ip": "172.16.1.12", "visca_id": "82"},
            ]
        }
        path = _write_yaml(tmp_path, data)
        result = load_config(path)
        assert len(result.cameras) == 2


# ── File errors ───────────────────────────────────────────────────────────────

class TestFileErrors:

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        p = tmp_path / "config.yaml"
        p.write_text("cameras: [{{bad yaml", encoding="utf-8")
        with pytest.raises(Exception):
            load_config(p)


# ── Camera IP and VISCA validation (#606) ────────────────────────────────────

class TestCameraIpAndViscaValidation:

    def test_invalid_ip_raises(self, tmp_path):
        path = _write_yaml(tmp_path, {"cameras": [{**MINIMAL_CAMERA, "ip": "999.999.0.0"}]})
        with pytest.raises(ConfigError, match="IPv4"):
            load_config(path)

    def test_duplicate_ip_raises(self, tmp_path):
        path = _write_yaml(tmp_path, {"cameras": [
            MINIMAL_CAMERA,
            {"id": "comments", "role": "comments", "ip": "172.16.1.11", "visca_id": "82"},
        ]})
        with pytest.raises(ConfigError, match="duplicad"):
            load_config(path)

    def test_invalid_visca_id_raises(self, tmp_path):
        path = _write_yaml(tmp_path, {"cameras": [{**MINIMAL_CAMERA, "visca_id": "ZZ"}]})
        with pytest.raises(ConfigError, match="VISCA"):
            load_config(path)

    def test_duplicate_visca_id_raises(self, tmp_path):
        path = _write_yaml(tmp_path, {"cameras": [
            MINIMAL_CAMERA,
            {"id": "comments", "role": "comments", "ip": "172.16.1.12", "visca_id": "81"},
        ]})
        with pytest.raises(ConfigError, match="VISCA"):
            load_config(path)

    def test_valid_ips_accepted(self, tmp_path):
        path = _write_yaml(tmp_path, {"cameras": [
            MINIMAL_CAMERA,
            {"id": "comments", "role": "comments", "ip": "172.16.1.12", "visca_id": "82"},
        ]})
        result = load_config(path)
        assert len(result.cameras) == 2


# ── Boolean parsing (#607) ────────────────────────────────────────────────────

class TestBooleanParsing:

    def test_quoted_false_string_parses_as_false(self, tmp_path):
        path = _write_yaml(tmp_path, {
            "cameras": [MINIMAL_CAMERA],
            "features": {"simulation": "false"},
        })
        result = load_config(path)
        assert result.features.simulation is False

    def test_quoted_true_string_parses_as_true(self, tmp_path):
        path = _write_yaml(tmp_path, {
            "cameras": [MINIMAL_CAMERA],
            "features": {"atem_enabled": "true"},
        })
        result = load_config(path)
        assert result.features.atem_enabled is True

    def test_zero_string_parses_as_false(self, tmp_path):
        path = _write_yaml(tmp_path, {
            "cameras": [MINIMAL_CAMERA],
            "features": {"simulation": "0"},
        })
        result = load_config(path)
        assert result.features.simulation is False

    def test_ambiguous_string_raises(self, tmp_path):
        path = _write_yaml(tmp_path, {
            "cameras": [MINIMAL_CAMERA],
            "features": {"simulation": "maybe"},
        })
        with pytest.raises(ConfigError, match="booleano"):
            load_config(path)

    def test_native_bool_true_accepted(self, tmp_path):
        path = _write_yaml(tmp_path, {
            "cameras": [MINIMAL_CAMERA],
            "features": {"simulation": True},
        })
        result = load_config(path)
        assert result.features.simulation is True


# ── Structured ConfigError fields (#443) ──────────────────────────────────────

class TestConfigErrorStructure:

    def test_error_has_field_path(self, tmp_path):
        camera = {k: v for k, v in MINIMAL_CAMERA.items() if k != "ip"}
        path = _write_yaml(tmp_path, {"cameras": [camera]})
        with pytest.raises(ConfigError) as exc_info:
            load_config(path)
        assert exc_info.value.field_path == "cameras[0].ip"

    def test_error_has_remediation(self, tmp_path):
        camera = {k: v for k, v in MINIMAL_CAMERA.items() if k != "ip"}
        path = _write_yaml(tmp_path, {"cameras": [camera]})
        with pytest.raises(ConfigError) as exc_info:
            load_config(path)
        assert exc_info.value.remediation != ""

    def test_error_severity_defaults_to_error(self, tmp_path):
        path = _write_yaml(tmp_path, {"cameras": []})
        with pytest.raises(ConfigError) as exc_info:
            load_config(path)
        assert exc_info.value.severity == "error"

    def test_invalid_ip_field_path(self, tmp_path):
        path = _write_yaml(tmp_path, {"cameras": [{**MINIMAL_CAMERA, "ip": "999.0.0.1"}]})
        with pytest.raises(ConfigError) as exc_info:
            load_config(path)
        assert exc_info.value.field_path == "cameras[0].ip"
        assert exc_info.value.remediation != ""

    def test_invalid_visca_field_path(self, tmp_path):
        path = _write_yaml(tmp_path, {"cameras": [{**MINIMAL_CAMERA, "visca_id": "ZZ"}]})
        with pytest.raises(ConfigError) as exc_info:
            load_config(path)
        assert exc_info.value.field_path == "cameras[0].visca_id"

    def test_bool_parse_error_field_path(self, tmp_path):
        path = _write_yaml(tmp_path, {
            "cameras": [MINIMAL_CAMERA],
            "features": {"simulation": "maybe"},
        })
        with pytest.raises(ConfigError) as exc_info:
            load_config(path)
        assert "features.simulation" in exc_info.value.field_path
        assert exc_info.value.remediation != ""

    def test_empty_cameras_field_path(self, tmp_path):
        path = _write_yaml(tmp_path, {"cameras": []})
        with pytest.raises(ConfigError) as exc_info:
            load_config(path)
        assert exc_info.value.field_path == "cameras"

    def test_duplicate_id_field_path(self, tmp_path):
        path = _write_yaml(tmp_path, {"cameras": [
            MINIMAL_CAMERA,
            {**MINIMAL_CAMERA, "ip": "172.16.1.99"},
        ]})
        with pytest.raises(ConfigError) as exc_info:
            load_config(path)
        assert "cameras[1].id" in exc_info.value.field_path


# ── ATEM canonical config schema (#550) ───────────────────────────────────────

class TestATEMCanonicalConfig:
    """Phase 1 ATEM config fields."""

    def _cfg(self, tmp_path, atem: dict) -> object:
        data = {**VALID_CONFIG, "atem": atem}
        return load_config(_write_yaml(tmp_path, data))

    def test_defaults_when_atem_section_empty(self, tmp_path):
        result = load_config(_write_yaml(tmp_path, {"cameras": [MINIMAL_CAMERA]}))
        assert result.atem.installed is False
        assert result.atem.enabled is False
        assert result.atem.me_index == 0
        assert result.atem.input_labels == {}
        assert result.atem.connect_timeout_secs == 10
        assert result.atem.reconnect_timeout_secs == 30
        assert result.atem.automation_disabled is True

    def test_installed_and_enabled_valid(self, tmp_path):
        result = self._cfg(tmp_path, {
            "ip": "192.168.1.240", "installed": True, "enabled": True
        })
        assert result.atem.installed is True
        assert result.atem.enabled is True

    def test_enabled_without_installed_raises(self, tmp_path):
        with pytest.raises(ConfigError) as exc_info:
            self._cfg(tmp_path, {"ip": "192.168.1.240", "installed": False, "enabled": True})
        assert exc_info.value.field_path == "atem.enabled"

    def test_installed_false_enabled_false_is_valid(self, tmp_path):
        result = self._cfg(tmp_path, {"installed": False, "enabled": False})
        assert result.atem.installed is False
        assert result.atem.enabled is False

    def test_input_labels_loaded(self, tmp_path):
        result = self._cfg(tmp_path, {
            "ip": "192.168.1.240",
            "installed": True,
            "enabled": True,
            "input_labels": {1: "Platform", 2: "Comments"},
        })
        assert result.atem.input_labels == {"1": "Platform", "2": "Comments"}

    def test_input_labels_invalid_type_raises(self, tmp_path):
        with pytest.raises(ConfigError) as exc_info:
            self._cfg(tmp_path, {"input_labels": "not-a-dict"})
        assert exc_info.value.field_path == "atem.input_labels"

    def test_me_index_loaded(self, tmp_path):
        result = self._cfg(tmp_path, {"me_index": 1})
        assert result.atem.me_index == 1

    def test_timeouts_loaded(self, tmp_path):
        result = self._cfg(tmp_path, {
            "connect_timeout_secs": 5,
            "reconnect_timeout_secs": 60,
        })
        assert result.atem.connect_timeout_secs == 5
        assert result.atem.reconnect_timeout_secs == 60

    def test_automation_disabled_false_loaded(self, tmp_path):
        result = self._cfg(tmp_path, {"automation_disabled": False})
        assert result.atem.automation_disabled is False

    def test_disabled_reason_loaded(self, tmp_path):
        result = self._cfg(tmp_path, {"disabled_reason": "under maintenance"})
        assert result.atem.disabled_reason == "under maintenance"
