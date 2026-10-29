#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_change_history_service.py — ChangeHistoryService unit tests

from __future__ import annotations

import json
from pathlib import Path


from application.change_history_service import ChangeHistoryService
from domain.change_event import ChangeEvent, AREA_CONFIG, ACTION_CAMERA_IP_CHANGED


# ── Helpers ───────────────────────────────────────────────────────────────────

def _svc(tmp_path: Path, max_lines: int = 100) -> ChangeHistoryService:
    return ChangeHistoryService(
        history_path=tmp_path / "change_history.json",
        max_lines=max_lines,
    )


def _event(area: str = AREA_CONFIG, action: str = ACTION_CAMERA_IP_CHANGED, target: str = "camera:1") -> ChangeEvent:
    return ChangeEvent(area=area, action=action, target=target, actor="installer")


# ── record ────────────────────────────────────────────────────────────────────

def test_record_creates_file_on_first_write(tmp_path):
    svc = _svc(tmp_path)
    result = svc.record(_event())
    assert result
    assert (tmp_path / "change_history.json").exists()


def test_record_appends_newline_delimited_json(tmp_path):
    svc = _svc(tmp_path)
    svc.record(_event(target="camera:1"))
    svc.record(_event(target="camera:2"))
    lines = (tmp_path / "change_history.json").read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["target"] == "camera:1"
    assert json.loads(lines[1])["target"] == "camera:2"


def test_record_creates_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "history.json"
    svc = ChangeHistoryService(history_path=path)
    svc.record(_event())
    assert path.exists()


def test_record_returns_false_on_write_error():
    from unittest.mock import MagicMock
    path = MagicMock()
    path.parent.mkdir = MagicMock()
    path.open.side_effect = OSError("disk full")
    svc = ChangeHistoryService(history_path=path)
    result = svc.record(_event())
    assert not result


def test_record_event_fields_are_persisted(tmp_path):
    svc = _svc(tmp_path)
    evt = ChangeEvent(
        area="config",
        action="camera_ip_changed",
        target="camera:comments",
        actor="operator",
        old_value="192.168.1.1",
        new_value="10.0.0.5",
        note="replaced encoder",
    )
    svc.record(evt)
    line = (tmp_path / "change_history.json").read_text().strip()
    d = json.loads(line)
    assert d["area"] == "config"
    assert d["old_value"] == "192.168.1.1"
    assert d["new_value"] == "10.0.0.5"
    assert d["note"] == "replaced encoder"


# ── read_recent ───────────────────────────────────────────────────────────────

def test_read_recent_returns_empty_when_file_missing(tmp_path):
    svc = _svc(tmp_path)
    assert svc.read_recent() == []


def test_read_recent_returns_all_events_when_few(tmp_path):
    svc = _svc(tmp_path)
    svc.record(_event(target="camera:1"))
    svc.record(_event(target="camera:2"))
    events = svc.read_recent(10)
    assert len(events) == 2


def test_read_recent_returns_only_last_n(tmp_path):
    svc = _svc(tmp_path)
    for i in range(5):
        svc.record(_event(target=f"camera:{i}"))
    events = svc.read_recent(2)
    assert len(events) == 2
    assert events[-1].target == "camera:4"
    assert events[0].target == "camera:3"


def test_read_recent_preserves_order_newest_last(tmp_path):
    svc = _svc(tmp_path)
    targets = ["a", "b", "c"]
    for t in targets:
        svc.record(_event(target=t))
    events = svc.read_recent(3)
    assert [e.target for e in events] == targets


def test_read_recent_skips_corrupt_lines(tmp_path):
    path = tmp_path / "change_history.json"
    path.write_text(
        '{"area":"config","action":"x","target":"t1","actor":"system","timestamp":"2026-01-01T00:00:00Z"}\n'
        'NOT_VALID_JSON\n'
        '{"area":"config","action":"y","target":"t2","actor":"system","timestamp":"2026-01-01T00:01:00Z"}\n'
    )
    svc = ChangeHistoryService(history_path=path)
    events = svc.read_recent(10)
    targets = [e.target for e in events]
    assert "t1" in targets
    assert "t2" in targets


def test_read_recent_skips_blank_lines(tmp_path):
    path = tmp_path / "change_history.json"
    path.write_text(
        '{"area":"config","action":"x","target":"t1","actor":"system","timestamp":"2026-01-01T00:00:00Z"}\n'
        '\n'
        '\n'
    )
    svc = ChangeHistoryService(history_path=path)
    events = svc.read_recent(10)
    assert len(events) == 1


# ── has_changes ───────────────────────────────────────────────────────────────

def test_has_changes_false_when_no_file(tmp_path):
    assert not _svc(tmp_path).has_changes()


def test_has_changes_true_after_record(tmp_path):
    svc = _svc(tmp_path)
    svc.record(_event())
    assert svc.has_changes()


# ── event_count ───────────────────────────────────────────────────────────────

def test_event_count_zero_when_no_file(tmp_path):
    assert _svc(tmp_path).event_count() == 0


def test_event_count_matches_recorded_events(tmp_path):
    svc = _svc(tmp_path)
    for _ in range(7):
        svc.record(_event())
    assert svc.event_count() == 7


def test_event_count_ignores_blank_lines(tmp_path):
    path = tmp_path / "change_history.json"
    path.write_text("line1\n\nline3\n")
    svc = ChangeHistoryService(history_path=path)
    assert svc.event_count() == 2


# ── rotate_if_needed ──────────────────────────────────────────────────────────

def test_rotate_returns_false_when_under_limit(tmp_path):
    svc = _svc(tmp_path, max_lines=100)
    for _ in range(50):
        svc.record(_event())
    assert not svc.rotate_if_needed()


def test_rotate_returns_false_when_no_file(tmp_path):
    svc = _svc(tmp_path, max_lines=10)
    assert not svc.rotate_if_needed()


def test_rotate_truncates_to_max_lines(tmp_path):
    svc = _svc(tmp_path, max_lines=5)
    for i in range(10):
        svc.record(_event(target=f"cam:{i}"))
    result = svc.rotate_if_needed()
    assert result
    assert svc.event_count() == 5


def test_rotate_keeps_newest_entries(tmp_path):
    svc = _svc(tmp_path, max_lines=3)
    for i in range(6):
        svc.record(_event(target=f"cam:{i}"))
    svc.rotate_if_needed()
    events = svc.read_recent(10)
    targets = [e.target for e in events]
    assert targets == ["cam:3", "cam:4", "cam:5"]


def test_rotate_is_idempotent(tmp_path):
    svc = _svc(tmp_path, max_lines=3)
    for i in range(6):
        svc.record(_event(target=f"cam:{i}"))
    svc.rotate_if_needed()
    result2 = svc.rotate_if_needed()
    assert not result2
    assert svc.event_count() == 3

