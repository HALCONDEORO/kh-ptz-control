#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_legacy_migration.py — legacy .txt to config.yaml migration tests

from __future__ import annotations

from pathlib import Path

import yaml

from application.legacy_migration import detect_legacy_files, migrate, _backup_existing_config


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write(directory: Path, name: str, content: str) -> None:
    (directory / name).write_text(content, encoding="utf-8")


def _full_legacy(app_dir: Path) -> None:
    _write(app_dir, "PTZ1IP.txt", "172.16.1.11")
    _write(app_dir, "Cam1ID.txt", "81")
    _write(app_dir, "PTZ2IP.txt", "172.16.1.12")
    _write(app_dir, "Cam2ID.txt", "82")
    _write(app_dir, "ATEMIP.txt", "172.16.1.100")
    _write(app_dir, "Contact.txt", "IT Support")


# ── detect_legacy_files ───────────────────────────────────────────────────────

def test_detect_all_legacy_files(tmp_path):
    _full_legacy(tmp_path)
    detected = detect_legacy_files(tmp_path)
    assert "PTZ1IP.txt" in detected
    assert "PTZ2IP.txt" in detected
    assert "Cam1ID.txt" in detected
    assert "Cam2ID.txt" in detected
    assert "ATEMIP.txt" in detected
    assert "Contact.txt" in detected


def test_detect_returns_empty_when_no_legacy(tmp_path):
    assert detect_legacy_files(tmp_path) == []


def test_detect_partial_set(tmp_path):
    _write(tmp_path, "PTZ1IP.txt", "10.0.0.1")
    detected = detect_legacy_files(tmp_path)
    assert detected == ["PTZ1IP.txt"]


# ── migrate: happy path ───────────────────────────────────────────────────────

def test_migrate_full_set_creates_config(tmp_path):
    _full_legacy(tmp_path)
    config_path = tmp_path / "config.yaml"
    result = migrate(tmp_path, config_path)

    assert result.config_written is True
    assert config_path.exists()
    assert result.config_path == config_path


def test_migrate_creates_valid_yaml(tmp_path):
    _full_legacy(tmp_path)
    config_path = tmp_path / "config.yaml"
    migrate(tmp_path, config_path)

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "cameras" in data
    assert "atem" in data
    assert "site" in data


def test_migrate_full_set_two_cameras(tmp_path):
    _full_legacy(tmp_path)
    config_path = tmp_path / "config.yaml"
    migrate(tmp_path, config_path)

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    cameras = data["cameras"]
    assert len(cameras) == 2
    assert cameras[0]["ip"] == "172.16.1.11"
    assert cameras[0]["visca_id"] == "81"
    assert cameras[1]["ip"] == "172.16.1.12"
    assert cameras[1]["visca_id"] == "82"


def test_migrate_single_camera(tmp_path):
    _write(tmp_path, "PTZ1IP.txt", "10.0.0.5")
    _write(tmp_path, "Cam1ID.txt", "81")
    config_path = tmp_path / "config.yaml"
    migrate(tmp_path, config_path)

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert len(data["cameras"]) == 1
    assert data["cameras"][0]["ip"] == "10.0.0.5"


def test_migrate_atem_ip_set(tmp_path):
    _full_legacy(tmp_path)
    config_path = tmp_path / "config.yaml"
    migrate(tmp_path, config_path)

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["atem"]["ip"] == "172.16.1.100"
    assert data["features"]["atem_enabled"] is True


def test_migrate_contact_in_site(tmp_path):
    _write(tmp_path, "PTZ1IP.txt", "10.0.0.1")
    _write(tmp_path, "Contact.txt", "PersonB Jones")
    config_path = tmp_path / "config.yaml"
    migrate(tmp_path, config_path)

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["site"]["contact"] == "PersonB Jones"


def test_migrate_preserves_legacy_files(tmp_path):
    _full_legacy(tmp_path)
    config_path = tmp_path / "config.yaml"
    migrate(tmp_path, config_path)

    assert (tmp_path / "PTZ1IP.txt").exists()
    assert (tmp_path / "PTZ2IP.txt").exists()
    assert (tmp_path / "ATEMIP.txt").exists()


def test_migrate_default_visca_id_when_cam1id_missing(tmp_path):
    _write(tmp_path, "PTZ1IP.txt", "10.0.0.1")
    config_path = tmp_path / "config.yaml"
    migrate(tmp_path, config_path)

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["cameras"][0]["visca_id"] == "81"


# ── migrate: safety rules ────────────────────────────────────────────────────

def test_migrate_does_not_overwrite_existing_config(tmp_path):
    _full_legacy(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("existing: content", encoding="utf-8")

    result = migrate(tmp_path, config_path)

    assert result.config_written is False
    assert result.skipped_reason is not None
    assert config_path.read_text(encoding="utf-8") == "existing: content"


def test_migrate_overwrite_flag_replaces_existing(tmp_path):
    _full_legacy(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("existing: content", encoding="utf-8")

    result = migrate(tmp_path, config_path, overwrite=True)

    assert result.config_written is True
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "cameras" in data


def test_migrate_no_legacy_files_is_noop(tmp_path):
    config_path = tmp_path / "config.yaml"
    result = migrate(tmp_path, config_path)

    assert result.config_written is False
    assert not config_path.exists()


def test_migrate_missing_ptz1ip_skips_migration(tmp_path):
    _write(tmp_path, "PTZ2IP.txt", "10.0.0.2")
    _write(tmp_path, "Cam1ID.txt", "81")
    config_path = tmp_path / "config.yaml"

    result = migrate(tmp_path, config_path)

    assert result.config_written is False
    assert result.skipped_reason is not None


def test_migrate_empty_ptz1ip_skips_migration(tmp_path):
    _write(tmp_path, "PTZ1IP.txt", "   ")
    config_path = tmp_path / "config.yaml"

    result = migrate(tmp_path, config_path)

    assert result.config_written is False


def test_migrate_result_summary_mentions_path(tmp_path):
    _write(tmp_path, "PTZ1IP.txt", "10.0.0.1")
    config_path = tmp_path / "config.yaml"
    result = migrate(tmp_path, config_path)

    summary = result.summary()
    assert str(config_path) in summary or "config.yaml" in summary


def test_migrate_atomic_no_tmp_leftover(tmp_path):
    _write(tmp_path, "PTZ1IP.txt", "10.0.0.1")
    config_path = tmp_path / "config.yaml"
    migrate(tmp_path, config_path)

    assert not Path(str(config_path) + ".tmp").exists()


# ── validate generated YAML with config loader ───────────────────────────────

def test_generated_yaml_loads_with_config_loader(tmp_path):
    _full_legacy(tmp_path)
    config_path = tmp_path / "config.yaml"
    migrate(tmp_path, config_path)

    from config.loader import load_config
    settings = load_config(config_path)
    assert len(settings.cameras) == 2
    assert settings.atem.ip == "172.16.1.100"


def test_single_camera_yaml_loads_with_config_loader(tmp_path):
    _write(tmp_path, "PTZ1IP.txt", "192.168.1.10")
    config_path = tmp_path / "config.yaml"
    migrate(tmp_path, config_path)

    from config.loader import load_config
    settings = load_config(config_path)
    assert len(settings.cameras) == 1


# ── CLI integration ───────────────────────────────────────────────────────────

# ── dry-run mode (#444) ───────────────────────────────────────────────────────

class TestDryRun:

    def test_dry_run_returns_no_write(self, tmp_path):
        _full_legacy(tmp_path)
        config_path = tmp_path / "config.yaml"
        result = migrate(tmp_path, config_path, dry_run=True)
        assert result.config_written is False
        assert result.dry_run is True

    def test_dry_run_does_not_create_file(self, tmp_path):
        _full_legacy(tmp_path)
        config_path = tmp_path / "config.yaml"
        migrate(tmp_path, config_path, dry_run=True)
        assert not config_path.exists()

    def test_dry_run_detects_legacy_files(self, tmp_path):
        _full_legacy(tmp_path)
        config_path = tmp_path / "config.yaml"
        result = migrate(tmp_path, config_path, dry_run=True)
        assert len(result.detected) == 6

    def test_dry_run_summary_mentions_dry_run(self, tmp_path):
        _full_legacy(tmp_path)
        result = migrate(tmp_path, tmp_path / "config.yaml", dry_run=True)
        assert "dry-run" in result.summary().lower() or "dry_run" in result.summary()

    def test_dry_run_no_legacy_files(self, tmp_path):
        result = migrate(tmp_path, tmp_path / "config.yaml", dry_run=True)
        assert result.config_written is False
        assert result.dry_run is True
        assert "no legacy" in result.summary().lower()

    def test_dry_run_existing_config_reports_would_overwrite(self, tmp_path):
        _full_legacy(tmp_path)
        config_path = tmp_path / "config.yaml"
        config_path.write_text("existing: yes", encoding="utf-8")
        result = migrate(tmp_path, config_path, overwrite=True, dry_run=True)
        assert result.config_written is False
        assert result.dry_run is True
        # file should not be changed
        assert config_path.read_text(encoding="utf-8") == "existing: yes"

    def test_dry_run_skipped_when_config_exists_no_overwrite(self, tmp_path):
        _full_legacy(tmp_path)
        config_path = tmp_path / "config.yaml"
        config_path.write_text("existing: yes", encoding="utf-8")
        result = migrate(tmp_path, config_path, dry_run=True)
        assert result.skipped_reason is not None
        assert result.dry_run is True


# ── pre-migration backup (#444) ───────────────────────────────────────────────

class TestPreMigrationBackup:

    def test_overwrite_creates_backup(self, tmp_path):
        _full_legacy(tmp_path)
        config_path = tmp_path / "config.yaml"
        config_path.write_text("original: content", encoding="utf-8")
        result = migrate(tmp_path, config_path, overwrite=True)
        assert result.backup_path is not None
        assert result.backup_path.exists()

    def test_backup_contains_original_content(self, tmp_path):
        _full_legacy(tmp_path)
        config_path = tmp_path / "config.yaml"
        config_path.write_text("original: content", encoding="utf-8")
        result = migrate(tmp_path, config_path, overwrite=True)
        assert result.backup_path.read_text(encoding="utf-8") == "original: content"

    def test_no_backup_when_config_does_not_exist(self, tmp_path):
        _full_legacy(tmp_path)
        config_path = tmp_path / "config.yaml"
        result = migrate(tmp_path, config_path)
        assert result.backup_path is None

    def test_summary_mentions_backup_path(self, tmp_path):
        _full_legacy(tmp_path)
        config_path = tmp_path / "config.yaml"
        config_path.write_text("original: content", encoding="utf-8")
        result = migrate(tmp_path, config_path, overwrite=True)
        assert str(result.backup_path) in result.summary()

    def test_backup_path_has_bak_suffix(self, tmp_path):
        _full_legacy(tmp_path)
        config_path = tmp_path / "config.yaml"
        config_path.write_text("original: content", encoding="utf-8")
        result = migrate(tmp_path, config_path, overwrite=True)
        assert result.backup_path.suffix == ".bak"

    def test_backup_existing_config_helper(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("data: here", encoding="utf-8")
        backup = _backup_existing_config(config_path)
        assert backup is not None
        assert backup.exists()
        assert backup.read_text(encoding="utf-8") == "data: here"


# ── repeat-run idempotency (#444) ─────────────────────────────────────────────

class TestIdempotency:

    def test_repeat_run_without_overwrite_is_noop(self, tmp_path):
        _write(tmp_path, "PTZ1IP.txt", "10.0.0.1")
        config_path = tmp_path / "config.yaml"
        # First run
        result1 = migrate(tmp_path, config_path)
        assert result1.config_written is True
        original_content = config_path.read_text(encoding="utf-8")
        # Second run
        result2 = migrate(tmp_path, config_path)
        assert result2.config_written is False
        assert config_path.read_text(encoding="utf-8") == original_content

    def test_repeat_overwrite_updates_config(self, tmp_path):
        _write(tmp_path, "PTZ1IP.txt", "10.0.0.1")
        config_path = tmp_path / "config.yaml"
        migrate(tmp_path, config_path)
        # Simulate a legacy file change
        _write(tmp_path, "PTZ1IP.txt", "10.0.0.2")
        result = migrate(tmp_path, config_path, overwrite=True)
        assert result.config_written is True
        data = __import__("yaml").safe_load(config_path.read_text(encoding="utf-8"))
        assert data["cameras"][0]["ip"] == "10.0.0.2"


def test_cli_migrate_command_with_legacy_files(tmp_path, monkeypatch):
    _write(tmp_path, "PTZ1IP.txt", "10.0.0.1")
    config_path = tmp_path / "out.yaml"

    monkeypatch.chdir(tmp_path)

    from unittest.mock import patch
    from application.legacy_migration import migrate as original_migrate

    # _COMMANDS["migrate"] holds a direct function reference — patching the
    # module attribute doesn't reach it. Patch migrate() in its origin module
    # so cmd_migrate's own import picks up the redirect.
    def patched_migrate(app_dir, cp, **kw):
        return original_migrate(tmp_path, cp, **kw)

    with patch("application.legacy_migration.migrate", patched_migrate):
        from runtime.cli import main
        rc = main(["migrate", "--config", str(config_path)])

    assert rc == 0
    assert config_path.exists()
