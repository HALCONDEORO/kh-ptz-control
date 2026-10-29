#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_fingerprint_service.py — Tests for InstallationFingerprint and FingerprintService (#563).

Covers:
- InstallationFingerprint defaults are safe 'unknown' strings
- fingerprint_hash() is deterministic (same state → same hash)
- fingerprint_hash() changes when config_hash changes
- fingerprint_hash() changes when cameras change
- fingerprint_hash() returns a 64-char hex string
- human_summary() returns a list of strings, no raw IPs
- to_dict() is JSON-serializable
- FingerprintService.generate() returns an InstallationFingerprint
- Secrets are not present in fingerprint output
- FingerprintService accepts injected RuntimePathResolver
- _safe_json_hash returns 'missing' for missing file
- _safe_json_hash returns 'invalid' for non-JSON file
- _file_sha256 returns 'missing' for missing file
- khptz fingerprint command exits 0
- khptz fingerprint --json produces valid JSON with expected keys
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


from application.fingerprint_service import (
    FingerprintService,
    InstallationFingerprint,
    _file_sha256,
    _safe_json_hash,
)


# ── InstallationFingerprint ───────────────────────────────────────────────────

class TestInstallationFingerprintDefaults:

    def test_defaults_are_unknown(self):
        fp = InstallationFingerprint()
        assert fp.installation_id == "unknown"
        assert fp.app_version == "unknown"
        assert fp.git_commit == "unknown"
        assert fp.profile == "unknown"
        assert fp.config_hash == "unknown"
        assert fp.layout_hash == "unknown"
        assert fp.atem_enabled == "unknown"
        assert fp.atem_configured == "unknown"
        assert fp.known_good_state_version == "unknown"

    def test_cameras_default_is_empty_list(self):
        fp = InstallationFingerprint()
        assert fp.cameras == []

    def test_runtime_paths_default_is_empty_dict(self):
        fp = InstallationFingerprint()
        assert fp.runtime_paths == {}


class TestFingerprintHash:

    def test_hash_is_64_char_hex(self):
        fp = InstallationFingerprint()
        h = fp.fingerprint_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_state_same_hash(self):
        fp1 = InstallationFingerprint(
            installation_id="khptz-2026-0042",
            app_version="3.18.0",
            config_hash="abc123",
            layout_hash="def456",
        )
        fp2 = InstallationFingerprint(
            installation_id="khptz-2026-0042",
            app_version="3.18.0",
            config_hash="abc123",
            layout_hash="def456",
        )
        assert fp1.fingerprint_hash() == fp2.fingerprint_hash()

    def test_config_hash_change_changes_fingerprint(self):
        fp1 = InstallationFingerprint(config_hash="aaa")
        fp2 = InstallationFingerprint(config_hash="bbb")
        assert fp1.fingerprint_hash() != fp2.fingerprint_hash()

    def test_layout_hash_change_changes_fingerprint(self):
        fp1 = InstallationFingerprint(layout_hash="aaa")
        fp2 = InstallationFingerprint(layout_hash="bbb")
        assert fp1.fingerprint_hash() != fp2.fingerprint_hash()

    def test_camera_change_changes_fingerprint(self):
        fp1 = InstallationFingerprint(cameras=[{"role": "cam1", "configured": "yes"}])
        fp2 = InstallationFingerprint(cameras=[{"role": "cam1", "configured": "no"}])
        assert fp1.fingerprint_hash() != fp2.fingerprint_hash()

    def test_atem_change_changes_fingerprint(self):
        fp1 = InstallationFingerprint(atem_enabled="yes")
        fp2 = InstallationFingerprint(atem_enabled="no")
        assert fp1.fingerprint_hash() != fp2.fingerprint_hash()

    def test_installation_id_change_changes_fingerprint(self):
        fp1 = InstallationFingerprint(installation_id="khptz-2026-0001")
        fp2 = InstallationFingerprint(installation_id="khptz-2026-0002")
        assert fp1.fingerprint_hash() != fp2.fingerprint_hash()


class TestHumanSummary:

    def test_returns_list_of_strings(self):
        fp = InstallationFingerprint()
        lines = fp.human_summary()
        assert isinstance(lines, list)
        assert all(isinstance(line, str) for line in lines)

    def test_contains_installation_id(self):
        fp = InstallationFingerprint(installation_id="khptz-2026-0042")
        summary = "\n".join(fp.human_summary())
        assert "khptz-2026-0042" in summary

    def test_config_hash_truncated(self):
        fp = InstallationFingerprint(config_hash="a" * 64)
        summary = "\n".join(fp.human_summary())
        # Should show first 16 chars + ellipsis, not the full 64-char hash
        assert "a" * 64 not in summary
        assert "…" in summary

    def test_fingerprint_hash_truncated(self):
        fp = InstallationFingerprint()
        lines = fp.human_summary()
        # fingerprint hash line should end with "…"
        hash_line = next(line for line in lines if "Fingerprint hash" in line)
        assert "…" in hash_line

    def test_camera_roles_appear_in_summary(self):
        fp = InstallationFingerprint(
            cameras=[
                {"role": "cam1", "configured": "yes"},
                {"role": "cam2", "configured": "no"},
            ]
        )
        summary = "\n".join(fp.human_summary())
        assert "cam1" in summary
        assert "cam2" in summary

    def test_no_raw_ips_in_summary(self):
        fp = InstallationFingerprint(
            installation_id="khptz-2026-0042",
            cameras=[{"role": "cam1", "configured": "yes"}],
        )
        summary = "\n".join(fp.human_summary())
        # Ensure no IP-like patterns sneak in
        import re
        ip_pattern = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
        assert not ip_pattern.search(summary)

    def test_known_good_version_appears_when_set(self):
        fp = InstallationFingerprint(known_good_state_version="2026-05-01T12:00:00")
        lines = fp.human_summary()
        summary = "\n".join(lines)
        assert "2026-05-01T12:00:00" in summary

    def test_known_good_version_absent_when_unknown(self):
        fp = InstallationFingerprint(known_good_state_version="unknown")
        lines = fp.human_summary()
        summary = "\n".join(lines)
        assert "Known-good" not in summary


class TestToDict:

    def test_to_dict_is_json_serializable(self):
        fp = InstallationFingerprint(
            installation_id="khptz-2026-0042",
            app_version="3.18.0",
            cameras=[{"role": "cam1", "configured": "yes"}],
        )
        d = fp.to_dict()
        # Should not raise
        json.dumps(d)

    def test_to_dict_contains_expected_keys(self):
        fp = InstallationFingerprint()
        d = fp.to_dict()
        for key in (
            "installation_id", "app_version", "git_commit", "profile",
            "config_hash", "layout_hash", "cameras", "atem_enabled",
            "atem_configured", "runtime_paths", "known_good_state_version",
        ):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_no_secrets(self):
        fp = InstallationFingerprint(
            installation_id="khptz-2026-0042",
            app_version="3.18.0",
        )
        text = json.dumps(fp.to_dict())
        for forbidden in ("password", "secret", "token", "private_key"):
            assert forbidden not in text.lower()


# ── Helper functions ──────────────────────────────────────────────────────────

class TestFileSha256:

    def test_missing_file_returns_missing(self, tmp_path):
        p = tmp_path / "does_not_exist.bin"
        assert _file_sha256(p) == "missing"

    def test_existing_file_returns_hex(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"hello world")
            tmp = Path(f.name)
        try:
            result = _file_sha256(tmp)
            assert len(result) == 64
            assert all(c in "0123456789abcdef" for c in result)
        finally:
            tmp.unlink(missing_ok=True)

    def test_same_content_same_hash(self):
        with tempfile.NamedTemporaryFile(delete=False) as f1,\
             tempfile.NamedTemporaryFile(delete=False) as f2:
            f1.write(b"deterministic")
            f2.write(b"deterministic")
            p1, p2 = Path(f1.name), Path(f2.name)
        try:
            assert _file_sha256(p1) == _file_sha256(p2)
        finally:
            p1.unlink(missing_ok=True)
            p2.unlink(missing_ok=True)


class TestSafeJsonHash:

    def test_missing_file_returns_missing(self, tmp_path):
        p = tmp_path / "does_not_exist.json"
        assert _safe_json_hash(p) == "missing"

    def test_invalid_json_returns_invalid(self):
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".json", mode="w", encoding="utf-8"
        ) as f:
            f.write("not valid json {{{")
            tmp = Path(f.name)
        try:
            assert _safe_json_hash(tmp) == "invalid"
        finally:
            tmp.unlink(missing_ok=True)

    def test_valid_json_returns_hex(self):
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".json", mode="w", encoding="utf-8"
        ) as f:
            json.dump({"room": "main", "seats": 4}, f)
            tmp = Path(f.name)
        try:
            result = _safe_json_hash(tmp)
            assert len(result) == 64
            assert all(c in "0123456789abcdef" for c in result)
        finally:
            tmp.unlink(missing_ok=True)

    def test_key_order_does_not_affect_hash(self):
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".json", mode="w", encoding="utf-8"
        ) as f1, tempfile.NamedTemporaryFile(
            delete=False, suffix=".json", mode="w", encoding="utf-8"
        ) as f2:
            json.dump({"b": 2, "a": 1}, f1)
            json.dump({"a": 1, "b": 2}, f2)
            p1, p2 = Path(f1.name), Path(f2.name)
        try:
            assert _safe_json_hash(p1) == _safe_json_hash(p2)
        finally:
            p1.unlink(missing_ok=True)
            p2.unlink(missing_ok=True)


# ── FingerprintService ────────────────────────────────────────────────────────

class TestFingerprintService:

    def _make_paths(self, tmp_path: Path):
        """Return a minimal RuntimePathResolver-like mock."""
        mock = MagicMock()
        mock.data_dir = tmp_path / "data"
        mock.config_dir = tmp_path / "config"
        mock.room_layout_file = tmp_path / "room_layout.json"
        mock.known_good_state_file = tmp_path / "known_good.json"
        mock.to_dict.return_value = {
            "config_dir": str(tmp_path / "config"),
            "data_dir": str(tmp_path / "data"),
        }
        return mock

    def test_generate_returns_installation_fingerprint(self, tmp_path):
        paths = self._make_paths(tmp_path)
        with patch("application.fingerprint_service.build_info") as mock_bi:
            mock_bi.return_value = MagicMock(
                installation_id="khptz-2026-test",
                app_version="3.18.0",
                git_commit="abc1234",
                runtime_profile="production",
            )
            svc = FingerprintService(paths=paths)
            fp = svc.generate()
        assert isinstance(fp, InstallationFingerprint)

    def test_generate_populates_known_fields(self, tmp_path):
        paths = self._make_paths(tmp_path)
        with patch("application.fingerprint_service.build_info") as mock_bi:
            mock_bi.return_value = MagicMock(
                installation_id="khptz-2026-test",
                app_version="3.18.0",
                git_commit="abc1234",
                runtime_profile="production",
            )
            svc = FingerprintService(paths=paths)
            fp = svc.generate()
        assert fp.installation_id == "khptz-2026-test"
        assert fp.app_version == "3.18.0"
        assert fp.git_commit == "abc1234"
        assert fp.profile == "production"

    def test_missing_config_yields_missing_hash(self, tmp_path):
        paths = self._make_paths(tmp_path)
        # No config.yaml in tmp_path
        with patch("application.fingerprint_service.build_info") as mock_bi:
            mock_bi.return_value = MagicMock(
                installation_id="x", app_version="x", git_commit="x", runtime_profile="x",
            )
            svc = FingerprintService(paths=paths)
            fp = svc.generate()
        assert fp.config_hash == "missing"

    def test_missing_layout_yields_missing_hash(self, tmp_path):
        paths = self._make_paths(tmp_path)
        # room_layout_file does not exist
        with patch("application.fingerprint_service.build_info") as mock_bi:
            mock_bi.return_value = MagicMock(
                installation_id="x", app_version="x", git_commit="x", runtime_profile="x",
            )
            svc = FingerprintService(paths=paths)
            fp = svc.generate()
        assert fp.layout_hash == "missing"

    def test_generate_output_is_json_serializable(self, tmp_path):
        paths = self._make_paths(tmp_path)
        with patch("application.fingerprint_service.build_info") as mock_bi:
            mock_bi.return_value = MagicMock(
                installation_id="x", app_version="x", git_commit="x", runtime_profile="x",
            )
            svc = FingerprintService(paths=paths)
            fp = svc.generate()
        # Should not raise
        json.dumps(fp.to_dict())

    def test_generate_output_no_secrets(self, tmp_path):
        paths = self._make_paths(tmp_path)
        with patch("application.fingerprint_service.build_info") as mock_bi:
            mock_bi.return_value = MagicMock(
                installation_id="x", app_version="x", git_commit="x", runtime_profile="x",
            )
            svc = FingerprintService(paths=paths)
            fp = svc.generate()
        # Check that secret credentials don't appear in data fields (exclude
        # runtime_paths which contains filesystem paths that may have arbitrary names)
        d = fp.to_dict()
        d_without_paths = {k: v for k, v in d.items() if k != "runtime_paths"}
        text = json.dumps(d_without_paths)
        for forbidden in ("password", "bearer"):
            assert forbidden not in text.lower()


# ── CLI integration ───────────────────────────────────────────────────────────

class TestFingerprintCLI:

    def test_fingerprint_command_exits_zero(self, tmp_path, capsys):
        from runtime.cli import main
        with patch("application.fingerprint_service.build_info") as mock_bi:
            mock_bi.return_value = MagicMock(
                installation_id="khptz-cli-test",
                app_version="3.18.0",
                git_commit="abc1234",
                runtime_profile="production",
            )
            rc = main(["fingerprint"])
        assert rc == 0

    def test_fingerprint_json_flag_produces_valid_json(self, tmp_path, capsys):
        from runtime.cli import main
        with patch("application.fingerprint_service.build_info") as mock_bi:
            mock_bi.return_value = MagicMock(
                installation_id="khptz-cli-test",
                app_version="3.18.0",
                git_commit="abc1234",
                runtime_profile="production",
            )
            rc = main(["fingerprint", "--json"])
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "installation_id" in data
        assert "app_version" in data
        assert "fingerprint_hash" not in data  # hash is computed, not stored in to_dict

    def test_fingerprint_human_output_has_lines(self, capsys):
        from runtime.cli import main
        with patch("application.fingerprint_service.build_info") as mock_bi:
            mock_bi.return_value = MagicMock(
                installation_id="khptz-cli-test",
                app_version="3.18.0",
                git_commit="abc1234",
                runtime_profile="production",
            )
            main(["fingerprint"])
        captured = capsys.readouterr()
        lines = [line for line in captured.out.splitlines() if line.strip()]
        assert len(lines) >= 5

