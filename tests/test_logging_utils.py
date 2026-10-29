# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from __future__ import annotations

import logging
import logging.handlers

import pytest

from core.logging_utils import RepeatedMessageFilter, configure_file_logging


def _record(message: str, *, level: int = logging.ERROR) -> logging.LogRecord:
    return logging.LogRecord(
        name="test.logger",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_first_error_is_logged():
    log_filter = RepeatedMessageFilter(summary_every=3)

    assert log_filter.filter(_record("camera timeout")) is True


def test_repeated_errors_are_suppressed_until_summary():
    log_filter = RepeatedMessageFilter(summary_every=3)

    assert log_filter.filter(_record("camera timeout")) is True
    assert log_filter.filter(_record("camera timeout")) is False
    assert log_filter.filter(_record("camera timeout")) is False
    summary = _record("camera timeout")
    assert log_filter.filter(summary) is True
    assert summary.getMessage() == "Previous log message repeated 3 times: camera timeout"


def test_different_error_is_logged():
    log_filter = RepeatedMessageFilter(summary_every=3)

    assert log_filter.filter(_record("camera timeout")) is True
    assert log_filter.filter(_record("camera timeout")) is False
    assert log_filter.filter(_record("atem timeout")) is True


def test_critical_error_is_not_suppressed():
    log_filter = RepeatedMessageFilter(summary_every=3)

    assert log_filter.filter(_record("camera timeout")) is True
    assert log_filter.filter(_record("camera timeout")) is False
    assert log_filter.filter(_record("camera timeout", level=logging.CRITICAL)) is True


# ── configure_file_logging ────────────────────────────────────────────────────

@pytest.fixture()
def isolated_logger():
    """Return a fresh named logger with no handlers; clean up after the test."""
    log = logging.getLogger(f"test.file_logging.{id(object())}")
    log.handlers.clear()
    yield log
    for h in list(log.handlers):
        log.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass


def test_configure_file_logging_adds_rotating_handler(tmp_path, isolated_logger):
    handler = configure_file_logging(tmp_path / "logs", logger=isolated_logger)
    assert handler is not None
    rotating = [h for h in isolated_logger.handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(rotating) == 1


def test_configure_file_logging_creates_log_file(tmp_path, isolated_logger):
    log_dir = tmp_path / "logs"
    configure_file_logging(log_dir, logger=isolated_logger)
    assert (log_dir / "app.log").exists()


def test_configure_file_logging_creates_missing_directory(tmp_path, isolated_logger):
    log_dir = tmp_path / "deep" / "nested" / "logs"
    assert not log_dir.exists()
    configure_file_logging(log_dir, logger=isolated_logger)
    assert log_dir.exists()


def test_configure_file_logging_max_bytes(tmp_path, isolated_logger):
    handler = configure_file_logging(tmp_path / "logs", logger=isolated_logger)
    assert handler is not None
    assert handler.maxBytes == 2_000_000


def test_configure_file_logging_backup_count(tmp_path, isolated_logger):
    handler = configure_file_logging(tmp_path / "logs", logger=isolated_logger)
    assert handler is not None
    assert handler.backupCount == 3


def test_configure_file_logging_returns_none_on_unwritable_path(tmp_path, isolated_logger):
    # Use a *file* as the parent so mkdir fails
    blocker = tmp_path / "i_am_a_file"
    blocker.write_text("block", encoding="utf-8")
    handler = configure_file_logging(blocker / "logs", logger=isolated_logger)
    # Must not raise; returns None and leaves logger handler-free
    assert handler is None


def test_configure_file_logging_uses_root_logger_by_default(tmp_path):
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    try:
        handler = configure_file_logging(tmp_path / "logs")
        assert handler is not None
        assert handler in root.handlers
    finally:
        if handler is not None:
            root.removeHandler(handler)
            handler.close()
        # Restore any handlers that were there before
        for h in original_handlers:
            if h not in root.handlers:
                root.addHandler(h)
