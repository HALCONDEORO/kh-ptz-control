#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tests for application/diagnostics_service.py and `khptz doctor` CLI command.

Hardware-free: all tests use tmp_path; no cameras, no ATEM, no Raspberry Pi.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from application.diagnostics_service import (
    CheckResult,
    DiagnosticsReport,
    DiagnosticsService,
    Status,
)
from application.network_diagnostics import NetworkDiagnosticsService
from runtime.cli import main as cli_main
from application.runtime_state_store import RuntimeStateStore


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_service(
    tmp_path: Path,
    *,
    with_config: bool = True,
    with_sim: bool = False,
    installation_profile: str = "starter_1_camera",
    installation_id: str = "khptz-2026-0001",
) -> DiagnosticsService:
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    (install_dir / "VERSION").write_text("1.2.3", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    if with_config:
        config = {
            "site": {
                "installation_profile": installation_profile,
                "installation_id": installation_id,
            },
            "cameras": [
                {"id": "platform", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"}
            ],
            "network": {
                "profile": "isolated_av_vlan",
            },
        }
        (install_dir / "config.yaml").write_text(
            yaml.dump(config), encoding="utf-8"
        )

    if with_sim:
        (install_dir / "sim_ip_backup.json").write_text("{}", encoding="utf-8")

    # Use a fake network service so tests don't depend on real TCP reachability
    network_svc = NetworkDiagnosticsService(
        probe_fn=lambda host, port: True,
        local_ips_fn=lambda: ["172.16.1.11"],
    )
    return DiagnosticsService(
        install_dir=install_dir,
        data_dir=data_dir,
        config_path=install_dir / "config.yaml",
        network_svc=network_svc,
    )


# ── CheckResult and DiagnosticsReport ────────────────────────────────────────

class TestDiagnosticsReport:

    def test_overall_ok_when_all_ok(self):
        report = DiagnosticsReport()
        report.add(CheckResult("a", Status.OK, "fine"))
        report.add(CheckResult("b", Status.OK, "also fine"))
        assert report.overall == Status.OK

    def test_overall_fail_when_any_fail(self):
        report = DiagnosticsReport()
        report.add(CheckResult("a", Status.OK, "fine"))
        report.add(CheckResult("b", Status.FAIL, "broken"))
        assert report.overall == Status.FAIL

    def test_overall_warning_when_any_warning(self):
        report = DiagnosticsReport()
        report.add(CheckResult("a", Status.OK, "fine"))
        report.add(CheckResult("b", Status.WARNING, "hmm"))
        assert report.overall == Status.WARNING

    def test_fail_overrides_warning(self):
        report = DiagnosticsReport()
        report.add(CheckResult("a", Status.WARNING, "hmm"))
        report.add(CheckResult("b", Status.FAIL, "broken"))
        assert report.overall == Status.FAIL

    def test_exit_code_zero_when_ok(self):
        report = DiagnosticsReport()
        report.add(CheckResult("a", Status.OK, "fine"))
        assert report.exit_code == 0

    def test_exit_code_nonzero_when_fail(self):
        report = DiagnosticsReport()
        report.add(CheckResult("a", Status.FAIL, "broken"))
        assert report.exit_code != 0

    def test_exit_code_nonzero_when_warning(self):
        report = DiagnosticsReport()
        report.add(CheckResult("a", Status.WARNING, "hmm"))
        assert report.exit_code != 0

    def test_to_json_dict_includes_runtime_state_when_provided(self):
        report = DiagnosticsReport()
        report.add(CheckResult("a", Status.OK, "fine"))
        runtime_state = {"session": {"active": False}}

        result = report.to_json_dict(runtime_state=runtime_state)

        assert result["runtime_state"] == runtime_state

    def test_to_json_dict_omits_runtime_state_by_default(self):
        report = DiagnosticsReport()
        report.add(CheckResult("a", Status.OK, "fine"))

        result = report.to_json_dict()

        assert "runtime_state" not in result


# ── Healthy scenario ──────────────────────────────────────────────────────────

class TestHealthyDiagnostics:

    def test_run_returns_report(self, tmp_path):
        svc = _make_service(tmp_path)
        report = svc.run()
        assert isinstance(report, DiagnosticsReport)

    def test_healthy_overall_ok(self, tmp_path, monkeypatch):
        # Pin the interpreter to the supported 3.9.x target so the python_version
        # check does not warn on the (newer) dev/CI interpreter running the suite.
        from application import diagnostics_service as _ds_mod
        monkeypatch.setattr(_ds_mod.sys, "version_info", (3, 9, 2))
        svc = _make_service(tmp_path)
        report = svc.run()
        assert report.overall == Status.OK

    def test_version_check_ok(self, tmp_path):
        svc = _make_service(tmp_path)
        report = svc.run()
        version_check = next(c for c in report.checks if c.name == "version")
        assert version_check.status == Status.OK
        assert "1.2.3" in version_check.message

    def test_python_version_check_ok_on_target(self, tmp_path, monkeypatch):
        from application import diagnostics_service as _ds_mod
        monkeypatch.setattr(_ds_mod.sys, "version_info", (3, 9, 2))
        check = _make_service(tmp_path)._check_python_version()
        assert check.status == Status.OK
        assert "3.9.2" in check.message

    def test_python_version_check_warns_on_310_plus(self, tmp_path, monkeypatch):
        from application import diagnostics_service as _ds_mod
        monkeypatch.setattr(_ds_mod.sys, "version_info", (3, 11, 2))
        check = _make_service(tmp_path)._check_python_version()
        assert check.status == Status.WARNING
        assert "not a validated runtime" in check.message
        assert check.suggested_action

    def test_python_version_check_fails_below_39(self, tmp_path, monkeypatch):
        from application import diagnostics_service as _ds_mod
        monkeypatch.setattr(_ds_mod.sys, "version_info", (3, 8, 10))
        check = _make_service(tmp_path)._check_python_version()
        assert check.status == Status.FAIL
        assert "too old" in check.message

    def test_config_check_ok(self, tmp_path):
        svc = _make_service(tmp_path)
        report = svc.run()
        config_check = next(c for c in report.checks if c.name == "config")
        assert config_check.status == Status.OK

    def test_data_dir_check_ok(self, tmp_path):
        svc = _make_service(tmp_path)
        report = svc.run()
        data_check = next(c for c in report.checks if c.name == "data_dir")
        assert data_check.status == Status.OK

    def test_sim_mode_off_ok(self, tmp_path):
        svc = _make_service(tmp_path)
        report = svc.run()
        sim_check = next(c for c in report.checks if c.name == "simulation")
        assert sim_check.status == Status.OK

    def test_starter_template_has_profile_and_network_fields(self, tmp_path):
        config_path = Path(__file__).parent.parent / "config" / "defaults" / "starter.yaml"
        install_dir = tmp_path / "app"
        data_dir = tmp_path / "data"
        install_dir.mkdir()
        data_dir.mkdir()
        (install_dir / "VERSION").write_text("1.2.3", encoding="utf-8")
        network_svc = NetworkDiagnosticsService(
            probe_fn=lambda host, port: True,
            local_ips_fn=lambda: ["172.16.1.11"],
        )
        svc = DiagnosticsService(
            install_dir=install_dir,
            data_dir=data_dir,
            config_path=config_path,
            network_svc=network_svc,
        )

        report = svc.run()
        messages = "\n".join(c.message for c in report.checks)

        assert "Installation profile not set" not in messages
        assert "Network profile not configured" not in messages

    def test_runtime_state_snapshot_redacts_chairman_name(self, tmp_path):
        svc = _make_service(tmp_path)
        store = RuntimeStateStore()
        store.update_session(active=True, session_id="s-1", chairman_name="Secret Name")
        svc.set_runtime_state_store(store)

        snapshot = svc.runtime_state_snapshot()

        assert snapshot is not None
        assert snapshot["session"]["chairman_name"] == "[REDACTED]"
        assert "Secret Name" not in str(snapshot)

    def test_runtime_state_snapshot_missing_store_returns_none(self, tmp_path):
        svc = _make_service(tmp_path)

        assert svc.runtime_state_snapshot() is None

    def test_runtime_state_snapshot_store_error_returns_none(self, tmp_path):
        svc = _make_service(tmp_path)

        class BrokenStore:
            def snapshot(self):
                raise RuntimeError("unavailable")

        svc.set_runtime_state_store(BrokenStore())

        assert svc.runtime_state_snapshot() is None


# ── Failing scenarios ─────────────────────────────────────────────────────────

class TestFailingDiagnostics:

    def test_missing_version_file_fails(self, tmp_path):
        svc = _make_service(tmp_path)
        (svc._version_file).unlink()
        report = svc.run()
        version_check = next(c for c in report.checks if c.name == "version")
        assert version_check.status == Status.FAIL

    def test_missing_config_warns(self, tmp_path):
        svc = _make_service(tmp_path, with_config=False)
        report = svc.run()
        config_check = next(c for c in report.checks if c.name == "config")
        assert config_check.status == Status.WARNING

    def test_invalid_config_fails(self, tmp_path):
        svc = _make_service(tmp_path)
        svc._config_path.write_text("cameras: [{bad yaml", encoding="utf-8")
        report = svc.run()
        config_check = next(c for c in report.checks if c.name == "config")
        assert config_check.status == Status.FAIL

    def test_sim_mode_active_warns(self, tmp_path):
        svc = _make_service(tmp_path, with_sim=True)
        report = svc.run()
        sim_check = next(c for c in report.checks if c.name == "simulation")
        assert sim_check.status == Status.WARNING

    def test_missing_data_dir_creates_it(self, tmp_path):
        svc = _make_service(tmp_path)
        import shutil
        shutil.rmtree(svc._data_dir)
        report = svc.run()
        data_check = next(c for c in report.checks if c.name == "data_dir")
        assert data_check.status == Status.OK
        assert svc._data_dir.exists()


# ── CLI doctor command ────────────────────────────────────────────────────────

class TestDoctorCLI:

    def test_doctor_exits_zero_on_healthy(self, tmp_path, monkeypatch):
        install_dir = tmp_path / "app"
        install_dir.mkdir()
        (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config = {
            "site": {
                "installation_profile": "starter_1_camera",
                "installation_id": "khptz-2026-0001",
            },
            "cameras": [
                {"id": "platform", "role": "platform", "ip": "1.2.3.4", "visca_id": "81"}
            ],
            "network": {
                "profile": "isolated_av_vlan",
            },
        }
        config_path = install_dir / "config.yaml"
        config_path.write_text(yaml.dump(config), encoding="utf-8")

        from application import diagnostics_service as _ds_mod
        from application.network_diagnostics import NetworkDiagnosticsService as _NDS

        _fake_net_svc = _NDS(
            probe_fn=lambda host, port: True,
            local_ips_fn=lambda: ["1.2.3.4"],
        )

        class _PatchedService(_ds_mod.DiagnosticsService):
            def __init__(self, **kwargs):
                super().__init__(
                    install_dir=install_dir,
                    data_dir=data_dir,
                    config_path=config_path,
                    network_svc=_fake_net_svc,
                )

        monkeypatch.setattr(_ds_mod, "DiagnosticsService", _PatchedService)
        # Treat the running interpreter as the supported 3.9.x target so the
        # python_version check does not turn a healthy doctor run into a warning.
        monkeypatch.setattr(_ds_mod.sys, "version_info", (3, 9, 2))
        rc = cli_main(["doctor"])
        assert rc == 0

    def test_doctor_exits_nonzero_on_failing_check(self, monkeypatch):
        """CLI must return the FAIL exit code (30) when any check has Status.FAIL.

        Exit codes distinguish the four deployment outcomes since #887; a FAIL
        check means the appliance cannot operate.
        """
        from application import diagnostics_service as _ds_mod

        class _FailingService(_ds_mod.DiagnosticsService):
            def __init__(self, **kwargs):
                pass  # skip all real init

            def run(self):
                report = _ds_mod.DiagnosticsReport()
                report.add(_ds_mod.CheckResult("version", _ds_mod.Status.OK, "ok"))
                report.add(_ds_mod.CheckResult("config", _ds_mod.Status.FAIL, "config.yaml invalid"))
                return report

        monkeypatch.setattr(_ds_mod, "DiagnosticsService", _FailingService)
        rc = cli_main(["doctor"])
        assert rc == 30
        assert rc != 0

    def test_doctor_exits_nonzero_on_warning_check(self, monkeypatch):
        """An unclassified WARNING is reported as CONFIG_REQUIRED (exit 20).

        Checks default to the CONFIGURATION category, so a warning that has not
        been explicitly classified surfaces as "needs attention" rather than
        being silently downgraded to advice (#887).
        """
        from application import diagnostics_service as _ds_mod

        class _WarnService(_ds_mod.DiagnosticsService):
            def __init__(self, **kwargs):
                pass  # skip all real init

            def run(self):
                report = _ds_mod.DiagnosticsReport()
                report.add(_ds_mod.CheckResult("version", _ds_mod.Status.OK, "ok"))
                report.add(_ds_mod.CheckResult("config", _ds_mod.Status.WARNING, "config.yaml not found"))
                return report

        monkeypatch.setattr(_ds_mod, "DiagnosticsService", _WarnService)
        rc = cli_main(["doctor"])
        assert rc == 20
        assert rc != 0

    def test_doctor_parses(self):
        from runtime.cli import build_parser
        args = build_parser().parse_args(["doctor"])
        assert args.command == "doctor"


# ── Installation ID checks ────────────────────────────────────────────────────

class TestInstallationIdCheck:

    def test_installation_id_present_ok(self, tmp_path):
        svc = _make_service(tmp_path, installation_id="khptz-2026-0042")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_id")
        assert check.status == Status.OK
        assert "khptz-2026-0042" in check.message

    def test_installation_id_missing_warns(self, tmp_path):
        svc = _make_service(tmp_path, installation_id="")
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_id")
        assert check.status == Status.WARNING

    def test_installation_id_missing_does_not_fail(self, tmp_path):
        svc = _make_service(tmp_path, installation_id="")
        report = svc.run()
        assert report.overall != Status.FAIL

    def test_no_config_installation_id_warns(self, tmp_path):
        svc = _make_service(tmp_path, with_config=False)
        report = svc.run()
        check = next(c for c in report.checks if c.name == "installation_id")
        assert check.status == Status.WARNING

