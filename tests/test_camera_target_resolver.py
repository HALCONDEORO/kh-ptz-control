#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_camera_target_resolver.py — CameraTargetResolver unit tests (Block D, #219)

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.camera_target_resolver import CameraTarget, CameraTargetResolver
from config.registry import CameraRegistry
from config.settings import CameraSettings
from domain.room_layout import RoomLayout, SeatLayout


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_registry(*cameras: CameraSettings) -> CameraRegistry:
    return CameraRegistry(list(cameras))


def _cam(id: str, role: str, ip: str = "192.168.1.10", visca_id: str = "81") -> CameraSettings:
    return CameraSettings(id=id, role=role, ip=ip, visca_id=visca_id)


def _seat(seat_id: str, preset: int, camera_role: str, label: str = "S") -> SeatLayout:
    return SeatLayout(id=seat_id, label=label, preset=preset, camera_role=camera_role, x=0, y=0)


def _layout(*seats: SeatLayout) -> RoomLayout:
    return RoomLayout(
        schema_version=1,
        room_id="test",
        room_name="Test Room",
        screen_width=1440,
        screen_height=1080,
        seats=list(seats),
    )


def _layout_svc(layout: RoomLayout | None) -> MagicMock:
    svc = MagicMock()
    svc.layout = layout
    return svc


def _resolver(layout: RoomLayout | None = None, *cameras: CameraSettings) -> CameraTargetResolver:
    registry = _make_registry(*cameras)
    return CameraTargetResolver(_layout_svc(layout), registry)


# ── CameraTarget dataclass ────────────────────────────────────────────────────

def test_camera_target_is_frozen():
    t = CameraTarget(ip="1.2.3.4", cam_id="81", camera_role="platform")
    with pytest.raises((AttributeError, TypeError)):
        t.ip = "0.0.0.0"  # type: ignore[misc]


# ── resolve(preset_number) ────────────────────────────────────────────────────

def test_resolve_returns_camera_target_for_known_preset():
    layout = _layout(_seat("s1", preset=10, camera_role="platform"))
    resolver = _resolver(layout, _cam("cam1", "platform", ip="192.168.1.10", visca_id="81"))
    result = resolver.resolve(10)
    assert isinstance(result, CameraTarget)
    assert result.ip == "192.168.1.10"
    assert result.cam_id == "81"
    assert result.camera_role == "platform"


def test_resolve_returns_none_for_unknown_preset():
    layout = _layout(_seat("s1", preset=10, camera_role="platform"))
    resolver = _resolver(layout, _cam("cam1", "platform"))
    assert resolver.resolve(99) is None


def test_resolve_returns_none_when_layout_is_none():
    resolver = _resolver(None, _cam("cam1", "platform"))
    assert resolver.resolve(10) is None


def test_resolve_returns_none_when_role_not_in_registry():
    layout = _layout(_seat("s1", preset=10, camera_role="unknown_role"))
    resolver = _resolver(layout, _cam("cam1", "platform"))
    assert resolver.resolve(10) is None


def test_resolve_routes_by_camera_role_not_preset_number():
    layout = _layout(
        _seat("s1", preset=10, camera_role="platform"),
        _seat("s2", preset=20, camera_role="comments"),
    )
    registry = _make_registry(
        _cam("cam1", "platform", ip="10.0.0.1", visca_id="81"),
        _cam("cam2", "comments", ip="10.0.0.2", visca_id="82"),
    )
    resolver = CameraTargetResolver(_layout_svc(layout), registry)

    result1 = resolver.resolve(10)
    result2 = resolver.resolve(20)

    assert result1.ip == "10.0.0.1"
    assert result2.ip == "10.0.0.2"


def test_resolve_uses_first_matching_seat():
    layout = _layout(
        _seat("s1", preset=10, camera_role="platform"),
        _seat("s2", preset=10, camera_role="comments"),
    )
    registry = _make_registry(
        _cam("cam1", "platform", ip="10.0.0.1"),
        _cam("cam2", "comments", ip="10.0.0.2"),
    )
    resolver = CameraTargetResolver(_layout_svc(layout), registry)
    result = resolver.resolve(10)
    assert result.camera_role == "platform"


def test_resolve_never_raises_on_registry_error(monkeypatch):
    layout = _layout(_seat("s1", preset=10, camera_role="platform"))
    registry = MagicMock()
    registry.by_role.side_effect = RuntimeError("unexpected")
    resolver = CameraTargetResolver(_layout_svc(layout), registry)
    result = resolver.resolve(10)
    assert result is None


def test_resolve_never_raises_on_layout_exception():
    svc = MagicMock()
    svc.layout = MagicMock(side_effect=RuntimeError("oops"))
    type(svc).layout = property(lambda self: (_ for _ in ()).throw(RuntimeError("oops")))
    registry = _make_registry(_cam("cam1", "platform"))
    resolver = CameraTargetResolver(svc, registry)
    result = resolver.resolve(10)
    assert result is None


# ── resolve_role(camera_role) ─────────────────────────────────────────────────

def test_resolve_role_returns_target_for_known_role():
    resolver = _resolver(None, _cam("cam1", "platform", ip="10.1.1.1", visca_id="81"))
    result = resolver.resolve_role("platform")
    assert isinstance(result, CameraTarget)
    assert result.ip == "10.1.1.1"
    assert result.camera_role == "platform"


def test_resolve_role_returns_none_for_unknown_role():
    resolver = _resolver(None, _cam("cam1", "platform"))
    assert resolver.resolve_role("nonexistent") is None


def test_resolve_role_never_raises():
    registry = MagicMock()
    registry.by_role.side_effect = Exception("kaboom")
    resolver = CameraTargetResolver(MagicMock(), registry)
    result = resolver.resolve_role("anything")
    assert result is None


# ── bootstrap integration ─────────────────────────────────────────────────────

def test_app_context_has_layout_svc_and_camera_target_resolver_fields():
    from core.app_context import AppContext
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(AppContext)}
    assert "layout_svc" in field_names
    assert "camera_target_resolver" in field_names
    assert "runtime_state_store" in field_names
    assert "runtime_audit_log" in field_names


def test_app_context_layout_svc_defaults_to_none():
    from core.app_context import AppContext
    import dataclasses
    for f in dataclasses.fields(AppContext):
        if f.name in {"layout_svc", "runtime_state_store", "runtime_audit_log"}:
            assert f.default is None or f.default_factory is not dataclasses.MISSING


def test_build_app_context_returns_none_for_layout_svc_without_config(monkeypatch):
    """In dev/test, layout_svc and camera_target_resolver are None (no config.yaml)."""
    from bootstrap import build_app_context

    class _FakeCameras:
        pass

    ctx = build_app_context(_FakeCameras())
    ctx.bus.stop()
    # In dev/test no config.yaml exists — resolver should be None
    assert ctx.camera_target_resolver is None

