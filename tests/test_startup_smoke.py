#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Hardware-free startup smoke tests.

Verifies that the non-UI startup path (bootstrap → AppContext → teardown)
completes without errors in CI and on developer machines, without requiring:
  - Real PTZ cameras
  - Real ATEM hardware
  - Raspberry Pi hardware
  - A visible display (Qt runs in offscreen mode via conftest / QT_QPA_PLATFORM)

Limitation: full MainWindow startup is not covered here because it requires
the complete Qt event loop. That path is partially covered in test_main_startup.py
via module-level mocking. A full UI smoke test is tracked separately in #236.
"""

from __future__ import annotations

import threading


from bootstrap import build_app_context
from core.app_context import AppContext
from core.state import SystemState
from config.registry import CameraRegistry
from config.loader import load_config
from pathlib import Path


DEFAULTS_DIR = Path(__file__).parent.parent / "config" / "defaults"


class _FakeCamera:
    """Minimal stub — no sockets, no threads."""
    pass


# ── AppContext lifecycle ──────────────────────────────────────────────────────

class TestBootstrapLifecycle:

    def test_context_creates_without_hardware(self):
        ctx = build_app_context(_FakeCamera())
        ctx.bus.stop()

    def test_context_is_app_context(self):
        ctx = build_app_context(_FakeCamera())
        assert isinstance(ctx, AppContext)
        ctx.bus.stop()

    def test_state_initialises_clean(self):
        ctx = build_app_context(_FakeCamera())
        assert isinstance(ctx.state, SystemState)
        assert ctx.state.session.active is False
        ctx.bus.stop()

    def test_bus_starts_and_stops_cleanly(self):
        ctx = build_app_context(_FakeCamera())
        assert ctx.bus._worker is not None
        assert ctx.bus._worker.is_alive()
        ctx.bus.stop()
        assert ctx.bus._worker is None

    def test_bus_worker_is_daemon(self):
        ctx = build_app_context(_FakeCamera())
        assert ctx.bus._worker.daemon is True
        ctx.bus.stop()

    def test_no_open_threads_after_stop(self):
        before = threading.active_count()
        ctx = build_app_context(_FakeCamera())
        ctx.bus.stop()
        after = threading.active_count()
        assert after <= before + 1  # hook thread or similar may linger briefly


# ── Config / registry smoke ───────────────────────────────────────────────────

class TestConfigSmoke:

    def test_starter_template_loads(self):
        settings = load_config(DEFAULTS_DIR / "starter.yaml")
        assert len(settings.cameras) >= 1

    def test_standard_template_loads(self):
        settings = load_config(DEFAULTS_DIR / "standard.yaml")
        assert len(settings.cameras) == 2

    def test_registry_builds_from_standard(self):
        settings = load_config(DEFAULTS_DIR / "standard.yaml")
        reg = CameraRegistry.from_settings(settings)
        assert "platform" in reg
        assert "comments" in reg

    def test_registry_role_lookup_smoke(self):
        settings = load_config(DEFAULTS_DIR / "standard.yaml")
        reg = CameraRegistry.from_settings(settings)
        platform = reg.by_role("platform")
        assert platform.ip != ""
        assert platform.visca_id != ""
