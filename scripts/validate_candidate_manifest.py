#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Verify a single candidate archive against both integrity manifests.

Checksums detect changed bytes, not authenticity, safety or release readiness.
The expected version and full commit must come from the reviewed candidate.
This does not inspect or extract archive contents and never publishes files.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sys

from release_manifest import _sha256

NAME = re.compile(r"kh-ptz-control-([0-9]+\.[0-9]+\.[0-9]+)-candidate-git\.tar\.gz")


def validate(directory: Path, version: str, commit: str) -> list[str]:
    try:
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("expected version/full commit is invalid")
        manifest_path = directory / "release_manifest.json"
        sums_path = directory / "SHA256SUMS.txt"
        for path in (manifest_path, sums_path):
            if path.is_symlink() or not path.is_file():
                raise ValueError("required manifest is missing, not regular or a symlink")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
            raise ValueError("unsupported manifest schema")
        if manifest.get("app_version") != version or manifest.get("git_commit") != commit:
            raise ValueError("manifest version/commit differs from expected reviewed candidate")
        if manifest.get("hash_algorithm") != "sha256":
            raise ValueError("manifest algorithm must be sha256")
        stamp = datetime.fromisoformat(manifest["created_at"])
        if stamp.tzinfo is None:
            raise ValueError("manifest timestamp must be timezone-aware")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or len(artifacts) != 1 or not isinstance(artifacts[0], dict):
            raise ValueError("candidate manifest must contain exactly one archive")
        record = artifacts[0]
        name = record.get("path")
        if not isinstance(name, str) or not NAME.fullmatch(name) or NAME.fullmatch(name).group(1) != version:
            raise ValueError("archive basename/version is invalid")
        digest = record.get("sha256")
        size = record.get("size_bytes")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("manifest SHA-256 is malformed")
        if type(size) is not int or size < 1:
            raise ValueError("manifest size must be a positive integer")
        archive = directory / name
        if archive.is_symlink() or not archive.is_file():
            raise ValueError("archive is missing, not regular or a symlink")
        if archive.stat().st_size != size or _sha256(archive) != digest:
            raise ValueError("archive size/digest mismatch")
        expected_sums = f"{digest}  {name}\n"
        if sums_path.read_text(encoding="utf-8") != expected_sums:
            raise ValueError("SHA256SUMS differs from manifest or includes extra/missing entries")
        expected_files = {name, "release_manifest.json", "SHA256SUMS.txt"}
        if {p.name for p in directory.iterdir()} != expected_files:
            raise ValueError("candidate directory contains extra or missing entries")
        return []
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [str(exc)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    problems = validate(args.directory, args.version, args.commit)
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("Candidate integrity verified; no release or hardware approval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
