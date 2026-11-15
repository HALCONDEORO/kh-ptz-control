# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("candidate_manifest", ROOT / "scripts/validate_candidate_manifest.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
sys.path.pop(0)

VERSION = "1.2.3"
COMMIT = "a" * 40
NAME = "kh-ptz-control-1.2.3-candidate-git.tar.gz"


def candidate(tmp_path):
    data = b"candidate bytes"
    (tmp_path / NAME).write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    manifest = {"schema_version": 1, "app_version": VERSION, "git_commit": COMMIT,
                "created_at": "2026-11-15T20:00:00+00:00", "hash_algorithm": "sha256",
                "artifacts": [{"path": NAME, "sha256": digest, "size_bytes": len(data)}]}
    write_manifest(tmp_path, manifest)
    (tmp_path / "SHA256SUMS.txt").write_text(f"{digest}  {NAME}\n")
    return manifest


def write_manifest(path, manifest):
    (path / "release_manifest.json").write_text(json.dumps(manifest))


def test_valid_candidate_passes(tmp_path):
    candidate(tmp_path)
    assert m.validate(tmp_path, VERSION, COMMIT) == []


@pytest.mark.parametrize("missing", [NAME, "release_manifest.json", "SHA256SUMS.txt"])
def test_missing_required_file_blocks(tmp_path, missing):
    candidate(tmp_path)
    (tmp_path / missing).unlink()
    assert m.validate(tmp_path, VERSION, COMMIT)


def test_changed_archive_blocks(tmp_path):
    candidate(tmp_path)
    (tmp_path / NAME).write_bytes(b"changed content")
    assert m.validate(tmp_path, VERSION, COMMIT)


@pytest.mark.parametrize("field,value", [("schema_version", True), ("schema_version", 2),
    ("app_version", "other"), ("git_commit", "unknown"), ("hash_algorithm", "md5"),
    ("created_at", None), ("created_at", "2026-11-15"), ("artifacts", []), ("artifacts", {})])
def test_bad_manifest_fields_block(tmp_path, field, value):
    manifest = candidate(tmp_path)
    manifest[field] = value
    write_manifest(tmp_path, manifest)
    assert m.validate(tmp_path, VERSION, COMMIT)


@pytest.mark.parametrize("field,value", [("path", "../outside.tar.gz"), ("path", "/tmp/outside"),
    ("path", "kh-ptz-control-9.9.9-candidate-git.tar.gz"), ("sha256", 123),
    ("sha256", "a" * 63), ("size_bytes", True), ("size_bytes", -1), ("size_bytes", 99)])
def test_bad_artifact_fields_block(tmp_path, field, value):
    manifest = candidate(tmp_path)
    manifest["artifacts"][0][field] = value
    write_manifest(tmp_path, manifest)
    assert m.validate(tmp_path, VERSION, COMMIT)


@pytest.mark.parametrize("contents", ["", "wrong\n", "extra entries\n"])
def test_sums_mismatch_blocks(tmp_path, contents):
    candidate(tmp_path)
    (tmp_path / "SHA256SUMS.txt").write_text(contents)
    assert m.validate(tmp_path, VERSION, COMMIT)


def test_extra_uncovered_artifact_blocks(tmp_path):
    candidate(tmp_path)
    (tmp_path / "rt.tar.gz").write_bytes(b"uncovered archive")
    assert m.validate(tmp_path, VERSION, COMMIT)


@pytest.mark.parametrize("name", [NAME, "SHA256SUMS.txt", "release_manifest.json"])
def test_symlinks_block(tmp_path, name):
    candidate(tmp_path)
    path = tmp_path / name
    other = tmp_path.parent / ("external-" + name)
    path.rename(other)
    path.symlink_to(other)
    assert m.validate(tmp_path, VERSION, COMMIT)


def test_package_real_commit_from_unrelated_cwd(tmp_path):
    output = tmp_path / "candidate"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/package_candidate.py"),
                             "--out", str(output)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    expected_commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    expected_version = subprocess.check_output(["git", "-C", str(ROOT), "show", "HEAD:VERSION"], text=True).strip()
    assert m.validate(output, expected_version, expected_commit) == []
    # No .git directory, no untracked checkout files in the archive.
    import tarfile
    archive = next(output.glob("*.tar.gz"))
    with tarfile.open(archive) as tar:
        assert all("/.git/" not in name for name in tar.getnames())
    again = subprocess.run([sys.executable, str(ROOT / "scripts/package_candidate.py"),
                            "--out", str(output)], cwd=tmp_path, capture_output=True)
    assert again.returncode != 0


def test_invalid_ref_does_not_create_output(tmp_path):
    output = tmp_path / "candidate"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/package_candidate.py"),
                             "--ref", "not-a-real-ref", "--out", str(output)], capture_output=True)
    assert result.returncode != 0
    assert not output.exists()
