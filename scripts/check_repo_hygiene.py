#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Fail when local runtime or secret-like artifacts are present in the repo.

This script is the original filename-based hygiene check from #52.
For deeper content scanning see scripts/check_secrets.py (#496).
"""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path


ROOT_ONLY = {
    ".env",
    ".env.local",
    ".env.production",
    "password.enc",
    "password.txt",
    "credentials.json",
    "audit_log.json",
    "boot_stats.json",
    "sim_ip_backup.json",
    "install_notes.md",
    # Legacy KHPTZ flat-file customer configs
    "PTZ1IP.txt",
    "PTZ2IP.txt",
    "ATEMIP.txt",
    "Contact.txt",
}

DIRS = {
    "reports",
    "customer_config",
    "local_config",
}

SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".sqlite",
    ".sqlite3",
    ".db",
}

NAMES = {
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
}

# Glob patterns matched against the filename only (case-insensitive).
NAME_GLOBS = [
    "support_bundle*.zip",
    "backup*.zip",
    "khptz_backup_*.zip",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_lines(root: Path, *args: str) -> set[Path]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        return set()
    return {root / line.strip() for line in result.stdout.splitlines() if line.strip()}


def _candidate_paths(root: Path) -> set[Path]:
    staged_adds = _git_lines(root, "diff", "--cached", "--name-only", "--diff-filter=A")
    untracked = _git_lines(root, "ls-files", "--others", "--exclude-standard")
    # Also scan already-tracked files: artifacts that slipped in before this
    # check existed (e.g. audit_log.json, boot_stats.json, sim_ip_backup.json)
    # would otherwise never be caught, since gitignore does not untrack them.
    tracked = _git_lines(root, "ls-files")
    return staged_adds | untracked | tracked


def _is_blocked(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    top = rel.parts[0] if rel.parts else path.name
    if rel.as_posix() in ROOT_ONLY or top in DIRS or path.name in NAMES or path.suffix in SUFFIXES:
        return True
    for pattern in NAME_GLOBS:
        if fnmatch.fnmatch(path.name.lower(), pattern.lower()):
            return True
    return False


def _find_blocked(root: Path) -> list[Path]:
    blocked: list[Path] = []

    for path in _candidate_paths(root):
        if path.exists() and _is_blocked(path, root):
            blocked.append(path)

    return sorted(set(blocked))


def main() -> int:
    root = _repo_root()
    blocked = _find_blocked(root)
    if not blocked:
        return 0

    print("Repository hygiene check failed. Remove or relocate these new local artifacts:")
    for path in blocked:
        print(f"- {path.relative_to(root)}")
    print("Use config.example/ or docs examples for safe fixtures, not real customer data.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
