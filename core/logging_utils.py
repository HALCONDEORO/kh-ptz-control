# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from __future__ import annotations

import logging
import logging.handlers
import time
from collections.abc import Callable
from pathlib import Path


class RepeatedMessageFilter(logging.Filter):
    def __init__(
        self,
        *,
        min_level: int = logging.ERROR,
        summary_every: int = 10,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self.min_level = min_level
        self.summary_every = max(2, summary_every)
        self._clock = clock
        self._last_key: tuple[str, int, str] | None = None
        self._repeat_count = 0

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.CRITICAL or record.levelno < self.min_level:
            self._reset()
            return True

        key = (record.name, record.levelno, record.getMessage())
        if key != self._last_key:
            self._last_key = key
            self._repeat_count = 0
            return True

        self._repeat_count += 1
        if self._repeat_count % self.summary_every != 0:
            return False

        record.msg = "Previous log message repeated %s times: %s"
        record.args = (self._repeat_count, key[2])
        return True

    def _reset(self) -> None:
        self._last_key = None
        self._repeat_count = 0


def install_repeated_message_filter(
    logger: logging.Logger | None = None,
    *,
    summary_every: int = 10,
) -> RepeatedMessageFilter:
    target = logger or logging.getLogger()
    rate_filter = RepeatedMessageFilter(summary_every=summary_every)
    handlers = target.handlers or logging.getLogger().handlers
    for handler in handlers:
        handler.addFilter(rate_filter)
    return rate_filter


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 3


def configure_file_logging(
    log_dir: Path,
    log_file: str = "app.log",
    *,
    logger: logging.Logger | None = None,
    max_bytes: int = _MAX_BYTES,
    backup_count: int = _BACKUP_COUNT,
) -> logging.handlers.RotatingFileHandler | None:
    """
    Add a ``RotatingFileHandler`` to *logger* (default: root logger).

    Creates *log_dir* if it does not exist.  Returns the handler on success,
    or ``None`` if the directory cannot be created or the file cannot be opened
    (graceful fallback — never raises, never blocks startup).

    Parameters
    ----------
    log_dir:
        Directory that will contain the rotating log file.
    log_file:
        File name inside *log_dir*.  Defaults to ``"app.log"``.
    logger:
        Logger to attach the handler to.  Defaults to the root logger.
    max_bytes:
        Roll over when the log file exceeds this size.  Defaults to 2 MB.
    backup_count:
        Number of backup files to keep.  Defaults to 3.
    """
    target = logger or logging.getLogger()
    try:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        target.addHandler(handler)
        return handler
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "configure_file_logging: could not set up file handler in %s: %s"
            " — continuing without file logging",
            log_dir,
            exc,
        )
        return None
