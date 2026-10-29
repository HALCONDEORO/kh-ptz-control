#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Smoke tests for AppContext and bootstrap.build_app_context().

Hardware-free: CameraManager is replaced with a minimal stub so
the test never opens a socket or touches production config files.
"""

from __future__ import annotations

import pytest

from core.app_context import AppContext
from bootstrap import build_app_context
from core.state import SystemState
from core.events import AsyncEventBus
from application.preset_service import PresetService
from application.session_service import SessionService
from application.runtime_audit_log import RuntimeAuditLog
from application.runtime_state_store import RuntimeStateStore
from core.controller import Controller
from ports.camera_port import CameraPort


class _FakeCameras:
    """Minimal CameraManager stub — no sockets, no threads."""
    pass


@pytest.fixture()
def ctx():
    cameras = _FakeCameras()
    context = build_app_context(cameras)
    yield context
    context.bus.stop()


class TestBuildAppContext:

    def test_returns_app_context_instance(self, ctx):
        assert isinstance(ctx, AppContext)

    def test_state_is_system_state(self, ctx):
        assert isinstance(ctx.state, SystemState)

    def test_bus_is_async_event_bus(self, ctx):
        assert isinstance(ctx.bus, AsyncEventBus)

    def test_preset_svc_is_preset_service(self, ctx):
        assert isinstance(ctx.preset_svc, PresetService)

    def test_session_svc_is_session_service(self, ctx):
        assert isinstance(ctx.session_svc, SessionService)

    def test_controller_is_controller(self, ctx):
        assert isinstance(ctx.controller, Controller)

    def test_bus_worker_is_alive(self, ctx):
        assert ctx.bus._worker is not None and ctx.bus._worker.is_alive()

    def test_camera_port_uses_provided_cameras(self, ctx):
        assert isinstance(ctx.camera_port._mgr, _FakeCameras)

    def test_session_svc_uses_camera_port(self, ctx):
        assert isinstance(ctx.session_svc._port, CameraPort)

    def test_controller_uses_shared_state(self, ctx):
        assert ctx.controller._state is ctx.state

    def test_controller_uses_shared_bus(self, ctx):
        assert ctx.controller._bus is ctx.bus

    def test_flight_recorder_attribute_exists(self, ctx):
        assert hasattr(ctx, "flight_recorder")

    def test_flight_recorder_is_none_in_dev(self):
        # When running_from_source is True, _create_flight_recorder() must return None.
        from unittest.mock import patch

        fake_resolver = type("R", (), {"running_from_source": True})()
        with patch(
            "runtime.path_resolver.RuntimePathResolver",
            return_value=fake_resolver,
        ):
            ctx = build_app_context(_FakeCameras())
            ctx.bus.stop()
        assert ctx.flight_recorder is None

    def test_runtime_state_store_is_wired(self, ctx):
        assert isinstance(ctx.runtime_state_store, RuntimeStateStore)

    def test_runtime_audit_log_is_wired(self, ctx):
        assert isinstance(ctx.runtime_audit_log, RuntimeAuditLog)

    def test_session_svc_uses_shared_runtime_state_store(self, ctx):
        assert ctx.session_svc._store is ctx.runtime_state_store

    def test_runtime_audit_log_subscribed_to_runtime_state_store(self, ctx):
        ctx.runtime_state_store.update_session(active=True, session_id="s-test")
        events = [entry.event for entry in ctx.runtime_audit_log.entries()]
        assert "session_started" in events

    def test_runtime_state_store_defaults_to_two_legacy_cameras(self, ctx):
        assert set(ctx.runtime_state_store.snapshot().cameras) == {"cam1", "cam2"}

    def test_runtime_state_store_uses_loaded_camera_config_ids(self, monkeypatch):
        import bootstrap

        monkeypatch.setattr(
            bootstrap,
            "_load_cam_configs",
            lambda: {
                1: ("192.0.2.10", "81"),
                3: ("192.0.2.30", "83"),
            },
        )

        ctx = build_app_context(_FakeCameras())
        try:
            assert set(ctx.runtime_state_store.snapshot().cameras) == {"cam1", "cam3"}
        finally:
            ctx.bus.stop()

    def test_explicit_flight_recorder_is_passed_through(self):
        from unittest.mock import MagicMock
        rec = MagicMock()
        ctx = build_app_context(_FakeCameras(), flight_recorder=rec)
        ctx.bus.stop()
        assert ctx.flight_recorder is rec
        assert ctx.session_svc._recorder is rec
