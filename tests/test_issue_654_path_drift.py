#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Regression tests for issue #654 — runtime path/config drift.

Covers four bugs:
  1. DiagnosticsService ignores HALLPTZ_CONFIG_DIR / /etc/hallptz/config.yaml.
  2. data_paths.CONFIG_DIR ignores HALLPTZ_DATA_DIR.
  3. hallptz support-bundle omits incident snapshots (incidents_dir never wired).
  4. installation_id from config.yaml not read by build_info / FingerprintService.

All tests are hardware-free and use tmp_path.
"""

from __future__ import annotations

import importlib
import json
import zipfile
from pathlib import Path

import yaml


# ── Bug 1: DiagnosticsService respects HALLPTZ_CONFIG_DIR ───────────────────────

class TestDiagnosticsServiceConfigPath:
    """DiagnosticsService must use RuntimePathResolver().config_dir by default."""

    def _make_version_file(self, install_dir: Path) -> Path:
        (install_dir / "VERSION").write_text("1.0.0-test", encoding="utf-8")
        return install_dir

    def test_default_config_path_comes_from_path_resolver(self, tmp_path, monkeypatch):
        """
        When no config_path is given, DiagnosticsService must resolve it via
        RuntimePathResolver().config_dir, not from install_dir.
        """
        config_dir = tmp_path / "etc_hallptz"
        config_dir.mkdir()
        monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(config_dir))

        install_dir = tmp_path / "app"
        install_dir.mkdir()
        self._make_version_file(install_dir)

        from application.diagnostics_service import DiagnosticsService
        svc = DiagnosticsService(install_dir=install_dir, data_dir=tmp_path / "data")

        assert svc._config_path == config_dir / "config.yaml"

    def test_check_config_finds_config_in_hallptz_config_dir(self, tmp_path, monkeypatch):
        """
        `hallptz doctor` must report config OK when config.yaml is in HALLPTZ_CONFIG_DIR,
        even if there is no config.yaml under install_dir.
        """
        config_dir = tmp_path / "etc_hallptz"
        config_dir.mkdir()
        monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(config_dir))

        install_dir = tmp_path / "app"
        install_dir.mkdir()
        self._make_version_file(install_dir)

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        cfg = {
            "site": {
                "installation_profile": "starter_1_camera",
                "installation_id": "hallptz-2026-regr-001",
            },
            "cameras": [
                {"id": "platform", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"},
            ],
            "network": {"profile": "isolated_av_vlan"},
        }
        (config_dir / "config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")

        from application.diagnostics_service import DiagnosticsService, Status
        from application.network_diagnostics import NetworkDiagnosticsService
        net = NetworkDiagnosticsService(
            probe_fn=lambda host, port: True,
            local_ips_fn=lambda: ["172.16.1.11"],
        )
        svc = DiagnosticsService(install_dir=install_dir, data_dir=data_dir, network_svc=net)
        report = svc.run()

        config_check = next(c for c in report.checks if c.name == "config")
        assert config_check.status == Status.OK, (
            f"Expected config OK from HALLPTZ_CONFIG_DIR, got: {config_check.message}"
        )

    def test_explicit_config_path_overrides_resolver(self, tmp_path, monkeypatch):
        """
        An explicitly provided config_path must always win over the env-resolved path.
        """
        config_dir = tmp_path / "etc_hallptz"
        config_dir.mkdir()
        monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(config_dir))

        explicit_path = tmp_path / "explicit_config.yaml"
        explicit_path.write_text("# stub", encoding="utf-8")

        install_dir = tmp_path / "app"
        install_dir.mkdir()

        from application.diagnostics_service import DiagnosticsService
        svc = DiagnosticsService(install_dir=install_dir, config_path=explicit_path)

        assert svc._config_path == explicit_path


# ── Bug 2: data_paths.CONFIG_DIR respects HALLPTZ_DATA_DIR ──────────────────────

class TestDataPathsHallptzDataDir:
    """data_paths.CONFIG_DIR must honour HALLPTZ_DATA_DIR."""

    def _reload_data_paths(self) -> object:
        """Reload data_paths so module-level CONFIG_DIR re-evaluates env vars."""
        import data_paths
        importlib.reload(data_paths)
        return data_paths

    def test_config_dir_uses_hallptz_data_dir(self, tmp_path, monkeypatch):
        """HALLPTZ_DATA_DIR must set data_paths.CONFIG_DIR."""
        target = tmp_path / "hallptz_data"
        target.mkdir()
        monkeypatch.setenv("HALLPTZ_DATA_DIR", str(target))

        dp = self._reload_data_paths()

        assert dp.CONFIG_DIR == target

    def test_config_dir_default_without_env(self, tmp_path, monkeypatch):
        """Without HALLPTZ_DATA_DIR, CONFIG_DIR falls back to its default."""
        monkeypatch.delenv("HALLPTZ_DATA_DIR", raising=False)

        dp = self._reload_data_paths()

        assert dp.CONFIG_DIR != tmp_path  # default, no el override

class TestSupportBundleIncidentsWiring:
    """
    hallptz support-bundle must pass incidents_dir from RuntimePathResolver
    so incident snapshots are included in the ZIP.
    """

    def test_incidents_included_when_dir_exists(self, tmp_path, monkeypatch):
        """
        SupportBundleService with an incidents_dir that exists must include
        incident files in the ZIP.
        """
        from application.support_bundle_service import SupportBundleService

        incidents_dir = tmp_path / "incidents"
        incidents_dir.mkdir()
        (incidents_dir / "incident-20260101-120000-abcd0001.json").write_text(
            json.dumps({
                "schema_version": 1,
                "reason": "regression_test",
                "last_events": [],
                "extra": {},
            }),
            encoding="utf-8",
        )

        svc = SupportBundleService(
            output_dir=tmp_path / "bundles",
            incidents_dir=incidents_dir,
            app_version="1.0.0",
            installation_id="test-654",
            installation_profile="starter_1_camera",
        )
        path = svc.create()
        assert path is not None

        with zipfile.ZipFile(path) as zf:
            incident_files = [n for n in zf.namelist() if n.startswith("blackbox/incidents/")]
        assert len(incident_files) == 1, "Incident snapshot must be in the support bundle"

    def test_incidents_warning_when_incidents_dir_is_none(self, tmp_path):
        """
        When incidents_dir is None the bundle still creates, but manifest warns.
        """
        from application.support_bundle_service import SupportBundleService

        svc = SupportBundleService(
            output_dir=tmp_path / "bundles",
            incidents_dir=None,
            app_version="1.0.0",
            installation_id="test-654",
        )
        path = svc.create()
        assert path is not None

        with zipfile.ZipFile(path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        assert any("incidents" in w for w in manifest["redaction_warnings"]), (
            "Manifest must warn when incidents_dir is None"
        )

    def test_cli_cmd_passes_incidents_dir(self, tmp_path, monkeypatch):
        """
        cmd_support_bundle must wire incidents_dir from RuntimePathResolver so
        existing incident files appear in the bundle.
        """

        # Set up isolated runtime dirs
        config_dir = tmp_path / "etc_hallptz"
        log_dir    = tmp_path / "log_hallptz"
        backup_dir = tmp_path / "backups_hallptz"
        data_dir   = tmp_path / "data_hallptz"

        for d in (config_dir, log_dir, backup_dir, data_dir):
            d.mkdir(parents=True)

        # Write a dummy config so DiagnosticsService doesn't warn
        cfg = {
            "site": {
                "installation_profile": "starter_1_camera",
                "installation_id": "hallptz-2026-cli-654",
            },
            "cameras": [
                {"id": "platform", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"},
            ],
            "network": {"profile": "isolated_av_vlan"},
        }
        (config_dir / "config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")

        # Write an incident file under the log/incidents dir
        incidents_dir = log_dir / "incidents"
        incidents_dir.mkdir()
        (incidents_dir / "incident-20260120-120000-abcd0002.json").write_text(
            json.dumps({"schema_version": 1, "reason": "cli_test", "last_events": [], "extra": {}}),
            encoding="utf-8",
        )

        monkeypatch.setenv("HALLPTZ_CONFIG_DIR",  str(config_dir))
        monkeypatch.setenv("HALLPTZ_LOG_DIR",     str(log_dir))
        monkeypatch.setenv("HALLPTZ_BACKUP_DIR",  str(backup_dir))
        monkeypatch.setenv("HALLPTZ_DATA_DIR",    str(data_dir))

        # Install a dummy VERSION file visible from path_resolver's source_root
        source_root = Path(__file__).resolve().parent.parent
        version_file = source_root / "VERSION"
        assert version_file.exists(), "VERSION file must exist in project root"

        from runtime.cli import cmd_support_bundle
        import types
        result = cmd_support_bundle(types.SimpleNamespace())
        assert result == 0

        support_dir = backup_dir / "support"
        bundles = list(support_dir.glob("support-*.zip"))
        assert bundles, "CLI must create a bundle ZIP"

        with zipfile.ZipFile(bundles[0]) as zf:
            incident_files = [n for n in zf.namelist() if n.startswith("blackbox/incidents/")]
        assert len(incident_files) >= 1, (
            "CLI bundle must include incident files when incidents_dir is wired"
        )


# ── Bug 4: build_info reads installation_id from config.yaml ─────────────────

class TestBuildInfoInstallationIdFromConfig:
    """
    When no installation_id.txt exists, build_info must read
    site.installation_id from the canonical config.yaml.
    """

    def test_reads_id_from_config_yaml_when_no_txt_file(self, tmp_path, monkeypatch):
        """_read_installation_id falls back to config.yaml site.installation_id."""
        config_dir = tmp_path / "etc_hallptz"
        config_dir.mkdir()
        monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(config_dir))
        # No installation_id.txt anywhere

        cfg = {
            "site": {"installation_id": "hallptz-2026-from-yaml"},
            "cameras": [],
        }
        (config_dir / "config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")

        # data_dir has no installation_id.txt
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        from runtime.build_info import _read_installation_id
        iid = _read_installation_id(data_dir)
        assert iid == "hallptz-2026-from-yaml", (
            f"Expected ID from config.yaml, got: {iid!r}"
        )

    def test_txt_file_takes_priority_over_config_yaml(self, tmp_path, monkeypatch):
        """installation_id.txt in data_dir wins over config.yaml."""
        config_dir = tmp_path / "etc_hallptz"
        config_dir.mkdir()
        monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(config_dir))

        cfg = {"site": {"installation_id": "from-yaml-should-not-win"}, "cameras": []}
        (config_dir / "config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "installation_id.txt").write_text("from-txt-wins", encoding="utf-8")

        from runtime.build_info import _read_installation_id
        iid = _read_installation_id(data_dir)
        assert iid == "from-txt-wins"

    def test_returns_unknown_when_neither_source_exists(self, tmp_path, monkeypatch):
        """Returns 'unknown' when there is no txt file and no config.yaml."""
        config_dir = tmp_path / "empty_etc"
        config_dir.mkdir()
        monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(config_dir))
        monkeypatch.delenv("HALLPTZ_DATA_DIR", raising=False)
        monkeypatch.delenv("HALLPTZ_DATA_DIR", raising=False)

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        from runtime.build_info import _read_installation_id
        iid = _read_installation_id(data_dir)
        assert iid == "unknown"

    def test_fingerprint_service_uses_config_yaml_id(self, tmp_path, monkeypatch):
        """
        FingerprintService.generate() must return the installation_id from
        config.yaml when no installation_id.txt file exists.
        """
        config_dir = tmp_path / "etc_hallptz"
        config_dir.mkdir()
        monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(config_dir))
        monkeypatch.setenv("HALLPTZ_DATA_DIR",   str(tmp_path / "data"))
        monkeypatch.delenv("HALLPTZ_DATA_DIR", raising=False)
        (tmp_path / "data").mkdir()

        cfg = {
            "site": {"installation_id": "hallptz-2026-fingerprint-test"},
            "cameras": [],
        }
        (config_dir / "config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")

        from runtime.path_resolver import RuntimePathResolver
        from application.fingerprint_service import FingerprintService
        fp = FingerprintService(paths=RuntimePathResolver()).generate()

        assert fp.installation_id == "hallptz-2026-fingerprint-test", (
            f"FingerprintService must read installation_id from config.yaml, got: {fp.installation_id!r}"
        )

