#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for domain/connectivity.py and offline mode integration (#269)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from domain.connectivity import (
    ConnectivityMode,
    DEFAULT_CONNECTIVITY_MODE,
    KNOWN_MODE_VALUES,
    parse_connectivity_mode,
    requires_internet,
)
from config.loader import load_config
from application.diagnostics_service import DiagnosticsService, Status


# ── ConnectivityMode enum ─────────────────────────────────────────────────────

class TestConnectivityModeEnum:

    def test_default_is_offline(self):
        assert DEFAULT_CONNECTIVITY_MODE == ConnectivityMode.OFFLINE

    def test_all_known_values_parseable(self):
        for value in KNOWN_MODE_VALUES:
            assert parse_connectivity_mode(value) is not None

    def test_unknown_returns_none(self):
        assert parse_connectivity_mode("cloud") is None
        assert parse_connectivity_mode("") is None

    @pytest.mark.parametrize("value,expected", [
        ("offline", ConnectivityMode.OFFLINE),
        ("online",  ConnectivityMode.ONLINE),
        ("hybrid",  ConnectivityMode.HYBRID),
    ])
    def test_parse_known(self, value, expected):
        assert parse_connectivity_mode(value) == expected


# ── requires_internet ─────────────────────────────────────────────────────────

class TestRequiresInternet:

    def test_offline_does_not_require_internet(self):
        assert not requires_internet(ConnectivityMode.OFFLINE)

    def test_online_requires_internet(self):
        assert requires_internet(ConnectivityMode.ONLINE)

    def test_hybrid_does_not_require_internet(self):
        assert not requires_internet(ConnectivityMode.HYBRID)


# ── Config loading ────────────────────────────────────────────────────────────

class TestConfigConnectivityMode:

    def _write_config(self, tmp_path: Path, runtime: dict | None = None) -> Path:
        config = {
            "runtime": runtime or {},
            "cameras": [
                {"id": "platform", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"}
            ],
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(config), encoding="utf-8")
        return p

    def test_connectivity_mode_offline_loaded(self, tmp_path):
        p = self._write_config(tmp_path, {"connectivity_mode": "offline"})
        settings = load_config(p)
        assert settings.runtime.connectivity_mode == "offline"

    def test_connectivity_mode_online_loaded(self, tmp_path):
        p = self._write_config(tmp_path, {"connectivity_mode": "online"})
        settings = load_config(p)
        assert settings.runtime.connectivity_mode == "online"

    def test_connectivity_mode_defaults_to_offline(self, tmp_path):
        p = self._write_config(tmp_path, {})
        settings = load_config(p)
        assert settings.runtime.connectivity_mode == "offline"

    def test_connectivity_mode_with_data_dir(self, tmp_path):
        p = self._write_config(tmp_path, {"data_dir": "/tmp/data", "connectivity_mode": "online"})
        settings = load_config(p)
        assert settings.runtime.data_dir == "/tmp/data"
        assert settings.runtime.connectivity_mode == "online"


# ── DiagnosticsService connectivity check ────────────────────────────────────

def _make_service(
    tmp_path: Path,
    *,
    connectivity_mode: str = "offline",
    with_config: bool = True,
) -> DiagnosticsService:
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    if with_config:
        config = {
            "runtime": {"connectivity_mode": connectivity_mode},
            "cameras": [
                {"id": "platform", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"}
            ],
        }
        (install_dir / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")

    return DiagnosticsService(
        install_dir=install_dir,
        data_dir=data_dir,
        config_path=install_dir / "config.yaml",
    )


class TestConnectivityModeCheck:

    def test_offline_mode_ok(self, tmp_path):
        svc = _make_service(tmp_path, connectivity_mode="offline")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "connectivity_mode")
        assert check.status == Status.OK
        assert "offline" in check.message

    def test_offline_mode_message_says_not_required(self, tmp_path):
        svc = _make_service(tmp_path, connectivity_mode="offline")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "connectivity_mode")
        assert "not required" in check.message.lower()

    def test_online_mode_ok(self, tmp_path):
        svc = _make_service(tmp_path, connectivity_mode="online")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "connectivity_mode")
        assert check.status == Status.OK
        assert "online" in check.message

    def test_unknown_mode_warns(self, tmp_path):
        svc = _make_service(tmp_path, connectivity_mode="cloud_always_on")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "connectivity_mode")
        assert check.status == Status.WARNING

    def test_no_config_warns(self, tmp_path):
        svc = _make_service(tmp_path, with_config=False)
        report = svc.run()
        check = next(c for c in report.checks if c.name == "connectivity_mode")
        assert check.status == Status.WARNING

    def test_offline_mode_not_a_failure(self, tmp_path):
        svc = _make_service(tmp_path, connectivity_mode="offline")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "connectivity_mode")
        assert check.status != Status.FAIL

    def test_offline_mode_does_not_cause_overall_failure(self, tmp_path):
        svc = _make_service(tmp_path, connectivity_mode="offline")
        report = svc.run()
        assert report.overall != Status.FAIL
