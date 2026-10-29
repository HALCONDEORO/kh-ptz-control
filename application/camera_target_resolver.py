#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/camera_target_resolver.py — Resolves VISCA preset → camera target (Block D, #219)
#
# Maps a VISCA preset number to (ip, cam_id) via room layout and camera registry.
#
# Usage:
#   resolver = CameraTargetResolver(layout_service, camera_registry)
#   result   = resolver.resolve(preset_number)   # → CameraTarget | None
#
# Safe failure contract:
#   - Returns None when the preset is not in the layout or the role is unknown.
#   - Never raises into live operation.

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraTarget:
    """Resolved (ip, cam_id) for a VISCA command."""
    ip: str
    cam_id: str
    camera_role: str


class CameraTargetResolver:
    """
    Resolves a VISCA preset number to a concrete camera target.

    Lookup sequence:
    1. Find a SeatLayout whose ``preset`` field matches *preset_number*.
    2. Look up the seat's ``camera_role`` in the CameraRegistry.
    3. Return a CameraTarget with the matched camera's IP and VISCA ID.

    Returns None when:
    - The layout has not been loaded yet.
    - No seat has the given preset number.
    - The seat's camera_role is not registered.

    Parameters
    ----------
    layout_service:
        LayoutService instance used to look up seat definitions.
    camera_registry:
        CameraRegistry instance used to resolve camera_role → camera.
    """

    def __init__(self, layout_service, camera_registry) -> None:
        self._layout = layout_service
        self._registry = camera_registry

    def resolve(self, preset_number: int) -> Optional[CameraTarget]:
        """
        Return a CameraTarget for *preset_number*, or None if unresolvable.

        Never raises.
        """
        try:
            layout = self._layout.layout
            if layout is None:
                return None
            for seat in layout.seats:
                if seat.preset == preset_number:
                    return self._resolve_role(seat.camera_role)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.debug("CameraTargetResolver.resolve(%d) failed: %s", preset_number, exc)
            return None

    def resolve_role(self, camera_role: str) -> Optional[CameraTarget]:
        """
        Return a CameraTarget for a camera_role, or None if unresolvable.

        Never raises.
        """
        try:
            return self._resolve_role(camera_role)
        except Exception as exc:  # noqa: BLE001
            logger.debug("CameraTargetResolver.resolve_role(%r) failed: %s", camera_role, exc)
            return None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _resolve_role(self, camera_role: str) -> Optional[CameraTarget]:
        from config.registry import RegistryError
        try:
            cam = self._registry.by_role(camera_role)
            return CameraTarget(ip=cam.ip, cam_id=cam.visca_id, camera_role=camera_role)
        except RegistryError:
            logger.debug("CameraTargetResolver: no camera for role %r", camera_role)
            return None
