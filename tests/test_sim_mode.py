#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tests de sim_mode aislando todos los archivos en un directorio temporal local.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import json

import pytest

import adapters.sim_mode as sim_mode


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def isolated_sim_mode(monkeypatch):
    root = ROOT / ".test_tmp" / f"sim_mode_{uuid.uuid4().hex}"
    root.mkdir(parents=True)
    monkeypatch.setattr(sim_mode, "BACKUP", root / "sim_ip_backup.json")

    def read_from_tmp(path: str) -> str:
        p = root / path
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""

    def write_to_tmp(path: str, value: str) -> None:
        (root / path).write_text(value, encoding="utf-8")

    monkeypatch.setattr(sim_mode, "_read", read_from_tmp)
    monkeypatch.setattr(sim_mode, "_write", write_to_tmp)
    try:
        yield root
    finally:
        for child in root.iterdir():
            child.unlink()
        root.rmdir()
        parent = root.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()


class TestSimMode:

    def test_activate_saves_original_values_and_writes_simulated_ips(self, isolated_sim_mode):
        (isolated_sim_mode / "PTZ1IP.txt").write_text("172.16.1.11\n", encoding="utf-8")
        (isolated_sim_mode / "PTZ2IP.txt").write_text("172.16.1.12\n", encoding="utf-8")
        (isolated_sim_mode / "ATEMIP.txt").write_text("192.168.1.240\n", encoding="utf-8")

        assert sim_mode.activate() is True

        assert (isolated_sim_mode / "PTZ1IP.txt").read_text(encoding="utf-8") == "127.0.0.1"
        assert (isolated_sim_mode / "PTZ2IP.txt").read_text(encoding="utf-8") == "127.0.0.2"
        assert json.loads(sim_mode.BACKUP.read_text(encoding="utf-8")) == {
            "PTZ1IP.txt": "172.16.1.11",
            "PTZ2IP.txt": "172.16.1.12",
            "ATEMIP.txt": "192.168.1.240",
        }

    def test_activate_is_idempotent_when_backup_exists(self, isolated_sim_mode):
        sim_mode.BACKUP.write_text("{}", encoding="utf-8")
        (isolated_sim_mode / "PTZ1IP.txt").write_text("real", encoding="utf-8")

        assert sim_mode.activate() is False

        assert (isolated_sim_mode / "PTZ1IP.txt").read_text(encoding="utf-8") == "real"

    def test_activate_records_missing_original_files_as_empty_strings(self, isolated_sim_mode):
        assert sim_mode.activate() is True

        assert json.loads(sim_mode.BACKUP.read_text(encoding="utf-8")) == {
            "PTZ1IP.txt": "",
            "PTZ2IP.txt": "",
            "ATEMIP.txt": "",
        }

    def test_deactivate_restores_backup_values_and_removes_backup(self, isolated_sim_mode):
        (isolated_sim_mode / "PTZ1IP.txt").write_text("127.0.0.1", encoding="utf-8")
        sim_mode.BACKUP.write_text(
            '{"PTZ1IP.txt": "172.16.1.11", "ATEMIP.txt": "192.168.1.240"}',
            encoding="utf-8",
        )

        assert sim_mode.deactivate() is True

        assert (isolated_sim_mode / "PTZ1IP.txt").read_text(encoding="utf-8") == "172.16.1.11"
        assert (isolated_sim_mode / "ATEMIP.txt").read_text(encoding="utf-8") == "192.168.1.240"
        assert not sim_mode.BACKUP.exists()

    def test_deactivate_returns_false_when_not_active(self, isolated_sim_mode):
        assert sim_mode.deactivate() is False

    def test_deactivate_raises_on_corrupt_backup(self, isolated_sim_mode):
        sim_mode.BACKUP.write_text("not json", encoding="utf-8")

        with pytest.raises(RuntimeError):
            sim_mode.deactivate()

    def test_is_active_tracks_backup_file(self, isolated_sim_mode):
        assert sim_mode.is_active() is False

        sim_mode.BACKUP.write_text("{}", encoding="utf-8")

        assert sim_mode.is_active() is True

    def test_activate_raises_and_does_not_overwrite_ips_when_backup_write_fails(
        self, isolated_sim_mode, monkeypatch
    ):
        (isolated_sim_mode / "PTZ1IP.txt").write_text("172.16.1.11", encoding="utf-8")
        (isolated_sim_mode / "PTZ2IP.txt").write_text("172.16.1.12", encoding="utf-8")
        (isolated_sim_mode / "ATEMIP.txt").write_text("192.168.1.240", encoding="utf-8")

        def _fail_replace(*_):
            raise OSError("simulated write failure")
        monkeypatch.setattr(sim_mode.os, "replace", _fail_replace)

        with pytest.raises(RuntimeError):
            sim_mode.activate()

        # Las IPs reales no deben haberse sobreescrito.
        assert (isolated_sim_mode / "PTZ1IP.txt").read_text(encoding="utf-8") == "172.16.1.11"
        assert (isolated_sim_mode / "PTZ2IP.txt").read_text(encoding="utf-8") == "172.16.1.12"
        assert (isolated_sim_mode / "ATEMIP.txt").read_text(encoding="utf-8") == "192.168.1.240"


class TestBackupKeyValidation:
    """Tests for backup key validation in deactivate() (#139)."""

    def test_unexpected_keys_in_backup_are_ignored(self, isolated_sim_mode):
        sim_mode.BACKUP.write_text(
            '{"PTZ1IP.txt": "172.16.1.11", "MALICIOUS.txt": "danger"}',
            encoding="utf-8",
        )
        sim_mode.deactivate()
        # Only expected files are written; unexpected key is ignored
        assert not (isolated_sim_mode / "MALICIOUS.txt").exists()

    def test_only_backup_files_are_restored(self, isolated_sim_mode):
        sim_mode.BACKUP.write_text(
            '{"PTZ1IP.txt": "10.0.0.1", "PTZ2IP.txt": "10.0.0.2", "EXTRA": "x"}',
            encoding="utf-8",
        )
        sim_mode.deactivate()
        assert (isolated_sim_mode / "PTZ1IP.txt").read_text() == "10.0.0.1"
        assert (isolated_sim_mode / "PTZ2IP.txt").read_text() == "10.0.0.2"
        assert not (isolated_sim_mode / "EXTRA").exists()

    def test_non_string_value_is_skipped(self, isolated_sim_mode):
        sim_mode.BACKUP.write_text(
            '{"PTZ1IP.txt": 12345, "PTZ2IP.txt": "10.0.0.2"}',
            encoding="utf-8",
        )
        (isolated_sim_mode / "PTZ1IP.txt").write_text("127.0.0.1", encoding="utf-8")
        sim_mode.deactivate()
        # Non-string value for PTZ1IP.txt must be skipped; PTZ2IP.txt restored
        assert (isolated_sim_mode / "PTZ1IP.txt").read_text() == "127.0.0.1"
        assert (isolated_sim_mode / "PTZ2IP.txt").read_text() == "10.0.0.2"

    def test_missing_key_in_backup_is_skipped_without_crash(self, isolated_sim_mode):
        sim_mode.BACKUP.write_text(
            '{"PTZ2IP.txt": "10.0.0.2"}',
            encoding="utf-8",
        )
        # No PTZ1IP.txt key — should not crash
        result = sim_mode.deactivate()
        assert result is True
        assert (isolated_sim_mode / "PTZ2IP.txt").read_text() == "10.0.0.2"

    def test_unexpected_key_is_logged(self, isolated_sim_mode, caplog):
        import logging
        sim_mode.BACKUP.write_text(
            '{"PTZ1IP.txt": "10.0.0.1", "ROGUE_KEY": "value"}',
            encoding="utf-8",
        )
        with caplog.at_level(logging.WARNING, logger="adapters.sim_mode"):
            sim_mode.deactivate()
        assert any("ROGUE_KEY" in r.message for r in caplog.records)


class TestSimModeCli:

    def _run_cli(self, tmp_path, *args):
        env = {**os.environ, "HALLPTZ_APP_DIR": str(tmp_path)}
        return subprocess.run(
            [sys.executable, "-m", "adapters.sim_mode", *args],
            env=env,
            text=True,
            capture_output=True,
            check=False,
            cwd=str(ROOT),
        )

    def test_cli_on_activates_simulation_files(self, tmp_path):
        (tmp_path / "PTZ1IP.txt").write_text("172.16.1.11", encoding="utf-8")
        (tmp_path / "PTZ2IP.txt").write_text("172.16.1.12", encoding="utf-8")
        (tmp_path / "ATEMIP.txt").write_text("192.168.1.240", encoding="utf-8")

        result = self._run_cli(tmp_path, "on")

        assert result.returncode == 0
        assert "ACTIVADO" in result.stdout
        assert (tmp_path / "PTZ1IP.txt").read_text(encoding="utf-8") == "127.0.0.1"
        assert (tmp_path / "PTZ2IP.txt").read_text(encoding="utf-8") == "127.0.0.2"
        assert json.loads((tmp_path / "sim_ip_backup.json").read_text(encoding="utf-8"))["ATEMIP.txt"] == "192.168.1.240"

    def test_cli_off_restores_real_values(self, tmp_path):
        (tmp_path / "PTZ1IP.txt").write_text("127.0.0.1", encoding="utf-8")
        (tmp_path / "sim_ip_backup.json").write_text(
            '{"PTZ1IP.txt": "172.16.1.11", "PTZ2IP.txt": "172.16.1.12"}',
            encoding="utf-8",
        )

        result = self._run_cli(tmp_path, "off")

        assert result.returncode == 0
        assert "DESACTIVADO" in result.stdout
        assert (tmp_path / "PTZ1IP.txt").read_text(encoding="utf-8") == "172.16.1.11"
        assert (tmp_path / "PTZ2IP.txt").read_text(encoding="utf-8") == "172.16.1.12"
        assert not (tmp_path / "sim_ip_backup.json").exists()

    def test_cli_show_reports_active_state_and_saved_backup(self, tmp_path):
        (tmp_path / "PTZ1IP.txt").write_text("127.0.0.1", encoding="utf-8")
        (tmp_path / "sim_ip_backup.json").write_text(
            '{"PTZ1IP.txt": "172.16.1.11"}',
            encoding="utf-8",
        )

        result = self._run_cli(tmp_path, "show")

        assert result.returncode == 0
        assert "ACTIVO" in result.stdout
        assert "IPs reales guardadas" in result.stdout
        assert "172.16.1.11" in result.stdout

    def test_cli_invalid_command_prints_usage_and_exits_1(self, tmp_path):
        result = self._run_cli(tmp_path, "invalid")

        assert result.returncode == 1
        assert "Uso: python -m adapters.sim_mode [on|off|show]" in result.stdout


class TestCwdIndependence:
    """BACKUP and file paths must not depend on the process working directory (#595)."""

    def test_backup_path_is_absolute(self):
        assert sim_mode.BACKUP.is_absolute()

    def test_backup_path_is_anchored_to_script_dir_or_env_override(self, monkeypatch):
        monkeypatch.delenv("HALLPTZ_APP_DIR", raising=False)
        import importlib
        reloaded = importlib.reload(sim_mode)
        assert reloaded.BACKUP.is_absolute()
        assert reloaded.BACKUP.parent == reloaded._APP_DIR

    def test_hallptz_app_dir_env_override_changes_backup_location(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HALLPTZ_APP_DIR", str(tmp_path))
        import importlib
        reloaded = importlib.reload(sim_mode)
        assert reloaded.BACKUP == tmp_path / "sim_ip_backup.json"
