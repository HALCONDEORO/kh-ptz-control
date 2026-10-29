#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
application/boot_metrics.py — Boot/startup telemetry models.

Pure-Python (no PyQt) helpers extracted from ui/splash_screen.py so the splash
widget keeps only presentation concerns:

  - TestResult     : tracks a single startup check (name, success, timing) and
                     serialises to a dict.
  - BootStatistics : reads/aggregates boot history from a JSON file for system
                     health monitoring.

ui/splash_screen.py re-exports both names for backward compatibility, so
`from ui.splash_screen import TestResult, BootStatistics` keeps working.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _default_stats_path() -> Path:
    from runtime.path_resolver import RuntimePathResolver
    return RuntimePathResolver().data_dir / "boot_stats.json"


# ═══════════════════════════════════════════════════════════════════════════════
#  RASTREO DE RESULTADOS DE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestResult:
    """Rastrear resultado individual de test y timing."""

    # Prevent pytest from trying to collect this class as a test suite.
    __test__ = False

    def __init__(self, name: str):
        self.name = name
        self.start_time = time.time()
        self.success = False
        self.error_msg: Optional[str] = None
        self.duration_ms = 0
        self._finished_at: Optional[str] = None

    def finish(self, success: bool, error: Optional[str] = None):
        self.success = success
        self.error_msg = error
        self.duration_ms = int((time.time() - self.start_time) * 1000)
        self._finished_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error_msg,
            "timestamp": self._finished_at or datetime.now().isoformat(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  ESTADÍSTICAS DE BOOTS
# ═══════════════════════════════════════════════════════════════════════════════

class BootStatistics:
    """Rastrear historial de boots para monitoreo de salud del sistema."""

    def __init__(self, stats_file: str | Path | None = None):
        self.stats_file = Path(stats_file) if stats_file is not None else _default_stats_path()
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not self.stats_file.exists():
            try:
                self.stats_file.parent.mkdir(parents=True, exist_ok=True)
                self.stats_file.write_text("[]", encoding='utf-8')
            except OSError:
                pass

    def record_boot(self, duration_ms: int, tests_passed: int, total_tests: int) -> bool:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "duration_ms": duration_ms,
            "tests_passed": tests_passed,
            "total_tests": total_tests,
            "success": tests_passed == total_tests
        }
        try:
            stats = self._read_stats()
            stats.append(entry)
            if len(stats) > 100:
                stats = stats[-100:]
            tmp = self.stats_file.with_name(self.stats_file.name + ".tmp")
            tmp.write_text(json.dumps(stats, indent=2), encoding='utf-8')
            os.replace(str(tmp), str(self.stats_file))
            return True
        except OSError as exc:
            logger.warning("boot_metrics: failed to record boot entry: %s", exc)
            return False

    def _read_stats(self) -> list:
        try:
            if not self.stats_file.exists():
                return []
            data = json.loads(self.stats_file.read_text(encoding='utf-8'))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return []

    def get_summary(self) -> dict:
        stats = self._read_stats()
        if not stats:
            return {}
        successful = sum(1 for s in stats if s.get("success", False))
        avg_duration = int(sum(s.get("duration_ms", 0) for s in stats) / len(stats))
        success_rate = successful / len(stats) * 100
        return {
            "total_boots": len(stats),
            "successful": successful,
            "success_rate": f"{success_rate:.1f}%",
            "avg_duration_ms": avg_duration,
            "last_boot": stats[-1].get("timestamp", "")
        }
