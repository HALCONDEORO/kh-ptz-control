# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for core.atomic_write — shared atomic persistence helper (#803)."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from core.atomic_write import write_bytes_atomic, write_text_atomic


class TestWriteBytesAtomic:

    def test_creates_file_with_correct_content(self, tmp_path):
        dest = tmp_path / "out.bin"
        write_bytes_atomic(dest, b"hello")
        assert dest.read_bytes() == b"hello"

    def test_replaces_existing_file(self, tmp_path):
        dest = tmp_path / "out.bin"
        dest.write_bytes(b"old")
        write_bytes_atomic(dest, b"new")
        assert dest.read_bytes() == b"new"

    def test_creates_parent_directories(self, tmp_path):
        dest = tmp_path / "a" / "b" / "c.bin"
        write_bytes_atomic(dest, b"data")
        assert dest.exists()

    def test_no_tmp_file_left_on_success(self, tmp_path):
        dest = tmp_path / "out.bin"
        write_bytes_atomic(dest, b"data")
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == [], f"leftover tmp files: {leftovers}"

    def test_preserves_existing_file_on_write_failure(self, tmp_path):
        dest = tmp_path / "out.bin"
        dest.write_bytes(b"original")

        with patch("core.atomic_write.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                write_bytes_atomic(dest, b"corrupt")

        assert dest.read_bytes() == b"original"

    def test_no_tmp_file_left_on_failure(self, tmp_path):
        dest = tmp_path / "out.bin"
        with patch("core.atomic_write.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                write_bytes_atomic(dest, b"data")
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == [], f"tmp file not cleaned up: {leftovers}"

    def test_writes_empty_bytes(self, tmp_path):
        dest = tmp_path / "empty.bin"
        write_bytes_atomic(dest, b"")
        assert dest.read_bytes() == b""


class TestHardening:
    """0600 temp window, fsync durability and explicit mode (#wizard-foundation)."""

    def test_fsync_called_on_success(self, tmp_path):
        dest = tmp_path / "out.bin"
        with patch("core.atomic_write.os.fsync") as fsync:
            write_bytes_atomic(dest, b"data")
        assert fsync.call_count >= 1, "expected the temp file to be fsync'd before rename"

    def test_no_tmp_left_when_open_fails(self, tmp_path):
        dest = tmp_path / "out.bin"
        with patch("core.atomic_write.os.open", side_effect=OSError("no fd")):
            with pytest.raises(OSError):
                write_bytes_atomic(dest, b"data")
        assert list(tmp_path.glob("*.tmp")) == []

    def test_stale_tmp_is_overwritten(self, tmp_path):
        dest = tmp_path / "out.bin"
        stale = dest.with_suffix(dest.suffix + ".tmp")
        stale.write_bytes(b"leftover from a crash")
        write_bytes_atomic(dest, b"fresh")
        assert dest.read_bytes() == b"fresh"
        assert not stale.exists()

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
    def test_mode_applied_to_destination(self, tmp_path):
        import stat
        dest = tmp_path / "secret.enc"
        write_bytes_atomic(dest, b"data", mode=0o600)
        assert stat.S_IMODE(dest.stat().st_mode) == 0o600

    @pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
    def test_default_temp_is_private(self, tmp_path):
        # Without an explicit mode the file lands at the private 0600 temp mode.
        import stat
        dest = tmp_path / "out.bin"
        write_bytes_atomic(dest, b"data")
        assert stat.S_IMODE(dest.stat().st_mode) == 0o600

    def test_mode_param_is_noop_safe_everywhere(self, tmp_path):
        dest = tmp_path / "out.txt"
        write_text_atomic(dest, "hello", mode=0o640)
        assert dest.read_text(encoding="utf-8") == "hello"


class TestWriteTextAtomic:

    def test_creates_file_with_correct_content(self, tmp_path):
        dest = tmp_path / "out.txt"
        write_text_atomic(dest, "hello")
        assert dest.read_text(encoding="utf-8") == "hello"

    def test_encodes_unicode_correctly(self, tmp_path):
        dest = tmp_path / "unicode.txt"
        text = "cámara — VISCA-over-IP ✓"
        write_text_atomic(dest, text)
        assert dest.read_text(encoding="utf-8") == text

    def test_replaces_existing_file(self, tmp_path):
        dest = tmp_path / "out.txt"
        dest.write_text("old", encoding="utf-8")
        write_text_atomic(dest, "new")
        assert dest.read_text(encoding="utf-8") == "new"

    def test_preserves_existing_file_on_failure(self, tmp_path):
        dest = tmp_path / "out.txt"
        dest.write_text("original", encoding="utf-8")
        with patch("core.atomic_write.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                write_text_atomic(dest, "corrupt")
        assert dest.read_text(encoding="utf-8") == "original"


class TestConfigWriterUsesAtomicWrite:
    """patch_config_yaml must use write_text_atomic (atomic, never write_text direct)."""

    def test_config_writer_uses_atomic_write(self, tmp_path):
        import yaml
        from config.writer import patch_config_yaml

        config = tmp_path / "config.yaml"
        config.write_text(
            yaml.dump({"cameras": [{"ip": "1.2.3.4", "visca_id": "81"}]}),
            encoding="utf-8",
        )

        atomic_calls = []
        original_replace = os.replace

        def spy_replace(src, dst):
            atomic_calls.append((str(src), str(dst)))
            return original_replace(src, dst)

        with patch("core.atomic_write.os.replace", side_effect=spy_replace):
            patch_config_yaml(config, cam_index=0, cam_ip="5.6.7.8")

        assert any(str(config) in dst for _, dst in atomic_calls), \
            "patch_config_yaml did not use atomic write (os.replace not called for config path)"
        assert config.exists()
        raw = yaml.safe_load(config.read_text(encoding="utf-8"))
        assert raw["cameras"][0]["ip"] == "5.6.7.8"

    def test_config_writer_preserves_file_on_failure(self, tmp_path):
        import yaml
        from config.writer import patch_config_yaml

        config = tmp_path / "config.yaml"
        original_yaml = yaml.dump({"cameras": [{"ip": "1.2.3.4", "visca_id": "81"}]})
        config.write_text(original_yaml, encoding="utf-8")

        with patch("core.atomic_write.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                patch_config_yaml(config, cam_index=0, cam_ip="5.6.7.8")

        assert config.read_text(encoding="utf-8") == original_yaml


class TestPresetVerificationWriterUsesAtomicWrite:
    """PresetVerificationService._save must leave no .tmp on failure."""

    def test_preset_writer_no_tmp_on_failure(self, tmp_path):
        from application.preset_verification_service import PresetVerificationService

        svc = PresetVerificationService(tmp_path / "verifications.json")
        with patch("core.atomic_write.os.replace", side_effect=OSError("disk full")):
            result = svc._save({})

        assert result is False
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == [], f"tmp file not cleaned up: {leftovers}"
