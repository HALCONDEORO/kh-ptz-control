#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Build a committed source candidate locally, never publish a release.

Uses git archive of one resolved commit, not a working-tree tar or git history.
The output directory must not exist. On failure it can contain partial files;
only exit 0 after manifest verification means preparation finished.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

from release_manifest import _sha256
from validate_candidate_manifest import validate

ROOT = Path(__file__).resolve().parent.parent


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        commit = git("rev-parse", "--verify", "--end-of-options", f"{args.ref}^{{commit}}")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("git did not resolve a full commit")
        version = git("show", f"{commit}:VERSION")
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            raise ValueError("committed VERSION must be a numeric three-part version")
        args.out.mkdir(parents=True, exist_ok=False)
        name = f"kh-ptz-control-{version}-candidate-git.tar.gz"
        archive = args.out / name
        subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar.gz",
                        f"--prefix=kh-ptz-control-{version}/", "-o", str(archive.resolve()), commit], check=True)
        digest = _sha256(archive)
        manifest = {"schema_version": 1, "app_version": version, "git_commit": commit,
                    "created_at": datetime.now(timezone.utc).isoformat(), "hash_algorithm": "sha256",
                    "artifacts": [{"path": name, "sha256": digest, "size_bytes": archive.stat().st_size}]}
        (args.out / "release_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (args.out / "SHA256SUMS.txt").write_text(f"{digest}  {name}\n", encoding="utf-8")
        problems = validate(args.out, version, commit)
        if problems:
            raise ValueError("; ".join(problems))
        print(f"Prepared and verified source candidate: {version} ({commit})")
        print("Integrity only: no publication, release readiness or physical acceptance")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: candidate preparation failed ({exc}); output may be incomplete", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
