#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_release_manifest.py — Tests for scripts/release_manifest.py (#514)
from __future__ import annotations

import hashlib
import json
from pathlib import Path



def _run(artifacts: list[str], tmp_path: Path) -> int:
    import sys
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    import importlib
    rm = importlib.import_module("release_manifest")
    import os
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return rm.main(artifacts)
    finally:
        os.chdir(old_cwd)
        sys.path.pop(0)


def test_manifest_created_for_single_artifact(tmp_path):
    artifact = tmp_path / "hallptz-1.0.0.zip"
    artifact.write_bytes(b"fake zip content")
    rc = _run([str(artifact)], tmp_path)
    assert rc == 0
    manifest = json.loads((tmp_path / "release" / "release_manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert manifest["hash_algorithm"] == "sha256"
    assert len(manifest["artifacts"]) == 1
    assert manifest["artifacts"][0]["path"] == "hallptz-1.0.0.zip"


def test_sha256sums_file_created(tmp_path):
    artifact = tmp_path / "hallptz-1.0.0.zip"
    content = b"release artifact"
    artifact.write_bytes(content)
    _run([str(artifact)], tmp_path)
    sha_file = (tmp_path / "release" / "SHA256SUMS.txt").read_text()
    expected_hash = hashlib.sha256(content).hexdigest()
    assert expected_hash in sha_file
    assert "hallptz-1.0.0.zip" in sha_file


def test_hash_is_correct(tmp_path):
    artifact = tmp_path / "test.zip"
    content = b"some content 12345"
    artifact.write_bytes(content)
    _run([str(artifact)], tmp_path)
    manifest = json.loads((tmp_path / "release" / "release_manifest.json").read_text())
    expected = hashlib.sha256(content).hexdigest()
    assert manifest["artifacts"][0]["sha256"] == expected


def test_missing_artifact_returns_nonzero(tmp_path):
    rc = _run([str(tmp_path / "nonexistent.zip")], tmp_path)
    assert rc != 0


def test_no_artifacts_no_files_returns_nonzero(tmp_path):
    rc = _run([], tmp_path)
    assert rc != 0


def test_manifest_has_no_secrets(tmp_path):
    artifact = tmp_path / "safe.zip"
    artifact.write_bytes(b"content")
    _run([str(artifact)], tmp_path)
    manifest_text = (tmp_path / "release" / "release_manifest.json").read_text()
    for secret_pattern in ("password", "token", "secret", "key", "credential"):
        assert secret_pattern not in manifest_text.lower(), \
            f"Manifest unexpectedly contains '{secret_pattern}'"
