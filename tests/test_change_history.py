# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for domain/change_event.py and application/change_history_service.py (#271)."""
from __future__ import annotations

import json
from pathlib import Path


from application.change_history_service import ChangeHistoryService
from domain.change_event import (
    AREA_CONFIG,
    ACTION_CAMERA_IP_CHANGED,
    ChangeEvent,
    _now_iso,
)


# ── ChangeEvent model ─────────────────────────────────────────────────────────

class TestChangeEvent:
    def test_to_dict_required_fields(self):
        ev = ChangeEvent(area="config", action="camera_ip_changed", target="camera:comments")
        d = ev.to_dict()
        assert d["area"] == "config"
        assert d["action"] == "camera_ip_changed"
        assert d["target"] == "camera:comments"
        assert "timestamp" in d

    def test_to_dict_omits_none_values(self):
        ev = ChangeEvent(area="config", action="x", target="y")
        d = ev.to_dict()
        assert "old_value" not in d
        assert "new_value" not in d

    def test_to_dict_includes_values_when_set(self):
        ev = ChangeEvent(area="config", action="x", target="y",
                         old_value="192.168.1.1", new_value="10.0.0.1")
        d = ev.to_dict()
        assert d["old_value"] == "192.168.1.1"
        assert d["new_value"] == "10.0.0.1"

    def test_from_dict_round_trip(self):
        ev = ChangeEvent(area=AREA_CONFIG, action=ACTION_CAMERA_IP_CHANGED,
                         target="camera:platform", actor="installer",
                         old_value="1.1.1.1", new_value="2.2.2.2")
        ev2 = ChangeEvent.from_dict(ev.to_dict())
        assert ev2.area == ev.area
        assert ev2.action == ev.action
        assert ev2.target == ev.target
        assert ev2.actor == ev.actor
        assert ev2.old_value == ev.old_value
        assert ev2.new_value == ev.new_value

    def test_from_json_round_trip(self):
        ev = ChangeEvent(area="layout", action="layout_changed", target="room_a")
        raw = json.dumps(ev.to_dict())
        ev2 = ChangeEvent.from_json(raw)
        assert ev2.area == "layout"
        assert ev2.target == "room_a"

    def test_default_actor_is_system(self):
        ev = ChangeEvent(area="x", action="y", target="z")
        assert ev.actor == "system"

    def test_timestamp_is_iso(self):
        ts = _now_iso()
        assert "T" in ts
        assert ts.endswith("Z")

    def test_note_omitted_when_empty(self):
        ev = ChangeEvent(area="x", action="y", target="z", note="")
        assert "note" not in ev.to_dict()

    def test_note_included_when_set(self):
        ev = ChangeEvent(area="x", action="y", target="z", note="migrated from v1")
        assert ev.to_dict()["note"] == "migrated from v1"


# ── ChangeHistoryService ──────────────────────────────────────────────────────

def _svc(tmp_path: Path, max_lines: int = 10_000) -> ChangeHistoryService:
    return ChangeHistoryService(history_path=tmp_path / "change_history.json",
                                max_lines=max_lines)


def _ev(area="config", action="x", target="y", **kw) -> ChangeEvent:
    return ChangeEvent(area=area, action=action, target=target, **kw)


class TestChangeHistoryServiceRecord:
    def test_record_creates_file(self, tmp_path):
        svc = _svc(tmp_path)
        svc.record(_ev())
        assert (tmp_path / "change_history.json").exists()

    def test_record_appends_lines(self, tmp_path):
        svc = _svc(tmp_path)
        svc.record(_ev(target="a"))
        svc.record(_ev(target="b"))
        lines = (tmp_path / "change_history.json").read_text().splitlines()
        assert len(lines) == 2

    def test_record_valid_json_per_line(self, tmp_path):
        svc = _svc(tmp_path)
        svc.record(_ev(action="camera_ip_changed", target="camera:comments",
                       old_value="1.2.3.4", new_value="5.6.7.8"))
        line = (tmp_path / "change_history.json").read_text().strip()
        d = json.loads(line)
        assert d["action"] == "camera_ip_changed"
        assert d["old_value"] == "1.2.3.4"

    def test_record_returns_true_on_success(self, tmp_path):
        assert _svc(tmp_path).record(_ev()) is True

    def test_record_returns_false_on_bad_path(self, tmp_path):
        # Make parent a file so mkdir() fails
        blocker = tmp_path / "notadir"
        blocker.write_text("x")
        svc = ChangeHistoryService(history_path=blocker / "file.json")
        assert svc.record(_ev()) is False


class TestChangeHistoryServiceRead:
    def test_read_recent_empty_when_no_file(self, tmp_path):
        assert _svc(tmp_path).read_recent() == []

    def test_read_recent_returns_events(self, tmp_path):
        svc = _svc(tmp_path)
        svc.record(_ev(action="a"))
        svc.record(_ev(action="b"))
        events = svc.read_recent(10)
        assert len(events) == 2
        assert events[0].action == "a"
        assert events[1].action == "b"

    def test_read_recent_respects_n(self, tmp_path):
        svc = _svc(tmp_path)
        for i in range(5):
            svc.record(_ev(action=f"action_{i}"))
        events = svc.read_recent(3)
        assert len(events) == 3
        assert events[0].action == "action_2"

    def test_read_recent_skips_corrupt_lines(self, tmp_path):
        path = tmp_path / "change_history.json"
        path.write_text(
            '{"area":"config","action":"x","target":"y","timestamp":"t"}\n'
            'NOT JSON\n'
            '{"area":"config","action":"z","target":"w","timestamp":"t"}\n',
            encoding="utf-8",
        )
        svc = ChangeHistoryService(history_path=path)
        events = svc.read_recent(10)
        assert len(events) == 2


class TestChangeHistoryServiceHelpers:
    def test_has_changes_false_when_empty(self, tmp_path):
        assert not _svc(tmp_path).has_changes()

    def test_has_changes_true_after_record(self, tmp_path):
        svc = _svc(tmp_path)
        svc.record(_ev())
        assert svc.has_changes()

    def test_event_count_zero_no_file(self, tmp_path):
        assert _svc(tmp_path).event_count() == 0

    def test_event_count_matches_records(self, tmp_path):
        svc = _svc(tmp_path)
        for _ in range(7):
            svc.record(_ev())
        assert svc.event_count() == 7


class TestChangeHistoryServiceRotate:
    def test_rotate_removes_oldest_entries(self, tmp_path):
        svc = _svc(tmp_path, max_lines=3)
        for i in range(5):
            svc.record(_ev(target=f"t{i}"))
        svc.rotate_if_needed()
        events = svc.read_recent(10)
        assert len(events) == 3
        assert events[0].target == "t2"

    def test_rotate_returns_false_when_not_needed(self, tmp_path):
        svc = _svc(tmp_path, max_lines=100)
        svc.record(_ev())
        assert svc.rotate_if_needed() is False

    def test_rotate_returns_false_when_no_file(self, tmp_path):
        assert _svc(tmp_path).rotate_if_needed() is False
