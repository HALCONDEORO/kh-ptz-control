#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
domain/migrations.py — Versioned runtime data migration framework (#155).

Usage
-----
Define a MigrationPlan for each data file format. Register step functions
from the current version to the next. Call migrate() before using the data;
it returns the migrated dict and a flag indicating whether migration occurred.

Example — seat_names.json migrating from v1 to v2:

    _NAMES_PLAN = MigrationPlan("seat_names")

    @_NAMES_PLAN.step(from_version=1, to_version=2)
    def _v1_to_v2(data: dict) -> dict:
        # rename "assignees" key to "seats"
        data.setdefault("seats", data.pop("assignees", {}))
        return data

    # In load_names_data():
    data, changed = migrate(_NAMES_PLAN, data, current_target_version=2)
    if changed:
        save_json(NAMES_FILE, data)

Rules
-----
- Always call migrate() on data loaded from disk, before using it.
- If migrate() returns changed=True, save the migrated data back with json_io
  (which creates a .bak automatically before overwriting).
- Step functions must be pure: return a new/modified dict, do not mutate in place
  unless returning self.
- A missing "schema_version" key is treated as version 0.
- Steps are applied sequentially; a step that raises leaves the original data intact.
- Gaps in version numbers are allowed; the framework skips non-existent steps.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

_MigrationStep = Callable[[dict], dict]


class MigrationPlan:
    """Registry of migration steps for a single data format."""

    def __init__(self, name: str):
        self._name = name
        self._steps: dict[tuple[int, int], _MigrationStep] = {}

    def step(self, *, from_version: int, to_version: int):
        """Decorator that registers a migration step."""
        if to_version != from_version + 1:
            raise ValueError(
                f"Migration step must increment version by 1: "
                f"got {from_version} → {to_version}"
            )

        def _decorator(fn: _MigrationStep) -> _MigrationStep:
            self._steps[(from_version, to_version)] = fn
            return fn

        return _decorator

    def migrate(self, data: dict, *, target_version: int) -> tuple[dict, bool]:
        """Apply all steps needed to reach *target_version*.

        Returns (migrated_data, changed) where changed is True if any
        step was applied. The original dict is not modified.

        If a step raises, the step is skipped and a warning is logged;
        the partially-migrated data from previous steps is returned.
        """
        current = data.get("schema_version", 0)
        if current >= target_version:
            return data, False

        result = dict(data)
        changed = False

        while current < target_version:
            step_fn = self._steps.get((current, current + 1))
            if step_fn is None:
                logger.debug(
                    "[migration:%s] no step for v%d → v%d — skipping",
                    self._name, current, current + 1,
                )
                current += 1
                continue
            try:
                result = step_fn(result)
                result["schema_version"] = current + 1
                logger.info(
                    "[migration:%s] v%d → v%d applied", self._name, current, current + 1
                )
                current += 1
                changed = True
            except Exception as exc:
                logger.warning(
                    "[migration:%s] v%d → v%d failed: %s — stopping migration at v%d",
                    self._name, current, current + 1, exc, current,
                )
                break

        return result, changed


def migrate(plan: MigrationPlan, data: Any, *, current_target_version: int) -> tuple[Any, bool]:
    """Convenience wrapper: if data is not a dict, return it unchanged.

    This means load_json callers can pass the raw loaded value without
    type-checking first.
    """
    if not isinstance(data, dict):
        return data, False
    return plan.migrate(data, target_version=current_target_version)
