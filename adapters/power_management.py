#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess

logger = logging.getLogger(__name__)


def _run_quiet(command: list[str]) -> bool:
    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("Could not run %s: %s", command[0], exc)
        return False


def disable_screen_blanking() -> None:
    """Desactivar el apagado automatico de pantalla en Linux/Raspberry Pi."""
    if platform.system() != "Linux":
        return

    if os.getenv("UPDATE2026_DISABLE_SCREEN_BLANKING", "1").lower() in {"0", "false", "no"}:
        return

    xset = shutil.which("xset")
    if xset and os.getenv("DISPLAY"):
        # En X11, DPMS y el screensaver son los que suelen apagar la tactil.
        for args in (["s", "off"], ["-dpms"], ["s", "noblank"]):
            _run_quiet([xset, *args])
        logger.info("Screen blanking disabled with xset")
        return

    setterm = shutil.which("setterm")
    if setterm:
        # En consola sin X11, setterm evita blanking y powerdown del terminal.
        if _run_quiet([setterm, "-blank", "0", "-powerdown", "0"]):
            logger.info("Console screen blanking disabled with setterm")
