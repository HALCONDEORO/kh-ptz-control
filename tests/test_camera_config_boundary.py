# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Boundary guard: UI widgets must not write camera/ATEM config directly (#893, ADR-006).

All camera/ATEM configuration writes flow through CameraConfigService. This test
walks every ui/*.py with `ast` and fails if any of them assigns to the mutable
config singletons — i.e. `config.CAM1.ip = ...`, `CAM2.cam_id = ...`,
`_cfg.ATEM.ip = ...`. It catches the exact regression the service was built to
prevent: two widgets drifting out of step on shared global state.

The service module itself is the one legitimate writer and lives in application/,
so it is not in scope here (this test only looks under ui/).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parents[1] / "ui"

# The mutable config singletons that must only be written by CameraConfigService.
FORBIDDEN_CONFIG_NAMES = {"CAM1", "CAM2", "ATEM"}
# Common aliases the UI used for `import config as _cfg` / `import config`.
CONFIG_MODULE_ALIASES = {"config", "_cfg", "_config"}


def _ui_files() -> list[Path]:
    return sorted(p for p in UI_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def _attr_root_name(node: ast.expr) -> str | None:
    """Return the leftmost Name of an attribute chain, or None."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _is_forbidden_target(target: ast.expr) -> bool:
    """True if *target* assigns an attribute of a config singleton.

    Matches both `CAM1.ip = ...` (singleton imported by name) and
    `config.CAM1.ip = ...` / `_cfg.ATEM.ip = ...` (via the module).
    """
    if not isinstance(target, ast.Attribute):
        return False
    obj = target.value  # the thing whose attribute is being set
    # Case 1: <SINGLETON>.attr = ...
    if isinstance(obj, ast.Name) and obj.id in FORBIDDEN_CONFIG_NAMES:
        return True
    # Case 2: <config-module>.<SINGLETON>.attr = ...
    if (
        isinstance(obj, ast.Attribute)
        and obj.attr in FORBIDDEN_CONFIG_NAMES
        and _attr_root_name(obj) in CONFIG_MODULE_ALIASES
    ):
        return True
    return False


@pytest.mark.parametrize("path", _ui_files(), ids=lambda p: p.name)
def test_ui_file_does_not_write_config_singletons(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        for target in targets:
            if _is_forbidden_target(target):
                offenders.append(f"{path.name}:{target.lineno}")

    assert not offenders, (
        "UI widgets must not write camera/ATEM config directly — route through "
        "MainWindow._camera_config (CameraConfigService) instead (#893, ADR-006). "
        f"Offending assignments: {offenders}"
    )
