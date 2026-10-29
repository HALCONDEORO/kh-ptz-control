#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application/network_handover_report.py (#508).

Hardware-free: all tests use tmp_path, fake configs, and injected DiagnosticsReports.
No real network I/O, no real camera, no real ATEM.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from application.network_handover_report import (
    NetworkHandoverReport,
    NetworkHandoverReportService,
    NetworkDeviceRecord,
    VerificationStatus,
)
from application.diagnostics_service import CheckResult, DiagnosticsReport, Status
from runtime.cli import main as cli_main


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_config(tmp_path: Path, config: dict) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(config), encoding="utf-8")
    return p


def _make_svc(tmp_path: Path, config: dict) -> NetworkHandoverReportService:
    p = _write_config(tmp_path, config)
    return NetworkHandoverReportService(config_path=p)


def _isolated_config(**overrides) -> dict:
    base = {
        "site": {
            "name": "Test Venue",
            "installation_id": "hallptz-2026-TEST",
            "installation_profile": "starter_1_camera",
        },
        "cameras": [
            {"id": "platform", "role": "platform", "ip": "192.168.30.20", "visca_id": "81"},
        ],
        "atem": {"ip": ""},
        "features": {"atem_enabled": False},
        "network": {
            "profile": "isolated_av_vlan",
            "av_vlan_id": "30",
            "av_subnet": "192.168.30.0/24",
            "guest_access_allowed": False,
            "internet_required": False,
            "static_ips": True,
        },
    }
    base.update(overrides)
    return base


def _make_preflight(checks: list[CheckResult]) -> DiagnosticsReport:
    report = DiagnosticsReport()
    for c in checks:
        report.add(c)
    return report


# ── NetworkHandoverReport defaults ────────────────────────────────────────────

class TestNetworkHandoverReportDefaults:

    def test_default_site_name(self):
        r = NetworkHandoverReport()
        assert r.site_name == "unknown"

    def test_default_preflight_summary(self):
        r = NetworkHandoverReport()
        assert r.preflight_summary == "NOT_RUN"

    def test_default_no_errors(self):
        r = NetworkHandoverReport()
        assert r.errors == []

    def test_default_cameras_empty(self):
        r = NetworkHandoverReport()
        assert r.cameras == []

    def test_to_dict_is_json_serializable(self):
        r = NetworkHandoverReport()
        d = r.to_dict()
        json.dumps(d)  # must not raise


# ── NetworkDeviceRecord ───────────────────────────────────────────────────────

class TestNetworkDeviceRecord:

    def test_defaults(self):
        rec = NetworkDeviceRecord(device_id="platform", role="platform", ip="192.168.30.20")
        assert rec.verification_status == VerificationStatus.CONFIGURED_NOT_VERIFIED

    def test_to_dict(self):
        rec = NetworkDeviceRecord(device_id="platform", role="platform", ip="192.168.30.20")
        d = rec.to_dict()
        assert d["device_id"] == "platform"
        assert d["ip"] == "192.168.30.20"


# ── Report generation from config ─────────────────────────────────────────────

class TestNetworkHandoverReportFromConfig:

    def test_site_name_extracted(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.site_name == "Test Venue"

    def test_installation_id_extracted(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.installation_id == "hallptz-2026-TEST"

    def test_network_profile_extracted(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.network_profile == "isolated_av_vlan"

    def test_vlan_id_extracted(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.vlan_id == "30"

    def test_av_subnet_extracted(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.av_subnet == "192.168.30.0/24"

    def test_static_ips_true(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.static_ips is True

    def test_guest_access_false(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.guest_access_allowed is False

    def test_internet_not_required(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.internet_required is False

    def test_cameras_populated(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert len(r.cameras) == 1
        cam = r.cameras[0]
        assert cam.device_id == "platform"
        assert cam.ip == "192.168.30.20"
        assert cam.verification_status == VerificationStatus.CONFIGURED_NOT_VERIFIED

    def test_atem_disabled(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.atem_enabled is False
        assert r.atem_verification == VerificationStatus.NOT_APPLICABLE

    def test_atem_enabled_with_ip(self, tmp_path):
        config = _isolated_config()
        config["atem"] = {"ip": "192.168.30.30"}
        config["features"] = {"atem_enabled": True}
        svc = _make_svc(tmp_path, config)
        r = svc.generate()
        assert r.atem_enabled is True
        assert r.atem_ip == "192.168.30.30"
        assert r.atem_verification == VerificationStatus.CONFIGURED_NOT_VERIFIED

    def test_flat_network_warning_is_false_for_isolated_vlan(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.flat_network_warning is False

    def test_flat_network_warning_true_for_flat_lan(self, tmp_path):
        config = _isolated_config()
        config["network"]["profile"] = "flat_lan"
        svc = _make_svc(tmp_path, config)
        r = svc.generate()
        assert r.flat_network_warning is True

    def test_no_network_section_produces_warning(self, tmp_path):
        # No explicit network section — loader returns default NetworkSettings(profile="unknown")
        config = {
            "site": {"name": "X", "installation_id": "hallptz-2026-TEST"},
            "cameras": [{"id": "platform", "role": "platform", "ip": "192.168.30.20", "visca_id": "81"}],
        }
        svc = _make_svc(tmp_path, config)
        r = svc.generate()
        assert r.flat_network_warning is True
        # profile will be "unknown" (the AppSettings default), not "not_configured"
        assert r.network_profile == "unknown"

    def test_missing_config_captured_in_errors(self, tmp_path):
        svc = NetworkHandoverReportService(config_path=tmp_path / "nofile.yaml")
        r = svc.generate()
        assert any("Config load error" in e for e in r.errors)

    def test_generated_at_present(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.generated_at != ""

    def test_notes_included(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate(notes="Installed by PersonA")
        assert r.notes == "Installed by PersonA"

    def test_no_secrets_in_to_dict(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        serialized = json.dumps(r.to_dict()).lower()
        for token in ("password", "secret", "token", "key", "credential"):
            assert token not in serialized


# ── Preflight enrichment ──────────────────────────────────────────────────────

class TestNetworkHandoverReportPreflight:

    def test_all_ok_gives_pass(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        preflight = _make_preflight([
            CheckResult("camera_platform_reachable", Status.OK, "reachable"),
            CheckResult("pi_subnet", Status.OK, "ok", evidence={"local_ip": "192.168.30.10"}),
        ])
        r = svc.generate(preflight_report=preflight)
        assert r.preflight_summary == "PASS"

    def test_warning_gives_pass_with_warnings(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        preflight = _make_preflight([
            CheckResult("camera_platform_reachable", Status.WARNING, "unreachable"),
        ])
        r = svc.generate(preflight_report=preflight)
        assert r.preflight_summary == "PASS_WITH_WARNINGS"

    def test_fail_gives_fail(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        preflight = _make_preflight([
            CheckResult("camera_platform_reachable", Status.FAIL, "fail"),
        ])
        r = svc.generate(preflight_report=preflight)
        assert r.preflight_summary == "FAIL"

    def test_pi_subnet_ok_sets_verified(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        preflight = _make_preflight([
            CheckResult("pi_subnet", Status.OK, "ok",
                        evidence={"local_ip": "192.168.30.10"}),
        ])
        r = svc.generate(preflight_report=preflight)
        assert r.pi_subnet_verification == VerificationStatus.VERIFIED
        assert r.pi_ip == "192.168.30.10"

    def test_pi_subnet_warning_sets_warning(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        preflight = _make_preflight([
            CheckResult("pi_subnet", Status.WARNING, "wrong subnet"),
        ])
        r = svc.generate(preflight_report=preflight)
        assert r.pi_subnet_verification == VerificationStatus.WARNING

    def test_camera_ok_sets_verified(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        preflight = _make_preflight([
            CheckResult("camera_platform_reachable", Status.OK, "reachable"),
        ])
        r = svc.generate(preflight_report=preflight)
        assert r.cameras[0].verification_status == VerificationStatus.VERIFIED

    def test_camera_warning_sets_warning(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        preflight = _make_preflight([
            CheckResult("camera_platform_reachable", Status.WARNING, "unreachable"),
        ])
        r = svc.generate(preflight_report=preflight)
        assert r.cameras[0].verification_status == VerificationStatus.WARNING

    def test_atem_ok_sets_verified(self, tmp_path):
        config = _isolated_config()
        config["atem"] = {"ip": "192.168.30.30"}
        config["features"] = {"atem_enabled": True}
        svc = _make_svc(tmp_path, config)
        preflight = _make_preflight([
            CheckResult("atem_reachable", Status.OK, "reachable"),
        ])
        r = svc.generate(preflight_report=preflight)
        assert r.atem_verification == VerificationStatus.VERIFIED

    def test_no_preflight_leaves_not_run(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        assert r.preflight_summary == "NOT_RUN"


# ── Human summary ─────────────────────────────────────────────────────────────

class TestNetworkHandoverReportHumanSummary:

    def test_summary_includes_site_name(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        text = "\n".join(r.human_summary())
        assert "Test Venue" in text

    def test_summary_includes_profile(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        text = "\n".join(r.human_summary())
        assert "isolated_av_vlan" in text

    def test_summary_includes_subnet(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        text = "\n".join(r.human_summary())
        assert "192.168.30.0/24" in text

    def test_flat_network_warning_in_summary(self, tmp_path):
        config = _isolated_config()
        config["network"]["profile"] = "flat_lan"
        svc = _make_svc(tmp_path, config)
        r = svc.generate()
        text = "\n".join(r.human_summary())
        assert "WARNING" in text

    def test_summary_ascii_safe(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate()
        for line in r.human_summary():
            line.encode("ascii")  # must not raise

    def test_notes_in_summary(self, tmp_path):
        svc = _make_svc(tmp_path, _isolated_config())
        r = svc.generate(notes="Test note here")
        text = "\n".join(r.human_summary())
        assert "Test note here" in text


# ── CLI integration ───────────────────────────────────────────────────────────

class TestNetworkReportCLI:

    def _setup(self, tmp_path, monkeypatch):
        config_path = _write_config(tmp_path, _isolated_config())
        from application import network_handover_report as _nhr_mod
        _orig_init = _nhr_mod.NetworkHandoverReportService.__init__

        def _patched_init(self_inner, config_path=None):
            _orig_init(self_inner, config_path=config_path or str(tmp_path / "config.yaml"))

        monkeypatch.setattr(_nhr_mod.NetworkHandoverReportService, "__init__", _patched_init)
        return config_path

    def test_network_report_exits_zero(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        rc = cli_main(["network-report"])
        assert rc == 0

    def test_network_report_json_exits_zero(self, tmp_path, monkeypatch):
        self._setup(tmp_path, monkeypatch)
        rc = cli_main(["network-report", "--json"])
        assert rc == 0

    def test_network_report_json_valid(self, tmp_path, monkeypatch, capsys):
        self._setup(tmp_path, monkeypatch)
        cli_main(["network-report", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)  # must not raise
        assert "network_profile" in data

    def test_network_report_parses(self):
        from runtime.cli import build_parser
        args = build_parser().parse_args(["network-report"])
        assert args.command == "network-report"

    def test_network_report_with_notes_parses(self):
        from runtime.cli import build_parser
        args = build_parser().parse_args(["network-report", "--notes", "hello"])
        assert args.notes == "hello"

    def test_network_report_with_preflight_flag_parses(self):
        from runtime.cli import build_parser
        args = build_parser().parse_args(["network-report", "--with-preflight"])
        assert args.with_preflight is True

