#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application/health_diagnostics.py and system health checks (#275).

Hardware-free: disk usage and temperature are injected, not read from real hardware.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import yaml

from application.health_diagnostics import (
    DISK_FAIL_FREE_MB,
    DISK_WARN_FREE_MB,
    TEMP_FAIL_CELSIUS,
    TEMP_WARN_CELSIUS,
    HealthDiagnosticsService,
)
from application.diagnostics_service import DiagnosticsService, Status
from application.network_diagnostics import NetworkDiagnosticsService


# ── Disk usage helpers ────────────────────────────────────────────────────────

class _DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


def _make_disk_fn(free_mb: int, total_mb: int = 32_000):
    free  = free_mb  * 1024 * 1024
    total = total_mb * 1024 * 1024
    used  = total - free
    usage = _DiskUsage(total=total, used=used, free=free)
    return lambda path: usage


def _make_temp_fn(celsius: float | None):
    return lambda: celsius


# ── HealthDiagnosticsService.check_disk ──────────────────────────────────────

class TestCheckDisk:

    def test_plenty_of_space_ok(self, tmp_path):
        svc = HealthDiagnosticsService(disk_usage_fn=_make_disk_fn(10_000))
        result = svc.check_disk(tmp_path)
        assert result.status == Status.OK
        assert "10000 MB" in result.message

    def test_below_warn_threshold_warns(self, tmp_path):
        svc = HealthDiagnosticsService(disk_usage_fn=_make_disk_fn(DISK_WARN_FREE_MB - 1))
        result = svc.check_disk(tmp_path)
        assert result.status == Status.WARNING
        assert "low" in result.message.lower()

    def test_below_fail_threshold_fails(self, tmp_path):
        svc = HealthDiagnosticsService(disk_usage_fn=_make_disk_fn(DISK_FAIL_FREE_MB - 1))
        result = svc.check_disk(tmp_path)
        assert result.status == Status.FAIL
        assert "critical" in result.message.lower()

    def test_exactly_at_warn_threshold_is_ok(self, tmp_path):
        # Exactly at the threshold is OK; only strictly below triggers WARNING
        svc = HealthDiagnosticsService(disk_usage_fn=_make_disk_fn(DISK_WARN_FREE_MB))
        result = svc.check_disk(tmp_path)
        assert result.status == Status.OK

    def test_disk_read_error_fails(self, tmp_path):
        def bad_fn(path):
            raise OSError("no such device")
        svc = HealthDiagnosticsService(disk_usage_fn=bad_fn)
        result = svc.check_disk(tmp_path)
        assert result.status == Status.FAIL

    def test_custom_threshold(self, tmp_path):
        svc = HealthDiagnosticsService(
            disk_usage_fn=_make_disk_fn(500),
            warn_free_mb=2000,
            fail_free_mb=100,
        )
        result = svc.check_disk(tmp_path)
        assert result.status == Status.WARNING

    def test_report_name_is_disk_space(self, tmp_path):
        svc = HealthDiagnosticsService(disk_usage_fn=_make_disk_fn(10_000))
        result = svc.check_disk(tmp_path)
        assert result.name == "disk_space"


# ── HealthDiagnosticsService.check_temperature ───────────────────────────────

class TestCheckTemperature:

    def test_normal_temp_ok(self):
        svc = HealthDiagnosticsService(temp_reader_fn=_make_temp_fn(55.0))
        result = svc.check_temperature()
        assert result.status == Status.OK
        assert "55.0" in result.message

    def test_high_temp_warns(self):
        svc = HealthDiagnosticsService(temp_reader_fn=_make_temp_fn(TEMP_WARN_CELSIUS))
        result = svc.check_temperature()
        assert result.status == Status.WARNING
        assert "high" in result.message.lower()

    def test_overheating_fails(self):
        svc = HealthDiagnosticsService(temp_reader_fn=_make_temp_fn(TEMP_FAIL_CELSIUS))
        result = svc.check_temperature()
        assert result.status == Status.FAIL

    def test_unavailable_temp_ok(self):
        svc = HealthDiagnosticsService(temp_reader_fn=_make_temp_fn(None))
        result = svc.check_temperature()
        assert result.status == Status.OK
        assert "not available" in result.message.lower()

    def test_custom_thresholds(self):
        svc = HealthDiagnosticsService(
            temp_reader_fn=_make_temp_fn(70.0),
            warn_temp=65.0,
            fail_temp=85.0,
        )
        result = svc.check_temperature()
        assert result.status == Status.WARNING

    def test_report_name_is_cpu_temperature(self):
        svc = HealthDiagnosticsService(temp_reader_fn=_make_temp_fn(50.0))
        result = svc.check_temperature()
        assert result.name == "cpu_temperature"


# ── DiagnosticsService integration ───────────────────────────────────────────

def _make_service(tmp_path: Path, *, free_mb: int = 10_000, temp: float | None = 55.0):
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config = {
        "site": {
            "installation_profile": "starter_1_camera",
            "installation_id": "hallptz-2026-0001",
        },
        "cameras": [
            {"id": "platform", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"}
        ],
        "network": {
            "profile": "isolated_av_vlan",
        },
    }
    (install_dir / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")

    health_svc = HealthDiagnosticsService(
        disk_usage_fn=_make_disk_fn(free_mb),
        temp_reader_fn=_make_temp_fn(temp),
    )
    # Use a fake network service so tests don't depend on real TCP reachability
    network_svc = NetworkDiagnosticsService(
        probe_fn=lambda host, port: True,
        local_ips_fn=lambda: ["172.16.1.11"],
    )
    return DiagnosticsService(
        install_dir=install_dir,
        data_dir=data_dir,
        config_path=install_dir / "config.yaml",
        health_svc=health_svc,
        network_svc=network_svc,
    )


class TestDiagnosticsServiceHealth:

    def test_healthy_disk_ok(self, tmp_path):
        svc = _make_service(tmp_path)
        report = svc.run()
        check = next(c for c in report.checks if c.name == "disk_space")
        assert check.status == Status.OK

    def test_low_disk_warns(self, tmp_path):
        svc = _make_service(tmp_path, free_mb=DISK_WARN_FREE_MB - 1)
        report = svc.run()
        check = next(c for c in report.checks if c.name == "disk_space")
        assert check.status == Status.WARNING

    def test_normal_temp_ok(self, tmp_path):
        svc = _make_service(tmp_path, temp=55.0)
        report = svc.run()
        check = next(c for c in report.checks if c.name == "cpu_temperature")
        assert check.status == Status.OK

    def test_high_temp_warns(self, tmp_path):
        svc = _make_service(tmp_path, temp=TEMP_WARN_CELSIUS)
        report = svc.run()
        check = next(c for c in report.checks if c.name == "cpu_temperature")
        assert check.status == Status.WARNING

    def test_unavailable_temp_ok(self, tmp_path):
        svc = _make_service(tmp_path, temp=None)
        report = svc.run()
        check = next(c for c in report.checks if c.name == "cpu_temperature")
        assert check.status == Status.OK

    def test_overall_ok_with_healthy_system(self, tmp_path, monkeypatch):
        # Pin to the supported 3.9.x target so the python_version check stays OK
        # regardless of the interpreter running the suite.
        from application import diagnostics_service as _ds_mod
        monkeypatch.setattr(_ds_mod.sys, "version_info", (3, 9, 2))
        svc = _make_service(tmp_path)
        report = svc.run()
        assert report.overall == Status.OK

