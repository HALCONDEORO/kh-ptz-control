#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/display_prefs.py — Operator display preferences (runtime data dir)
#
# Small persisted preferences that the operator toggles at runtime and that must
# survive a restart in EVERY profile (production, demo, simulation).  They live
# in the runtime data dir (/var/lib/khptz/display_prefs.json), NOT in config.yaml:
# config.yaml is installer/site config and is absent in demo/simulation runs.
#
# STRUCTURE:
#   { "second_platform": true }
#
# All writes are atomic (core.json_io).  Missing/corrupt file → safe defaults.

from __future__ import annotations

import logging
from pathlib import Path

from core.json_io import load_json, save_json
from runtime.path_resolver import RuntimePathResolver

logger = logging.getLogger(__name__)

_FILENAME = "display_prefs.json"
_KEY_SECOND_PLATFORM = "second_platform"


def _path() -> Path:
    # Resolved lazily so test/demo data-dir overrides are honoured.
    return RuntimePathResolver().data_dir / _FILENAME


def _load() -> dict:
    data = load_json(_path(), default={})
    return data if isinstance(data, dict) else {}


def is_second_platform_enabled() -> bool:
    """Return True if the optional Platform 2 button is enabled. Defaults to False."""
    return bool(_load().get(_KEY_SECOND_PLATFORM, False))


def set_second_platform_enabled(enabled: bool) -> bool:
    """Persist the Platform 2 toggle. Returns True on success."""
    data = _load()
    data[_KEY_SECOND_PLATFORM] = bool(enabled)
    ok = save_json(_path(), data)
    if not ok:
        logger.error("display_prefs: failed to save %s", _path())
    return ok
