#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/crash_reporter.py — Local crash report writer for unhandled exceptions (#118)
#
# Usage (call once at startup, before any UI or service initialisation):
#
#   from application.crash_reporter import install_crash_reporter
#   install_crash_reporter()
#
# On an unhandled exception the hook writes:
#   logs/crash_YYYY-MM-DD_HHMMSS.log
# under the application install directory (or a caller-supplied log_dir).
#
# Report contents: traceback, version, mode, Python/platform summary.
# Excluded: passwords, seat names, customer personal data.

from __future__ import annotations

import os
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

_DEFAULT_LOG_DIR = Path(__file__).parent.parent / "logs"
_MAX_REPORT_BYTES = 64 * 1024  # 64 KB cap

# Set by install_crash_reporter() so the hook can include mode/version
_installed_version: str = "unknown"
_installed_mode: str = "unknown"
_installed_log_dir: Path = _DEFAULT_LOG_DIR


def _build_report(exc_type, exc_value, exc_tb) -> str:
    """Assemble the crash report text. Never raises."""
    lines: list[str] = []

    lines.append("=" * 60)
    lines.append("KH PTZ Control — crash report")
    lines.append(f"Time:    {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Version: {_installed_version}")
    lines.append(f"Mode:    {_installed_mode}")
    lines.append(f"Python:  {sys.version}")
    lines.append(f"Platform:{platform.platform()}")
    lines.append("=" * 60)
    lines.append("")
    lines.append("Traceback (most recent call last):")

    try:
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        lines.extend("".join(tb_lines).splitlines())
    except Exception as fmt_exc:
        lines.append(f"[crash_reporter] Could not format traceback: {fmt_exc}")

    lines.append("")
    lines.append("=" * 60)
    report = "\n".join(lines) + "\n"

    # Cap report size to avoid filling storage
    if len(report.encode()) > _MAX_REPORT_BYTES:
        report = report[: _MAX_REPORT_BYTES].rsplit("\n", 1)[0]
        report += "\n[crash_reporter] Report truncated at 64 KB\n"
    return report


def _user_fallback_dir() -> Optional[Path]:
    """Per-user crash report directory, used when the production path is read-only.

    Kept dependency-free on purpose: application/ must not import runtime/.
    """
    try:
        base = os.environ.get("XDG_STATE_HOME")
        root = Path(base) if base else Path.home() / ".local" / "state"
        return root / "khptz" / "crash"
    except Exception:  # noqa: BLE001
        return None


def _write_report(report: str) -> Optional[Path]:
    """Write *report* to the first writable candidate directory.

    On a real install /opt/khptz is read-only to the service and /var/log/khptz is
    owned by the service user, so a crash report written by the desktop user had
    nowhere to go and was silently lost (#884). Try the configured production
    path first, then fall back to the calling user's own state directory.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    for directory in (_installed_log_dir, _user_fallback_dir()):
        if directory is None:
            continue
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"crash_{timestamp}.log"
            path.write_text(report, encoding="utf-8")
            return path
        except Exception:  # noqa: BLE001
            continue
    return None


def _excepthook(exc_type, exc_value, exc_tb):
    """Replacement for sys.excepthook — writes a crash report then falls through."""
    # Skip KeyboardInterrupt so Ctrl-C still works cleanly
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    try:
        report = _build_report(exc_type, exc_value, exc_tb)
        path = _write_report(report)
        if path:
            print(f"\n[crash_reporter] Crash report saved: {path}", file=sys.stderr)
        else:
            print(
                f"\n[crash_reporter] Could not write crash report to {_installed_log_dir}",
                file=sys.stderr,
            )
    except Exception:  # noqa: BLE001
        pass  # crash reporter must not crash

    # Always delegate to the default hook so the traceback appears on stderr
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def install_crash_reporter(
    version: str = "unknown",
    mode: str = "unknown",
    log_dir: Path | None = None,
) -> None:
    """
    Install the crash reporter as sys.excepthook.

    Parameters
    ----------
    version:
        Application version string (from VERSION file).
    mode:
        Runtime mode label, e.g. 'production', 'demo', 'simulation'.
    log_dir:
        Directory for crash report files. Defaults to <install_root>/logs/.
    """
    global _installed_version, _installed_mode, _installed_log_dir
    _installed_version = version
    _installed_mode = mode
    _installed_log_dir = Path(log_dir) if log_dir is not None else _DEFAULT_LOG_DIR
    sys.excepthook = _excepthook
