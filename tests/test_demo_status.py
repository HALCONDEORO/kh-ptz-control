# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for demo isolation checks in DiagnosticsService (#302)."""
from __future__ import annotations

from pathlib import Path

import yaml

from application.diagnostics_service import DiagnosticsService, Status
from domain.runtime_mode import RuntimeMode


# ── Helpers ───────────────────────────────────────────────────────────────────

def _svc(
    tmp_path: Path,
    mode: RuntimeMode = RuntimeMode.DEMO,
    with_config: bool = False,
) -> DiagnosticsService:
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    if with_config:
        config = {
            "site": {"installation_profile": "demo", "installation_id": "demo-001"},
            "cameras": [{"id": "platform", "role": "platform", "ip": "127.0.0.1", "visca_id": "81"}],
        }
        (install_dir / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")
    return DiagnosticsService(
        install_dir=install_dir,
        data_dir=data_dir,
        config_path=install_dir / "config.yaml",
        mode=mode,
    )


def _check(report, name):
    return next((c for c in report.checks if c.name == name), None)


# ── Demo isolation checks present ─────────────────────────────────────────────

class TestDemoIsolationChecksPresent:
    def test_demo_checks_appear_in_demo_mode(self, tmp_path):
        report = _svc(tmp_path, mode=RuntimeMode.DEMO).run()
        names = [c.name for c in report.checks]
        assert "demo_camera_adapter" in names
        assert "demo_atem_adapter" in names
        assert "demo_data_path" in names
        assert "demo_production_protected" in names
        assert "demo_atem_automation" in names

    def test_demo_checks_appear_in_simulation_mode(self, tmp_path):
        report = _svc(tmp_path, mode=RuntimeMode.SIMULATION).run()
        names = [c.name for c in report.checks]
        assert "demo_camera_adapter" in names
        assert "demo_atem_adapter" in names

    def test_demo_checks_absent_in_production_mode(self, tmp_path):
        report = _svc(tmp_path, mode=RuntimeMode.PRODUCTION).run()
        names = [c.name for c in report.checks]
        assert "demo_camera_adapter" not in names
        assert "demo_atem_adapter" not in names
        assert "demo_data_path" not in names


# ── Adapter type checks ────────────────────────────────────────────────────────

class TestDemoAdapterChecks:
    def test_camera_adapter_shows_fake(self, tmp_path):
        report = _svc(tmp_path).run()
        r = _check(report, "demo_camera_adapter")
        assert r is not None
        assert r.status == Status.OK
        assert "FakeCamera" in r.message

    def test_atem_adapter_shows_fake(self, tmp_path):
        report = _svc(tmp_path).run()
        r = _check(report, "demo_atem_adapter")
        assert r is not None
        assert r.status == Status.OK
        assert "FakeATEM" in r.message

    def test_camera_adapter_no_real_hardware(self, tmp_path):
        report = _svc(tmp_path).run()
        r = _check(report, "demo_camera_adapter")
        assert "no real hardware" in r.message.lower()

    def test_atem_adapter_no_real_atem(self, tmp_path):
        report = _svc(tmp_path).run()
        r = _check(report, "demo_atem_adapter")
        assert "no real atem" in r.message.lower()


# ── Runtime data path check ───────────────────────────────────────────────────

class TestDemoDataPathCheck:
    def test_data_path_shows_current_dir(self, tmp_path):
        svc = _svc(tmp_path)
        report = svc.run()
        r = _check(report, "demo_data_path")
        assert r is not None
        assert r.status == Status.OK
        assert str(tmp_path / "data") in r.message

    def test_data_path_message_contains_demo_marker(self, tmp_path):
        report = _svc(tmp_path).run()
        r = _check(report, "demo_data_path")
        assert "[DEMO]" in r.message

    def test_data_path_says_isolated(self, tmp_path):
        report = _svc(tmp_path).run()
        r = _check(report, "demo_data_path")
        assert "isolated" in r.message.lower()


# ── Production protection check ───────────────────────────────────────────────

class TestDemoProductionProtectionCheck:
    def test_production_protected_ok_for_safe_path(self, tmp_path):
        report = _svc(tmp_path).run()
        r = _check(report, "demo_production_protected")
        assert r is not None
        assert r.status == Status.OK

    def test_production_protected_message_says_yes(self, tmp_path):
        report = _svc(tmp_path).run()
        r = _check(report, "demo_production_protected")
        assert "yes" in r.message.lower()

    def test_production_protected_fail_when_using_production_dir(self, tmp_path):
        from application.demo_guard import _PRODUCTION_DATA_DIR
        install_dir = tmp_path / "app"
        install_dir.mkdir()
        (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
        svc = DiagnosticsService(
            install_dir=install_dir,
            data_dir=_PRODUCTION_DATA_DIR,
            config_path=install_dir / "config.yaml",
            mode=RuntimeMode.DEMO,
        )
        report = svc.run()
        r = _check(report, "demo_production_protected")
        assert r.status == Status.FAIL
        assert "not protected" in r.message.lower()


# ── ATEM automation mode check ────────────────────────────────────────────────

class TestDemoATEMAutomationCheck:
    def test_atem_automation_disarmed_in_demo(self, tmp_path):
        report = _svc(tmp_path).run()
        r = _check(report, "demo_atem_automation")
        assert r is not None
        assert r.status == Status.OK
        assert "disarmed" in r.message.lower()

    def test_atem_automation_has_demo_marker(self, tmp_path):
        report = _svc(tmp_path).run()
        r = _check(report, "demo_atem_automation")
        assert "[DEMO]" in r.message


# ── Check ordering ────────────────────────────────────────────────────────────

class TestDemoCheckOrdering:
    def test_demo_checks_appear_early_after_version(self, tmp_path):
        report = _svc(tmp_path).run()
        names = [c.name for c in report.checks]
        version_idx = names.index("version")
        python_idx = names.index("python_version")
        camera_idx = names.index("demo_camera_adapter")
        # Order: version -> python_version -> demo isolation checks (still early).
        assert python_idx == version_idx + 1
        assert camera_idx == python_idx + 1

    def test_no_secrets_in_any_message(self, tmp_path):
        report = _svc(tmp_path).run()
        for c in report.checks:
            msg = c.message.lower()
            assert "password" not in msg
            assert "api_key" not in msg
            assert "bearer" not in msg
