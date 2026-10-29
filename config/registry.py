#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# config/registry.py — Registro de cámaras por ID y rol
#
# CameraRegistry reemplaza los lookups hardcodeados CAM1/CAM2.
# Construirlo desde AppSettings; CAM1/CAM2 siguen activos en el legacy path.
# Sin Qt. Sin I/O de red.

from __future__ import annotations

from typing import List

from config.settings import CameraSettings


class RegistryError(KeyError):
    """Raised when a camera lookup fails."""


class CameraRegistry:
    """
    Resolves cameras by stable id or role from an AppSettings cameras list.

    Rules
    -----
    - Duplicate IDs are rejected at construction time.
    - Role lookups raise RegistryError if zero or more than one camera
      matches the requested role (ambiguity is not silently handled).
    """

    def __init__(self, cameras: List[CameraSettings]) -> None:
        self._by_id: dict[str, CameraSettings] = {}
        for cam in cameras:
            if cam.id in self._by_id:
                raise RegistryError(f"Duplicate camera id: '{cam.id}'")
            self._by_id[cam.id] = cam

    # ── Public API ────────────────────────────────────────────────────────

    def get(self, camera_id: str) -> CameraSettings:
        """Return the camera with the given id. Raises RegistryError if not found."""
        try:
            return self._by_id[camera_id]
        except KeyError:
            raise RegistryError(f"No camera with id '{camera_id}'") from None

    def by_role(self, role: str) -> CameraSettings:
        """
        Return the single camera assigned to *role*.

        Raises RegistryError if no camera matches or more than one matches.
        """
        matches = [c for c in self._by_id.values() if c.role == role]
        if not matches:
            raise RegistryError(f"No camera with role '{role}'")
        if len(matches) > 1:
            ids = ", ".join(c.id for c in matches)
            raise RegistryError(
                f"Ambiguous role '{role}': matched {ids}"
            )
        return matches[0]

    def list_enabled(self) -> List[CameraSettings]:
        """Return all registered cameras in insertion order."""
        return list(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, camera_id: str) -> bool:
        return camera_id in self._by_id

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def from_settings(cls, settings) -> "CameraRegistry":
        """Build a registry from an AppSettings instance."""
        return cls(settings.cameras)
