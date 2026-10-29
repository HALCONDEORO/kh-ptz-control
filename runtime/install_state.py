#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# runtime/install_state.py — single Python reader for /etc/khptz/install-state.env
#
# Python mirror of scripts/lib/install_state.sh. Both exist because the install
# path crosses languages: the installer and the wizard's integration step are
# shell, while the provisioning entry point and the CLI are Python — and every
# one of them has to agree on which process owns the GUI (#885).
#
# Getting that wrong is not cosmetic. A component that assumes the system
# service will enable (or worse, start) khptz-control on a session-owned install,
# and the appliance ends up running two full-screen GUIs driving the same
# cameras. Keep this file and the shell library behaving identically; their
# shared fallback rule is asserted by tests/test_gui_mode_consistency.py.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: Written by runtime/installer/install.sh.
STATE_FILENAME = "install-state.env"

#: The launcher that owns the GUI.
GUI_MODE_SYSTEM = "system"
GUI_MODE_USER = "user"

_VALID_GUI_MODES = frozenset({GUI_MODE_SYSTEM, GUI_MODE_USER})


def _state_path(resolver=None) -> Optional[Path]:
    try:
        if resolver is None:
            from runtime.path_resolver import RuntimePathResolver

            resolver = RuntimePathResolver()
        return Path(resolver.config_dir) / STATE_FILENAME
    except Exception as exc:  # noqa: BLE001 — never fail a caller over this
        logger.debug("Could not resolve the install-state path: %s", exc)
        return None


def state_value(key: str, resolver=None) -> str:
    """Return the recorded value for *key*, or an empty string.

    Never raises: a missing or unreadable state file simply yields "". The file
    is parsed as plain ``KEY=value`` lines rather than sourced, so a malformed
    entry cannot execute anything.
    """
    path = _state_path(resolver)
    if path is None:
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.debug("Could not read %s: %s", path, exc)
        return ""

    value = ""
    for line in text.splitlines():
        name, sep, raw = line.partition("=")
        if sep and name.strip() == key:
            # Last occurrence wins, matching the shell reader.
            value = raw.strip().strip('"').strip("'")
    return value


def gui_mode(resolver=None) -> str:
    """Return ``"user"`` or ``"system"`` — never anything else.

    Falls back to ``"system"`` when the key is missing, unreadable or holds an
    unrecognised value. That is the safe default in both directions: installs
    predating the flag were all system mode, and treating an unknown value as
    ``"user"`` would disable the only launcher such a machine has.
    """
    value = state_value("KHPTZ_GUI_MODE", resolver)
    return value if value in _VALID_GUI_MODES else GUI_MODE_SYSTEM


def gui_is_session_owned(resolver=None) -> bool:
    """True when the desktop session owns the GUI (``--gui-mode user``)."""
    return gui_mode(resolver) == GUI_MODE_USER
