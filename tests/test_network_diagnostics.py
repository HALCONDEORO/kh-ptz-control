#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for network validation and NetworkDiagnosticsService (#272).

Hardware-free: reachability tests use an injectable probe function instead of real TCP.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest
import yaml

from domain.network_validation import (
    is_loopback,
    is_valid_ipv4,
    validate_ip_config,
)
from application.network_diagnostics import NetworkDiagnosticsService
from application.diagnostics_service import DiagnosticsService, Status
from config.loader import load_config


def test_network_diagnostics_uses_runtime_visca_port(monkeypatch):
    import config
    from types import SimpleNamespace

    monkeypatch.setattr(config, "VISCA_PORT", 4321)
    seen_ports = []
    svc = NetworkDiagnosticsService(
        probe_fn=lambda host, port: seen_ports.append(port) or True,
    )
    settings = SimpleNamespace(
        cameras=[SimpleNamespace(id="platform", ip="172.16.1.11")]
    )

    svc.check_cameras(settings)

    assert seen_ports == [4321]


# ── Local IPs helper ──────────────────────────────────────────────────────────

def _make_local_ips(*ips: str):
    """Return a callable that yields the given IP list (injectable for tests)."""
    def _fn() -> list[str]:
        return list(ips)
    return _fn


# ── is_valid_ipv4 ─────────────────────────────────────────────────────────────

class TestIsValidIpv4:

    @pytest.mark.parametrize("value", [
        "192.168.1.1", "10.0.0.1", "172.16.1.11", "255.255.255.0", "0.0.0.0",
    ])
    def test_valid(self, value):
        assert is_valid_ipv4(value)

    @pytest.mark.parametrize("value", [
        "", "abc", "192.168.1", "192.168.1.256", "192.168.1.1.1", "1.2.3.4.5",
        "300.1.1.1", "192.168.1.-1",
    ])
    def test_invalid(self, value):
        assert not is_valid_ipv4(value)


# ── is_loopback ───────────────────────────────────────────────────────────────

class TestIsLoopback:

    def test_127_0_0_1_is_loopback(self):
        assert is_loopback("127.0.0.1")

    def test_127_anything_is_loopback(self):
        assert is_loopback("127.1.2.3")

    def test_192_168_is_not_loopback(self):
        assert not is_loopback("192.168.1.1")


# ── validate_ip_config ────────────────────────────────────────────────────────

def _load(tmp_path: Path, config: dict) -> object:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(config), encoding="utf-8")
    return load_config(p)


def _cam(cam_id: str, ip: str, visca: str = "81", role: str = "platform") -> dict:
    return {"id": cam_id, "role": role, "ip": ip, "visca_id": visca}


class TestValidateIpConfig:

    def test_valid_config_no_issues(self, tmp_path):
        settings = _load(tmp_path, {"cameras": [_cam("platform", "192.168.1.11")]})
        assert validate_ip_config(settings) == []

    def test_two_valid_cameras_no_issues(self, tmp_path):
        settings = _load(tmp_path, {"cameras": [
            _cam("platform", "192.168.1.11", "81"),
            _cam("comments", "192.168.1.12", "82", "comments"),
        ]})
        assert validate_ip_config(settings) == []

    def test_duplicate_camera_ips_flagged(self, tmp_path):
        from config.loader import ConfigError
        with pytest.raises(ConfigError, match="duplicad"):
            _load(tmp_path, {"cameras": [
                _cam("platform", "192.168.1.11"),
                _cam("comments", "192.168.1.11", "82", "comments"),
            ]})

    def test_invalid_ip_format_flagged(self, tmp_path):
        from config.loader import ConfigError
        with pytest.raises(ConfigError, match="IPv4"):
            _load(tmp_path, {"cameras": [_cam("platform", "not.an.ip.addr")]})

    def test_loopback_without_simulation_flagged(self, tmp_path):
        settings = _load(tmp_path, {"cameras": [_cam("platform", "127.0.0.1")]})
        issues = validate_ip_config(settings)
        assert any("loopback" in i.message.lower() for i in issues)

    def test_loopback_in_simulation_not_flagged(self, tmp_path):
        settings = _load(tmp_path, {
            "cameras": [_cam("platform", "127.0.0.1")],
            "features": {"simulation": True},
        })
        issues = validate_ip_config(settings)
        assert not any("loopback" in i.message.lower() for i in issues)

    def test_duplicate_visca_ids_flagged(self, tmp_path):
        from config.loader import ConfigError
        with pytest.raises(ConfigError, match="VISCA"):
            _load(tmp_path, {"cameras": [
                _cam("platform", "192.168.1.11", "81"),
                _cam("comments", "192.168.1.12", "81", "comments"),
            ]})

    def test_atem_ip_conflicts_with_camera(self, tmp_path):
        settings = _load(tmp_path, {
            "cameras": [_cam("platform", "192.168.1.11")],
            "atem": {"ip": "192.168.1.11"},
            "features": {"atem_enabled": True},
        })
        issues = validate_ip_config(settings)
        assert any("atem" in i.message.lower() and "conflict" in i.message.lower() for i in issues)

    def test_atem_invalid_ip_flagged_when_enabled(self, tmp_path):
        settings = _load(tmp_path, {
            "cameras": [_cam("platform", "192.168.1.11")],
            "atem": {"ip": "bad-ip"},
            "features": {"atem_enabled": True},
        })
        issues = validate_ip_config(settings)
        assert any("atem" in i.message.lower() for i in issues)

    def test_atem_disabled_not_checked(self, tmp_path):
        settings = _load(tmp_path, {
            "cameras": [_cam("platform", "192.168.1.11")],
            "atem": {"ip": "bad-ip"},
            "features": {"atem_enabled": False},
        })
        issues = validate_ip_config(settings)
        assert not any("atem" in i.message.lower() for i in issues)


# ── NetworkDiagnosticsService ─────────────────────────────────────────────────

def _make_probe(reachable_hosts: Dict[str, bool]) -> object:
    """Return a probe function that uses a lookup table instead of real TCP."""
    def probe(host: str, port: int) -> bool:
        return reachable_hosts.get(host, False)
    return probe


def _settings(tmp_path: Path, config: dict) -> object:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(config), encoding="utf-8")
    return load_config(p)


class TestNetworkDiagnosticsService:

    def test_reachable_camera_ok(self, tmp_path):
        s = _settings(tmp_path, {"cameras": [_cam("platform", "192.168.1.11")]})
        svc = NetworkDiagnosticsService(probe_fn=_make_probe({"192.168.1.11": True}))
        results = svc.check_cameras(s)
        assert len(results) == 1
        assert results[0].status == Status.OK
        assert "reachable" in results[0].message

    def test_unreachable_camera_warning(self, tmp_path):
        s = _settings(tmp_path, {"cameras": [_cam("platform", "192.168.1.11")]})
        svc = NetworkDiagnosticsService(probe_fn=_make_probe({"192.168.1.11": False}))
        results = svc.check_cameras(s)
        assert results[0].status == Status.WARNING
        assert "unreachable" in results[0].message

    def test_multiple_cameras_independent_results(self, tmp_path):
        s = _settings(tmp_path, {"cameras": [
            _cam("platform", "192.168.1.11", "81"),
            _cam("comments", "192.168.1.12", "82", "comments"),
        ]})
        svc = NetworkDiagnosticsService(probe_fn=_make_probe({
            "192.168.1.11": True,
            "192.168.1.12": False,
        }))
        results = svc.check_cameras(s)
        assert len(results) == 2
        statuses = {r.name: r.status for r in results}
        assert statuses["camera_platform_reachable"] == Status.OK
        assert statuses["camera_comments_reachable"] == Status.WARNING

    def test_atem_reachable_ok(self, tmp_path):
        s = _settings(tmp_path, {
            "cameras": [_cam("platform", "192.168.1.11")],
            "atem": {"ip": "192.168.1.20"},
            "features": {"atem_enabled": True},
        })
        svc = NetworkDiagnosticsService(probe_fn=_make_probe({"192.168.1.20": True}))
        result = svc.check_atem(s)
        assert result is not None
        assert result.status == Status.OK

    def test_atem_unreachable_warning(self, tmp_path):
        s = _settings(tmp_path, {
            "cameras": [_cam("platform", "192.168.1.11")],
            "atem": {"ip": "192.168.1.20"},
            "features": {"atem_enabled": True},
        })
        svc = NetworkDiagnosticsService(probe_fn=_make_probe({"192.168.1.20": False}))
        result = svc.check_atem(s)
        assert result is not None
        assert result.status == Status.WARNING

    def test_atem_disabled_returns_none(self, tmp_path):
        s = _settings(tmp_path, {
            "cameras": [_cam("platform", "192.168.1.11")],
            "atem": {"ip": "192.168.1.20"},
            "features": {"atem_enabled": False},
        })
        svc = NetworkDiagnosticsService(probe_fn=_make_probe({}))
        assert svc.check_atem(s) is None

    def test_atem_enabled_no_ip_warns(self, tmp_path):
        s = _settings(tmp_path, {
            "cameras": [_cam("platform", "192.168.1.11")],
            "features": {"atem_enabled": True},
        })
        svc = NetworkDiagnosticsService(probe_fn=_make_probe({}))
        result = svc.check_atem(s)
        assert result is not None
        assert result.status == Status.WARNING


# ── DiagnosticsService IP config check ───────────────────────────────────────

def _make_diag_service(tmp_path: Path, config: dict, with_sim: bool = False) -> DiagnosticsService:
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    p = install_dir / "config.yaml"
    p.write_text(yaml.dump(config), encoding="utf-8")
    if with_sim:
        (install_dir / "sim_ip_backup.json").write_text("{}", encoding="utf-8")
    return DiagnosticsService(install_dir=install_dir, data_dir=data_dir, config_path=p)


class TestIpConfigCheck:

    def test_valid_ips_ok(self, tmp_path):
        svc = _make_diag_service(tmp_path, {"cameras": [_cam("platform", "172.16.1.11")]})
        report = svc.run()
        check = next(c for c in report.checks if c.name == "ip_config")
        assert check.status == Status.OK

    def test_duplicate_ip_config_fails(self, tmp_path):
        # Duplicate IPs are now rejected at load time: config check is FAIL,
        # ip_config check is WARNING (settings could not be loaded).
        svc = _make_diag_service(tmp_path, {"cameras": [
            _cam("platform", "172.16.1.11"),
            _cam("comments", "172.16.1.11", "82", "comments"),
        ]})
        report = svc.run()
        config_check = next(c for c in report.checks if c.name == "config")
        assert config_check.status == Status.FAIL
        ip_check = next(c for c in report.checks if c.name == "ip_config")
        assert ip_check.status == Status.WARNING

    def test_no_config_warns(self, tmp_path):
        install_dir = tmp_path / "app"
        install_dir.mkdir()
        (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        svc = DiagnosticsService(
            install_dir=install_dir, data_dir=data_dir,
            config_path=install_dir / "config.yaml",
        )
        report = svc.run()
        check = next(c for c in report.checks if c.name == "ip_config")
        assert check.status == Status.WARNING


# ── NetworkDiagnosticsService.check_pi_subnet ─────────────────────────────────

def _settings_with_network(tmp_path: Path, av_subnet: str) -> object:
    config = {
        "cameras": [_cam("platform", "192.168.30.20")],
        "network": {
            "profile": "isolated_av_vlan",
            "av_subnet": av_subnet,
        },
    }
    return _settings(tmp_path, config)


class TestCheckPiSubnet:

    def test_pi_on_expected_subnet_ok(self, tmp_path):
        s = _settings_with_network(tmp_path, "192.168.30.0/24")
        svc = NetworkDiagnosticsService(local_ips_fn=_make_local_ips("192.168.30.10"))
        result = svc.check_pi_subnet(s)
        assert result is not None
        assert result.status == Status.OK
        assert "192.168.30.0/24" in result.message

    def test_pi_on_wrong_subnet_warns(self, tmp_path):
        s = _settings_with_network(tmp_path, "192.168.30.0/24")
        svc = NetworkDiagnosticsService(local_ips_fn=_make_local_ips("10.0.0.5"))
        result = svc.check_pi_subnet(s)
        assert result is not None
        assert result.status == Status.WARNING
        assert "192.168.30.0/24" in result.message

    def test_no_local_ips_warns(self, tmp_path):
        s = _settings_with_network(tmp_path, "192.168.30.0/24")
        svc = NetworkDiagnosticsService(local_ips_fn=_make_local_ips())
        result = svc.check_pi_subnet(s)
        assert result is not None
        assert result.status == Status.WARNING
        assert "No local" in result.message

    def test_no_av_subnet_returns_none(self, tmp_path):
        config = {
            "cameras": [_cam("platform", "192.168.30.20")],
            "network": {"profile": "isolated_av_vlan", "av_subnet": ""},
        }
        s = _settings(tmp_path, config)
        svc = NetworkDiagnosticsService(local_ips_fn=_make_local_ips("192.168.30.10"))
        assert svc.check_pi_subnet(s) is None

    def test_no_network_section_returns_none(self, tmp_path):
        s = _settings(tmp_path, {"cameras": [_cam("platform", "192.168.30.20")]})
        svc = NetworkDiagnosticsService(local_ips_fn=_make_local_ips("192.168.30.10"))
        assert svc.check_pi_subnet(s) is None

    def test_malformed_av_subnet_warns(self, tmp_path):
        s = _settings_with_network(tmp_path, "not-a-subnet")
        svc = NetworkDiagnosticsService(local_ips_fn=_make_local_ips("192.168.30.10"))
        result = svc.check_pi_subnet(s)
        assert result is not None
        assert result.status == Status.WARNING
        assert "invalid" in result.message.lower()

    def test_multiple_local_ips_any_match_ok(self, tmp_path):
        s = _settings_with_network(tmp_path, "192.168.30.0/24")
        # First IP not matching, second IP matching
        svc = NetworkDiagnosticsService(
            local_ips_fn=_make_local_ips("10.0.0.1", "192.168.30.5")
        )
        result = svc.check_pi_subnet(s)
        assert result is not None
        assert result.status == Status.OK

    def test_evidence_contains_subnet_and_ip(self, tmp_path):
        s = _settings_with_network(tmp_path, "192.168.30.0/24")
        svc = NetworkDiagnosticsService(local_ips_fn=_make_local_ips("192.168.30.20"))
        result = svc.check_pi_subnet(s)
        assert result.evidence.get("av_subnet") == "192.168.30.0/24"
        assert result.evidence.get("local_ip") == "192.168.30.20"


# ── DiagnosticsService network reachability integration ───────────────────────

def _make_full_diag_service(
    tmp_path: Path,
    config: dict,
    *,
    probe_table: dict | None = None,
    local_ips: list[str] | None = None,
) -> DiagnosticsService:
    """Create a DiagnosticsService with an injectable network service."""
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    p = install_dir / "config.yaml"
    p.write_text(yaml.dump(config), encoding="utf-8")

    net_svc = NetworkDiagnosticsService(
        probe_fn=_make_probe(probe_table or {}),
        local_ips_fn=_make_local_ips(*(local_ips or [])),
    )
    return DiagnosticsService(
        install_dir=install_dir,
        data_dir=data_dir,
        config_path=p,
        network_svc=net_svc,
    )


class TestDiagnosticsServiceNetworkIntegration:

    def test_reachable_camera_ok_in_report(self, tmp_path):
        config = {
            "cameras": [_cam("platform", "192.168.30.20")],
            "network": {"profile": "isolated_av_vlan", "av_subnet": "192.168.30.0/24"},
        }
        svc = _make_full_diag_service(
            tmp_path, config,
            probe_table={"192.168.30.20": True},
            local_ips=["192.168.30.1"],
        )
        report = svc.run()
        check = next(c for c in report.checks if c.name == "camera_platform_reachable")
        assert check.status == Status.OK

    def test_unreachable_camera_warns_in_report(self, tmp_path):
        config = {
            "cameras": [_cam("platform", "192.168.30.20")],
            "network": {"profile": "isolated_av_vlan"},
        }
        svc = _make_full_diag_service(
            tmp_path, config,
            probe_table={"192.168.30.20": False},
        )
        report = svc.run()
        check = next(c for c in report.checks if c.name == "camera_platform_reachable")
        assert check.status == Status.WARNING

    def test_pi_subnet_mismatch_warns_in_report(self, tmp_path):
        config = {
            "cameras": [_cam("platform", "192.168.30.20")],
            "network": {"profile": "isolated_av_vlan", "av_subnet": "192.168.30.0/24"},
        }
        svc = _make_full_diag_service(
            tmp_path, config,
            probe_table={"192.168.30.20": True},
            local_ips=["10.0.0.5"],  # wrong subnet
        )
        report = svc.run()
        check = next(c for c in report.checks if c.name == "pi_subnet")
        assert check.status == Status.WARNING

    def test_pi_subnet_match_ok_in_report(self, tmp_path):
        config = {
            "cameras": [_cam("platform", "192.168.30.20")],
            "network": {"profile": "isolated_av_vlan", "av_subnet": "192.168.30.0/24"},
        }
        svc = _make_full_diag_service(
            tmp_path, config,
            probe_table={"192.168.30.20": True},
            local_ips=["192.168.30.1"],
        )
        report = svc.run()
        check = next(c for c in report.checks if c.name == "pi_subnet")
        assert check.status == Status.OK

    def test_atem_reachable_ok_in_report(self, tmp_path):
        config = {
            "cameras": [_cam("platform", "192.168.30.20")],
            "atem": {"ip": "192.168.30.30"},
            "features": {"atem_enabled": True},
            "network": {"profile": "isolated_av_vlan"},
        }
        svc = _make_full_diag_service(
            tmp_path, config,
            probe_table={"192.168.30.20": True, "192.168.30.30": True},
        )
        report = svc.run()
        check = next(c for c in report.checks if c.name == "atem_reachable")
        assert check.status == Status.OK

    def test_atem_disabled_no_atem_check(self, tmp_path):
        config = {
            "cameras": [_cam("platform", "192.168.30.20")],
            "atem": {"ip": "192.168.30.30"},
            "features": {"atem_enabled": False},
            "network": {"profile": "isolated_av_vlan"},
        }
        svc = _make_full_diag_service(tmp_path, config, probe_table={})
        report = svc.run()
        names = [c.name for c in report.checks]
        assert "atem_reachable" not in names

    def test_no_network_section_no_pi_subnet_check(self, tmp_path):
        config = {
            "cameras": [_cam("platform", "192.168.30.20")],
            "network": {"profile": "isolated_av_vlan"},  # no av_subnet
        }
        svc = _make_full_diag_service(tmp_path, config, probe_table={})
        report = svc.run()
        names = [c.name for c in report.checks]
        assert "pi_subnet" not in names

    def test_offline_profile_internet_not_required(self, tmp_path):
        """Offline-first: missing internet access must not cause FAIL."""
        config = {
            "cameras": [_cam("platform", "192.168.30.20")],
            "network": {
                "profile": "isolated_av_vlan",
                "internet_required": False,
            },
            "runtime": {"connectivity_mode": "offline"},
        }
        svc = _make_full_diag_service(
            tmp_path, config,
            probe_table={"192.168.30.20": True},
        )
        report = svc.run()
        # No check should have FAIL status due to internet being unavailable
        assert not any(
            c.status == Status.FAIL and "internet" in c.name.lower()
            for c in report.checks
        )
