#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# scripts/release_manifest.py — Generate SHA-256 checksum manifest for release artifacts (#514)
#
# Usage:
#   python3 scripts/release_manifest.py [artifact1 artifact2 ...]
#
# If no artifacts are given, scans the current directory for *.zip and *.tar.gz files.
#
# Outputs:
#   release/SHA256SUMS.txt       — standard sha256sum-compatible file
#   release/release_manifest.json — structured manifest with version/build metadata
#
# Manual verification:
#   sha256sum -c release/SHA256SUMS.txt
#
# Safety rules:
#   - No secrets, tokens or customer data are included.
#   - The checksum is NOT a cryptographic signature — use for integrity only.

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _app_version() -> str:
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def main(artifacts: list[str]) -> int:
    if not artifacts:
        cwd = Path(".")
        found = list(cwd.glob("*.zip")) + list(cwd.glob("*.tar.gz"))
        if not found:
            print("No artifacts supplied and no *.zip / *.tar.gz found in current directory.", file=sys.stderr)
            return 1
        artifacts = [str(p) for p in sorted(found)]

    paths = [Path(a) for a in artifacts]
    missing = [p for p in paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"Artifact not found: {p}", file=sys.stderr)
        return 1

    out_dir = Path("release")
    out_dir.mkdir(exist_ok=True)

    app_version = _app_version()
    git_commit = _git_commit()
    created_at = datetime.now(timezone.utc).isoformat()

    artifact_records = []
    sha256sums_lines = []

    for path in paths:
        digest = _sha256(path)
        size = path.stat().st_size
        artifact_records.append({
            "path": path.name,
            "sha256": digest,
            "size_bytes": size,
        })
        sha256sums_lines.append(f"{digest}  {path.name}")

    manifest = {
        "schema_version": 1,
        "app_version": app_version,
        "git_commit": git_commit,
        "created_at": created_at,
        "hash_algorithm": "sha256",
        "artifacts": artifact_records,
    }

    sha256sums_path = out_dir / "SHA256SUMS.txt"
    sha256sums_path.write_text("\n".join(sha256sums_lines) + "\n", encoding="utf-8")
    print(f"Written: {sha256sums_path}")

    manifest_path = out_dir / "release_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Written: {manifest_path}")

    print(f"\nRelease manifest — {app_version} ({git_commit}) — {len(artifact_records)} artifact(s)")
    for rec in artifact_records:
        print(f"  {rec['sha256'][:16]}...  {rec['path']}  ({rec['size_bytes']:,} bytes)")

    print(f"\nTo verify: sha256sum -c {sha256sums_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
