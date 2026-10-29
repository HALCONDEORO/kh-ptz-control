#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_backup_service.py — BackupService unit tests

from __future__ import annotations

import json
import zipfile
from pathlib import Path


from domain.backup_contract import (
    CONFIG_ARCHIVE_NAME,
    RESTORABLE_ARCHIVE_NAMES,
)
from application.backup_service import BackupService, BackupResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_service(tmp_path: Path, **extra):
    install_dir = tmp_path / "app"
    data_dir    = tmp_path / "data"
    install_dir.mkdir()
    data_dir.mkdir()
    (install_dir / "VERSION").write_text("1.2.3", encoding="utf-8")
    return BackupService(
        install_dir=install_dir,
        data_dir=data_dir,
        config_path=install_dir / "config.yaml",
        backup_dir=tmp_path / "backups",
        version_file=install_dir / "VERSION",
        **extra,
    )


def _populate(svc: BackupService, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = svc._data_dir / name if not name.endswith(".yaml") else svc._config_path
        path.write_text(content, encoding="utf-8")


# ── create_backup: happy path ─────────────────────────────────────────────────

def test_backup_creates_zip_with_manifest(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {
        "config.yaml":          "cameras: []",
        "chairman_presets.json": "{}",
        "seat_names.json":       "{}",
    })

    result = svc.create_backup()

    assert isinstance(result, BackupResult)
    assert result.path.exists()
    assert result.path.suffix == ".zip"
    assert zipfile.is_zipfile(result.path)


def test_manifest_content(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {
        "config.yaml":           "cameras: []",
        "chairman_presets.json": "{}",
    })

    result = svc.create_backup()

    with zipfile.ZipFile(result.path) as zf:
        manifest = json.loads(zf.read("manifest.json"))

    assert manifest["app_version"] == "1.2.3"
    assert "created_at" in manifest
    assert "config.yaml" in manifest["included"]
    assert "chairman_presets.json" in manifest["included"]
    assert set(manifest["included"]) == set(result.included)
    assert set(manifest["skipped"]) == set(result.skipped)


def test_included_and_skipped_lists(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {
        "config.yaml":           "cameras: []",
        "seat_names.json":       "{}",
    })

    result = svc.create_backup()

    assert "config.yaml" in result.included
    assert "seat_names.json" in result.included
    assert "chairman_presets.json" in result.skipped
    assert "schedule.json" in result.skipped
    assert "room_layout.json" in result.skipped


def test_all_optional_missing_does_not_crash(tmp_path):
    svc = _make_service(tmp_path)
    result = svc.create_backup()

    assert result.path.exists()
    assert result.included == []
    # Counted from the shared contract, not restated here: BackupService and
    # RestoreService both derive their file set from it, and a number typed in
    # a third place is how the two sides drifted apart in the first place.
    assert sorted(result.skipped) == sorted(RESTORABLE_ARCHIVE_NAMES)


def test_all_files_present(tmp_path):
    """Every member the contract names must be collectable — no exceptions.

    Driving the fixture from the contract means adding a file there without
    teaching BackupService about it fails here, rather than shipping a backup
    that silently omits customer data.
    """
    svc = _make_service(tmp_path)
    _populate(svc, {
        name: ("cameras: []" if name == CONFIG_ARCHIVE_NAME else "{}")
        for name in RESTORABLE_ARCHIVE_NAMES
    })

    result = svc.create_backup()

    assert result.skipped == []
    assert sorted(result.included) == sorted(RESTORABLE_ARCHIVE_NAMES)


def test_zip_contains_included_files(tmp_path):
    svc = _make_service(tmp_path)
    content = '{"key": "value"}'
    _populate(svc, {
        "chairman_presets.json": content,
        "seat_names.json":       "{}",
    })

    result = svc.create_backup()

    with zipfile.ZipFile(result.path) as zf:
        names = zf.namelist()
    assert "chairman_presets.json" in names
    assert "seat_names.json" in names
    assert "manifest.json" in names


def test_backup_excludes_password_and_key_files(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {"seat_names.json": "{}"})
    (svc._data_dir / "password.enc").write_text("encrypted-secret", encoding="utf-8")
    (svc._data_dir / "support.key").write_text("private-key", encoding="utf-8")
    (svc._install_dir / "password.enc").write_text("legacy-secret", encoding="utf-8")

    result = svc.create_backup()

    with zipfile.ZipFile(result.path) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("manifest.json"))

    assert "password.enc" not in names
    assert "support.key" not in names
    assert "password.enc" not in manifest["included"]
    assert "support.key" not in manifest["included"]


def test_file_content_preserved(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {"seat_names.json": '{"names": ["PersonA", "PersonB"]}'})

    result = svc.create_backup()

    with zipfile.ZipFile(result.path) as zf:
        data = json.loads(zf.read("seat_names.json"))
    assert data == {"names": ["PersonA", "PersonB"]}


# ── explicit dest ─────────────────────────────────────────────────────────────

def test_explicit_dest(tmp_path):
    svc = _make_service(tmp_path)
    dest = tmp_path / "my_backup.zip"
    result = svc.create_backup(dest=dest)

    assert result.path == dest
    assert dest.exists()


def test_default_dest_inside_backup_dir(tmp_path):
    svc = _make_service(tmp_path)
    result = svc.create_backup()

    assert result.path.parent == tmp_path / "backups"
    assert result.path.name.startswith("hallptz_backup_")


def test_default_dest_names_do_not_collide_within_same_second(tmp_path):
    svc = _make_service(tmp_path)

    first = svc.create_backup()
    second = svc.create_backup()

    assert first.path != second.path
    assert first.path.exists()
    assert second.path.exists()


def test_default_config_path_uses_runtime_config_dir(tmp_path, monkeypatch):
    install_dir = tmp_path / "app"
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    backup_dir = tmp_path / "backups"
    install_dir.mkdir()
    data_dir.mkdir()
    config_dir.mkdir()
    (install_dir / "VERSION").write_text("1.2.3", encoding="utf-8")
    runtime_config = config_dir / "config.yaml"
    runtime_config.write_text(
        """
site:
  installation_profile: starter_1_camera
  installation_id: hallptz-2026-0001
cameras:
  - id: platform
    role: platform
    ip: 172.16.1.11
    visca_id: "81"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(config_dir))

    svc = BackupService(
        install_dir=install_dir,
        data_dir=data_dir,
        backup_dir=backup_dir,
        version_file=install_dir / "VERSION",
    )
    result = svc.create_backup()

    assert svc._config_path == runtime_config
    assert "config.yaml" in result.included
    assert result.manifest["installation_id"] == "hallptz-2026-0001"


# ── version fallback ──────────────────────────────────────────────────────────

def test_version_unknown_when_file_missing(tmp_path):
    svc = _make_service(tmp_path)
    svc._version_file = tmp_path / "MISSING_VERSION"

    result = svc.create_backup()

    assert result.manifest["app_version"] == "unknown"


# ── CLI integration ───────────────────────────────────────────────────────────

def test_cli_backup_command(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent))

    dest = tmp_path / "cli_backup.zip"
    from runtime.cli import main
    rc = main(["backup", "--dest", str(dest)])

    assert rc == 0
    assert dest.exists()


# ── SHA-256 hash manifest (#502) ──────────────────────────────────────────────

def test_manifest_has_schema_version_2(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {"config.yaml": "cameras: []"})
    result = svc.create_backup()
    assert result.manifest["schema_version"] == 2


def test_manifest_has_hash_algorithm(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {"config.yaml": "cameras: []"})
    result = svc.create_backup()
    assert result.manifest["hash_algorithm"] == "sha256"


def test_manifest_files_field_present(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {"config.yaml": "cameras: []", "seat_names.json": "{}"})
    result = svc.create_backup()
    assert "files" in result.manifest


def test_manifest_files_contains_sha256(tmp_path):
    svc = _make_service(tmp_path)
    content = "cameras: []"
    _populate(svc, {"config.yaml": content})
    result = svc.create_backup()
    file_entry = next(f for f in result.manifest["files"] if f["path"] == "config.yaml")
    assert "sha256" in file_entry
    # Verify the hash is correct
    import hashlib
    expected = hashlib.sha256(content.encode()).hexdigest()
    assert file_entry["sha256"] == expected


def test_manifest_files_contains_size_bytes(tmp_path):
    svc = _make_service(tmp_path)
    content = "cameras: []"
    _populate(svc, {"config.yaml": content})
    result = svc.create_backup()
    file_entry = next(f for f in result.manifest["files"] if f["path"] == "config.yaml")
    assert file_entry["size_bytes"] == len(content.encode())


def test_manifest_files_only_included_files(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {"config.yaml": "cameras: []"})
    result = svc.create_backup()
    file_paths = {f["path"] for f in result.manifest["files"]}
    assert file_paths == {"config.yaml"}


def test_manifest_files_multiple_files(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {
        "config.yaml":           "cameras: []",
        "chairman_presets.json": "{}",
        "seat_names.json":       "{}",
    })
    result = svc.create_backup()
    file_paths = {f["path"] for f in result.manifest["files"]}
    assert file_paths == {"config.yaml", "chairman_presets.json", "seat_names.json"}


def test_manifest_has_installation_id_field(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {"config.yaml": "cameras: []"})
    result = svc.create_backup()
    assert "installation_id" in result.manifest


def test_sha256_in_written_zip(tmp_path):
    svc = _make_service(tmp_path)
    _populate(svc, {"seat_names.json": '{"v": 1}'})
    result = svc.create_backup()
    with zipfile.ZipFile(result.path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    file_entry = next(f for f in manifest["files"] if f["path"] == "seat_names.json")
    import hashlib
    expected = hashlib.sha256('{"v": 1}'.encode()).hexdigest()
    assert file_entry["sha256"] == expected
