#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tests for config/registry.py — CameraRegistry lookup by id and role.

Hardware-free: no sockets, no Qt, no production files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from config.loader import load_config
from config.registry import CameraRegistry, RegistryError
from config.settings import CameraSettings

DEFAULTS_DIR = Path(__file__).parent.parent / "config" / "defaults"

# ── Fixtures ──────────────────────────────────────────────────────────────────

PLATFORM = CameraSettings(id="platform", role="platform", ip="172.16.1.11", visca_id="81")
COMMENTS = CameraSettings(id="comments", role="comments", ip="172.16.1.12", visca_id="82")


@pytest.fixture()
def two_camera_registry():
    return CameraRegistry([PLATFORM, COMMENTS])


@pytest.fixture()
def one_camera_registry():
    return CameraRegistry([PLATFORM])


# ── Construction ──────────────────────────────────────────────────────────────

class TestConstruction:

    def test_builds_from_list(self):
        reg = CameraRegistry([PLATFORM])
        assert len(reg) == 1

    def test_duplicate_id_raises(self):
        dup = CameraSettings(id="platform", role="comments", ip="1.2.3.4", visca_id="82")
        with pytest.raises(RegistryError, match="Duplicate"):
            CameraRegistry([PLATFORM, dup])

    def test_empty_registry_allowed(self):
        reg = CameraRegistry([])
        assert len(reg) == 0

    def test_from_settings_factory(self):
        settings = load_config(DEFAULTS_DIR / "standard.yaml")
        reg = CameraRegistry.from_settings(settings)
        assert len(reg) == 2


# ── ID lookup ─────────────────────────────────────────────────────────────────

class TestGetById:

    def test_get_existing_id(self, two_camera_registry):
        cam = two_camera_registry.get("platform")
        assert cam.id == "platform"
        assert cam.ip == "172.16.1.11"

    def test_get_second_camera(self, two_camera_registry):
        cam = two_camera_registry.get("comments")
        assert cam.id == "comments"

    def test_get_missing_id_raises(self, two_camera_registry):
        with pytest.raises(RegistryError, match="platform-x"):
            two_camera_registry.get("platform-x")

    def test_contains_existing(self, two_camera_registry):
        assert "platform" in two_camera_registry

    def test_not_contains_missing(self, two_camera_registry):
        assert "other" not in two_camera_registry


# ── Role lookup ───────────────────────────────────────────────────────────────

class TestByRole:

    def test_by_role_platform(self, two_camera_registry):
        cam = two_camera_registry.by_role("platform")
        assert cam.role == "platform"
        assert cam.id == "platform"

    def test_by_role_comments(self, two_camera_registry):
        cam = two_camera_registry.by_role("comments")
        assert cam.role == "comments"

    def test_missing_role_raises(self, two_camera_registry):
        with pytest.raises(RegistryError, match="operator"):
            two_camera_registry.by_role("operator")

    def test_ambiguous_role_raises(self):
        cam2 = CameraSettings(id="platform2", role="platform", ip="1.2.3.4", visca_id="83")
        reg = CameraRegistry([PLATFORM, cam2])
        with pytest.raises(RegistryError, match="Ambiguous"):
            reg.by_role("platform")


# ── list_enabled ──────────────────────────────────────────────────────────────

class TestListEnabled:

    def test_returns_all_cameras(self, two_camera_registry):
        cameras = two_camera_registry.list_enabled()
        assert len(cameras) == 2

    def test_preserves_insertion_order(self, two_camera_registry):
        cameras = two_camera_registry.list_enabled()
        assert cameras[0].id == "platform"
        assert cameras[1].id == "comments"

    def test_returns_copy(self, two_camera_registry):
        cameras = two_camera_registry.list_enabled()
        cameras.clear()
        assert len(two_camera_registry) == 2


# ── Integration with default templates ───────────────────────────────────────

class TestWithDefaultTemplates:

    def test_starter_registry_has_platform(self):
        settings = load_config(DEFAULTS_DIR / "starter.yaml")
        reg = CameraRegistry.from_settings(settings)
        cam = reg.by_role("platform")
        assert cam.id == "platform"

    def test_standard_registry_resolves_both_roles(self):
        settings = load_config(DEFAULTS_DIR / "standard.yaml")
        reg = CameraRegistry.from_settings(settings)
        assert reg.by_role("platform").id == "platform"
        assert reg.by_role("comments").id == "comments"
