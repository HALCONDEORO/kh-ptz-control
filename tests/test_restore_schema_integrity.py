# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Versioned integrity checks apply before safety backups or restoration."""
import copy
import hashlib
import json
import zipfile
from unittest.mock import Mock

import pytest

from application.restore_service import RestoreError, RestoreService


PAYLOAD = b'{"archived": true}'
MEMBER = "seat_names.json"


def manifest_v2():
    return {"schema_version": 2, "hash_algorithm": "sha256", "included": [MEMBER],
            "files": [{"path": MEMBER, "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
                       "size_bytes": len(PAYLOAD)}]}


def malformed_manifests():
    for version in (0, -1, 3, 9999, None, True, "2", 2.0):
        m = manifest_v2()
        m["schema_version"] = version
        yield m
    for records in (None, 0, False, {}, "", [], [None], [{"path": MEMBER}]):
        m = manifest_v2()
        m["files"] = records
        yield m
    for key in ("files", "hash_algorithm"):
        m = manifest_v2()
        del m[key]
        yield m
    for field, value in (("sha256", "g" * 64), ("sha256", "A" * 64),
                         ("sha256", None), ("size_bytes", True),
                         ("size_bytes", -1), ("size_bytes", "18"),
                         ("size_bytes", len(PAYLOAD) + 1)):
        m = manifest_v2()
        m["files"][0][field] = value
        yield m
    m = manifest_v2()
    del m["files"][0]["size_bytes"]
    yield m
    m = manifest_v2()
    m["files"].append(copy.deepcopy(m["files"][0]))
    yield m
    m = manifest_v2()
    m["included"].append(MEMBER)
    yield m
    m = manifest_v2()
    m["included"] = []
    yield m
    m = manifest_v2()
    m["files"][0]["path"] = "manifest.json"
    yield m
    m = manifest_v2()
    m["hash_algorithm"] = "md5"
    yield m
    # Exact audit reproduction: future schema with falsey non-list files.
    yield {"schema_version": 9999, "files": 0, "included": [MEMBER]}


def archive_and_service(tmp_path, manifest):
    data = tmp_path / "data"
    data.mkdir()
    (data / MEMBER).write_bytes(b"current state")
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr(MEMBER, PAYLOAD)
    svc = RestoreService(install_dir=tmp_path, data_dir=data,
                         config_path=tmp_path / "config.yaml", backup_dir=tmp_path / "backups")
    return archive, svc


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("manifest", list(malformed_manifests()))
def test_invalid_versioned_manifest_never_backs_up_or_writes(tmp_path, monkeypatch, manifest, dry_run):
    archive, svc = archive_and_service(tmp_path, manifest)
    backup = Mock(side_effect=AssertionError("must validate before backup"))
    write = Mock(side_effect=AssertionError("must not restore"))
    monkeypatch.setattr(svc, "_create_pre_restore_backup", backup)
    monkeypatch.setattr(svc, "_atomic_write", write)
    monkeypatch.setattr("application.evidence_snapshot_service.EvidenceSnapshotService.capture",
                        lambda *a, **k: None)
    with pytest.raises(RestoreError):
        svc.restore(archive, dry_run=dry_run)
    backup.assert_not_called()
    write.assert_not_called()
    assert (tmp_path / "data" / MEMBER).read_bytes() == b"current state"
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("version", [None, 1])
def test_legacy_unhashed_remains_supported(tmp_path, version):
    m = {"included": [MEMBER]}
    if version is not None:
        m["schema_version"] = version
    archive, svc = archive_and_service(tmp_path, m)
    result = svc.restore(archive, dry_run=True)
    assert result.restored == [MEMBER]
    assert (tmp_path / "data" / MEMBER).read_bytes() == b"current state"


def test_modern_complete_manifest_validates(tmp_path):
    archive, svc = archive_and_service(tmp_path, manifest_v2())
    assert svc.restore(archive, dry_run=True).restored == [MEMBER]


def test_modern_unlisted_member_rejected(tmp_path):
    archive, svc = archive_and_service(tmp_path, manifest_v2())
    with zipfile.ZipFile(archive, "a") as zf:
        zf.writestr("camera_overrides.json", b"{}")
    with pytest.raises(RestoreError, match="cover"):
        svc.restore(archive, dry_run=True)
