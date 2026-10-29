#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/runtime_safety_service.py — Product-level STOP contract (#779).
#
# RuntimeSafetyService is the single application-layer authority for STOP
# actions. UI and controller code calls this service; they never embed VISCA
# or hardware details. The service delegates to CameraPort, which owns the
# hardware boundary.
#
# Definitions:
#   CAMERA_STOP   — stop one camera's movement.
#   STOP_ALL      — stop every configured camera, bypasses session guards.
#
# SafetyResetService (#765) builds on this service for full runtime cleanup.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from domain.supportability import OperationCode, OperationResult

if TYPE_CHECKING:
    from ports.camera_port import CameraPort

logger = logging.getLogger(__name__)


class RuntimeSafetyService:
    """Application-level STOP authority.

    Coordinates camera STOP actions without exposing VISCA or socket details
    to UI or controller layers.  All methods are safe to call with no active
    session and when hardware is disconnected.

    Parameters
    ----------
    camera_port:
        Application-level CameraPort adapter.
    camera_ids:
        Ordered list of camera IDs to operate on.  Defaults to ["cam1", "cam2"].
    """

    def __init__(
        self,
        camera_port: "CameraPort",
        camera_ids: "list[str] | None" = None,
    ) -> None:
        self._port = camera_port
        self._camera_ids: list[str] = list(camera_ids or ["cam1", "cam2"])

    def stop_camera(self, camera_id: str) -> OperationResult:
        """Stop movement on one camera.

        Safe to call with no active session or when the camera is
        disconnected — the adapter reports failure cleanly in those cases.
        """
        try:
            result = self._port.stop_move(camera_id)
            if result.ok:
                logger.info("RuntimeSafetyService: STOP %s", camera_id)
                return OperationResult.success(
                    operation="stop_camera",
                    target=camera_id,
                )
            logger.warning(
                "RuntimeSafetyService: STOP %s failed: %s", camera_id, result.message
            )
            return OperationResult.failure(
                code=OperationCode.CAMERA_COMMAND_FAILED,
                message=result.message,
                operation="stop_camera",
                target=camera_id,
            )
        except Exception as exc:
            logger.exception("RuntimeSafetyService: stop_camera %s raised: %s", camera_id, exc)
            return OperationResult.failure(
                code=OperationCode.CAMERA_UNAVAILABLE,
                message=str(exc),
                operation="stop_camera",
                target=camera_id,
            )

    def stop_all_cameras(self) -> OperationResult:
        """Stop every configured camera.

        Bypasses session guards — safe to call with no active session.
        Attempts all cameras even if one fails; reports partial failure
        in the result message without raising.
        """
        try:
            result = self._port.stop_all()
            if result.ok:
                logger.info(
                    "RuntimeSafetyService: STOP_ALL (%d cameras)", len(self._camera_ids)
                )
                return OperationResult.success(
                    operation="stop_all_cameras",
                    target="all",
                )
            logger.warning(
                "RuntimeSafetyService: STOP_ALL partial failure: %s", result.message
            )
            return OperationResult.failure(
                code=OperationCode.CAMERA_COMMAND_FAILED,
                message=result.message,
                operation="stop_all_cameras",
                target="all",
            )
        except Exception as exc:
            logger.exception("RuntimeSafetyService: stop_all_cameras raised: %s", exc)
            return OperationResult.failure(
                code=OperationCode.CAMERA_UNAVAILABLE,
                message=str(exc),
                operation="stop_all_cameras",
                target="all",
            )
