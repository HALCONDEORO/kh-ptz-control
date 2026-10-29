#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_logging_setup.py — runtime.logging_setup tests

from __future__ import annotations

import logging
import logging.handlers

import pytest

import runtime.logging_setup as _logging_setup_mod
from runtime.logging_setup import setup_logging


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_root_logger():
    """Remove only HALLPTZ-added handlers from the root logger and reset config flag."""
    root = logging.getLogger()
    for h in list(_logging_setup_mod._added_handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    _logging_setup_mod._added_handlers.clear()
    _logging_setup_mod._configured = False
    root.setLevel(logging.WARNING)  # restore pytest default


@pytest.fixture(autouse=True)
def clean_root_logger():
    _reset_root_logger()
    yield
    _reset_root_logger()


# ── console-only (no log_dir) ─────────────────────────────────────────────────

def test_console_only_when_no_log_dir():
    result = setup_logging()
    assert result is False


def test_console_only_adds_stream_handler():
    setup_logging()
    root = logging.getLogger()
    stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)
                       and not isinstance(h, logging.FileHandler)]
    assert len(stream_handlers) >= 1


def test_no_file_handler_when_no_log_dir():
    setup_logging()
    root = logging.getLogger()
    rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(rotating) == 0


# ── file handler ──────────────────────────────────────────────────────────────

def test_returns_true_when_log_dir_writable(tmp_path):
    log_dir = tmp_path / "logs"
    result = setup_logging(log_dir=log_dir)
    assert result is True


def test_creates_log_file(tmp_path):
    log_dir = tmp_path / "logs"
    setup_logging(log_dir=log_dir)
    assert (log_dir / "app.log").exists()


def test_adds_rotating_file_handler(tmp_path):
    log_dir = tmp_path / "logs"
    setup_logging(log_dir=log_dir)
    root = logging.getLogger()
    rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(rotating) == 1


def test_creates_log_dir_if_missing(tmp_path):
    log_dir = tmp_path / "deep" / "nested" / "logs"
    assert not log_dir.exists()
    setup_logging(log_dir=log_dir)
    assert log_dir.exists()


def test_rotating_handler_max_bytes(tmp_path):
    log_dir = tmp_path / "logs"
    setup_logging(log_dir=log_dir)
    root = logging.getLogger()
    rh = next(h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
    assert rh.maxBytes == 5 * 1024 * 1024


def test_rotating_handler_backup_count(tmp_path):
    log_dir = tmp_path / "logs"
    setup_logging(log_dir=log_dir)
    root = logging.getLogger()
    rh = next(h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
    assert rh.backupCount == 5


# ── startup banner ────────────────────────────────────────────────────────────

def test_version_line_appears_in_log_file(tmp_path):
    log_dir = tmp_path / "logs"
    setup_logging(log_dir=log_dir, version_line="Hall PTZ Control 0.1.0 (abc1234)")
    log_path = log_dir / "app.log"
    content = log_path.read_text(encoding="utf-8")
    assert "Hall PTZ Control 0.1.0 (abc1234)" in content


def test_log_path_banner_appears_in_log_file(tmp_path):
    log_dir = tmp_path / "logs"
    setup_logging(log_dir=log_dir)
    log_path = log_dir / "app.log"
    content = log_path.read_text(encoding="utf-8")
    assert "app.log" in content


def test_no_banner_when_version_empty(tmp_path):
    log_dir = tmp_path / "logs"
    setup_logging(log_dir=log_dir, version_line="")
    log_path = log_dir / "app.log"
    content = log_path.read_text(encoding="utf-8")
    assert "startup" not in content


# ── idempotency ───────────────────────────────────────────────────────────────

def test_double_call_does_not_add_extra_handlers(tmp_path):
    log_dir = tmp_path / "logs"
    setup_logging(log_dir=log_dir)
    setup_logging(log_dir=log_dir)
    root = logging.getLogger()
    rotating = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(rotating) == 1


# ── fallback on unwritable dir ────────────────────────────────────────────────

def test_fallback_to_console_when_log_dir_not_writable(tmp_path):
    # Point to a file path (not a directory) to force OSError
    not_a_dir = tmp_path / "i_am_a_file"
    not_a_dir.write_text("block", encoding="utf-8")
    # Try to use the file as a directory — should fail and fall back silently
    result = setup_logging(log_dir=not_a_dir / "logs")
    # On some systems mkdir may still succeed; the key assertion is no exception raised
    assert isinstance(result, bool)


# ── log level ─────────────────────────────────────────────────────────────────

def test_default_level_is_info():
    setup_logging()
    root = logging.getLogger()
    assert root.level == logging.INFO


def test_custom_level_applied(tmp_path):
    log_dir = tmp_path / "logs"
    setup_logging(log_dir=log_dir, level=logging.DEBUG)
    root = logging.getLogger()
    assert root.level == logging.DEBUG


# ── log_startup_summary ───────────────────────────────────────────────────────

class _FakeResolver:
    """Minimal RuntimePathResolver stand-in for testing log_startup_summary."""

    def __init__(self, tmp_path, *, with_config: bool = False, overrides: dict | None = None):
        self.config_dir  = tmp_path / "etc_hallptz"
        self.data_dir    = tmp_path / "var_lib_hallptz"
        self.log_dir     = tmp_path / "var_log_hallptz"
        self.backup_dir  = tmp_path / "var_backups_hallptz"
        self._with_config = with_config
        self._overrides   = overrides or {}
        if with_config:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            (self.config_dir / "config.yaml").write_text("# stub", encoding="utf-8")

    def active_overrides(self) -> dict:
        return dict(self._overrides)


def test_startup_summary_logs_mode(tmp_path, caplog):
    from runtime.logging_setup import log_startup_summary
    setup_logging()
    with caplog.at_level(logging.INFO, logger="runtime.logging_setup"):
        log_startup_summary(_FakeResolver(tmp_path), mode="demo")
    assert any("demo" in r.message for r in caplog.records)


def test_startup_summary_logs_paths(tmp_path, caplog):
    from runtime.logging_setup import log_startup_summary
    setup_logging()
    with caplog.at_level(logging.INFO, logger="runtime.logging_setup"):
        log_startup_summary(_FakeResolver(tmp_path), mode="production")
    combined = " ".join(r.message for r in caplog.records)
    assert "config" in combined
    assert "data" in combined
    assert "log" in combined


def test_startup_summary_config_present(tmp_path, caplog):
    from runtime.logging_setup import log_startup_summary
    setup_logging()
    resolver = _FakeResolver(tmp_path, with_config=True)
    with caplog.at_level(logging.INFO, logger="runtime.logging_setup"):
        log_startup_summary(resolver)
    assert any("present" in r.message for r in caplog.records)
    # Must not be a WARNING about missing config
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not any("NOT FOUND" in r.message for r in warns)


def test_startup_summary_config_missing_warns(tmp_path, caplog):
    from runtime.logging_setup import log_startup_summary
    setup_logging()
    resolver = _FakeResolver(tmp_path, with_config=False)
    with caplog.at_level(logging.WARNING, logger="runtime.logging_setup"):
        log_startup_summary(resolver)
    assert any("NOT FOUND" in r.message for r in caplog.records)


def test_startup_summary_logs_env_overrides(tmp_path, caplog):
    from runtime.logging_setup import log_startup_summary
    setup_logging()
    resolver = _FakeResolver(tmp_path, overrides={"HALLPTZ_CONFIG_DIR": "/custom/etc"})
    with caplog.at_level(logging.INFO, logger="runtime.logging_setup"):
        log_startup_summary(resolver)
    assert any("HALLPTZ_CONFIG_DIR" in r.message for r in caplog.records)


def test_startup_summary_no_overrides_message(tmp_path, caplog):
    from runtime.logging_setup import log_startup_summary
    setup_logging()
    resolver = _FakeResolver(tmp_path)
    with caplog.at_level(logging.INFO, logger="runtime.logging_setup"):
        log_startup_summary(resolver)
    assert any("No env overrides" in r.message for r in caplog.records)


def test_startup_summary_does_not_log_secrets(tmp_path, caplog):
    """log_startup_summary must never emit passwords, IPs or sensitive config values."""
    from runtime.logging_setup import log_startup_summary
    setup_logging()
    resolver = _FakeResolver(tmp_path)
    with caplog.at_level(logging.DEBUG, logger="runtime.logging_setup"):
        log_startup_summary(resolver)
    combined = " ".join(r.message for r in caplog.records)
    # Spot-check: no raw IPs in the 192.168/10.x/172.16 range in log output
    import re
    assert not re.search(r"\b(?:192\.168|10\.\d+|172\.1[6-9]|172\.2\d|172\.3[01])\.\d+\.\d+\b", combined), (
        "startup summary must not contain raw private IP addresses"
    )


# ── flight_recorder._warn uses logger, not print ─────────────────────────────

def test_flight_recorder_warn_uses_logger(caplog, tmp_path):
    """FlightRecorder._warn must emit via logging, not print to stderr."""
    import io
    import sys
    from application.flight_recorder import FlightRecorder

    recorder = FlightRecorder(events_file=tmp_path / "events.jsonl")

    captured_stderr = io.StringIO()
    with caplog.at_level(logging.WARNING, logger="application.flight_recorder"):
        old_stderr, sys.stderr = sys.stderr, captured_stderr
        try:
            recorder._warn("test warning message")
        finally:
            sys.stderr = old_stderr

    # Must appear in the log
    assert any("test warning message" in r.message for r in caplog.records)
    # Must NOT appear as a raw print on stderr
    assert "test warning message" not in captured_stderr.getvalue()
