#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_atem_mapping_location.py - the ATEM mapping lives where the service
# can actually write it.
#
# It used to resolve to /etc/hallptz/atem_mapping.json. On a product install that
# directory is root:hallptz 2751 and the service runs as User=hallptz, so every save
# failed with EACCES - and the failure was swallowed as a log warning. The
# operator toggled PiP automation in the UI, saw no error, and the change was
# gone after the next restart. It also broke two written rules: config_dir is
# admin-write only (docs/RUNTIME_PATH_CONTRACT.md) and `hallptz backup` only ever
# collects config.yaml out of config_dir, so the file was outside backups too.

from __future__ import annotations

import json

import pytest

from adapters import atem_dispatcher

# conftest installs an autouse fixture that redirects _mapping_file to a temp
# path, so no test can write the real /etc or /var. These tests are ABOUT that
# resolution, so they need the genuine implementation - captured here at import
# time, which runs before any fixture has replaced it.
_REAL_MAPPING_FILE = atem_dispatcher._mapping_file

# A mapping written on a site whose desktop locale is Latin-1, not UTF-8.
# Encoded rather than spelled as escapes so the intent is visible: these
# are real bytes a real install can contain, not a synthetic blob.
_LATIN1_MAPPING = '{"1": "platform_home", "note": "cámara"}'.encode("latin-1")


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """Point the resolver at a temp config_dir and data_dir."""
    config_dir = tmp_path / "etc"
    data_dir = tmp_path / "var-lib"
    config_dir.mkdir()
    data_dir.mkdir()
    monkeypatch.setattr(atem_dispatcher, "_mapping_file", _REAL_MAPPING_FILE)
    monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("HALLPTZ_DATA_DIR", str(data_dir))
    return config_dir, data_dir


class TestLocation:
    def test_mapping_resolves_into_the_data_directory(self, dirs):
        config_dir, data_dir = dirs
        assert atem_dispatcher._mapping_file() == data_dir / "atem_mapping.json"

    def test_mapping_is_not_in_the_config_directory(self, dirs):
        """config_dir is admin-write only; the service cannot write there."""
        config_dir, _ = dirs
        assert atem_dispatcher._mapping_file().parent != config_dir

    def test_the_legacy_location_is_still_known(self, dirs):
        config_dir, _ = dirs
        assert atem_dispatcher._legacy_mapping_file() == config_dir / "atem_mapping.json"


class TestMigration:
    def test_a_pre_move_mapping_is_carried_over(self, dirs):
        config_dir, data_dir = dirs
        (config_dir / "atem_mapping.json").write_text(
            json.dumps({"1": "platform_home"}), encoding="utf-8"
        )
        mapping, _ = atem_dispatcher._load_mapping()
        assert mapping["1"] == "platform_home"
        assert (data_dir / "atem_mapping.json").exists(), "migration did not run"

    def test_migration_never_deletes_the_original(self, dirs):
        """A rollback to an older release must still find the file it reads."""
        config_dir, _ = dirs
        legacy = config_dir / "atem_mapping.json"
        legacy.write_text(json.dumps({"2": "comments_home"}), encoding="utf-8")
        atem_dispatcher._load_mapping()
        assert legacy.exists()

    def test_an_existing_new_file_is_never_overwritten(self, dirs):
        """Current settings beat a stale pre-move copy."""
        config_dir, data_dir = dirs
        (config_dir / "atem_mapping.json").write_text(
            json.dumps({"1": "platform_home"}), encoding="utf-8"
        )
        (data_dir / "atem_mapping.json").write_text(
            json.dumps({"1": "comments_home"}), encoding="utf-8"
        )
        mapping, _ = atem_dispatcher._load_mapping()
        assert mapping["1"] == "comments_home"

    def test_pip_automation_flag_survives_the_move(self, dirs):
        config_dir, _ = dirs
        (config_dir / "atem_mapping.json").write_text(
            json.dumps({"pip_automation_enabled": False, "1": "pip_on"}),
            encoding="utf-8",
        )
        _, pip_enabled = atem_dispatcher._load_mapping()
        assert pip_enabled is False

    def test_an_unwritable_data_dir_falls_back_to_reading_in_place(
        self, dirs, monkeypatch
    ):
        """If the migration cannot write, the appliance must still use the
        operator's mapping rather than silently reverting to defaults."""
        config_dir, _ = dirs
        (config_dir / "atem_mapping.json").write_text(
            json.dumps({"3": "pip_off"}), encoding="utf-8"
        )

        def _refuse(*_a, **_k):
            raise OSError("read-only file system")

        monkeypatch.setattr(atem_dispatcher, "write_text_atomic", _refuse)
        mapping, _ = atem_dispatcher._load_mapping()
        assert mapping["3"] == "pip_off"


class TestACorruptLegacyFileCannotStopTheApp:
    """_load_mapping already treated an unreadable mapping as "use the
    defaults" - UnicodeDecodeError is named in its own handler. The migration
    added in front of it decoded the legacy file too, and UnicodeDecodeError is
    a ValueError, not an OSError: it escaped the migration AND _load_mapping,
    so a pre-move mapping written under a non-UTF-8 locale could stop
    ATEMDispatcher from being constructed at all. A migration must never be
    able to prevent the application from starting.
    """

    def test_non_utf8_legacy_bytes_do_not_raise(self, dirs):
        config_dir, _ = dirs
        (config_dir / "atem_mapping.json").write_bytes(
            _LATIN1_MAPPING
        )
        mapping, pip_enabled = atem_dispatcher._load_mapping()
        assert mapping == dict(atem_dispatcher._DEFAULT_MAPPING)
        assert pip_enabled is True

    def test_the_bytes_are_copied_verbatim_not_transcoded(self, dirs):
        """Copying bytes rather than decoding means the loader makes exactly
        the same decision about the migrated file as it would have made about
        the original."""
        config_dir, data_dir = dirs
        raw = _LATIN1_MAPPING
        (config_dir / "atem_mapping.json").write_bytes(raw)
        atem_dispatcher._load_mapping()
        assert (data_dir / "atem_mapping.json").read_bytes() == raw

    def test_a_corrupt_legacy_file_is_still_never_deleted(self, dirs):
        config_dir, _ = dirs
        legacy = config_dir / "atem_mapping.json"
        legacy.write_bytes(bytes([0xFF, 0xFE]) + b" not json at all")
        atem_dispatcher._load_mapping()
        assert legacy.exists()

    def test_malformed_json_still_falls_back(self, dirs):
        config_dir, _ = dirs
        (config_dir / "atem_mapping.json").write_text("{ not json", encoding="utf-8")
        mapping, _ = atem_dispatcher._load_mapping()
        assert mapping == dict(atem_dispatcher._DEFAULT_MAPPING)


class TestPersistence:
    def test_saving_writes_to_the_data_directory(self, dirs):
        _, data_dir = dirs
        atem_dispatcher._save_mapping({"1": "platform_home"})
        written = json.loads(
            (data_dir / "atem_mapping.json").read_text(encoding="utf-8")
        )
        assert written == {"1": "platform_home"}

    def test_a_saved_mapping_reads_back(self, dirs):
        """The regression in one line: the operator changes a setting and it
        is still there on the next start."""
        atem_dispatcher._save_mapping({"1": "pip_on"}, pip_automation_enabled=False)
        mapping, pip_enabled = atem_dispatcher._load_mapping()
        assert mapping["1"] == "pip_on"
        assert pip_enabled is False

    def test_saving_creates_a_missing_data_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(atem_dispatcher, "_mapping_file", _REAL_MAPPING_FILE)
        monkeypatch.setenv("HALLPTZ_DATA_DIR", str(tmp_path / "absent"))
        atem_dispatcher._save_mapping({"1": "none"})
        assert (tmp_path / "absent" / "atem_mapping.json").exists()

    def test_a_failed_save_never_raises(self, dirs, monkeypatch):
        """Persisting a preference must not be able to take the GUI down."""
        def _refuse(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(atem_dispatcher, "write_text_atomic", _refuse)
        atem_dispatcher._save_mapping({"1": "none"})  # must not raise
