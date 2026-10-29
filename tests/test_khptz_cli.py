#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tests for runtime/cli.py — khptz CLI command routing.

Hardware-free: no cameras, no ATEM, no Raspberry Pi.
"""

from __future__ import annotations

import json
import os
import zipfile

import pytest

from runtime.cli import build_parser, main, APP_NAME


class TestParser:

    def test_version_subcommand_parses(self):
        parser = build_parser()
        args = parser.parse_args(["version"])
        assert args.command == "version"

    def test_status_subcommand_parses(self):
        parser = build_parser()
        args = parser.parse_args(["status"])
        assert args.command == "status"

    def test_no_subcommand_raises(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_unknown_subcommand_raises(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["unknown-xyz"])


class TestVersionCommand:

    def test_returns_zero(self, capsys):
        rc = main(["version"])
        assert rc == 0

    def test_prints_app_name(self, capsys):
        main(["version"])
        out = capsys.readouterr().out
        assert APP_NAME in out

    def test_prints_version_number(self, capsys):
        main(["version"])
        out = capsys.readouterr().out
        # Version should look like digits-and-dots, e.g. 3.7.0
        parts = out.strip().split()
        version = parts[-1]
        assert any(c.isdigit() for c in version)

    def test_profile_flag_is_applied_to_version(self, capsys, monkeypatch):
        monkeypatch.delenv("KHPTZ_PROFILE", raising=False)
        rc = main(["--profile", "demo", "version"])
        out = capsys.readouterr().out

        assert rc == 0
        assert "[DEMO]" in out

    def test_profile_flag_does_not_leak_between_calls(self, capsys, monkeypatch):
        monkeypatch.delenv("KHPTZ_PROFILE", raising=False)
        main(["--profile", "demo", "version"])
        capsys.readouterr()

        main(["version"])
        out = capsys.readouterr().out

        assert "[DEMO]" not in out


class TestStatusCommand:

    def test_returns_int(self, capsys):
        rc = main(["status"])
        assert isinstance(rc, int)

    def test_prints_app_name(self, capsys):
        main(["status"])
        out = capsys.readouterr().out
        assert APP_NAME in out

    def test_prints_version_check(self, capsys):
        main(["status"])
        out = capsys.readouterr().out
        assert "version" in out.lower()


class TestDoctorCommand:
    def test_json_output_is_valid(self, capsys):
        rc = main(["doctor", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)

        assert isinstance(rc, int)
        assert "overall" in data
        assert "exit_code" in data
        assert "checks" in data

    def test_json_checks_have_required_fields(self, capsys):
        main(["doctor", "--json"])
        data = json.loads(capsys.readouterr().out)

        assert data["checks"]
        for check in data["checks"]:
            assert "key" in check
            assert "severity" in check
            assert "message" in check

    def test_json_exit_code_matches_return_code(self, capsys):
        rc = main(["doctor", "--json"])
        data = json.loads(capsys.readouterr().out)

        assert data["exit_code"] == rc

    def test_json_profile_demo_does_not_leak_env(self, capsys, monkeypatch):
        monkeypatch.delenv("KHPTZ_PROFILE", raising=False)

        main(["--profile", "demo", "doctor", "--json"])
        capsys.readouterr()

        assert "KHPTZ_PROFILE" not in os.environ


class TestVersionFile:

    def test_version_not_unknown(self, capsys):
        main(["version"])
        out = capsys.readouterr().out
        assert "unknown" not in out

    def test_version_is_semver_like(self, capsys):
        main(["version"])
        out = capsys.readouterr().out
        # Version line may include a git hash suffix: "App Name X.Y.Z (abc1234)"
        # Find the first token that looks like a semver (digits and dots).
        tokens = out.strip().split()
        semver_tokens = [t for t in tokens if t.count(".") >= 1 and t[0].isdigit()]
        assert semver_tokens, f"No semver-like token found in version output: {out!r}"


class TestVersionJsonFlag:

    def test_json_flag_parses(self):
        parser = build_parser()
        args = parser.parse_args(["version", "--json"])
        assert args.json is True

    def test_json_flag_default_is_false(self):
        parser = build_parser()
        args = parser.parse_args(["version"])
        assert args.json is False

    def test_json_output_is_valid_json(self, capsys):
        rc = main(["version", "--json"])
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, dict)

    def test_json_output_has_version_key(self, capsys):
        main(["version", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "version" in data

    def test_json_version_is_semver_like(self, capsys):
        main(["version", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        version = data["version"]
        assert any(c.isdigit() for c in version)
        assert version != "unknown"

    def test_json_output_has_build_key(self, capsys):
        main(["version", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "build" in data

    def test_json_output_has_python_key(self, capsys):
        main(["version", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "python" in data
        assert data["python"][0].isdigit()

    def test_json_output_has_platform_key(self, capsys):
        main(["version", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "platform" in data
        assert isinstance(data["platform"], str)

    def test_json_does_not_include_app_name_text(self, capsys):
        main(["version", "--json"])
        out = capsys.readouterr().out
        # JSON output should not contain the human-readable version line
        data = json.loads(out)
        assert APP_NAME not in data["version"]

    def test_human_output_unchanged_without_flag(self, capsys):
        main(["version"])
        out = capsys.readouterr().out
        assert APP_NAME in out


class TestDemoProfileIsolation:
    """Regression tests: --profile demo must not touch production paths.

    Covers the bugs from issue #659:
    - demo reset was blocking itself because DemoResetService._production_paths()
      treated KHPTZ_DATA_DIR (the demo dir) as production after DemoGuard.apply().
    - fingerprint/backup/supportability were not applying demo isolation consistently.
    """

    def _clear_env(self, monkeypatch):
        monkeypatch.delenv("KHPTZ_PROFILE", raising=False)
        monkeypatch.delenv("KHPTZ_DATA_DIR", raising=False)
        monkeypatch.delenv("KHPTZ_DATA_DIR", raising=False)

    # ── Smoke tests: the three manual demo CLI checks from CLAUDE.md ─────────

    def test_demo_status_exits_without_exception(self, capsys, monkeypatch, tmp_path):
        """python3 -m runtime.cli --profile demo status must not raise."""
        self._clear_env(monkeypatch)
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(tmp_path / "demo"))
        rc = main(["--profile", "demo", "status"])
        assert isinstance(rc, int)

    def test_demo_doctor_exits_without_exception(self, capsys, monkeypatch, tmp_path):
        """python3 -m runtime.cli --profile demo doctor must not raise."""
        self._clear_env(monkeypatch)
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(tmp_path / "demo"))
        rc = main(["--profile", "demo", "doctor"])
        assert isinstance(rc, int)

    def test_demo_demo_reset_exits_without_exception(self, capsys, monkeypatch, tmp_path):
        """python3 -m runtime.cli --profile demo demo reset must not raise."""
        self._clear_env(monkeypatch)
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(tmp_path / "demo"))
        rc = main(["--profile", "demo", "demo", "reset"])
        assert isinstance(rc, int)

    def test_demo_status_prints_mode_marker(self, capsys, monkeypatch, tmp_path):
        """--profile demo status output must label the DEMO mode."""
        self._clear_env(monkeypatch)
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(tmp_path / "demo"))
        main(["--profile", "demo", "status"])
        out = capsys.readouterr().out
        assert "DEMO" in out

    def test_demo_doctor_prints_mode_marker(self, capsys, monkeypatch, tmp_path):
        """--profile demo doctor output must label the DEMO mode."""
        self._clear_env(monkeypatch)
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(tmp_path / "demo"))
        main(["--profile", "demo", "doctor"])
        out = capsys.readouterr().out
        assert "DEMO" in out

    # ── Existing profile-isolation regression tests ───────────────────────────

    def test_demo_reset_exits_zero(self, capsys, monkeypatch, tmp_path):
        self._clear_env(monkeypatch)
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(tmp_path / "demo"))
        rc = main(["--profile", "demo", "demo", "reset"])
        assert rc == 0

    def test_demo_reset_does_not_block_on_demo_dir(self, capsys, monkeypatch, tmp_path):
        """DemoResetService must not refuse to reset the active demo directory."""
        self._clear_env(monkeypatch)
        demo_dir = tmp_path / "demo-data"
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(demo_dir))
        rc = main(["--profile", "demo", "demo", "reset"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Error" not in out

    def test_demo_fingerprint_reports_demo_profile(self, capsys, monkeypatch, tmp_path):
        self._clear_env(monkeypatch)
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(tmp_path / "demo"))
        rc = main(["--profile", "demo", "fingerprint", "--json"])
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["profile"] == "demo"

    def test_demo_backup_exits_zero(self, capsys, monkeypatch, tmp_path):
        self._clear_env(monkeypatch)
        demo_dir = tmp_path / "demo-data"
        demo_dir.mkdir()
        (demo_dir / "seat_names.json").write_text('{"seats": []}', encoding="utf-8")
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(demo_dir))
        dest = tmp_path / "backup.zip"
        rc = main(["--profile", "demo", "backup", "--dest", str(dest)])
        assert rc == 0

    def test_demo_backup_includes_demo_data(self, capsys, monkeypatch, tmp_path):
        """Backup with --profile demo must read from the demo data directory."""
        self._clear_env(monkeypatch)
        demo_dir = tmp_path / "demo-data"
        demo_dir.mkdir()
        (demo_dir / "seat_names.json").write_text('{"seats": ["A", "B"]}', encoding="utf-8")
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(demo_dir))
        dest = tmp_path / "backup.zip"
        main(["--profile", "demo", "backup", "--dest", str(dest)])
        capsys.readouterr()
        with zipfile.ZipFile(dest) as zf:
            assert "seat_names.json" in zf.namelist()


class TestVerifyInstallCommand:
    """Tests for 'khptz verify-install' post-install smoke command (#672)."""

    def test_returns_int(self, capsys):
        rc = main(["verify-install"])
        assert isinstance(rc, int)

    def test_subcommand_parses(self):
        parser = build_parser()
        args = parser.parse_args(["verify-install"])
        assert args.command == "verify-install"

    def test_json_flag_parses(self):
        parser = build_parser()
        args = parser.parse_args(["verify-install", "--json"])
        assert args.json is True

    def test_json_output_is_valid(self, capsys):
        main(["verify-install", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "overall" in data
        assert "checks" in data
        assert isinstance(data["checks"], list)

    def test_json_overall_is_pass_warn_or_fail(self, capsys):
        main(["verify-install", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["overall"] in ("PASS", "WARN", "FAIL")

    def test_json_checks_have_required_fields(self, capsys):
        main(["verify-install", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        for check in data["checks"]:
            assert "name" in check
            assert "status" in check
            assert "message" in check
            assert check["status"] in ("PASS", "WARN", "FAIL")

    def test_human_output_contains_overall(self, capsys):
        main(["verify-install"])
        out = capsys.readouterr().out
        assert "Overall:" in out

    def test_app_version_check_present(self, capsys):
        main(["verify-install", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        names = [c["name"] for c in data["checks"]]
        assert "app_version" in names

    def test_pyqt5_check_present(self, capsys):
        main(["verify-install", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        names = [c["name"] for c in data["checks"]]
        assert "pyqt5" in names

    def test_app_version_passes(self, capsys):
        """App version must be readable in a source checkout."""
        main(["verify-install", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        version_check = next(c for c in data["checks"] if c["name"] == "app_version")
        assert version_check["status"] == "PASS"
