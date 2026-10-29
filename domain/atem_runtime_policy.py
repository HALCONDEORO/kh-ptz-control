#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/atem_runtime_policy.py — ATEM backend selection rule (no Qt, no I/O)
#
# Answers: should the runtime use FakeATEM (demo/sim) or ATEMMonitor (production)?
#
# Extracted from MainWindow._start_atem_monitor so the decision can be unit-tested
# without importing PyQt5 or any UI module.

from __future__ import annotations

import os


def is_fake_atem_mode(profile: str | None = None, sim_active: bool = False) -> bool:
    """Return True when the runtime should use FakeATEM instead of ATEMMonitor.

    Parameters
    ----------
    profile:
        HALLPTZ_PROFILE value.  When None, reads from the environment.
    sim_active:
        Whether simulation mode is currently active (sim_ip_backup.json present).
        Callers should pass ``adapters.sim_mode.is_active()``; default False.

    Rules (in priority order)
    -------------------------
    1. Profile is "demo" or "simulation"  → FakeATEM.
    2. sim_mode is active                  → FakeATEM (overrides production profile).
    3. Otherwise                           → ATEMMonitor (real hardware).
    """
    p = profile if profile is not None else os.environ.get("HALLPTZ_PROFILE", "production")
    return p in ("demo", "simulation") or sim_active
