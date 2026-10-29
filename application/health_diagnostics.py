#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/health_diagnostics.py — HealthDiagnosticsService
#
# Comprueba estado del disco y temperatura de la CPU.
# Todo I/O es inyectable para que los tests sean hardware-free.

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Callable, Optional

from application.diagnostics_service import CheckResult, Status

# ── Umbrales por defecto ──────────────────────────────────────────────────────

DISK_WARN_FREE_MB:  int = 1024   # advertir si hay menos de 1 GB libre
DISK_FAIL_FREE_MB:  int = 256    # fallo si hay menos de 256 MB libre

TEMP_WARN_CELSIUS:  float = 78.0
TEMP_FAIL_CELSIUS:  float = 90.0

# Ruta del sensor de temperatura en Raspberry Pi (Linux)
_RPI_TEMP_PATH = Path("/sys/class/thermal/thermal_zone0/temp")


def _read_rpi_temperature() -> Optional[float]:
    """Read CPU temperature in Celsius from the Raspberry Pi thermal sensor.
    Returns None if unavailable (non-Linux, missing file, read error).
    """
    if sys.platform != "linux":
        return None
    try:
        raw = _RPI_TEMP_PATH.read_text(encoding="utf-8").strip()
        return int(raw) / 1000.0
    except (OSError, ValueError):
        return None


class HealthDiagnosticsService:
    """
    Checks disk space and CPU temperature for the `khptz doctor` command.

    Parameters
    ----------
    disk_usage_fn:
        Injectable. Defaults to shutil.disk_usage.  Override in tests.
    temp_reader_fn:
        Injectable. Defaults to the Raspberry Pi thermal sensor reader.
        Must return temperature in Celsius as float, or None if unavailable.
    warn_free_mb / fail_free_mb:
        Disk space thresholds in megabytes.
    warn_temp / fail_temp:
        CPU temperature thresholds in Celsius.
    """

    def __init__(
        self,
        disk_usage_fn: Optional[Callable] = None,
        temp_reader_fn: Optional[Callable[[], Optional[float]]] = None,
        warn_free_mb: int = DISK_WARN_FREE_MB,
        fail_free_mb: int = DISK_FAIL_FREE_MB,
        warn_temp: float = TEMP_WARN_CELSIUS,
        fail_temp: float = TEMP_FAIL_CELSIUS,
    ) -> None:
        self._disk_usage = disk_usage_fn or shutil.disk_usage
        self._read_temp   = temp_reader_fn or _read_rpi_temperature
        self._warn_free   = warn_free_mb * 1024 * 1024   # convert MB → bytes
        self._fail_free   = fail_free_mb * 1024 * 1024
        self._warn_temp   = warn_temp
        self._fail_temp   = fail_temp

    # ── Public API ────────────────────────────────────────────────────────────

    def check_disk(self, path: Path) -> CheckResult:
        """Check free disk space at *path*."""
        try:
            usage = self._disk_usage(path)
        except OSError as exc:
            return CheckResult("disk_space", Status.FAIL, f"Cannot read disk usage at {path}: {exc}")

        free_mb  = usage.free  // (1024 * 1024)
        total_mb = usage.total // (1024 * 1024)
        pct_free = (usage.free / usage.total * 100) if usage.total else 0

        label = f"Disk space: {free_mb} MB free of {total_mb} MB ({pct_free:.0f}%)"

        if usage.free < self._fail_free:
            return CheckResult("disk_space", Status.FAIL, f"Disk critically low — {label}")
        if usage.free < self._warn_free:
            return CheckResult("disk_space", Status.WARNING, f"Disk space low — {label}")
        return CheckResult("disk_space", Status.OK, label)

    def check_temperature(self) -> CheckResult:
        """Check CPU temperature (Raspberry Pi only; reports OK on other platforms)."""
        temp = self._read_temp()
        if temp is None:
            return CheckResult(
                "cpu_temperature",
                Status.OK,
                "CPU temperature: not available on this platform",
            )

        label = f"CPU temperature: {temp:.1f}°C"

        if temp >= self._fail_temp:
            return CheckResult("cpu_temperature", Status.FAIL, f"CPU overheating — {label}")
        if temp >= self._warn_temp:
            return CheckResult("cpu_temperature", Status.WARNING, f"CPU temperature high — {label}")
        return CheckResult("cpu_temperature", Status.OK, label)
