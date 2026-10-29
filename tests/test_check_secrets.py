#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for scripts/check_secrets.py and scripts/check_repo_hygiene.py (#496).

Hardware-free: uses tmp_path, fake secret files with FAKE/EXAMPLE content.
IMPORTANT: No real secrets are present in any test. Fake/sample values only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ── Import helpers from the scripts under test ────────────────────────────────

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from check_secrets import (
    _is_blocked_name,
    _is_safe_path,
    _scan_content,
    run_scan,
)
from check_repo_hygiene import _is_blocked


# ── check_secrets._is_safe_path ──────────────────────────────────────────────

class TestIsSafePath:

    @pytest.mark.parametrize("path", [
        "config/examples/starter_1_camera.yaml",
        "config/defaults/starter.yaml",
        "tests/fixtures/config/minimal_valid.yaml",
        "docs/NETWORK_ARCHITECTURE.md",
    ])
    def test_explicit_safe_prefixes_are_safe(self, path):
        assert _is_safe_path(path)

    @pytest.mark.parametrize("path", [
        "config.yaml",
        "password.enc",
        "id_rsa",
        "my_backup.zip",
    ])
    def test_non_safe_paths_are_not_safe(self, path):
        assert not _is_safe_path(path)


# ── check_secrets._is_blocked_name ───────────────────────────────────────────

class TestIsBlockedName:

    def _blocked(self, tmp_path, name, rel_path=None) -> str | None:
        root = tmp_path
        if rel_path:
            path = root / rel_path
        else:
            path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fake content", encoding="utf-8")
        return _is_blocked_name(path, root)

    def test_ptz1ip_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "PTZ1IP.txt") is not None

    def test_ptz2ip_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "PTZ2IP.txt") is not None

    def test_atemip_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "ATEMIP.txt") is not None

    def test_contact_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "Contact.txt") is not None

    def test_id_rsa_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "id_rsa") is not None

    def test_id_ed25519_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "id_ed25519") is not None

    def test_pem_extension_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "cert.pem") is not None

    def test_key_extension_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "server.key") is not None

    def test_p12_extension_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "store.p12") is not None

    def test_env_blocked(self, tmp_path):
        assert self._blocked(tmp_path, ".env") is not None

    def test_password_enc_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "password.enc") is not None

    def test_support_bundle_zip_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "support_bundle_2026.zip") is not None

    def test_backup_zip_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "backup_20260508.zip") is not None

    def test_hallptz_backup_zip_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "hallptz_backup_20260508_120000.zip") is not None

    def test_safe_python_file_not_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "my_module.py") is None

    def test_safe_yaml_file_not_blocked(self, tmp_path):
        assert self._blocked(tmp_path, "settings.yaml") is None

    def test_config_examples_not_blocked(self, tmp_path):
        root = tmp_path
        path = root / "config" / "examples" / "starter_1_camera.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("site:\n  name: 'Example Venue'", encoding="utf-8")
        result = _is_blocked_name(path, root)
        assert result is None

    def test_tests_fixtures_not_blocked(self, tmp_path):
        root = tmp_path
        path = root / "tests" / "fixtures" / "config" / "minimal_valid.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("site:\n  name: 'Test Venue'", encoding="utf-8")
        result = _is_blocked_name(path, root)
        assert result is None


# ── check_secrets._scan_content ──────────────────────────────────────────────

class TestScanContent:

    def test_clean_file_returns_empty(self, tmp_path):
        root = tmp_path
        f = root / "example.yaml"
        f.write_text("cameras:\n  - ip: 192.168.30.20\n", encoding="utf-8")
        assert _scan_content(f, root) == []

    def test_rsa_private_key_block_detected(self, tmp_path):
        root = tmp_path
        f = root / "bad.yaml"
        # FAKE sample key header — not a real private key
        f.write_text("-----BEGIN RSA PRIVATE KEY-----\nFAKE_KEY_DATA_FOR_TEST\n-----END RSA PRIVATE KEY-----\n", encoding="utf-8")
        findings = _scan_content(f, root)
        assert findings  # at least one category detected
        # Must not include the actual key content in findings
        for finding in findings:
            assert "FAKE_KEY_DATA" not in finding

    def test_openssh_private_key_block_detected(self, tmp_path):
        root = tmp_path
        f = root / "bad.key"
        # FAKE sample key header — not a real key
        f.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nFAKE_DATA\n-----END OPENSSH PRIVATE KEY-----\n", encoding="utf-8")
        findings = _scan_content(f, root)
        assert findings

    def test_safe_prefix_not_scanned(self, tmp_path):
        root = tmp_path
        path = root / "config" / "examples" / "demo.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Even if a safe example contains a private key header (it shouldn't, but)
        path.write_text("-----BEGIN RSA PRIVATE KEY-----\nFAKE\n-----END RSA PRIVATE KEY-----\n", encoding="utf-8")
        assert _scan_content(path, root) == []

    def test_binary_extension_not_scanned(self, tmp_path):
        root = tmp_path
        f = root / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake data")
        assert _scan_content(f, root) == []


# ── check_repo_hygiene extended names ────────────────────────────────────────

class TestCheckRepoHygieneExtended:

    def _path(self, tmp_path, name):
        p = tmp_path / name
        p.write_text("fake", encoding="utf-8")
        return p

    def test_ptz1ip_txt_blocked(self, tmp_path):
        p = self._path(tmp_path, "PTZ1IP.txt")
        assert _is_blocked(p, tmp_path)

    def test_contact_txt_blocked(self, tmp_path):
        p = self._path(tmp_path, "Contact.txt")
        assert _is_blocked(p, tmp_path)

    def test_key_extension_blocked(self, tmp_path):
        p = self._path(tmp_path, "server.key")
        assert _is_blocked(p, tmp_path)

    def test_backup_zip_glob_blocked(self, tmp_path):
        p = self._path(tmp_path, "backup_20260508.zip")
        assert _is_blocked(p, tmp_path)

    def test_hallptz_backup_zip_glob_blocked(self, tmp_path):
        p = self._path(tmp_path, "hallptz_backup_20260508_120000.zip")
        assert _is_blocked(p, tmp_path)

    def test_support_bundle_zip_glob_blocked(self, tmp_path):
        p = self._path(tmp_path, "support_bundle_abc.zip")
        assert _is_blocked(p, tmp_path)

    def test_regular_zip_not_blocked(self, tmp_path):
        p = self._path(tmp_path, "archive.zip")
        assert not _is_blocked(p, tmp_path)

    def test_id_ecdsa_blocked(self, tmp_path):
        p = self._path(tmp_path, "id_ecdsa")
        assert _is_blocked(p, tmp_path)


# ── run_scan integration ──────────────────────────────────────────────────────

class TestRunScan:

    def test_clean_repo_dir_no_errors(self, tmp_path):
        """A directory with no dangerous files produces no errors."""
        (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
        errors, _ = run_scan(tmp_path)
        assert errors == []

    def test_blocked_file_produces_error(self, tmp_path, monkeypatch):
        """A PTZ1IP.txt file in staged/untracked produces an error."""
        bad_file = tmp_path / "PTZ1IP.txt"
        bad_file.write_text("192.168.1.100\n", encoding="utf-8")

        # Monkeypatch git calls to return the bad file
        import check_secrets as _cs
        monkeypatch.setattr(
            _cs, "_staged_and_untracked",
            lambda root: {bad_file},
        )
        monkeypatch.setattr(
            _cs, "_tracked_files",
            lambda root: set(),
        )

        errors, _ = run_scan(tmp_path)
        assert any("PTZ1IP.txt" in e for e in errors)

    def test_private_key_content_produces_error(self, tmp_path, monkeypatch):
        """A file with a PRIVATE KEY block in content produces an error."""
        bad_file = tmp_path / "bad.yaml"
        # FAKE key header — not real
        bad_file.write_text(
            "-----BEGIN RSA PRIVATE KEY-----\nFAKE_KEY_FOR_TEST\n-----END RSA PRIVATE KEY-----\n",
            encoding="utf-8",
        )

        import check_secrets as _cs
        monkeypatch.setattr(
            _cs, "_staged_and_untracked",
            lambda root: {bad_file},
        )
        monkeypatch.setattr(
            _cs, "_tracked_files",
            lambda root: set(),
        )

        errors, _ = run_scan(tmp_path)
        # Should find the file via content scan
        assert any("PRIVATE KEY" in e.upper() or "bad.yaml" in e for e in errors)

    def test_secret_value_not_in_error_messages(self, tmp_path, monkeypatch):
        """Error messages must never include the actual secret content."""
        bad_file = tmp_path / "secret.yaml"
        bad_file.write_text(
            "-----BEGIN RSA PRIVATE KEY-----\nSECRET_VALUE_DO_NOT_LEAK\n-----END RSA PRIVATE KEY-----\n",
            encoding="utf-8",
        )

        import check_secrets as _cs
        monkeypatch.setattr(
            _cs, "_staged_and_untracked",
            lambda root: {bad_file},
        )
        monkeypatch.setattr(
            _cs, "_tracked_files",
            lambda root: set(),
        )

        errors, _ = run_scan(tmp_path)
        for e in errors:
            assert "SECRET_VALUE_DO_NOT_LEAK" not in e


# ── Logging-call secret-leak scan (#89) ──────────────────────────────────────

class TestNoSecretsInLogCalls:
    """Scan all Python source files for logging calls that could leak secrets.

    Logs may be shared during support; they must never contain passwords,
    attempted passwords, secrets or tokens.

    Banned patterns (case-insensitive):
        - attempted_password in a log call argument
        - password= in a log call argument
        - secret= in a log call argument
        - Direct logging of a variable named password/passwd/secret/token
          as a positional format argument

    Safe exceptions (explicit allow-list):
        - tests/          — test files may reference these patterns as fixtures
        - scripts/        — scripts/check_secrets.py contains the regex itself
        - docs/           — documentation examples
    """

    # Regex for any logging call: logger.X(...), logging.X(...)
    _LOG_CALL = re.compile(
        r"""(?:logger|logging|log)\s*\.\s*(?:debug|info|warning|warn|error|critical|exception)\s*\(""",
        re.IGNORECASE,
    )

    # Banned substrings that must not appear inside a log call (case-insensitive)
    _BANNED_SUBSTRINGS: list[str] = [
        "attempted_password",
        "password=",
        "secret=",
        "token=",
    ]

    # Regex: direct use of a password/secret/token variable as a format arg,
    # e.g. logger.info("...", password) or logger.debug("%s", secret)
    _BANNED_VAR_PATTERN = re.compile(
        r"""\b(?:password|passwd|secret|token)\b""",
        re.IGNORECASE,
    )

    # Path prefixes (relative to repo root) to skip
    _SAFE_PREFIXES: tuple[str, ...] = ("tests/", "scripts/", "docs/", ".claude/")

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[1]

    def _collect_py_files(self) -> list[Path]:
        root = self._repo_root()
        files = []
        for path in sorted(root.rglob("*.py")):
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if any(rel.startswith(p) for p in self._SAFE_PREFIXES):
                continue
            files.append(path)
        return files

    def _check_file(self, path: Path) -> list[str]:
        """Return list of violation descriptions for a single file."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []

        root = self._repo_root()
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = str(path)

        violations: list[str] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            # Only examine lines that contain a logging call
            if not self._LOG_CALL.search(line):
                continue

            line_lower = line.lower()

            # Check banned keyword=value patterns
            for banned in self._BANNED_SUBSTRINGS:
                if banned.lower() in line_lower:
                    violations.append(
                        f"{rel}:{lineno}: log call contains banned pattern '{banned}'"
                    )

            # Check for direct variable leak: variable named password/secret/token
            # appearing as a format argument after a comma inside the call
            # Match only the portion after the first opening paren
            paren_idx = line.find("(")
            if paren_idx != -1:
                args_part = line[paren_idx + 1 :]
                # Find commas to isolate format arguments
                comma_idx = args_part.find(",")
                if comma_idx != -1:
                    format_args = args_part[comma_idx + 1 :]
                    if self._BANNED_VAR_PATTERN.search(format_args):
                        violations.append(
                            f"{rel}:{lineno}: log call passes a password/secret/token "
                            "variable as a format argument"
                        )

        return violations

    def test_no_secrets_in_log_calls(self):
        """All Python source files must not log passwords, secrets or tokens."""
        py_files = self._collect_py_files()
        assert py_files, "No Python source files found — check repo root detection"

        all_violations: list[str] = []
        for path in py_files:
            all_violations.extend(self._check_file(path))

        assert not all_violations, (
            "Logging calls that may leak secrets were found:\n"
            + "\n".join(f"  {v}" for v in all_violations)
        )

    # ── Unit tests for the checker itself (synthetic files) ──────────────────

    def test_clean_log_call_is_ok(self, tmp_path):
        """A normal log call without secret references must not trigger."""
        f = tmp_path / "clean.py"
        f.write_text(
            'import logging\nlogger.info("Camera %s connected", camera_id)\n',
            encoding="utf-8",
        )
        assert self._check_file(f) == []

    def test_attempted_password_in_log_is_caught(self, tmp_path):
        """attempted_password in a log call must be flagged."""
        f = tmp_path / "bad.py"
        f.write_text(
            'logger.debug("attempted_password=%s", user_input)\n',
            encoding="utf-8",
        )
        violations = self._check_file(f)
        assert violations, "Expected a violation for attempted_password in log call"

    def test_password_equals_in_log_is_caught(self, tmp_path):
        """password= in a log call must be flagged."""
        f = tmp_path / "bad2.py"
        f.write_text(
            'logger.info("password=%s", password)\n',
            encoding="utf-8",
        )
        violations = self._check_file(f)
        assert violations

    def test_secret_equals_in_log_is_caught(self, tmp_path):
        """secret= in a log call must be flagged."""
        f = tmp_path / "bad3.py"
        f.write_text(
            'logging.warning("secret=%s", token)\n',
            encoding="utf-8",
        )
        violations = self._check_file(f)
        assert violations

    def test_direct_password_var_in_log_is_caught(self, tmp_path):
        """Passing a variable named `password` as a format arg must be flagged."""
        f = tmp_path / "bad4.py"
        f.write_text(
            'logger.error("Auth failed for %s", password)\n',
            encoding="utf-8",
        )
        violations = self._check_file(f)
        assert violations

    def test_non_log_line_with_password_is_ignored(self, tmp_path):
        """A line with 'password=' that is not a log call must not be flagged."""
        f = tmp_path / "ok.py"
        f.write_text(
            "hashed = hash(password)\n",
            encoding="utf-8",
        )
        assert self._check_file(f) == []
