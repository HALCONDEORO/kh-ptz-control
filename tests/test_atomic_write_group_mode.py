#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_atomic_write_group_mode.py — restore and import stay readable (#885)
#
# core.atomic_write creates files privately (0600). Correct for secrets, wrong
# for shared runtime data once the service and a session-owned GUI both use
# /var/lib/hallptz through the hallptz group:
#
#   - `hallptz restore` writes every file 0600 as whoever ran it, so the other
#     identity cannot read the restored presets, seats or layout;
#   - layout import and the preset verification report have the same problem.
#
# Restore is the recovery path, so this failed exactly when something had
# already gone wrong. The policy now lives in group_shared_mode() and is applied
# whenever a caller does not ask for a specific mode — secrets still pass 0o600
# explicitly and are unaffected.
#
# These assert the decision rather than resulting mode bits: Windows reports
# 0666 for everything and cannot express the distinction.

from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import atomic_write


class _Dir:
    def __init__(self, mode: int):
        self._mode = mode

    def stat(self):
        return SimpleNamespace(st_mode=self._mode)


class TestGroupSharedMode:
    def test_group_writable_directory_is_shared(self):
        """2770 — what install.sh sets for --gui-mode user."""
        assert atomic_write.group_shared_mode(_Dir(0o42770)) == 0o660

    def test_plain_group_writable_directory_is_shared(self):
        assert atomic_write.group_shared_mode(_Dir(0o40770)) == 0o660

    def test_private_directory_keeps_the_default(self):
        """0750 — system mode. Returning None leaves 0600 untouched, so the
        desktop user gains no access it does not already have."""
        assert atomic_write.group_shared_mode(_Dir(0o40750)) is None

    def test_group_readable_only_is_not_shared(self):
        assert atomic_write.group_shared_mode(_Dir(0o40750 | stat.S_IRGRP)) is None

    def test_unreadable_directory_keeps_the_default(self):
        class _Broken:
            def stat(self):
                raise OSError("gone")

        assert atomic_write.group_shared_mode(_Broken()) is None


class TestWriteAppliesThePolicy:
    """The bug was that write_bytes_atomic never consulted the directory."""

    def _fchmod_modes(self, tmp_path: Path, dir_mode: int, **kwargs) -> list[int]:
        with patch.object(atomic_write, "group_shared_mode", return_value=(
            0o660 if dir_mode & stat.S_IWGRP else None
        )):
            with patch.object(atomic_write.os, "fchmod") as fchmod:
                atomic_write.write_bytes_atomic(tmp_path / "f.bin", b"x", **kwargs)
                return [c.args[1] for c in fchmod.call_args_list]

    def test_shared_directory_yields_group_access(self, tmp_path):
        assert self._fchmod_modes(tmp_path, 0o40770) == [0o660]

    def test_private_directory_leaves_the_default(self, tmp_path):
        assert self._fchmod_modes(tmp_path, 0o40750) == []

    def test_explicit_mode_always_wins(self, tmp_path):
        """Secrets pass 0o600 and must never be widened by the policy."""
        assert self._fchmod_modes(tmp_path, 0o40770, mode=0o600) == [0o600]

    def test_secret_writer_still_requests_private_mode(self):
        """provision_handoff writes the wizard's privileged request."""
        source = (
            Path(__file__).resolve().parent.parent
            / "application" / "provision_handoff.py"
        ).read_text(encoding="utf-8")
        assert "mode=0o600" in source


class TestWriteContractIsIntact:
    def test_round_trip(self, tmp_path):
        dest = tmp_path / "data.bin"
        atomic_write.write_bytes_atomic(dest, b"hello")
        assert dest.read_bytes() == b"hello"

    def test_text_round_trip(self, tmp_path):
        dest = tmp_path / "data.txt"
        atomic_write.write_text_atomic(dest, "hola — adios")
        assert dest.read_text(encoding="utf-8") == "hola — adios"

    def test_no_temp_left_behind(self, tmp_path):
        dest = tmp_path / "data.bin"
        atomic_write.write_bytes_atomic(dest, b"x")
        assert not list(tmp_path.glob("*.tmp"))

    def test_existing_file_is_not_corrupted_on_failure(self, tmp_path):
        dest = tmp_path / "data.bin"
        atomic_write.write_bytes_atomic(dest, b"original")
        with patch.object(atomic_write.os, "replace", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                atomic_write.write_bytes_atomic(dest, b"replacement")
        assert dest.read_bytes() == b"original"
        assert not list(tmp_path.glob("*.tmp"))


class TestRestorePathUsesIt:
    def test_restore_writes_without_forcing_a_private_mode(self):
        """Passing mode=0o600 here would defeat the policy."""
        source = (
            Path(__file__).resolve().parent.parent
            / "application" / "restore_service.py"
        ).read_text(encoding="utf-8")
        assert "write_bytes_atomic(dest, data)" in source
