#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
ui/icon_loader.py — Centralised icon loader for production UI (#185).

All production UI code should load icons through get_icon() rather than
hard-coding paths. If a PNG is missing at development time, FileNotFoundError
is raised immediately so missing assets are caught early. In production the
app continues without the icon (text labels remain visible for all actions).

SVG files in assets/icons/svg/ are the editable source of truth.
PNG files in assets/icons/png/ are pre-generated for runtime use.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets" / "icons"
_PNG_DIR = _ASSET_ROOT / "png"
_SVG_DIR = _ASSET_ROOT / "svg"

# Registry of icon names used by the application.
ICON_SETTINGS = "settings"
ICON_CAMERA    = "camera"
ICON_SAVE      = "save"
ICON_DELETE    = "delete"
ICON_WARNING   = "warning"
ICON_REFRESH   = "refresh"
ICON_LOCK      = "lock"
ICON_DATA      = "data"

# Sizes expected to be present in assets/icons/png/
REQUIRED_SIZES = (24, 32, 48)

_STRICT = os.getenv("KHPTZ_STRICT_ICONS", "0") == "1"


def get_icon(name: str, size: int = 32):
    """Return a QIcon for the given icon name and pixel size.

    Raises FileNotFoundError in strict mode (KHPTZ_STRICT_ICONS=1) or
    during testing when the PNG is missing. In production, logs a warning
    and returns an empty QIcon so the text label remains usable.
    """
    from PyQt5.QtGui import QIcon
    path = _PNG_DIR / f"{name}_{size}.png"
    if path.exists():
        return QIcon(str(path))
    if _STRICT:
        raise FileNotFoundError(f"Missing UI icon: {path}")
    logger.warning("UI icon not found: %s — text label will be used", path)
    return QIcon()


def svg_path(name: str) -> Path:
    """Return the Path to the SVG source for the given icon name."""
    return _SVG_DIR / f"{name}.svg"


def required_png_paths() -> list[Path]:
    """Return the full list of PNG paths that should exist for all P1 icons."""
    p1_icons = [
        ICON_SETTINGS, ICON_CAMERA, ICON_SAVE, ICON_DELETE,
        ICON_WARNING, ICON_REFRESH, ICON_LOCK, ICON_DATA,
    ]
    return [_PNG_DIR / f"{icon}_{size}.png" for icon in p1_icons for size in REQUIRED_SIZES]
