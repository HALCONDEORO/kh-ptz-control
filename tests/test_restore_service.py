#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_restore_service.py — RestoreService unit tests

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from application.backup_service import BackupService
from application.restore_service import RestoreService, RestoreError, RestoreResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_services(tmp_path: Path):
    install_dir = tmp_path / "app"
    data_dir    = tmp_path / "data"
    backup_dir  = tmp_path / "backups"
    install_dir.mkdir()
    data_dir.mkdir()
    (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")

    common = dict(
        install_dir=install_dir,
        data_dir=data_dir,
        config_path=install_dir / "config.yaml",
        backup_dir=backup_dir,
        version_file=install_dir / "VERSION",
    )
    return BackupService(**common), RestoreService(**common)


def _make_zip(tmp_path: Path, files: dict[str, str], include_manifest: bool = True) -> Path:
    """Create a ZIP that looks like a backup produced by BackupService."""
    dest = tmp_path / "test_backup.zip"
    included = [n for n in files if n != "manifest.json"]
    manifest = {
        "app_version": "1.0.0",
        "created_at": "2026-01-01T00:00:00+00:00",
        "included": included,
        "skipped": [],
    }
    with zipfile.ZipFile(dest, "w") as zf:
        if include_manifest:
            zf.writestr("manifest.json", json.dumps(manifest))
        for name, content in files.items():
            if name != "manifest.json":
                zf.writestr(name, content)
    return dest


# ── Happy path ────────────────────────────────────────────────────────────────

def test_restore_known_files(tmp_path):
    backup_svc, restore_svc = _make_services(tmp_path)
    data_dir = restore_svc._data_dir

    # create original data
    (data_dir / "seat_names.json").write_text('{"a": 1}', encoding="utf-8")
    (data_dir / "chairman_presets.json").write_text('{"b": 2}', encoding="utf-8")

    # create backup
    result_bk = backup_svc.create_backup()

    # overwrite to simulate corruption
    (data_dir / "seat_names.json").write_text("BAD", encoding="utf-8")

    result = restore_svc.restore(result_bk.path)

    assert isinstance(result, RestoreResult)
    assert "seat_names.json" in result.restored
    assert "chairman_presets.json" in result.restored
    restored_text = (data_dir / "seat_names.json").read_text(encoding="utf-8")
    assert json.loads(restored_text) == {"a": 1}


def test_restore_creates_pre_restore_backup(tmp_path):
    backup_svc, restore_svc = _make_services(tmp_path)
    zip_path = _make_zip(tmp_path, {"seat_names.json": '{"x": 1}'})

    result = restore_svc.restore(zip_path)

    assert result.pre_restore_backup is not None
    assert result.pre_restore_backup.exists()
    assert zipfile.is_zipfile(result.pre_restore_backup)


def test_restore_result_summary_contains_key_info(tmp_path):
    _, restore_svc = _make_services(tmp_path)
    zip_path = _make_zip(tmp_path, {"seat_names.json": "{}"})

    result = restore_svc.restore(zip_path)
    summary = result.summary()

    assert "seat_names.json" in summary
    assert "Restored" in summary


def test_restore_missing_files_in_manifest_are_skipped(tmp_path):
    _, restore_svc = _make_services(tmp_path)
    # ZIP contains seat_names but manifest says only chairman_presets was included
    dest = tmp_path / "partial.zip"
    manifest = {
        "app_version": "1.0.0",
        "created_at": "2026-01-01T00:00:00+00:00",
        "included": ["chairman_presets.json"],
        "skipped": ["seat_names.json"],
    }
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("seat_names.json", '{"unexpected": true}')

    result = restore_svc.restore(dest)
    assert "seat_names.json" not in result.restored


def test_restore_config_yaml(tmp_path):
    backup_svc, restore_svc = _make_services(tmp_path)
    config_path = restore_svc._config_path
    config_path.write_text("cameras: []", encoding="utf-8")

    result_bk = backup_svc.create_backup()
    config_path.write_text("cameras: [bad]", encoding="utf-8")

    result = restore_svc.restore(result_bk.path)

    assert "config.yaml" in result.restored
    assert config_path.read_text(encoding="utf-8") == "cameras: []"


def test_default_config_path_uses_runtime_config_dir(tmp_path, monkeypatch):
    install_dir = tmp_path / "app"
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    backup_dir = tmp_path / "backups"
    install_dir.mkdir()
    data_dir.mkdir()
    config_dir.mkdir()
    (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
    monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(config_dir))

    restore_svc = RestoreService(
        install_dir=install_dir,
        data_dir=data_dir,
        backup_dir=backup_dir,
        version_file=install_dir / "VERSION",
    )

    assert restore_svc._config_path == config_dir / "config.yaml"


def test_restore_atomic_write(tmp_path):
    _, restore_svc = _make_services(tmp_path)
    zip_path = _make_zip(tmp_path, {"schedule.json": '{"v": 99}'})

    restore_svc.restore(zip_path)

    dest = restore_svc._data_dir / "schedule.json"
    assert dest.exists()
    assert json.loads(dest.read_text()) == {"v": 99}
    # no .tmp leftover
    assert not dest.with_suffix(".json.tmp").exists()


# ── Safety: corrupt or missing ZIP ───────────────────────────────────────────

def test_missing_zip_raises_restore_error(tmp_path):
    _, restore_svc = _make_services(tmp_path)
    with pytest.raises(RestoreError, match="not found"):
        restore_svc.restore(tmp_path / "nonexistent.zip")


def test_corrupt_zip_raises_restore_error(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"this is not a zip file at all")
    _, restore_svc = _make_services(tmp_path)
    with pytest.raises(RestoreError):
        restore_svc.restore(bad)


def test_zip_without_manifest_raises_restore_error(tmp_path):
    _, restore_svc = _make_services(tmp_path)
    no_manifest = _make_zip(tmp_path, {"seat_names.json": "{}"}, include_manifest=False)
    with pytest.raises(RestoreError, match="manifest"):
        restore_svc.restore(no_manifest)


def test_corrupt_manifest_raises_restore_error(tmp_path):
    _, restore_svc = _make_services(tmp_path)
    dest = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("manifest.json", "NOT JSON {{{{")
    with pytest.raises(RestoreError, match="corrupt"):
        restore_svc.restore(dest)


def test_unknown_path_in_zip_raises_restore_error(tmp_path):
    _, restore_svc = _make_services(tmp_path)
    dest = tmp_path / "unknown.zip"
    manifest = {"app_version": "1.0.0", "created_at": "x", "included": ["evil.sh"], "skipped": []}
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("evil.sh", "rm -rf /")
    with pytest.raises(RestoreError, match="unexpected path"):
        restore_svc.restore(dest)


def test_path_traversal_rejected(tmp_path):
    _, restore_svc = _make_services(tmp_path)
    dest = tmp_path / "traversal.zip"
    manifest = {"app_version": "1.0.0", "created_at": "x", "included": ["../evil"], "skipped": []}
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("../evil", "bad content")
    with pytest.raises(RestoreError):
        restore_svc.restore(dest)


# ── CLI integration ───────────────────────────────────────────────────────────

def test_cli_restore_command(tmp_path, monkeypatch):
    backup_svc, _ = _make_services(tmp_path)
    (backup_svc._data_dir / "seat_names.json").write_text("{}", encoding="utf-8")
    bk = backup_svc.create_backup()

    from runtime.cli import main
    rc = main(["restore", str(bk.path)])
    assert rc == 0


def test_cli_restore_missing_zip_returns_nonzero(tmp_path):
    from runtime.cli import main
    rc = main(["restore", str(tmp_path / "missing.zip")])
    assert rc != 0


# ── SHA-256 hash verification (#502) ─────────────────────────────────────────

def _make_zip_with_hashes(tmp_path: Path, files: dict[str, str]) -> Path:
    """Create a v2 backup ZIP with SHA-256 hashes in the manifest."""
    import hashlib
    dest = tmp_path / "hashed_backup.zip"
    included = list(files.keys())
    file_records = [
        {
            "path": name,
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "size_bytes": len(content.encode()),
        }
        for name, content in files.items()
    ]
    manifest = {
        "schema_version": 2,
        "app_version": "1.0.0",
        "created_at": "2026-01-01T00:00:00+00:00",
        "installation_id": "hallptz-2026-TEST",
        "hash_algorithm": "sha256",
        "files": file_records,
        "included": included,
        "skipped": [],
    }
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for name, content in files.items():
            zf.writestr(name, content)
    return dest


def test_restore_with_valid_hashes_succeeds(tmp_path):
    _, restore_svc = _make_services(tmp_path)
    zip_path = _make_zip_with_hashes(tmp_path, {"seat_names.json": '{"v": 42}'})
    result = restore_svc.restore(zip_path)
    assert "seat_names.json" in result.restored


def test_restore_hash_mismatch_raises_restore_error(tmp_path):
    import hashlib
    _, restore_svc = _make_services(tmp_path)
    dest = tmp_path / "tampered.zip"
    original_content = '{"v": 42}'
    tampered_content = '{"v": 999}'
    # Manifest hash is for original_content but ZIP contains tampered_content
    manifest = {
        "schema_version": 2,
        "app_version": "1.0.0",
        "created_at": "2026-01-01T00:00:00+00:00",
        "hash_algorithm": "sha256",
        "files": [
            {
                "path": "seat_names.json",
                "sha256": hashlib.sha256(original_content.encode()).hexdigest(),
                "size_bytes": len(original_content),
            }
        ],
        "included": ["seat_names.json"],
        "skipped": [],
    }
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("seat_names.json", tampered_content)  # wrong content
    with pytest.raises(RestoreError, match="Hash mismatch"):
        restore_svc.restore(dest)


def test_restore_hash_mismatch_does_not_write_data(tmp_path):
    """A hash mismatch must not touch current data on disk."""
    import hashlib
    _, restore_svc = _make_services(tmp_path)
    orig_file = restore_svc._data_dir / "seat_names.json"
    orig_file.write_text('{"original": true}', encoding="utf-8")

    dest = tmp_path / "tampered2.zip"
    manifest = {
        "schema_version": 2,
        "app_version": "1.0.0",
        "created_at": "x",
        "hash_algorithm": "sha256",
        "files": [
            {
                "path": "seat_names.json",
                "sha256": hashlib.sha256(b"correct").hexdigest(),  # wrong hash
                "size_bytes": 7,
            }
        ],
        "included": ["seat_names.json"],
        "skipped": [],
    }
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("seat_names.json", "tampered")

    with pytest.raises(RestoreError, match="Hash mismatch"):
        restore_svc.restore(dest)

    # The original file must be unchanged
    assert orig_file.read_text(encoding="utf-8") == '{"original": true}'


def test_restore_old_format_without_hashes_succeeds(tmp_path):
    """Old-format backups (no 'files' key) must still restore without error."""
    _, restore_svc = _make_services(tmp_path)
    zip_path = _make_zip(tmp_path, {"seat_names.json": '{"old": true}'})
    result = restore_svc.restore(zip_path)
    assert "seat_names.json" in result.restored


def test_backup_restore_roundtrip_with_hashes(tmp_path):
    """Full roundtrip: backup produces hashes; restore verifies them successfully."""
    backup_svc, restore_svc = _make_services(tmp_path)
    data_dir = backup_svc._data_dir
    (data_dir / "seat_names.json").write_text('{"seats": 30}', encoding="utf-8")
    bk = backup_svc.create_backup()

    assert bk.manifest.get("schema_version") == 2
    assert "files" in bk.manifest

    (data_dir / "seat_names.json").write_text("CORRUPTED", encoding="utf-8")
    result = restore_svc.restore(bk.path)
    assert "seat_names.json" in result.restored
    assert json.loads((data_dir / "seat_names.json").read_text(encoding="utf-8")) == {"seats": 30}


def test_config_dialog_export_path_restorable_via_service(tmp_path):
    """Backup created with an explicit dest (as ConfigDialog now does) is restorable (#597)."""
    backup_svc, restore_svc = _make_services(tmp_path)
    data_dir = backup_svc._data_dir
    (data_dir / "seat_names.json").write_text('{"ui": true}', encoding="utf-8")
    (data_dir / "schedule.json").write_text('{"days": []}', encoding="utf-8")

    explicit_dest = tmp_path / "ui_export.zip"
    bk = backup_svc.create_backup(dest=explicit_dest)
    assert bk.path == explicit_dest
    assert "manifest.json" in zipfile.ZipFile(explicit_dest).namelist()

    (data_dir / "seat_names.json").write_text("{}", encoding="utf-8")
    result = restore_svc.restore(explicit_dest)
    assert "seat_names.json" in result.restored
    assert json.loads((data_dir / "seat_names.json").read_text(encoding="utf-8")) == {"ui": True}


def test_change_history_included_in_backup_and_restored(tmp_path):
    """change_history.json is backed up and restored end-to-end (#596)."""
    backup_svc, restore_svc = _make_services(tmp_path)
    data_dir = backup_svc._data_dir
    (data_dir / "change_history.json").write_text('{"ev": 1}\n{"ev": 2}\n', encoding="utf-8")

    bk = backup_svc.create_backup()
    assert "change_history.json" in bk.included

    (data_dir / "change_history.json").write_text("CORRUPTED", encoding="utf-8")
    result = restore_svc.restore(bk.path)
    assert "change_history.json" in result.restored
    assert (data_dir / "change_history.json").read_text(encoding="utf-8") == '{"ev": 1}\n{"ev": 2}\n'


def test_legacy_data_paths_zip_rejected_by_restore_service(tmp_path):
    """A ZIP without manifest.json (old data_paths.export_backup format) is rejected (#597)."""
    _, restore_svc = _make_services(tmp_path)
    legacy_zip = tmp_path / "legacy.zip"
    with zipfile.ZipFile(legacy_zip, "w") as zf:
        zf.writestr("config/PTZ1IP.txt", "192.168.1.1")
        zf.writestr("seat_names.json", '{"legacy": true}')
    with pytest.raises(RestoreError, match="manifest"):
        restore_svc.restore(legacy_zip)


# ── dry-run ───────────────────────────────────────────────────────────────────

def test_dry_run_returns_would_restore_without_writing(tmp_path):
    """dry_run=True must report the files that would be restored but not write them."""
    _, restore_svc = _make_services(tmp_path)
    zip_path = _make_zip(tmp_path, {"seat_names.json": '{"dry": true}'})

    result = restore_svc.restore(zip_path, dry_run=True)

    assert "seat_names.json" in result.restored
    # File must NOT have been written
    assert not (restore_svc._data_dir / "seat_names.json").exists()


def test_dry_run_does_not_create_pre_restore_backup(tmp_path):
    """dry_run must not create a pre-restore backup."""
    backup_svc, restore_svc = _make_services(tmp_path)
    (restore_svc._data_dir / "seat_names.json").write_text("{}", encoding="utf-8")
    bk = backup_svc.create_backup()

    result = restore_svc.restore(bk.path, dry_run=True)

    assert result.pre_restore_backup is None


def test_dry_run_still_validates_zip(tmp_path):
    """dry_run must still raise RestoreError for a missing or corrupt ZIP."""
    _, restore_svc = _make_services(tmp_path)
    with pytest.raises(RestoreError, match="not found"):
        restore_svc.restore(tmp_path / "nonexistent.zip", dry_run=True)


def test_dry_run_still_validates_manifest(tmp_path):
    """dry_run must reject a ZIP that has no manifest.json."""
    _, restore_svc = _make_services(tmp_path)
    no_manifest = _make_zip(tmp_path, {"seat_names.json": "{}"}, include_manifest=False)
    with pytest.raises(RestoreError, match="manifest"):
        restore_svc.restore(no_manifest, dry_run=True)


def test_cli_restore_dry_run_returns_zero_and_no_files_written(tmp_path, monkeypatch):
    """CLI --dry-run exits 0 and does not modify data files."""
    backup_svc, _ = _make_services(tmp_path)
    data_dir = backup_svc._data_dir
    (data_dir / "seat_names.json").write_text('{"original": 1}', encoding="utf-8")
    bk = backup_svc.create_backup()

    # Overwrite so we can detect if restore wrote anything
    (data_dir / "seat_names.json").write_text("CHANGED", encoding="utf-8")

    from runtime.cli import main
    rc = main(["restore", "--dry-run", str(bk.path)])
    assert rc == 0
    # dry-run must not restore — file must still show the overwritten content
    assert (data_dir / "seat_names.json").read_text(encoding="utf-8") == "CHANGED"
