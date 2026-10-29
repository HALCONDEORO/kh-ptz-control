#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for domain/blackbox_event.py and application/flight_recorder.py (#487, #488).

Hardware-free: uses tmp_path only; no camera, ATEM, or network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from domain.blackbox_event import (
    SCHEMA_VERSION,
    BlackBoxEvent,
    EventLevel,
    EventResult,
    EventSource,
    EventType,
    redact_event_dict,
)
from application.flight_recorder import FlightRecorder


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minimal_event(**kwargs) -> BlackBoxEvent:
    """Return a minimal valid BlackBoxEvent, overridable via kwargs."""
    defaults = dict(
        timestamp="2026-05-08T15:42:12.231Z",
        level=EventLevel.INFO.value,
        event_type=EventType.SESSION_STARTED.value,
        app_version="3.22.0",
        installation_profile="starter_1_camera",
        runtime_mode="production",
        session_id="session-1",
        correlation_id="cmd-001",
        source=EventSource.OPERATOR_UI.value,
        result=EventResult.SUCCEEDED.value,
    )
    defaults.update(kwargs)
    return BlackBoxEvent(**defaults)


def _make_recorder(tmp_path: Path, **kwargs) -> FlightRecorder:
    events_file = tmp_path / "blackbox" / "events.jsonl"
    return FlightRecorder(events_file, **kwargs)


# ── BlackBoxEvent schema ───────────────────────────────────────────────────────

class TestBlackBoxEvent:

    def test_to_dict_returns_plain_types(self):
        event = _minimal_event()
        d = event.to_dict()
        assert isinstance(d, dict)
        assert d["schema_version"] == SCHEMA_VERSION
        assert d["level"] == "INFO"
        assert d["event_type"] == "SessionStarted"
        assert d["source"] == "operator_ui"
        assert d["result"] == "succeeded"

    def test_required_fields_present(self):
        event = _minimal_event()
        d = event.to_dict()
        for field in ("timestamp", "level", "event_type", "app_version",
                      "installation_profile", "runtime_mode",
                      "session_id", "correlation_id", "source", "result"):
            assert field in d, f"Missing required field: {field}"

    def test_schema_version_default(self):
        event = _minimal_event()
        assert event.schema_version == SCHEMA_VERSION

    def test_optional_fields_default_none(self):
        event = _minimal_event()
        assert event.seat_id is None
        assert event.camera_role is None
        assert event.preset is None
        assert event.error_code is None
        assert event.duration_ms is None
        assert event.git_commit is None

    def test_extra_dict_default_empty(self):
        event = _minimal_event()
        assert event.extra == {}

    def test_installation_id_default_unknown(self):
        event = _minimal_event()
        assert event.installation_id == "unknown"

    def test_with_optional_fields(self):
        event = _minimal_event(
            seat_id="seat-3",
            camera_role="wide",
            preset="preset-1",
            error_code="VISCA_TIMEOUT",
            duration_ms=120,
            installation_id="khptz-2026-0007",
            extra={"attempt": 1},
        )
        d = event.to_dict()
        assert d["seat_id"] == "seat-3"
        assert d["camera_role"] == "wide"
        assert d["preset"] == "preset-1"
        assert d["error_code"] == "VISCA_TIMEOUT"
        assert d["duration_ms"] == 120
        assert d["installation_id"] == "khptz-2026-0007"
        assert d["extra"] == {"attempt": 1}

    def test_event_is_frozen(self):
        event = _minimal_event()
        with pytest.raises((AttributeError, TypeError)):
            event.level = "ERROR"  # type: ignore[misc]

    def test_json_serialisable(self):
        event = _minimal_event(extra={"note": "test"})
        d = event.to_dict()
        serialised = json.dumps(d)
        assert isinstance(serialised, str)


# ── redact_event_dict ─────────────────────────────────────────────────────────

class TestRedactEventDict:

    def test_password_key_redacted(self):
        d = {"message": "ok", "password": "hunter2"}
        result = redact_event_dict(d)
        assert result["password"] == "[REDACTED]"
        assert result["message"] == "ok"

    def test_token_key_redacted(self):
        d = {"token": "abc123"}
        assert redact_event_dict(d)["token"] == "[REDACTED]"

    def test_secret_key_redacted(self):
        d = {"secret": "shhh"}
        assert redact_event_dict(d)["secret"] == "[REDACTED]"

    def test_private_key_field_redacted(self):
        d = {"private_key": "-----BEGIN RSA PRIVATE KEY-----"}
        assert redact_event_dict(d)["private_key"] == "[REDACTED]"

    def test_nested_dict_redacted(self):
        d = {"credentials": {"password": "s3cr3t", "user": "admin"}}
        result = redact_event_dict(d)
        assert result["credentials"]["password"] == "[REDACTED]"
        assert result["credentials"]["user"] == "admin"

    def test_safe_fields_pass_through(self):
        d = {"seat_id": "seat-1", "event_type": "SessionStarted", "duration_ms": 50}
        result = redact_event_dict(d)
        assert result == d

    def test_returns_copy_not_mutating_original(self):
        d = {"password": "abc"}
        result = redact_event_dict(d)
        assert d["password"] == "abc"   # original unchanged
        assert result["password"] == "[REDACTED]"


# ── FlightRecorder — basic write ──────────────────────────────────────────────

class TestFlightRecorderWrite:

    def test_record_creates_file(self, tmp_path):
        recorder = _make_recorder(tmp_path)
        recorder.record(_minimal_event())
        assert recorder._events_file.exists()

    def test_record_creates_parent_dir(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c" / "events.jsonl"
        recorder = FlightRecorder(nested)
        recorder.record(_minimal_event())
        assert nested.exists()

    def test_record_writes_valid_json_line(self, tmp_path):
        recorder = _make_recorder(tmp_path)
        recorder.record(_minimal_event())
        content = recorder._events_file.read_text(encoding="utf-8")
        parsed = json.loads(content.strip())
        assert parsed["event_type"] == "SessionStarted"
        assert parsed["schema_version"] == SCHEMA_VERSION

    def test_record_appends_multiple_events(self, tmp_path):
        recorder = _make_recorder(tmp_path)
        for i in range(5):
            recorder.record(_minimal_event(correlation_id=f"cmd-{i:03d}"))
        lines = [ln for ln in recorder._events_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 5

    def test_record_dict_writes_dict(self, tmp_path):
        recorder = _make_recorder(tmp_path)
        recorder.record_dict({"event_type": "Custom", "level": "INFO"})
        content = recorder._events_file.read_text(encoding="utf-8")
        parsed = json.loads(content.strip())
        assert parsed["event_type"] == "Custom"

    def test_record_dict_redacts_secrets(self, tmp_path):
        recorder = _make_recorder(tmp_path)
        recorder.record_dict({"password": "secret123", "level": "INFO"})
        content = recorder._events_file.read_text(encoding="utf-8")
        parsed = json.loads(content.strip())
        assert parsed["password"] == "[REDACTED]"
        assert "secret123" not in content

    def test_record_redacts_secret_in_extra(self, tmp_path):
        recorder = _make_recorder(tmp_path)
        recorder.record(_minimal_event(extra={"token": "abc"}))
        content = recorder._events_file.read_text(encoding="utf-8")
        parsed = json.loads(content.strip())
        assert parsed["extra"]["token"] == "[REDACTED]"


# ── FlightRecorder — safe failure ─────────────────────────────────────────────

class TestFlightRecorderSafeFailure:

    def test_write_failure_does_not_raise(self, tmp_path):
        """If the write function raises, record() must not propagate the exception."""
        def bad_write(path, line):
            raise OSError("disk full")

        recorder = FlightRecorder(
            tmp_path / "events.jsonl",
            _write_fn=bad_write,
        )
        # Must not raise
        recorder.record(_minimal_event())

    def test_get_recent_nonexistent_file_returns_empty(self, tmp_path):
        recorder = _make_recorder(tmp_path)
        result = recorder.get_recent(50)
        assert result == []

    def test_get_recent_corrupt_lines_skipped(self, tmp_path):
        recorder = _make_recorder(tmp_path)
        recorder._events_file.parent.mkdir(parents=True, exist_ok=True)
        recorder._events_file.write_text(
            '{"event_type": "ok"}\nNOT_JSON\n{"event_type": "also_ok"}\n',
            encoding="utf-8",
        )
        result = recorder.get_recent(100)
        assert len(result) == 2
        assert result[0]["event_type"] == "ok"
        assert result[1]["event_type"] == "also_ok"

    def test_get_recent_exception_returns_empty(self, tmp_path):
        """get_recent() never raises even if the file path is inaccessible."""
        # Point recorder at a path under a non-existent inaccessible dir —
        # we simulate this by making events_file a directory instead of a file.
        events_path = tmp_path / "events.jsonl"
        events_path.mkdir()  # directory where a file is expected
        recorder = FlightRecorder(events_path)
        result = recorder.get_recent(10)
        assert result == []

    def test_record_dict_failure_does_not_raise(self, tmp_path):
        def bad_write(path, line):
            raise PermissionError("no write")

        recorder = FlightRecorder(
            tmp_path / "events.jsonl",
            _write_fn=bad_write,
        )
        recorder.record_dict({"level": "INFO"})  # must not raise


# ── FlightRecorder — get_recent ───────────────────────────────────────────────

class TestFlightRecorderGetRecent:

    def test_returns_newest_last(self, tmp_path):
        recorder = _make_recorder(tmp_path)
        for i in range(10):
            recorder.record(_minimal_event(correlation_id=f"cmd-{i:03d}"))
        events = recorder.get_recent(10)
        assert len(events) == 10
        assert events[-1]["correlation_id"] == "cmd-009"

    def test_limit_respected(self, tmp_path):
        recorder = _make_recorder(tmp_path)
        for i in range(20):
            recorder.record(_minimal_event(correlation_id=f"cmd-{i:03d}"))
        events = recorder.get_recent(5)
        assert len(events) == 5
        # Should be the last 5
        assert events[0]["correlation_id"] == "cmd-015"
        assert events[-1]["correlation_id"] == "cmd-019"

    def test_export_for_support_returns_list(self, tmp_path):
        recorder = _make_recorder(tmp_path)
        recorder.record(_minimal_event())
        result = recorder.export_for_support(500)
        assert isinstance(result, list)
        assert len(result) == 1


# ── FlightRecorder — rotation ─────────────────────────────────────────────────

class TestFlightRecorderRotation:

    def test_rotation_triggered_on_size_exceeded(self, tmp_path):
        """When the active file exceeds max_file_bytes, it is rotated."""
        recorder = FlightRecorder(
            tmp_path / "events.jsonl",
            max_file_bytes=50,   # very small limit to trigger rotation
        )
        # Write enough events to exceed 50 bytes
        for i in range(5):
            recorder.record(_minimal_event(correlation_id=f"cmd-{i:03d}"))

        # After rotation, events.1.jsonl should exist
        rotated = tmp_path / "events.1.jsonl"
        assert rotated.exists()

    def test_oldest_file_deleted_when_max_exceeded(self, tmp_path):
        """When max_rotated is 2 and 3 rotations happen, events.3.jsonl is never created."""
        recorder = FlightRecorder(
            tmp_path / "events.jsonl",
            max_file_bytes=10,   # tiny limit
            max_rotated=2,
        )
        for i in range(30):
            recorder.record(_minimal_event(correlation_id=f"x-{i}"))

        assert not (tmp_path / "events.3.jsonl").exists()

    def test_rotation_preserves_new_writes(self, tmp_path):
        """After rotation, new events are still appended to events.jsonl."""
        recorder = FlightRecorder(
            tmp_path / "events.jsonl",
            max_file_bytes=50,
        )
        for i in range(10):
            recorder.record(_minimal_event(correlation_id=f"cmd-{i:03d}"))

        # The active file should still exist and contain valid JSONL
        content = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
        lines = [ln for ln in content.splitlines() if ln.strip()]
        assert all(json.loads(ln) for ln in lines)


# ── FlightRecorder — injectable write_fn ─────────────────────────────────────

class TestFlightRecorderInjectable:

    def test_custom_write_fn_called(self, tmp_path):
        written: list[str] = []

        def capture(path, line):
            written.append(line)

        recorder = FlightRecorder(tmp_path / "events.jsonl", _write_fn=capture)
        recorder.record(_minimal_event())
        assert len(written) == 1
        parsed = json.loads(written[0])
        assert parsed["event_type"] == "SessionStarted"

    def test_multiple_events_captured(self, tmp_path):
        written: list[str] = []

        def capture(path, line):
            written.append(line)

        recorder = FlightRecorder(tmp_path / "events.jsonl", _write_fn=capture)
        recorder.record(_minimal_event(correlation_id="a"))
        recorder.record(_minimal_event(correlation_id="b"))
        assert len(written) == 2


# ── Path resolver integration ─────────────────────────────────────────────────

class TestPathResolverBlackboxPaths:

    def test_blackbox_dir_under_log_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KHPTZ_LOG_DIR", str(tmp_path / "logs"))
        from runtime.path_resolver import RuntimePathResolver
        resolver = RuntimePathResolver()
        assert resolver.blackbox_dir == tmp_path / "logs" / "blackbox"

    def test_blackbox_events_file_under_blackbox_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KHPTZ_LOG_DIR", str(tmp_path / "logs"))
        from runtime.path_resolver import RuntimePathResolver
        resolver = RuntimePathResolver()
        assert resolver.blackbox_events_file == tmp_path / "logs" / "blackbox" / "events.jsonl"
