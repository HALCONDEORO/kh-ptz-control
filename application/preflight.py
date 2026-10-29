#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Readiness checks for the on-device setup wizard.

The basic checks are blocking when installation cannot work. Raspberry Pi runtime
advisories are warning-only because the privileged provisioning integration fixes
what it safely can (UTF-8, X11 authorization and legacy autostarts) after the
operator confirms the wizard.
"""
from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

MIN_FREE_BYTES = 500 * 1024 * 1024
SUPPORTED_PY: Tuple[int, int] = (3, 9)


@dataclass(frozen=True)
class PreflightCheck:
    key: str
    label: str
    ok: bool
    warn_only: bool
    detail: str
    remediation: str = ""

    @property
    def blocking(self) -> bool:
        return not self.ok and not self.warn_only


def check_python(version: Tuple[int, int, int] = sys.version_info[:3]) -> PreflightCheck:
    major, minor = version[0], version[1]
    if (major, minor) == SUPPORTED_PY:
        return PreflightCheck(
            "python", "Python 3.9.2", True, False,
            f"Python {major}.{minor} — supported",
        )
    if (major, minor) > SUPPORTED_PY:
        return PreflightCheck(
            "python", "Python version", False, True,
            f"Python {major}.{minor} is newer than the validated 3.9.2",
            "Use Raspberry Pi OS Bullseye (Python 3.9.2) for production",
        )
    return PreflightCheck(
        "python", "Python version", False, False,
        f"Python {major}.{minor} is too old (need 3.9)",
        "Install Python 3.9.2 (Raspberry Pi OS Bullseye)",
    )


def check_pyqt(available: Optional[bool] = None) -> PreflightCheck:
    if available is None:
        import importlib.util
        available = importlib.util.find_spec("PyQt5") is not None
    if available:
        return PreflightCheck("pyqt", "PyQt5", True, False, "PyQt5 is available")
    return PreflightCheck(
        "pyqt", "PyQt5", False, False, "PyQt5 is not installed",
        "sudo apt install -y python3-pyqt5 python3-pyqt5.qtsvg",
    )


def check_disk_space(free_bytes: int, min_bytes: int = MIN_FREE_BYTES) -> PreflightCheck:
    free_mb = free_bytes // (1024 * 1024)
    if free_bytes >= min_bytes:
        return PreflightCheck("disk", "Disk space", True, False, f"{free_mb} MB free")
    return PreflightCheck(
        "disk", "Disk space", False, False,
        f"Only {free_mb} MB free (need {min_bytes // (1024 * 1024)} MB)",
        "Free up space on the SD card before installing",
    )


def _rpi_advisory_checks() -> List[PreflightCheck]:
    from application.rpi_runtime_readiness import collect_rpi_setup_advisories

    checks: List[PreflightCheck] = []
    for advisory in collect_rpi_setup_advisories():
        detail = advisory.detail
        if advisory.remediation:
            detail = f"{detail}. {advisory.remediation}"
        checks.append(PreflightCheck(
            advisory.key,
            advisory.label,
            advisory.ok,
            advisory.warn_only,
            detail,
            advisory.remediation,
        ))
    return checks


def run_preflight(
    *,
    free_bytes: Optional[int] = None,
    pyqt_available: Optional[bool] = None,
    python_version: Optional[Tuple[int, int, int]] = None,
    include_rpi_advisories: bool = True,
) -> List[PreflightCheck]:
    """Run setup readiness checks. Arguments are injectable for tests.

    A probe that cannot run must degrade to a warning, never raise. This runs
    from DeviceCheckPage.initializePage — a Qt hook — so an exception escaping
    here does not show an error, it takes the whole wizard down before the
    operator has entered anything.
    """
    checks: List[PreflightCheck] = [
        check_python(python_version if python_version is not None else sys.version_info[:3]),
        check_pyqt(pyqt_available),
    ]

    if free_bytes is None:
        try:
            free_bytes = shutil.disk_usage(".").free
        except OSError as exc:
            # e.g. the process was started in a directory that has since been
            # removed, or an unreadable mount point.
            checks.append(PreflightCheck(
                "disk_space", "Free disk space", True, True,
                f"Could not be measured ({exc})",
                "Check available space manually with: df -h",
            ))
            free_bytes = None

    if free_bytes is not None:
        checks.append(check_disk_space(free_bytes))

    if include_rpi_advisories:
        try:
            checks.extend(_rpi_advisory_checks())
        except Exception as exc:  # noqa: BLE001 — advisories are never blocking
            checks.append(PreflightCheck(
                "rpi_advisories", "Raspberry Pi readiness", True, True,
                f"Advisory checks could not run ({exc})",
                "Run 'khptz doctor' after setup for a full report",
            ))

    return checks


def has_blocking(checks: List[PreflightCheck]) -> bool:
    return any(c.blocking for c in checks)
