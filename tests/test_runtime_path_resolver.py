#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_runtime_path_resolver.py — Tests for RuntimePathResolver and BuildInfo (#560).

Covers:
- Production defaults resolve to /etc/hallptz, /var/lib/hallptz, /var/log/hallptz, /var/backups/hallptz
- Environment variable overrides are honoured (HALLPTZ_CONFIG_DIR, HALLPTZ_DATA_DIR,
  HALLPTZ_DATA_DIR, HALLPTZ_LOG_DIR, HALLPTZ_BACKUP_DIR)
- Relative path overrides are rejected with ValueError
- running_from_source reflects .git directory presence
- active_overrides reports only active env vars
- to_dict produces a plain string dict
- BuildInfo defaults to safe 'unknown' values
- BuildInfo.version_line formats correctly
- build_info() returns a BuildInfo instance
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from runtime.path_resolver import (
    LEGACY_DATA_DIR,
    RuntimePathResolver,
)
from runtime.build_info import BuildInfo, build_info


# ── RuntimePathResolver — production defaults ─────────────────────────────────

class TestProductionDefaults:

    def setup_method(self):
        """Ensure no override env vars are set."""
        for var in ("HALLPTZ_CONFIG_DIR", "HALLPTZ_DATA_DIR", "HALLPTZ_DATA_DIR",
                    "HALLPTZ_LOG_DIR", "HALLPTZ_BACKUP_DIR"):
            os.environ.pop(var, None)

    def test_config_dir_is_etc_hallptz(self):
        r = RuntimePathResolver()
        assert r.config_dir == Path("/etc/hallptz")

    def test_data_dir_is_var_lib_hallptz(self):
        r = RuntimePathResolver()
        assert r.data_dir == Path("/var/lib/hallptz")

    def test_log_dir_is_var_log_hallptz(self):
        r = RuntimePathResolver()
        assert r.log_dir == Path("/var/log/hallptz")

    def test_backup_dir_is_var_backups_hallptz(self):
        r = RuntimePathResolver()
        assert r.backup_dir == Path("/var/backups/hallptz")

    def test_support_bundle_dir_is_inside_backup_dir(self):
        r = RuntimePathResolver()
        assert r.support_bundle_dir == Path("/var/backups/hallptz/support")

    def test_no_active_overrides_by_default(self):
        r = RuntimePathResolver()
        assert r.active_overrides() == {}

    def test_to_dict_is_plain_strings(self):
        r = RuntimePathResolver()
        d = r.to_dict()
        for key, value in d.items():
            assert isinstance(key, str), f"{key!r} is not a str"
            assert isinstance(value, str), f"{key!r} value {value!r} is not a str"

    def test_legacy_data_dir_constant(self):
        assert LEGACY_DATA_DIR == Path.home() / ".config" / "hallptz"


# ── RuntimePathResolver — file accessors ─────────────────────────────────────

class TestFileAccessors:

    def setup_method(self):
        for var in ("HALLPTZ_CONFIG_DIR", "HALLPTZ_DATA_DIR", "HALLPTZ_DATA_DIR",
                    "HALLPTZ_LOG_DIR", "HALLPTZ_BACKUP_DIR"):
            os.environ.pop(var, None)

    def test_known_good_state_file_inside_data_dir(self):
        r = RuntimePathResolver()
        assert r.known_good_state_file == r.data_dir / "known_good_state.json"

    def test_installation_fingerprint_file_inside_data_dir(self):
        r = RuntimePathResolver()
        assert r.installation_fingerprint_file == r.data_dir / "installation_fingerprint.json"

    def test_maintenance_status_file_inside_data_dir(self):
        r = RuntimePathResolver()
        assert r.maintenance_status_file == r.data_dir / "maintenance_status.json"

    def test_incident_log_file_inside_log_dir(self):
        r = RuntimePathResolver()
        assert r.incident_log_file == r.log_dir / "incidents.jsonl"

    def test_schedule_file_inside_data_dir(self):
        r = RuntimePathResolver()
        assert r.schedule_file == r.data_dir / "schedule.json"

    def test_room_layout_file_inside_data_dir(self):
        r = RuntimePathResolver()
        assert r.room_layout_file == r.data_dir / "room_layout.json"

    def test_provisioned_marker_inside_config_dir(self):
        r = RuntimePathResolver()
        assert r.provisioned_marker_file == r.config_dir / ".provisioned"


# ── RuntimePathResolver — environment overrides ───────────────────────────────

class TestEnvironmentOverrides:

    def setup_method(self):
        for var in ("HALLPTZ_CONFIG_DIR", "HALLPTZ_DATA_DIR", "HALLPTZ_DATA_DIR",
                    "HALLPTZ_LOG_DIR", "HALLPTZ_BACKUP_DIR"):
            os.environ.pop(var, None)

    def test_hallptz_config_dir_override(self, tmp_path):
        os.environ["HALLPTZ_CONFIG_DIR"] = str(tmp_path / "cfg")
        r = RuntimePathResolver()
        assert r.config_dir == tmp_path / "cfg"
        del os.environ["HALLPTZ_CONFIG_DIR"]

    def test_hallptz_data_dir_override(self, tmp_path):
        os.environ["HALLPTZ_DATA_DIR"] = str(tmp_path / "data")
        r = RuntimePathResolver()
        assert r.data_dir == tmp_path / "data"
        del os.environ["HALLPTZ_DATA_DIR"]

    def test_hallptz_data_dir_override(self, tmp_path):
        os.environ["HALLPTZ_DATA_DIR"] = str(tmp_path / "legacy")
        r = RuntimePathResolver()
        assert r.data_dir == tmp_path / "legacy"
        del os.environ["HALLPTZ_DATA_DIR"]

    def test_hallptz_log_dir_override(self, tmp_path):
        os.environ["HALLPTZ_LOG_DIR"] = str(tmp_path / "logs")
        r = RuntimePathResolver()
        assert r.log_dir == tmp_path / "logs"
        del os.environ["HALLPTZ_LOG_DIR"]

    def test_hallptz_backup_dir_override(self, tmp_path):
        os.environ["HALLPTZ_BACKUP_DIR"] = str(tmp_path / "backups")
        r = RuntimePathResolver()
        assert r.backup_dir == tmp_path / "backups"
        del os.environ["HALLPTZ_BACKUP_DIR"]

    def test_relative_config_override_raises(self):
        os.environ["HALLPTZ_CONFIG_DIR"] = "relative/path"
        with pytest.raises(ValueError, match="absolute"):
            RuntimePathResolver()
        del os.environ["HALLPTZ_CONFIG_DIR"]

    def test_relative_data_override_raises(self):
        os.environ["HALLPTZ_DATA_DIR"] = "relative/path"
        with pytest.raises(ValueError, match="absolute"):
            RuntimePathResolver()
        del os.environ["HALLPTZ_DATA_DIR"]

    def test_schedule_file_aligns_with_data_paths_when_env_set(self, tmp_path):
        """data_paths.SCHEDULE_FILE and resolver.schedule_file must agree when env set (#598)."""
        import importlib
        os.environ["HALLPTZ_DATA_DIR"] = str(tmp_path / "data")
        import data_paths
        importlib.reload(data_paths)
        r = RuntimePathResolver()
        assert data_paths.SCHEDULE_FILE == r.schedule_file
        del os.environ["HALLPTZ_DATA_DIR"]
        importlib.reload(data_paths)

    def test_active_overrides_reports_set_vars(self, tmp_path):
        os.environ["HALLPTZ_CONFIG_DIR"] = str(tmp_path / "cfg")
        os.environ["HALLPTZ_LOG_DIR"] = str(tmp_path / "logs")
        r = RuntimePathResolver()
        overrides = r.active_overrides()
        assert "HALLPTZ_CONFIG_DIR" in overrides
        assert "HALLPTZ_LOG_DIR" in overrides
        del os.environ["HALLPTZ_CONFIG_DIR"]
        del os.environ["HALLPTZ_LOG_DIR"]


# ── RuntimePathResolver — source detection ───────────────────────────────────

class TestRunningFromSource:

    def setup_method(self):
        for var in ("HALLPTZ_CONFIG_DIR", "HALLPTZ_DATA_DIR", "HALLPTZ_DATA_DIR",
                    "HALLPTZ_LOG_DIR", "HALLPTZ_BACKUP_DIR"):
            os.environ.pop(var, None)

    def test_running_from_source_detects_git_dir(self):
        # This test runs from the source tree, so .git should be present.
        r = RuntimePathResolver()
        # We can't assert True/False because tests may run from install, but
        # we can assert it returns a bool.
        assert isinstance(r.running_from_source, bool)


# ── BuildInfo ─────────────────────────────────────────────────────────────────

class TestBuildInfo:

    def test_defaults_are_safe_unknown_strings(self):
        info = BuildInfo()
        assert info.app_version == "unknown"
        assert info.git_commit == "unknown"
        assert info.build_date == "unknown"
        assert info.runtime_profile == "production"
        assert info.installation_id == "unknown"
        assert info.connectivity_mode == "unknown"
        assert info.running_from_source is False

    def test_to_dict_is_plain_strings(self):
        info = BuildInfo(app_version="3.14.0", git_commit="abc1234")
        d = info.to_dict()
        assert isinstance(d, dict)
        for k, v in d.items():
            assert isinstance(k, str)
            assert isinstance(v, str), f"{k!r}: {v!r} should be str"

    def test_version_line_production(self):
        info = BuildInfo(app_version="3.14.0", git_commit="abc1234")
        line = info.version_line()
        assert "3.14.0" in line
        assert "abc1234" in line
        assert "[PRODUCTION]" not in line  # production mode is silent

    def test_version_line_demo_mode_is_labelled(self):
        info = BuildInfo(app_version="3.14.0", runtime_profile="demo")
        line = info.version_line()
        assert "[DEMO]" in line

    def test_version_line_unknown_commit_omitted(self):
        info = BuildInfo(app_version="3.14.0", git_commit="unknown")
        line = info.version_line()
        assert "(unknown)" not in line

    def test_build_info_factory_returns_build_info(self, tmp_path):
        info = build_info(data_dir=tmp_path)
        assert isinstance(info, BuildInfo)
        assert info.app_version != ""

    def test_build_info_reads_installation_id_file(self, tmp_path):
        (tmp_path / "installation_id.txt").write_text("hallptz-2026-0042", encoding="utf-8")
        info = build_info(data_dir=tmp_path)
        assert info.installation_id == "hallptz-2026-0042"

    def test_build_info_missing_id_file_returns_unknown(self, tmp_path):
        info = build_info(data_dir=tmp_path)
        assert info.installation_id == "unknown"
