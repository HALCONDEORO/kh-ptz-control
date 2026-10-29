#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_preset_test_history_service.py — Unit tests for PresetTestHistoryService.

Pure Python — no Qt, no hardware. Uses tmp_path for file isolation.
"""
from __future__ import annotations

import json
from pathlib import Path


from application.preset_test_history_service import (
    MAX_HISTORY_ENTRIES,
    PresetTestHistoryService,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _svc(tmp_path: Path) -> PresetTestHistoryService:
    return PresetTestHistoryService(history_file=tmp_path / "history.json")


def _record(svc: PresetTestHistoryService, **kwargs) -> None:
    svc.record(
        total=kwargs.get("total", 10),
        ok=kwargs.get("ok", 8),
        warning=kwargs.get("warning", 1),
        error=kwargs.get("error", 1),
        skipped=kwargs.get("skipped", 0),
        cancelled=kwargs.get("cancelled", False),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  record()
# ══════════════════════════════════════════════════════════════════════════════

class TestRecord:
    def test_creates_file_on_first_record(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc)
        assert (tmp_path / "history.json").exists()

    def test_file_contains_valid_json(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc)
        data = json.loads((tmp_path / "history.json").read_text())
        assert isinstance(data, list)

    def test_single_record_has_expected_fields(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc, total=5, ok=4, warning=0, error=1, skipped=0, cancelled=False)
        data = json.loads((tmp_path / "history.json").read_text())
        entry = data[0]
        assert entry["total"] == 5
        assert entry["ok"] == 4
        assert entry["warning"] == 0
        assert entry["error"] == 1
        assert entry["skipped"] == 0
        assert entry["cancelled"] is False
        assert "timestamp" in entry

    def test_multiple_records_appended(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc, total=3, ok=3)
        _record(svc, total=7, ok=5)
        data = json.loads((tmp_path / "history.json").read_text())
        assert len(data) == 2

    def test_rotation_at_max_history_entries(self, tmp_path):
        svc = _svc(tmp_path)
        for i in range(MAX_HISTORY_ENTRIES + 5):
            _record(svc, total=i, ok=i)
        data = json.loads((tmp_path / "history.json").read_text())
        assert len(data) == MAX_HISTORY_ENTRIES

    def test_rotation_keeps_newest_entries(self, tmp_path):
        svc = _svc(tmp_path)
        for i in range(MAX_HISTORY_ENTRIES + 3):
            _record(svc, total=i, ok=i)
        data = json.loads((tmp_path / "history.json").read_text())
        # Newest entry: total = MAX_HISTORY_ENTRIES + 2
        assert data[-1]["total"] == MAX_HISTORY_ENTRIES + 2

    def test_cancelled_flag_stored_correctly(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc, cancelled=True)
        data = json.loads((tmp_path / "history.json").read_text())
        assert data[0]["cancelled"] is True

    def test_handles_corrupt_existing_file(self, tmp_path):
        f = tmp_path / "history.json"
        f.write_text("NOT JSON")
        svc = _svc(tmp_path)
        _record(svc)  # must not raise
        data = json.loads(f.read_text())
        assert len(data) == 1


# ══════════════════════════════════════════════════════════════════════════════
#  last_entry()
# ══════════════════════════════════════════════════════════════════════════════

class TestLastEntry:
    def test_returns_none_when_no_file(self, tmp_path):
        svc = _svc(tmp_path)
        assert svc.last_entry() is None

    def test_returns_none_when_file_empty_list(self, tmp_path):
        f = tmp_path / "history.json"
        f.write_text("[]")
        svc = _svc(tmp_path)
        assert svc.last_entry() is None

    def test_returns_last_after_multiple_records(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc, total=1, ok=1)
        _record(svc, total=99, ok=90)
        entry = svc.last_entry()
        assert entry["total"] == 99

    def test_returns_single_record(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc, total=5, ok=5)
        entry = svc.last_entry()
        assert entry is not None
        assert entry["total"] == 5

    def test_returns_none_for_corrupt_file(self, tmp_path):
        f = tmp_path / "history.json"
        f.write_text("CORRUPT")
        svc = _svc(tmp_path)
        assert svc.last_entry() is None


# ══════════════════════════════════════════════════════════════════════════════
#  summary_line()
# ══════════════════════════════════════════════════════════════════════════════

class TestSummaryLine:
    def test_no_records_returns_placeholder(self, tmp_path):
        svc = _svc(tmp_path)
        assert svc.summary_line() == "No test runs yet"

    def test_summary_contains_ok_and_total(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc, total=10, ok=8)
        line = svc.summary_line()
        assert "8" in line
        assert "10" in line

    def test_summary_mentions_ok_label(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc, total=5, ok=4)
        line = svc.summary_line()
        assert "OK" in line

    def test_summary_mentions_cancelled_when_true(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc, total=10, ok=5, cancelled=True)
        line = svc.summary_line()
        assert "cancelled" in line.lower()

    def test_summary_no_cancelled_when_false(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc, total=10, ok=5, cancelled=False)
        line = svc.summary_line()
        assert "cancelled" not in line.lower()

    def test_summary_contains_date_prefix(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc)
        line = svc.summary_line()
        assert "Last test:" in line

    def test_summary_is_string(self, tmp_path):
        svc = _svc(tmp_path)
        _record(svc)
        assert isinstance(svc.summary_line(), str)

