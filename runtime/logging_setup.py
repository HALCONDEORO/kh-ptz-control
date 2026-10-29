#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# runtime/logging_setup.py — Production logging configuration for Hall PTZ Control.
#
# Call setup_logging() once at startup, before any other application code runs.
#
# Behaviour:
#   - Always adds a console handler (stderr) with a compact format.
#   - If log_dir is provided and writable, also adds a RotatingFileHandler:
#       <log_dir>/app.log   5 MB per file, 5 backup files, UTF-8.
#   - Logs a startup banner (version line + active log path) at INFO level.
#   - Falls back silently to console-only if the log directory cannot be created
#     or written (never blocks startup).
#
# Production use:
#   log_dir = RuntimePathResolver().log_dir   # /var/log/hallptz/
#
# Dev/test use:
#   setup_logging()                           # console-only
#   setup_logging(log_dir=tmp_path / "logs")  # file + console

from __future__ import annotations

import logging
import os
import logging.handlers
import sys
from pathlib import Path

_LOG_FILE_NAME = "app.log"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 5

_CONSOLE_FORMAT = "[%(levelname)s] %(name)s: %(message)s"
_FILE_FORMAT    = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT    = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger(__name__)

_configured = False
_added_handlers: list[logging.Handler] = []


def setup_logging(
    log_dir: Path | None = None,
    *,
    version_line: str = "",
    level: int = logging.INFO,
) -> bool:
    """
    Configure the root logger for Hall PTZ Control.

    Parameters
    ----------
    log_dir:
        Directory for the rotating log file. If None or not writable,
        logging falls back to console-only (no error raised).
    version_line:
        Human-readable identity string to emit in the startup banner.
        Example: "Hall PTZ Control 0.1.0 (a1b2c3d)"
    level:
        Root log level. Defaults to INFO.

    Returns
    -------
    bool
        True if a file handler was successfully added; False for console-only.
    """
    global _configured
    root = logging.getLogger()
    if _configured:
        return _has_file_handler(root)

    root.setLevel(level)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    root.addHandler(console)
    _added_handlers.append(console)

    file_active = _try_add_file_handler(root, log_dir)
    _configured = True

    if version_line:
        logger.info("=== %s — startup ===", version_line)
    if file_active and log_dir is not None:
        logger.info("Log file: %s", log_dir / _LOG_FILE_NAME)

    return file_active


def _has_file_handler(root: logging.Logger) -> bool:
    return any(
        isinstance(h, logging.handlers.RotatingFileHandler)
        for h in root.handlers
    )


class _GroupSharedRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler that lets the log directory's group write the file.

    Python opens log files with the default mode (0644 after a typical umask),
    which is fine while one identity logs. Under --gui-mode user (#885) two do:
    the GUI runs as the desktop user, while `hallptz doctor`, `hallptz backup` and the
    support bundle run as `hallptz`. Whichever creates app.log first owns it, and
    the other — group member or not — gets read-only access, so its file logging
    silently degrades to console. Production logs are exactly what is needed
    when something goes wrong on an appliance.

    Overriding ``_open`` covers rotation too: doRollover creates the next file
    through the same call, so ownership flipping mid-life does not reintroduce
    the problem.
    """

    def _open(self):
        stream = super()._open()
        try:
            from core.atomic_write import group_shared_mode

            mode = group_shared_mode(Path(self.baseFilename).parent)
            if mode is not None:
                os.chmod(self.baseFilename, mode)
        except OSError:
            # Never let a permissions detail break logging itself.
            pass
        return stream


def _try_add_file_handler(root: logging.Logger, log_dir: Path | None) -> bool:
    if log_dir is None:
        return False
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / _LOG_FILE_NAME
        fh = _GroupSharedRotatingFileHandler(
            log_path,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        fh.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT))
        root.addHandler(fh)
        _added_handlers.append(fh)
        return True
    except OSError as exc:
        # Never block startup — log to console and continue.
        logging.getLogger(__name__).warning(
            "Could not set up file logging in %s: %s — continuing with console only",
            log_dir, exc,
        )
        return False


def log_startup_summary(resolver, *, mode: str = "production") -> None:
    """
    Log a one-time startup summary: runtime mode, paths and config presence.

    Safe in production — never logs config values, passwords or raw network IPs.
    Call once after setup_logging(), before the main loop starts.

    Parameters
    ----------
    resolver:
        A RuntimePathResolver instance (avoids importing at module level).
    mode:
        Runtime profile name: "production", "demo" or "simulation".
    """
    _log = logging.getLogger(__name__)
    _log.info("Runtime mode: %s", mode)
    _log.info("Paths — config: %s | data: %s | log: %s | backup: %s",
              resolver.config_dir, resolver.data_dir,
              resolver.log_dir, resolver.backup_dir)
    config_yaml = resolver.config_dir / "config.yaml"
    if config_yaml.exists():
        _log.info("config.yaml: present (%s)", config_yaml)
    else:
        _log.warning("config.yaml: NOT FOUND at %s — copy config/defaults/starter.yaml to get started",
                     config_yaml)
    overrides = resolver.active_overrides()
    if overrides:
        _log.info("Env overrides active: %s", ", ".join(sorted(overrides)))
    else:
        _log.info("No env overrides active — using production path defaults")
