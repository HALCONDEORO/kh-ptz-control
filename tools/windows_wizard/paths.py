# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from __future__ import annotations

import os
from pathlib import Path


def default_state_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Hall PTZ Control" / "Windows Wizard"
    return Path.home() / ".hallptz" / "windows_wizard"


def ensure_state_dirs(base_dir: Path | None = None) -> Path:
    state_dir = base_dir or default_state_dir()
    (state_dir / "logs").mkdir(parents=True, exist_ok=True)
    (state_dir / "settings").mkdir(parents=True, exist_ok=True)
    return state_dir

