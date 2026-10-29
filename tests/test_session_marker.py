#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_session_marker.py — Tests for session_marker module (#120).

Verifies:
- mark_session_active() creates the marker file with timestamp content
- clear_session_marker() removes the marker file
- was_session_interrupted() returns True when marker exists (and logs warning)
- was_session_interrupted() returns False when no marker exists
- clear_session_marker() is safe when no marker exists
- mark_session_active() survives write errors gracefully
- Marker file contains ISO-format timestamp
"""
from __future__ import annotations

import logging


import application.session_marker as sm


# ── mark_session_active ───────────────────────────────────────────────────────

class TestMarkSessionActive:

    def test_creates_marker_file(self, tmp_path):
        path = tmp_path / "session.active"
        sm.mark_session_active(path)
        assert path.exists()

    def test_marker_contains_timestamp(self, tmp_path):
        path = tmp_path / "session.active"
        sm.mark_session_active(path)
        content = path.read_text(encoding="utf-8").strip()
        assert content  # non-empty
        # ISO format: YYYY-MM-DDTHH:MM:SS[.ffffff]
        assert "T" in content or "-" in content

    def test_overwrites_existing_marker(self, tmp_path):
        path = tmp_path / "session.active"
        path.write_text("old", encoding="utf-8")
        sm.mark_session_active(path)
        assert path.read_text(encoding="utf-8").strip() != "old"

    def test_write_failure_does_not_raise(self, tmp_path):
        path = tmp_path / "nonexistent_dir" / "session.active"
        sm.mark_session_active(path)  # parent dir doesn't exist → OSError → logged, not raised


# ── clear_session_marker ──────────────────────────────────────────────────────

class TestClearSessionMarker:

    def test_removes_existing_marker(self, tmp_path):
        path = tmp_path / "session.active"
        sm.mark_session_active(path)
        sm.clear_session_marker(path)
        assert not path.exists()

    def test_safe_when_no_marker(self, tmp_path):
        path = tmp_path / "session.active"
        sm.clear_session_marker(path)  # no marker — must not raise

    def test_idempotent(self, tmp_path):
        path = tmp_path / "session.active"
        sm.mark_session_active(path)
        sm.clear_session_marker(path)
        sm.clear_session_marker(path)  # second call must not raise


# ── was_session_interrupted ───────────────────────────────────────────────────

class TestWasSessionInterrupted:

    def test_returns_false_when_no_marker(self, tmp_path):
        path = tmp_path / "session.active"
        assert sm.was_session_interrupted(path) is False

    def test_returns_true_when_marker_exists(self, tmp_path):
        path = tmp_path / "session.active"
        sm.mark_session_active(path)
        assert sm.was_session_interrupted(path) is True

    def test_logs_warning_when_interrupted(self, tmp_path, caplog):
        path = tmp_path / "session.active"
        sm.mark_session_active(path)
        with caplog.at_level(logging.WARNING, logger="application.session_marker"):
            sm.was_session_interrupted(path)
        assert any("unexpectedly" in r.message.lower() or "session" in r.message.lower()
                   for r in caplog.records)

    def test_no_warning_when_no_marker(self, tmp_path, caplog):
        path = tmp_path / "session.active"
        with caplog.at_level(logging.WARNING, logger="application.session_marker"):
            sm.was_session_interrupted(path)
        assert not caplog.records

    def test_returns_true_when_marker_has_no_content(self, tmp_path):
        path = tmp_path / "session.active"
        path.write_text("", encoding="utf-8")  # empty marker (edge case)
        assert sm.was_session_interrupted(path) is True

    def test_warning_includes_start_time_from_marker(self, tmp_path, caplog):
        path = tmp_path / "session.active"
        path.write_text("2026-05-07T14:30:00", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="application.session_marker"):
            sm.was_session_interrupted(path)
        assert any("2026-05-07" in r.message for r in caplog.records)


# ── Session lifecycle integration ─────────────────────────────────────────────

class TestSessionLifecycle:

    def test_mark_then_clear_leaves_no_marker(self, tmp_path):
        path = tmp_path / "session.active"
        sm.mark_session_active(path)
        sm.clear_session_marker(path)
        assert not sm.was_session_interrupted(path)

    def test_interrupted_then_clear_resolves_state(self, tmp_path):
        path = tmp_path / "session.active"
        sm.mark_session_active(path)
        # Simulate startup check
        interrupted = sm.was_session_interrupted(path)
        assert interrupted is True
        # On next clean end
        sm.clear_session_marker(path)
        assert not sm.was_session_interrupted(path)
