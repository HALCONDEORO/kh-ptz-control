#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_power_loss_recovery.py — Power-loss simulation tests for runtime file recovery (#165).

Simulates the scenarios that a Raspberry Pi power cut or SD-card error can produce:
- Leftover .tmp files from an interrupted atomic write
- Partially written (truncated) primary files
- Missing primary file with valid .bak
- Missing primary file with corrupt .bak
- Both primary and backup missing (fresh install scenario)
- Valid backup superseding corrupt primary
- Corrupt file preserved for diagnosis (.corrupt.*)
"""
from __future__ import annotations

import json
from pathlib import Path


from core.json_io import load_json, save_json


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_raw(path: Path, content: str) -> None:
    """Write raw bytes without going through json_io (simulates interrupted write)."""
    path.write_text(content, encoding="utf-8")


def _leftover_tmp(directory: Path, content: str = '{"partial":') -> Path:
    """Create a leftover .tmp file as if an atomic write was interrupted mid-write."""
    tmp = directory / ".tmp_interrupted.json"
    tmp.write_text(content, encoding="utf-8")
    return tmp


# ── Scenario: leftover .tmp files ────────────────────────────────────────────

class TestLeftoverTmpFiles:

    def test_leftover_tmp_does_not_affect_primary_load(self, tmp_path):
        """A .tmp file left by an interrupted write must not corrupt load_json."""
        f = tmp_path / "data.json"
        save_json(f, {"good": True})
        _leftover_tmp(tmp_path, '{"bad": true, "partial":')

        result = load_json(f)
        assert result == {"good": True}

    def test_next_save_overwrites_leftover_tmp(self, tmp_path):
        """save_json must succeed even if a .tmp_* file already exists in the directory."""
        _leftover_tmp(tmp_path)
        f = tmp_path / "data.json"
        ok = save_json(f, {"after_recovery": True})
        assert ok
        assert load_json(f) == {"after_recovery": True}

    def test_load_missing_primary_with_leftover_tmp_returns_default(self, tmp_path):
        """If primary is missing and only a .tmp exists, load_json returns the default."""
        _leftover_tmp(tmp_path)
        f = tmp_path / "data.json"
        result = load_json(f, default={"fallback": True})
        assert result == {"fallback": True}


# ── Scenario: truncated / partially written primary file ─────────────────────

class TestTruncatedPrimaryFile:

    def test_truncated_primary_uses_bak_if_present(self, tmp_path):
        """If power is cut mid-write, the .bak is used for recovery.

        json_io.save_json() copies the *current* primary to .bak before overwriting.
        So after two saves: primary=v2, .bak=v1.
        If the primary is then truncated, load_json recovers from .bak (v1).
        """
        f = tmp_path / "data.json"
        save_json(f, {"version": 1})     # first save → primary=v1, no .bak
        save_json(f, {"version": 2})     # second save → .bak=v1, primary=v2

        # Simulate truncated primary (e.g. power cut during a third write attempt)
        _write_raw(f, '{"version": 3, "key":')  # truncated

        result = load_json(f, default=None)
        # .bak contains v1 (the version before v2 overwrote it)
        assert result == {"version": 1}

    def test_truncated_primary_preserved_as_corrupt_file(self, tmp_path):
        """Corrupt files must be renamed to .corrupt.* for diagnosis, not deleted."""
        f = tmp_path / "data.json"
        save_json(f, {"x": 1})
        _write_raw(f, '{"incomplete":')  # truncate

        load_json(f, default=None)

        corrupt_files = list(tmp_path.glob("*.corrupt.*"))
        assert len(corrupt_files) == 1, "Expected exactly one .corrupt.* diagnostic file"

    def test_truncated_primary_no_bak_returns_default(self, tmp_path):
        """Without a .bak, load_json falls back to the provided default."""
        f = tmp_path / "data.json"
        _write_raw(f, '{"truncated":')  # no prior save → no .bak

        result = load_json(f, default={"safe": "default"})
        assert result == {"safe": "default"}


# ── Scenario: missing primary with backup ─────────────────────────────────────

class TestMissingPrimaryWithBackup:

    def test_primary_deleted_bak_valid(self, tmp_path):
        """If primary is deleted but .bak is valid, load_json returns the default (primary not found)."""
        f = tmp_path / "data.json"
        bak = f.with_suffix(".bak")

        # Simulate: last good state in .bak, primary deleted (e.g. corruption mid-save)
        bak.write_text(json.dumps({"recovered": True}), encoding="utf-8")

        result = load_json(f, default={"fallback": True})
        # Primary doesn't exist → json_io returns default (doesn't proactively check .bak)
        assert result == {"fallback": True}

    def test_save_then_delete_primary_next_load_uses_default(self, tmp_path):
        """After deleting the primary, next load correctly returns the default."""
        f = tmp_path / "data.json"
        save_json(f, {"v": 1})
        save_json(f, {"v": 2})  # .bak now has {"v": 1}
        f.unlink()

        result = load_json(f, default={"empty": True})
        assert result == {"empty": True}


# ── Scenario: both primary and backup missing ─────────────────────────────────

class TestBothFilesMissing:

    def test_returns_default_when_nothing_exists(self, tmp_path):
        """Fresh install: no primary, no .bak. load_json must return the default."""
        f = tmp_path / "never_created.json"
        result = load_json(f, default={"fresh": True})
        assert result == {"fresh": True}

    def test_returns_none_default_when_nothing_exists(self, tmp_path):
        """Default of None works as a sentinel for "file does not exist yet"."""
        f = tmp_path / "never_created.json"
        assert load_json(f) is None


# ── Scenario: corrupt primary, corrupt backup ─────────────────────────────────

class TestBothFilesCorrupt:

    def test_corrupt_primary_and_bak_return_default(self, tmp_path):
        """If both files are unreadable, load_json returns the provided default."""
        f = tmp_path / "data.json"
        bak = f.with_suffix(".bak")
        _write_raw(f, "{{broken json")
        _write_raw(bak, "{{also broken")

        result = load_json(f, default={"last_resort": True})
        assert result == {"last_resort": True}

    def test_corrupt_both_logs_warning(self, tmp_path, caplog):
        """A clear warning must appear when both files are unreadable."""
        import logging
        f = tmp_path / "data.json"
        bak = f.with_suffix(".bak")
        _write_raw(f, "{bad")
        _write_raw(bak, "{also bad")

        with caplog.at_level(logging.WARNING):
            load_json(f, default=None)

        assert any("corrupt" in r.message.lower() or "unreadable" in r.message.lower()
                   or "backup" in r.message.lower()
                   for r in caplog.records), \
            "Expected a warning about corrupt/unreadable files"


# ── Scenario: atomic write guarantees ────────────────────────────────────────

class TestAtomicWriteGuarantees:

    def test_no_partial_tmp_left_after_successful_save(self, tmp_path):
        """A successful save must leave no .tmp_* files behind."""
        f = tmp_path / "data.json"
        save_json(f, {"clean": True})

        tmp_files = list(tmp_path.glob(".tmp_*"))
        assert not tmp_files, f"Unexpected .tmp files: {tmp_files}"

    def test_save_failure_leaves_no_tmp_file(self, tmp_path):
        """If serialisation fails, no .tmp file should be left."""
        f = tmp_path / "data.json"
        save_json(f, object())  # not serialisable → will fail

        tmp_files = list(tmp_path.glob(".tmp_*"))
        assert not tmp_files, f"Unexpected .tmp files after failed save: {tmp_files}"

    def test_original_preserved_when_save_fails(self, tmp_path):
        """A failed save must not destroy the existing primary file."""
        f = tmp_path / "data.json"
        save_json(f, {"original": True})
        save_json(f, object())  # fails

        result = load_json(f)
        assert result == {"original": True}

