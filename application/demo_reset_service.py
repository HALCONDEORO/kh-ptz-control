#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/demo_reset_service.py — Safe demo data reset
#
# Restores only the demo data directory to a known clean state by copying
# the bundled demo templates from config/demo/.
#
# Safety guarantees:
#   - Only writes inside the demo data path (KHPTZ_DATA_DIR when in demo mode).
#   - Never touches production paths (~/.config/khptz/).
#   - Never deletes password, config.yaml, or PTZ/ATEM config files.
#   - Validates the target path before writing anything.

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_DEMO_TEMPLATES_DIR = Path(__file__).parent.parent / "config" / "demo"

_DEMO_FILES = (
    "room_layout.json",
    "seat_names.json",
    "chairman_presets.json",
)


@dataclass
class DemoResetResult:
    reset_path: Path
    restored: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def summary(self) -> str:
        lines = [f"Demo reset in: {self.reset_path}"]
        if self.restored:
            lines.append(f"  Restored ({len(self.restored)}): {', '.join(self.restored)}")
        if self.skipped:
            lines.append(f"  Skipped  ({len(self.skipped)}): {', '.join(self.skipped)}")
        if self.error:
            lines.append(f"  Error: {self.error}")
        return "\n".join(lines)

    @property
    def success(self) -> bool:
        return self.error is None


class DemoResetError(RuntimeError):
    pass


_PRODUCTION_PATH = Path.home() / ".config" / "khptz"


def _production_paths() -> list[Path]:
    """Return all recognized production data directories (legacy + env overrides)."""
    paths = [_PRODUCTION_PATH]
    for var in ("KHPTZ_DATA_DIR", "KHPTZ_DATA_DIR"):
        val = os.environ.get(var, "").strip()
        if val:
            p = Path(val)
            if p.is_absolute():
                paths.append(p)
    return paths


class DemoResetService:
    """
    Restores demo data files to a known clean state.

    Parameters
    ----------
    demo_data_dir:
        Path to reset. Must not be the production directory.
        Defaults to the current KHPTZ_DATA_DIR env var value.
    templates_dir:
        Source of clean demo templates. Defaults to config/demo/ in the app.
    """

    def __init__(
        self,
        demo_data_dir: Optional[Path] = None,
        templates_dir: Optional[Path] = None,
        production_data_dirs: Optional[list[Path]] = None,
    ) -> None:
        if demo_data_dir is None:
            from runtime.path_resolver import RuntimePathResolver
            demo_data_dir = RuntimePathResolver().data_dir
        self._demo_dir = Path(demo_data_dir)
        self._templates_dir = Path(templates_dir or _DEMO_TEMPLATES_DIR)
        self._production_data_dirs = production_data_dirs

    def reset(self) -> DemoResetResult:
        """
        Copy demo templates to the demo data directory.

        Raises DemoResetError if the target path looks like the production directory.
        """
        result = DemoResetResult(reset_path=self._demo_dir)
        try:
            self._assert_safe_path(self._demo_dir, self._production_data_dirs)
        except DemoResetError as exc:
            result.error = str(exc)
            return result

        self._demo_dir.mkdir(parents=True, exist_ok=True)

        for filename in _DEMO_FILES:
            src = self._templates_dir / filename
            dst = self._demo_dir / filename
            if not src.exists():
                result.skipped.append(filename)
                logger.warning("Demo template not found: %s", src)
                continue
            try:
                content = src.read_text(encoding="utf-8")
                # Validate JSON before writing
                json.loads(content)
                tmp = dst.with_suffix(".tmp")
                tmp.write_text(content, encoding="utf-8")
                os.replace(tmp, dst)
                result.restored.append(filename)
                logger.info("Demo reset: %s → %s", filename, dst)
            except (OSError, json.JSONDecodeError) as exc:
                result.skipped.append(filename)
                logger.warning("Could not restore %s: %s", filename, exc)

        return result

    @staticmethod
    def _assert_safe_path(path: Path, production_data_dirs: Optional[list[Path]] = None) -> None:
        """Raise DemoResetError if path equals or is inside any production data directory."""
        try:
            resolved = path.resolve()
        except OSError:
            return
        production_paths = production_data_dirs if production_data_dirs is not None else _production_paths()
        for prod in production_paths:
            try:
                production = prod.resolve()
            except OSError:
                continue
            if resolved == production:
                raise DemoResetError(
                    "Demo reset refused: target path is the production directory. "
                    "Set KHPTZ_DATA_DIR to a demo-specific path before resetting."
                )
            try:
                resolved.relative_to(production)
                raise DemoResetError(
                    f"Demo reset refused: {path} is inside the production directory {production}."
                )
            except ValueError:
                pass  # not relative — safe
