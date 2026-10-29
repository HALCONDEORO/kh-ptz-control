# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from __future__ import annotations

from pathlib import Path


APP_NAME = "Hall PTZ Control"
VERSION_FILE = Path(__file__).resolve().parent / "VERSION"


def read_version(version_file: Path | None = None) -> str:
    path = version_file or VERSION_FILE
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return value or "unknown"


def app_version_label(version_file: Path | None = None) -> str:
    return f"{APP_NAME} {read_version(version_file)}"
