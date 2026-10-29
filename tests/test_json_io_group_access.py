#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_json_io_group_access.py — data files stay reachable across GUI modes (#885)
#
# tempfile.mkstemp always creates 0600 and os.replace preserves it, so every
# JSON data file is readable only by whoever wrote it. That is fine while one
# identity owns the data, and silently broken once two share it through the
# `khptz` group:
#
#   - switching to --gui-mode user leaves every existing /var/lib/khptz file
#     0600 khptz:khptz, so the GUI starts with no presets, seats or layout;
#   - files the GUI then writes are 0600 <desktop-user>:khptz, so `khptz doctor`,
#     `khptz backup` and the support bundle cannot read them.
#
# The fix mirrors the directory's intent onto the file. These tests assert the
# decision rather than the resulting filesystem bits, so they are meaningful on
# any OS — Windows reports 0666 for everything and cannot express the
# distinction at all.

from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core import json_io


class _Dir:
    """Stand-in for a directory whose stat() reports a chosen mode."""

    def __init__(self, mode: int):
        self._mode = mode

    def stat(self):
        return SimpleNamespace(st_mode=self._mode)


class TestGroupAccessDecision:
    def _chmod_calls(self, dir_mode: int) -> list:
        with patch.object(json_io.os, "chmod") as chmod:
            json_io._apply_group_access("/tmp/whatever.tmp", _Dir(dir_mode))
            return chmod.call_args_list

    def test_group_writable_directory_grants_group_access(self):
        """2770 — the mode install.sh sets for --gui-mode user."""
        calls = self._chmod_calls(0o42770)
        assert calls, "no chmod issued for a group-writable directory"
        assert calls[0].args[1] == 0o660

    def test_plain_group_writable_directory_also_grants_it(self):
        calls = self._chmod_calls(0o40770)
        assert calls and calls[0].args[1] == 0o660

    def test_non_group_writable_directory_is_left_alone(self):
        """0750 — the system-mode default. Files must stay 0600: widening them
        here would hand the desktop user write access it does not have today."""
        assert self._chmod_calls(0o40750) == []

    def test_private_directory_is_left_alone(self):
        assert self._chmod_calls(0o40700) == []

    def test_group_readable_but_not_writable_is_left_alone(self):
        """Read-only group access is not the signal; only g+w is."""
        assert self._chmod_calls(0o40750 | stat.S_IRGRP) == []


class TestNeverBreaksTheWrite:
    """A permissions problem must not lose the operator's data."""

    def test_chmod_failure_is_swallowed(self):
        with patch.object(json_io.os, "chmod", side_effect=OSError("read-only fs")):
            json_io._apply_group_access("/tmp/x", _Dir(0o42770))  # must not raise

    def test_stat_failure_is_swallowed(self):
        class _Broken:
            def stat(self):
                raise OSError("gone")

        json_io._apply_group_access("/tmp/x", _Broken())  # must not raise


class TestSaveJsonStillWorks:
    """The hook must not disturb the atomic-write contract."""

    def test_round_trip(self, tmp_path: Path):
        target = tmp_path / "data.json"
        assert json_io.save_json(target, {"seat": 3}) is True
        assert json_io.load_json(target, default=None) == {"seat": 3}

    def test_no_temp_file_left_behind(self, tmp_path: Path):
        target = tmp_path / "data.json"
        json_io.save_json(target, {"a": 1})
        assert not list(tmp_path.glob(".tmp_*"))

    def test_write_succeeds_even_if_chmod_fails(self, tmp_path: Path):
        target = tmp_path / "data.json"
        with patch.object(json_io.os, "chmod", side_effect=OSError):
            assert json_io.save_json(target, {"a": 1}) is True
        assert json_io.load_json(target, default=None) == {"a": 1}


class TestInstallerRepairsExistingFiles:
    """Fixing new writes is not enough — a system-mode install leaves a tree of
    0600 files behind, and the GUI would start empty without them."""

    def test_installer_relaxes_existing_runtime_data(self):
        installer = (
            Path(__file__).resolve().parent.parent
            / "runtime" / "installer" / "install.sh"
        ).read_text(encoding="utf-8")
        assert "chmod g+rw" in installer
        assert "chmod g+rwxs" in installer

    @pytest.mark.parametrize("path", ["DATA_DIR", "LOG_DIR", "BACKUP_DIR"])
    def test_covers_every_runtime_directory(self, path):
        installer = (
            Path(__file__).resolve().parent.parent
            / "runtime" / "installer" / "install.sh"
        ).read_text(encoding="utf-8")
        assert path in installer
