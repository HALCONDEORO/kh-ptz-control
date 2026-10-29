#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_event_builder.py — Tests for application/event_builder.py

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from application.event_builder import EventBuilder
from domain.blackbox_event import (
    SCHEMA_VERSION,
    BlackBoxEvent,
    EventLevel,
    EventResult,
    EventSource,
)

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _builder(**kwargs) -> EventBuilder:
    defaults = dict(
        app_version="3.0.0",
        installation_profile="starter_1_camera",
        runtime_mode="production",
        installation_id="abc123",
        git_commit="deadbeef",
        session_id="sess-1",
        source=EventSource.OPERATOR_UI,
    )
    defaults.update(kwargs)
    return EventBuilder(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# Return type
# ═══════════════════════════════════════════════════════════════════════════════

class TestReturnType:
    def test_returns_blackbox_event(self):
        ev = _builder().event("AppStarted")
        assert isinstance(ev, BlackBoxEvent)

    def test_event_is_immutable(self):
        ev = _builder().event("AppStarted")
        with pytest.raises(AttributeError):
            ev.level = "BAD"  # type: ignore


# ═══════════════════════════════════════════════════════════════════════════════
# Schema version and static context fields
# ═══════════════════════════════════════════════════════════════════════════════

class TestStaticFields:
    def test_schema_version_matches_domain_constant(self):
        ev = _builder().event("AppStarted")
        assert ev.schema_version == SCHEMA_VERSION

    def test_app_version_propagated(self):
        ev = EventBuilder(app_version="9.9.9").event("AppStarted")
        assert ev.app_version == "9.9.9"

    def test_installation_profile_propagated(self):
        ev = EventBuilder(installation_profile="dual_camera").event("AppStarted")
        assert ev.installation_profile == "dual_camera"

    def test_runtime_mode_propagated(self):
        ev = EventBuilder(runtime_mode="demo").event("AppStarted")
        assert ev.runtime_mode == "demo"

    def test_installation_id_propagated(self):
        ev = EventBuilder(installation_id="xyz-999").event("AppStarted")
        assert ev.installation_id == "xyz-999"

    def test_git_commit_propagated(self):
        ev = EventBuilder(git_commit="abc123").event("AppStarted")
        assert ev.git_commit == "abc123"

    def test_git_commit_none_allowed(self):
        ev = EventBuilder(git_commit=None).event("AppStarted")
        assert ev.git_commit is None

    def test_session_id_propagated(self):
        ev = EventBuilder(session_id="sess-42").event("AppStarted")
        assert ev.session_id == "sess-42"

    def test_source_propagated(self):
        ev = EventBuilder(source=EventSource.CLI).event("AppStarted")
        assert ev.source == EventSource.CLI


# ═══════════════════════════════════════════════════════════════════════════════
# Per-event fields
# ═══════════════════════════════════════════════════════════════════════════════

class TestPerEventFields:
    def test_event_type_set(self):
        ev = _builder().event("SessionStarted")
        assert ev.event_type == "SessionStarted"

    def test_level_defaults_to_info(self):
        ev = _builder().event("AppStarted")
        assert ev.level == EventLevel.INFO

    def test_level_can_be_overridden(self):
        ev = _builder().event("AppStarted", level=EventLevel.ERROR)
        assert ev.level == EventLevel.ERROR

    def test_level_warning_accepted(self):
        ev = _builder().event("AppStarted", level=EventLevel.WARNING)
        assert ev.level == EventLevel.WARNING

    def test_result_defaults_to_unknown(self):
        ev = _builder().event("AppStarted")
        assert ev.result == EventResult.UNKNOWN

    def test_result_can_be_overridden(self):
        ev = _builder().event("CameraCommandSent", result=EventResult.SENT)
        assert ev.result == EventResult.SENT

    def test_message_defaults_to_empty_string(self):
        ev = _builder().event("AppStarted")
        assert ev.message == ""

    def test_message_can_be_set(self):
        ev = _builder().event("AppStarted", message="startup complete")
        assert ev.message == "startup complete"


# ═══════════════════════════════════════════════════════════════════════════════
# Timestamp
# ═══════════════════════════════════════════════════════════════════════════════

class TestTimestamp:
    def test_timestamp_matches_iso_milliseconds_format(self):
        ev = _builder().event("AppStarted")
        assert _ISO_RE.match(ev.timestamp), f"Unexpected format: {ev.timestamp!r}"

    def test_timestamp_ends_with_z(self):
        ev = _builder().event("AppStarted")
        assert ev.timestamp.endswith("Z")

    def test_timestamp_is_recent(self):
        before = datetime.now(timezone.utc).replace(microsecond=0)
        ev = _builder().event("AppStarted")
        after = datetime.now(timezone.utc)
        ts = datetime.fromisoformat(ev.timestamp.replace("Z", "+00:00"))
        assert before <= ts <= after

    def test_each_event_has_valid_timestamp(self):
        b = _builder()
        for _ in range(5):
            ev = b.event("AppStarted")
            assert _ISO_RE.match(ev.timestamp)


# ═══════════════════════════════════════════════════════════════════════════════
# Correlation ID
# ═══════════════════════════════════════════════════════════════════════════════

class TestCorrelationId:
    def test_auto_generated_is_uuid4(self):
        ev = _builder().event("AppStarted")
        assert _UUID4_RE.match(ev.correlation_id), f"Not a UUID4: {ev.correlation_id!r}"

    def test_explicit_correlation_id_preserved(self):
        cid = "my-trace-id-123"
        ev = _builder().event("AppStarted", correlation_id=cid)
        assert ev.correlation_id == cid

    def test_consecutive_auto_ids_differ(self):
        b = _builder()
        ids = {b.event("AppStarted").correlation_id for _ in range(10)}
        assert len(ids) == 10


# ═══════════════════════════════════════════════════════════════════════════════
# Extra keyword arguments passed to BlackBoxEvent
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtraKwargs:
    def test_seat_id_passed_through(self):
        ev = _builder().event("SeatPresetRecallRequested", seat_id="seat-3")
        assert ev.seat_id == "seat-3"

    def test_camera_id_passed_through(self):
        ev = _builder().event("CameraCommandSent", camera_id="cam-1")
        assert ev.camera_id == "cam-1"

    def test_duration_ms_passed_through(self):
        ev = _builder().event("CameraCommandSucceeded", duration_ms=42)
        assert ev.duration_ms == 42

    def test_preset_field_passed_through(self):
        ev = _builder().event("SeatPresetRecallRequested", preset="10")
        assert ev.preset == "10"


# ═══════════════════════════════════════════════════════════════════════════════
# Default constructor values
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuilderDefaults:
    def test_default_app_version(self):
        ev = EventBuilder().event("AppStarted")
        assert ev.app_version == "unknown"

    def test_default_source_is_system(self):
        ev = EventBuilder().event("AppStarted")
        assert ev.source == EventSource.SYSTEM

    def test_default_runtime_mode_is_production(self):
        ev = EventBuilder().event("AppStarted")
        assert ev.runtime_mode == "production"

    def test_default_session_id(self):
        ev = EventBuilder().event("AppStarted")
        assert ev.session_id == "none"

    def test_default_installation_id(self):
        ev = EventBuilder().event("AppStarted")
        assert ev.installation_id == "unknown"

    def test_same_builder_instance_for_multiple_events(self):
        b = EventBuilder(app_version="1.0.0", session_id="sess-x")
        ev1 = b.event("AppStarted")
        ev2 = b.event("SessionStarted")
        assert ev1.app_version == ev2.app_version == "1.0.0"
        assert ev1.session_id == ev2.session_id == "sess-x"
