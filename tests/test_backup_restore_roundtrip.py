#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_backup_restore_roundtrip.py - a backup this product writes must be
# restorable by this product.
#
# BackupService chose what went into the ZIP; RestoreService kept a separate
# allow-list of what it would accept out of one. They drifted: backup started
# including preset_brightness.json, restore never learned about it, and restore
# treats an unlisted member as tampering - so it aborted the WHOLE archive,
# config.yaml and presets included. Every appliance where an operator had
# adjusted preset brightness could no longer be recovered from its own backup,
# and the failure only surfaced during a recovery.
#
# The fix is one shared definition (domain/backup_contract.py). These tests are
# what stops the two sides drifting again, and they deliberately assert the
# ROUND TRIP rather than either list on its own: a matching pair of lists is
# the mechanism, but "the backup restores" is the property that matters.

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from application.backup_service import BackupService
from application.restore_service import RestoreService
from domain.backup_contract import (
    CONFIG_ARCHIVE_NAME,
    DATA_ARCHIVE_NAMES,
    MANIFEST_ARCHIVE_NAME,
    RESTORABLE_ARCHIVE_NAMES,
)


@pytest.fixture
def site(tmp_path: Path):
    """A populated install: config plus every data file the contract names."""
    data = tmp_path / "data"
    data.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text("site:\n  name: Test Room\n", encoding="utf-8")
    for name in DATA_ARCHIVE_NAMES:
        (data / name).write_text('{"marker": "%s"}' % name, encoding="utf-8")
    return {
        "install_dir": tmp_path,
        "data_dir": data,
        "backup_dir": tmp_path / "backups",
        "config_path": config,
    }


def _backup(site) -> BackupService:
    return BackupService(**site)


def _restore(site) -> RestoreService:
    return RestoreService(**site)


class TestRoundTrip:
    def test_a_full_backup_restores(self, site):
        """The property that matters. This failed outright before the shared
        contract: restore rejected preset_brightness.json and aborted."""
        result = _backup(site).create_backup()
        restored = _restore(site).restore(result.path)
        assert sorted(restored.restored) == sorted(RESTORABLE_ARCHIVE_NAMES)
        assert restored.failed == []

    def test_every_member_survives_byte_for_byte(self, site):
        before = {
            name: (site["data_dir"] / name).read_text(encoding="utf-8")
            for name in DATA_ARCHIVE_NAMES
        }
        result = _backup(site).create_backup()
        for name in DATA_ARCHIVE_NAMES:
            (site["data_dir"] / name).write_text("CLOBBERED", encoding="utf-8")
        _restore(site).restore(result.path)
        for name in DATA_ARCHIVE_NAMES:
            assert (site["data_dir"] / name).read_text(encoding="utf-8") == before[name]

    def test_a_partial_install_still_round_trips(self, site):
        """Most real sites have only some of these files. A backup of what
        exists must restore what exists, not fail on what does not."""
        for name in DATA_ARCHIVE_NAMES[2:]:
            (site["data_dir"] / name).unlink()
        result = _backup(site).create_backup()
        restored = _restore(site).restore(result.path)
        assert sorted(restored.restored) == sorted(result.included)

    def test_dry_run_agrees_with_the_real_restore(self, site):
        result = _backup(site).create_backup()
        dry = _restore(site).restore(result.path, dry_run=True)
        real = _restore(site).restore(result.path)
        assert sorted(dry.restored) == sorted(real.restored)


class TestTheTwoSidesCannotDrift:
    """Structural guards. The round-trip tests above prove today's behaviour;
    these make the next added file fail loudly instead of quietly."""

    def test_backup_collects_exactly_the_contract(self, site):
        collected = {name for name, _ in _backup(site)._collect_candidates()}
        assert collected == set(RESTORABLE_ARCHIVE_NAMES)

    def test_restore_accepts_exactly_the_contract(self):
        from application.restore_service import _KNOWN_ARC_NAMES
        assert _KNOWN_ARC_NAMES == RESTORABLE_ARCHIVE_NAMES

    def test_the_manifest_is_not_treated_as_a_restorable_file(self, site):
        """It describes the archive; writing it into data_dir would be a bug."""
        assert MANIFEST_ARCHIVE_NAME not in RESTORABLE_ARCHIVE_NAMES
        result = _backup(site).create_backup()
        with zipfile.ZipFile(result.path) as zf:
            assert MANIFEST_ARCHIVE_NAME in zf.namelist()
        restored = _restore(site).restore(result.path)
        assert MANIFEST_ARCHIVE_NAME not in restored.restored
        assert not (site["data_dir"] / MANIFEST_ARCHIVE_NAME).exists()

    def test_config_is_the_only_member_outside_data_dir(self, site):
        """Everything else resolves against data_dir; config.yaml is the one
        member that lands in config_dir."""
        svc = _restore(site)
        assert svc._resolve_dest(CONFIG_ARCHIVE_NAME) == site["config_path"]
        for name in DATA_ARCHIVE_NAMES:
            assert svc._resolve_dest(name) == site["data_dir"] / name

    def test_an_unknown_member_is_still_rejected(self, site):
        """Widening the contract must not have widened it to everything: an
        archive carrying an unexpected path is still treated as tampering."""
        from application.restore_service import RestoreError

        result = _backup(site).create_backup()
        with zipfile.ZipFile(result.path, "a") as zf:
            zf.writestr("../../etc/passwd", "root:x:0:0")
        with pytest.raises(RestoreError):
            _restore(site).restore(result.path)


class TestAtemMappingIsCoveredNow:
    """The ATEM mapping moved out of config_dir, which `hallptz backup` never
    collected beyond config.yaml. If it were not in the contract, a restore
    would silently drop the operator's ATEM action mapping and their
    PiP-automation setting."""

    def test_mapping_is_part_of_a_backup(self):
        assert "atem_mapping.json" in RESTORABLE_ARCHIVE_NAMES

    def test_mapping_restores_to_the_directory_the_app_reads(self, site):
        from adapters import atem_dispatcher

        result = _backup(site).create_backup()
        (site["data_dir"] / "atem_mapping.json").unlink()
        _restore(site).restore(result.path)
        assert (site["data_dir"] / "atem_mapping.json").exists()
        assert atem_dispatcher._mapping_file().name == "atem_mapping.json"
