#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_boot_metrics.py — boot telemetry models had no coverage at all
#
# application/boot_metrics.py records how every boot of the appliance went. It
# is the only history a technician has when a customer reports "it sometimes
# takes ages to start", so the two properties that matter are:
#
#   - it must never break startup. Every failure mode (unwritable data dir,
#     truncated JSON after a power cut, a file holding something that is not a
#     list) has to degrade to "no statistics", never to an exception — the
#     caller is the splash screen, on the critical path of a headless appliance.
#   - the history must stay bounded, or a machine that boots daily for years
#     grows a file the support bundle then has to carry.

from __future__ import annotations

import json
from pathlib import Path

import pytest

from application.boot_metrics import BootStatistics, TestResult


@pytest.fixture
def stats_file(tmp_path: Path) -> Path:
    return tmp_path / "boot_stats.json"


class TestTestResultModel:
    def test_not_collected_as_a_test_class(self):
        """The class is named TestResult; without __test__ = False pytest would
        try to collect it and warn on every run."""
        assert TestResult.__test__ is False

    def test_starts_unsuccessful(self):
        """A check that never reported back must not count as passed."""
        assert TestResult("config").success is False

    def test_finish_records_the_outcome(self):
        result = TestResult("config")
        result.finish(True)
        assert result.success is True
        assert result.error_msg is None

    def test_finish_records_the_failure_reason(self):
        result = TestResult("cameras")
        result.finish(False, "no route to host")
        assert result.success is False
        assert result.error_msg == "no route to host"

    def test_duration_is_measured_in_milliseconds(self):
        result = TestResult("config")
        result.start_time -= 0.25          # pretend a quarter second elapsed
        result.finish(True)
        assert 200 <= result.duration_ms <= 400

    def test_to_dict_carries_every_field_the_history_stores(self):
        result = TestResult("cameras")
        result.finish(False, "timeout")
        entry = result.to_dict()
        assert entry["name"] == "cameras"
        assert entry["success"] is False
        assert entry["error"] == "timeout"
        assert isinstance(entry["duration_ms"], int)
        assert entry["timestamp"]

    def test_to_dict_is_json_serialisable(self):
        """It is written straight into the history file."""
        json.dumps(TestResult("config").to_dict())

    def test_unfinished_result_still_timestamps(self):
        """A check still running when the splash gives up must not produce a
        None timestamp in the history."""
        assert TestResult("config").to_dict()["timestamp"]


class TestFileCreation:
    def test_missing_file_is_created_empty(self, stats_file):
        BootStatistics(stats_file)
        assert json.loads(stats_file.read_text(encoding="utf-8")) == []

    def test_missing_parent_directory_is_created(self, tmp_path):
        nested = tmp_path / "var" / "lib" / "khptz" / "boot_stats.json"
        BootStatistics(nested)
        assert nested.is_file()

    def test_existing_history_is_not_truncated(self, stats_file):
        stats_file.write_text(json.dumps([{"duration_ms": 1}]), encoding="utf-8")
        BootStatistics(stats_file)
        assert len(json.loads(stats_file.read_text(encoding="utf-8"))) == 1

    def test_unwritable_location_does_not_raise(self, tmp_path):
        """Construction happens during startup: a read-only /var/lib must cost
        the statistics, not the boot."""
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("", encoding="utf-8")
        BootStatistics(blocker / "boot_stats.json")   # must not raise

    def test_accepts_a_string_path(self, stats_file):
        """The splash passes whatever the path resolver hands it."""
        stats = BootStatistics(str(stats_file))
        assert isinstance(stats.stats_file, Path)


class TestRecordBoot:
    def test_records_an_entry(self, stats_file):
        assert BootStatistics(stats_file).record_boot(4200, 5, 5) is True
        entries = json.loads(stats_file.read_text(encoding="utf-8"))
        assert len(entries) == 1
        assert entries[0]["duration_ms"] == 4200
        assert entries[0]["tests_passed"] == 5
        assert entries[0]["total_tests"] == 5

    def test_all_checks_passing_is_a_successful_boot(self, stats_file):
        BootStatistics(stats_file).record_boot(1000, 5, 5)
        assert json.loads(stats_file.read_text(encoding="utf-8"))[0]["success"] is True

    def test_one_failed_check_is_an_unsuccessful_boot(self, stats_file):
        BootStatistics(stats_file).record_boot(1000, 4, 5)
        assert json.loads(stats_file.read_text(encoding="utf-8"))[0]["success"] is False

    def test_entries_accumulate_across_boots(self, stats_file):
        stats = BootStatistics(stats_file)
        for i in range(3):
            stats.record_boot(1000 + i, 5, 5)
        assert len(json.loads(stats_file.read_text(encoding="utf-8"))) == 3

    def test_history_is_capped_at_one_hundred(self, stats_file):
        """An appliance boots every working day for years; unbounded history
        ends up inside every support bundle."""
        stats_file.write_text(
            json.dumps([{"duration_ms": i, "success": True} for i in range(100)]),
            encoding="utf-8",
        )
        BootStatistics(stats_file).record_boot(9999, 5, 5)
        entries = json.loads(stats_file.read_text(encoding="utf-8"))
        assert len(entries) == 100
        assert entries[-1]["duration_ms"] == 9999
        assert entries[0]["duration_ms"] == 1        # the oldest one was dropped

    def test_no_temp_file_is_left_behind(self, stats_file):
        BootStatistics(stats_file).record_boot(1000, 5, 5)
        assert not list(stats_file.parent.glob("*.tmp"))

    def test_corrupt_history_is_replaced_not_propagated(self, stats_file):
        """A power cut mid-write leaves half a JSON document. The next boot has
        to record itself anyway."""
        stats_file.write_text("[{'truncated'", encoding="utf-8")
        assert BootStatistics(stats_file).record_boot(1000, 5, 5) is True
        assert len(json.loads(stats_file.read_text(encoding="utf-8"))) == 1

    def test_unwritable_file_reports_failure_without_raising(self, tmp_path):
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("", encoding="utf-8")
        stats = BootStatistics(blocker / "boot_stats.json")
        assert stats.record_boot(1000, 5, 5) is False


class TestReadStats:
    def test_absent_file_reads_as_empty(self, stats_file):
        stats = BootStatistics(stats_file)
        stats_file.unlink()
        assert stats._read_stats() == []

    def test_corrupt_json_reads_as_empty(self, stats_file):
        stats = BootStatistics(stats_file)
        stats_file.write_text("not json at all", encoding="utf-8")
        assert stats._read_stats() == []

    def test_a_json_object_is_not_accepted_as_history(self, stats_file):
        """Anything but a list would break every consumer downstream."""
        stats = BootStatistics(stats_file)
        stats_file.write_text('{"boots": 3}', encoding="utf-8")
        assert stats._read_stats() == []

    def test_undecodable_bytes_read_as_empty(self, stats_file):
        stats = BootStatistics(stats_file)
        stats_file.write_bytes(b"\xff\xfe\x00 not utf-8")
        assert stats._read_stats() == []


class TestSummary:
    def test_no_history_yields_no_summary(self, stats_file):
        assert BootStatistics(stats_file).get_summary() == {}

    def test_counts_and_averages(self, stats_file):
        stats = BootStatistics(stats_file)
        stats.record_boot(1000, 5, 5)
        stats.record_boot(3000, 4, 5)
        summary = stats.get_summary()
        assert summary["total_boots"] == 2
        assert summary["successful"] == 1
        assert summary["success_rate"] == "50.0%"
        assert summary["avg_duration_ms"] == 2000

    def test_reports_the_most_recent_boot(self, stats_file):
        stats = BootStatistics(stats_file)
        stats.record_boot(1000, 5, 5)
        stats.record_boot(2000, 5, 5)
        entries = json.loads(stats_file.read_text(encoding="utf-8"))
        assert stats.get_summary()["last_boot"] == entries[-1]["timestamp"]

    def test_tolerates_entries_written_by_an_older_version(self, stats_file):
        """Fields the current writer always emits may be missing in history
        carried across an upgrade — the summary must still render."""
        stats_file.write_text(json.dumps([{}, {"success": True}]), encoding="utf-8")
        summary = BootStatistics(stats_file).get_summary()
        assert summary["total_boots"] == 2
        assert summary["successful"] == 1
        assert summary["avg_duration_ms"] == 0
        assert summary["last_boot"] == ""

    def test_corrupt_history_yields_no_summary(self, stats_file):
        stats = BootStatistics(stats_file)
        stats_file.write_text("]", encoding="utf-8")
        assert stats.get_summary() == {}


class TestSplashCompatibility:
    """The module docstring promises `from ui.splash_screen import TestResult,
    BootStatistics` keeps working — installed splash code still imports it."""

    def test_splash_reexports_the_models(self):
        pytest.importorskip("PyQt5")
        from conftest import ensure_real_qt
        ensure_real_qt()

        import ui.splash_screen as splash

        assert splash.TestResult is TestResult
        assert splash.BootStatistics is BootStatistics
