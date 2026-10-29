#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/camera_config_service.py — single owner of camera/ATEM config writes
#
# Responsibilities (ADR-006: customer data writes go through a service, never widgets):
#   - Validate a proposed camera IP / VISCA id / ATEM IP.
#   - Update the in-memory config singletons (config.CAM1/CAM2/ATEM).
#   - Repoint the live camera runtime (CameraManager + CameraPort) so PTZ/preset
#     commands reach the new address without an app restart.
#   - Persist the change to config.yaml (best-effort; a persist failure never
#     loses the in-memory/runtime update — it is reported as a partial success).
#
# Before this service the four steps above were duplicated inline in three UI
# widgets, each assigning config.CAMn.* directly. Two of those sites could drift
# out of step (the #886 "profile vs camera count" / "ATEM without IP" class of
# bug). Widgets now call this service instead; a boundary test forbids direct
# config.CAM* mutation from ui/.
#
# No Qt, no sockets. Collaborators are injected as providers so the service does
# not depend on when MainWindow wires them up.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional, Protocol

import config as _config
from config import is_valid_cam_id, is_valid_ip
from config.writer import patch_config_yaml
from domain.supportability import OperationCode, OperationResult

logger = logging.getLogger(__name__)


class _CameraRuntime(Protocol):
    """Minimal shape the service needs from CameraManager / CameraPort."""

    def update_camera_ip(self, camera_index: int, new_ip: str) -> object: ...


# Providers may legitimately return None (runtime not built yet, or absent in a
# headless/test context), so every collaborator lookup is optional.
_PathProvider = Callable[[], Optional[Path]]
_RuntimeProvider = Callable[[], Optional[_CameraRuntime]]


def _noop_path() -> Optional[Path]:
    return None


def _noop_runtime() -> Optional[_CameraRuntime]:
    return None


class CameraConfigService:
    """Validate, apply and persist camera/ATEM configuration changes."""

    def __init__(
        self,
        *,
        config_path_provider: _PathProvider = _noop_path,
        camera_manager_provider: _RuntimeProvider = _noop_runtime,
        camera_port_provider: _RuntimeProvider = _noop_runtime,
        config_module=_config,
    ) -> None:
        self._config_path = config_path_provider
        self._camera_manager = camera_manager_provider
        self._camera_port = camera_port_provider
        self._config = config_module

    # ── Public API ────────────────────────────────────────────────────────────

    def set_camera_ip(self, cam_num: int, ip: str) -> OperationResult:
        """Set camera *cam_num* (1 or 2) to *ip*, live and persisted."""
        target = f"cam{cam_num}"
        if cam_num not in (1, 2):
            return self._invalid(
                "set_camera_ip", target, f"Unknown camera number: {cam_num!r}"
            )
        clean = (ip or "").strip()
        if not is_valid_ip(clean):
            return self._invalid(
                "set_camera_ip", target,
                "Enter a valid IPv4 address (e.g. 172.16.1.11).",
            )

        self._camera(cam_num).ip = clean
        self._repoint_runtime(cam_num, clean)
        return self._persist(
            "set_camera_ip", target, cam_index=cam_num - 1, cam_ip=clean
        )

    def set_camera_visca_id(self, cam_num: int, visca_id: str) -> OperationResult:
        """Set camera *cam_num* VISCA id (hex byte), persisted."""
        target = f"cam{cam_num}"
        if cam_num not in (1, 2):
            return self._invalid(
                "set_camera_visca_id", target, f"Unknown camera number: {cam_num!r}"
            )
        clean = (visca_id or "").strip()
        if not is_valid_cam_id(clean):
            return self._invalid(
                "set_camera_visca_id", target,
                'Enter a hex VISCA id such as "81" or "82".',
            )

        self._camera(cam_num).cam_id = clean
        return self._persist(
            "set_camera_visca_id", target, cam_index=cam_num - 1, cam_visca_id=clean
        )

    def set_atem_ip(self, ip: str) -> OperationResult:
        """Set the ATEM switcher IP, live and persisted."""
        clean = (ip or "").strip()
        if not is_valid_ip(clean):
            return self._invalid(
                "set_atem_ip", "atem",
                "Enter a valid IPv4 address for the ATEM switcher.",
            )

        self._config.ATEM.ip = clean
        return self._persist("set_atem_ip", "atem", atem_ip=clean)

    def apply_simulation_ips(self, cam1_ip: str, cam2_ip: str) -> None:
        """Patch the in-memory camera IPs for simulation startup only.

        Simulation seeds loopback IPs before any worker is built; this is an
        in-memory-only concern (no validation gate, no config.yaml write) and
        deliberately separate from the customer-config write path above.
        """
        self._config.CAM1.ip = cam1_ip
        self._config.CAM2.ip = cam2_ip

    # ── Internals ─────────────────────────────────────────────────────────────

    def _camera(self, cam_num: int):
        return self._config.CAM1 if cam_num == 1 else self._config.CAM2

    def _repoint_runtime(self, cam_num: int, ip: str) -> None:
        """Update the live CameraManager and CameraPort, if present.

        A runtime that is absent or raises must not fail the config change: the
        in-memory value is already updated and config.yaml is the source of truth
        on next start. Errors are logged, not propagated.
        """
        for provider, label in (
            (self._camera_manager, "CameraManager"),
            (self._camera_port, "CameraPort"),
        ):
            runtime = provider()
            if runtime is None:
                continue
            update = getattr(runtime, "update_camera_ip", None)
            if update is None:
                continue
            try:
                update(cam_num, ip)
            except Exception:  # noqa: BLE001 — runtime repoint is best-effort
                logger.exception("%s.update_camera_ip failed for cam %s", label, cam_num)

    def _persist(self, operation: str, target: str, **fields) -> OperationResult:
        """Write the change to config.yaml; report partial success on failure."""
        path = self._config_path()
        if path is None or not path.exists():
            return OperationResult.partial(
                "Applied in memory; config.yaml not found, change is not persisted.",
                operation=operation,
                target=target,
                subsystem="camera",
            )
        try:
            patch_config_yaml(path, **fields)
        except Exception as exc:  # noqa: BLE001 — persist must not lose the live change
            logger.exception("Failed to persist %s to config.yaml", operation)
            return OperationResult.partial(
                f"Applied in memory, but saving to config.yaml failed: {exc}",
                operation=operation,
                target=target,
                subsystem="camera",
            )
        return OperationResult.success(
            operation=operation, target=target, message="Saved.", subsystem="camera"
        )

    def _invalid(self, operation: str, target: str, message: str) -> OperationResult:
        return OperationResult.failure(
            OperationCode.INVALID_INPUT,
            message,
            operation=operation,
            target=target,
            subsystem="camera",
        )
