#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/demo_guard.py — Demo mode isolation and production-config protection
#
# DemoGuard enforces that demo mode never reads from or writes to production
# config/data paths. Call DemoGuard.apply() once at startup before any I/O.
#
# Data directory isolation:
#   Production: ~/.config/hallptz/          (HALLPTZ_DATA_DIR or default)
#   Demo:       ~/.config/hallptz-demo/     (always; cannot be overridden by env)
#
# Protected production paths (never touched in demo mode):
#   config.yaml, PTZ1IP.txt, PTZ2IP.txt, Cam1ID.txt, Cam2ID.txt,
#   ATEMIP.txt, Contact.txt, password.enc, room_layout.json,
#   chairman_presets.json, seat_names.json, schedule.json
#   (from the production data dir ~/.config/hallptz/)

from __future__ import annotations

import logging
import os
from pathlib import Path

from domain.runtime_mode import RuntimeMode

logger = logging.getLogger(__name__)

_DEMO_DATA_DIR = Path.home() / ".config" / "hallptz-demo"
_PRODUCTION_DATA_DIR = Path.home() / ".config" / "hallptz"

# Legacy .txt files that live in the app directory
_PROTECTED_TXT_NAMES = frozenset({
    "PTZ1IP.txt", "PTZ2IP.txt",
    "Cam1ID.txt", "Cam2ID.txt",
    "ATEMIP.txt", "Contact.txt",
    "password.enc",
})

# JSON data files that live in the production data dir
_PROTECTED_JSON_NAMES = frozenset({
    "room_layout.json",
    "chairman_presets.json",
    "seat_names.json",
    "schedule.json",
})

# Config file name
_PROTECTED_CONFIG_NAMES = frozenset({"config.yaml"})

_ALL_PROTECTED_NAMES = _PROTECTED_TXT_NAMES | _PROTECTED_JSON_NAMES | _PROTECTED_CONFIG_NAMES


class DemoModeViolation(RuntimeError):
    """Raised when demo mode would touch a production config or data path."""


class DemoGuard:
    """
    Enforces demo mode isolation.

    Usage:
        guard = DemoGuard()
        guard.apply()          # sets HALLPTZ_DATA_DIR to demo dir, logs [DEMO]
        guard.assert_safe(p)   # raises DemoModeViolation if p is a protected path
    """

    def __init__(
        self,
        mode: RuntimeMode = RuntimeMode.DEMO,
        demo_data_dir: Path | None = None,
        production_data_dir: Path | None = None,
        app_dir: Path | None = None,
    ) -> None:
        self._mode = mode
        self._demo_dir = (demo_data_dir or _DEMO_DATA_DIR).resolve()
        self._prod_dir = (production_data_dir or _PRODUCTION_DATA_DIR).resolve()
        self._app_dir = (app_dir or Path.cwd()).resolve()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def active(self) -> bool:
        """True when guard is enforcing demo mode isolation."""
        return self._mode in (RuntimeMode.DEMO, RuntimeMode.SIMULATION)

    def apply(self) -> Path:
        """
        Set up the demo data directory and point HALLPTZ_DATA_DIR at it.

        Returns the demo data directory path.
        Idempotent — safe to call multiple times.
        """
        if not self.active:
            return self._prod_dir

        self._demo_dir.mkdir(parents=True, exist_ok=True)
        os.environ["HALLPTZ_DATA_DIR"] = str(self._demo_dir)
        os.environ["HALLPTZ_DATA_DIR"] = str(self._demo_dir)
        logger.info("[DEMO] Data directory isolated to: %s", self._demo_dir)
        logger.info("[DEMO] Production config at %s is protected", self._prod_dir)
        return self._demo_dir

    def assert_safe(self, path: Path) -> None:
        """
        Raise DemoModeViolation if *path* is a production-protected file.

        A path is protected when ALL of:
          - its name is in _ALL_PROTECTED_NAMES
          - it lives under the production data dir OR the app dir
          - it does NOT live under the demo dir
        """
        if not self.active:
            return
        resolved = path.resolve()
        if resolved.name not in _ALL_PROTECTED_NAMES:
            return
        # Allow writes to the demo dir itself
        try:
            resolved.relative_to(self._demo_dir)
            return  # path is inside demo dir — safe
        except ValueError:
            pass
        # Only block if the path is under a protected root (prod dir or app dir).
        # Protected filenames in unrelated directories are not blocked.
        for root in (self._prod_dir, self._app_dir):
            try:
                resolved.relative_to(root)
                raise DemoModeViolation(
                    f"[DEMO] Blocked write to production path: {path}. "
                    "Demo mode must not modify production config or data files."
                )
            except ValueError:
                pass

    def log(self, message: str) -> None:
        """Emit a [DEMO]-prefixed info log line."""
        logger.info("[DEMO] %s", message)

    @property
    def data_dir(self) -> Path:
        """Demo data directory (created by apply())."""
        return self._demo_dir

    @property
    def production_data_dir(self) -> Path:
        """Directorio de datos de producción protegido por este guard."""
        return self._prod_dir
