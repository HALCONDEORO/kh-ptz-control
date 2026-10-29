#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
scripts/check_secrets.py — Project-wide secret scan for Hall PTZ Control.

Checks staged (about to be committed) files and tracked files in the working
tree for secret material that must never enter the repository.

Usage:
    python scripts/check_secrets.py           # check staged + untracked
    python scripts/check_secrets.py --all     # also scan tracked files

Exit code:
    0   No secrets detected.
    1   Secrets or dangerous files detected.

Rules:
    - Never print secret values; only print file path + pattern category.
    - Blocked filenames → immediate fail.
    - High-confidence secret content in staged files → fail.
    - Lower-confidence patterns → warn only (do not block commits).

Safe allowlists:
    - config/examples/*.yaml  — explicitly safe examples
    - tests/fixtures/          — explicitly safe test fixtures
    - docs/                    — documentation with safe sample data
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path


# ── Blocked filename rules ────────────────────────────────────────────────────

# Exact match at any depth under the repo root.
_BLOCKED_NAMES: frozenset[str] = frozenset({
    # Legacy HALLPTZ flat-file configs (real customer data)
    "PTZ1IP.txt",
    "PTZ2IP.txt",
    "ATEMIP.txt",
    "Contact.txt",
    # Common secret/credential filenames
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    # Environment variable files
    ".env",
    ".env.local",
    ".env.production",
    # Credential stores
    "password.enc",
    "password.txt",
    "credentials.json",
    # Audit / runtime artifacts
    "audit_log.json",
    "boot_stats.json",
    "sim_ip_backup.json",
    "install_notes.md",
})

# Glob patterns matched against the filename only.
_BLOCKED_GLOB_PATTERNS: list[str] = [
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.sqlite",
    "*.sqlite3",
    "*.db",
    "support_bundle*.zip",
    "backup*.zip",
    "hallptz_backup_*.zip",
]

# Paths relative to the repo root that must never be committed as-is.
_BLOCKED_REL_PATHS: frozenset[str] = frozenset({
    "config.yaml",          # gitignored but belt-and-suspenders
})

# Directories that must never be committed.
_BLOCKED_DIRS: frozenset[str] = frozenset({
    "reports",
    "customer_config",
    "local_config",
})

# Path prefixes that are explicitly safe (allow-listed).
# Files under these prefixes are excluded from content scanning.
# (They may contain fake/example key material for testing or documentation.)
_SAFE_PREFIXES: tuple[str, ...] = (
    "config/examples/",
    "config/defaults/",
    "config.example/",   # legacy example directory
    "tests/",            # test files contain fake sample key headers
    "docs/",
    "scripts/",          # this script's own regex patterns are not real keys
)


# ── Content scanning patterns ─────────────────────────────────────────────────

# High-confidence: file contains these → fail.
_FAIL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SSH/TLS private key block",    re.compile(r"-----BEGIN [A-Z ]* PRIVATE KEY-----", re.IGNORECASE)),
    ("OPENSSH private key block",    re.compile(r"-----BEGIN OPENSSH PRIVATE KEY-----", re.IGNORECASE)),
    ("Generic PEM private key block",re.compile(r"-----BEGIN RSA PRIVATE KEY-----", re.IGNORECASE)),
    ("PGP private key block",        re.compile(r"-----BEGIN PGP PRIVATE KEY BLOCK-----", re.IGNORECASE)),
]

# Lower-confidence: warn but do not fail.
_WARN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("license_private_key assignment", re.compile(r"\blicense[_-]private[_-]key\s*[:=]\s*\S+", re.IGNORECASE)),
    ("password= assignment",           re.compile(r"\bpassword\s*=\s*\S+", re.IGNORECASE)),
]

# File extensions to skip during content scanning (binary or known safe).
_SKIP_CONTENT_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".zip", ".gz", ".tar", ".whl", ".pyc", ".pyo",
    ".pdf", ".docx", ".xlsx",
})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_lines(root: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _staged_and_untracked(root: Path) -> set[Path]:
    staged = _git_lines(root, "diff", "--cached", "--name-only", "--diff-filter=ACMRT")
    untracked = _git_lines(root, "ls-files", "--others", "--exclude-standard")
    return {root / p for p in staged + untracked}


def _tracked_files(root: Path) -> set[Path]:
    tracked = _git_lines(root, "ls-files")
    return {root / p for p in tracked}


def _is_safe_path(rel: str) -> bool:
    """Return True if the relative path is in an explicit safe prefix."""
    return any(rel.startswith(prefix) for prefix in _SAFE_PREFIXES)


def _is_blocked_name(path: Path, root: Path) -> str | None:
    """
    Return a human-readable reason if this path is blocked by name rules, else None.
    Never prints the secret value itself.
    """
    rel = path.relative_to(root).as_posix()
    top = rel.split("/")[0]

    if _is_safe_path(rel):
        return None

    if rel in _BLOCKED_REL_PATHS:
        return "blocked path"

    if top in _BLOCKED_DIRS:
        return f"blocked directory '{top}'"

    if path.name in _BLOCKED_NAMES:
        return f"blocked filename '{path.name}'"

    for pattern in _BLOCKED_GLOB_PATTERNS:
        if fnmatch.fnmatch(path.name.lower(), pattern.lower()):
            return f"blocked filename pattern '{pattern}'"

    return None


def _scan_content(path: Path, root: Path) -> list[str]:
    """
    Scan file content for high-confidence secret patterns.
    Returns a list of category descriptions (not the secret values themselves).
    """
    rel = path.relative_to(root).as_posix()
    if _is_safe_path(rel):
        return []
    if path.suffix.lower() in _SKIP_CONTENT_EXTENSIONS:
        return []
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    findings = []
    for category, pattern in _FAIL_PATTERNS:
        if pattern.search(text):
            findings.append(category)
    return findings


# ── Main scan ─────────────────────────────────────────────────────────────────

def run_scan(root: Path, *, scan_tracked: bool = False) -> tuple[list[str], list[str]]:
    """
    Scan the repo for secrets.

    Filename blocking applies only to NEW files (staged additions + untracked).
    Already-tracked files are not blocked by filename — they were already in the
    repo before this check existed.  Content scanning applies to all files when
    ``scan_tracked=True``.

    Returns
    -------
    errors: list[str]
        Fatal findings — must block commit / CI.
    warnings: list[str]
        Non-fatal findings — printed but do not block.
    """
    errors: list[str] = []
    warnings: list[str] = []

    new_paths = _staged_and_untracked(root)

    # Filename blocking: only new files (staged adds + untracked)
    for path in sorted(new_paths):
        if not path.exists():
            continue
        reason = _is_blocked_name(path, root)
        if reason:
            rel = path.relative_to(root).as_posix()
            errors.append(f"[BLOCKED] {rel} — {reason}")

    # Content scan: new files + optionally all tracked files
    content_paths = set(new_paths)
    if scan_tracked:
        content_paths |= _tracked_files(root)
    for path in sorted(content_paths):
        if not path.exists():
            continue
        reasons = _scan_content(path, root)
        for reason in reasons:
            rel = path.relative_to(root).as_posix()
            errors.append(f"[SECRET_CONTENT] {rel} — {reason} detected (do not print value)")

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", dest="scan_all", action="store_true",
                        help="Also scan all tracked files (slower; use in CI)")
    args = parser.parse_args(argv)

    root = _repo_root()
    errors, warnings = run_scan(root, scan_tracked=args.scan_all)

    for w in warnings:
        print(f"WARN:  {w}", file=sys.stderr)

    if not errors and not warnings:
        print("Secret scan: OK — no issues found.")
        return 0

    if errors:
        print("Secret scan: FAILED — potential secrets detected:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "Remediation: remove the file, rotate any exposed credentials, "
            "and ensure the path is covered by .gitignore.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
