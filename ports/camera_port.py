#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ports/camera_port.py — Application-level CameraPort protocol.
#
# This is the stable camera hardware boundary.  Application services depend
# on this Protocol; they never import VISCA protocol classes, sockets, or
# concrete adapter implementations.
#
# Two adapters implement this contract:
#   ViscaCameraAdapter  — VISCA-over-IP production adapter.
#   FakeCameraPort      — deterministic fake for tests and demo mode.
#
# See also domain/ports.py which defines the lower-level per-instance
# CameraPort ABC (bool returns) used by FakeCamera and FakeATEM.  This
# module is the application-level version with CommandResult returns and
# a camera_id parameter so one adapter can dispatch to multiple cameras.

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from domain.ports import CameraStatus
from domain.supportability import CommandResult


# ── Factory helper ─────────────────────────────────────────────────────────────

def make_command_result(
    *,
    ok: bool,
    command: str,
    camera_id: str,
    duration_ms: int | None = None,
    error_code: str | None = None,
    message: str = "",
) -> CommandResult:
    """Build a CommandResult for a camera operation.

    Adapter implementations should use this helper to ensure a consistent
    result shape across ViscaCameraAdapter and FakeCameraPort.
    """
    return CommandResult(
        ok=ok,
        command=command,
        target=camera_id,
        duration_ms=duration_ms,
        correlation_id=str(uuid.uuid4()),
        error_code=None if ok else (error_code or "CAMERA_ERROR"),
        message=message or ("OK" if ok else "Camera error or timeout"),
    )


# ── CameraPort protocol ────────────────────────────────────────────────────────

@runtime_checkable
class CameraPort(Protocol):
    """Application-level contract for PTZ camera adapters.

    Both ViscaCameraAdapter (production) and FakeCameraPort (demo/test)
    must satisfy this protocol.  Application services and diagnostics
    depend only on this interface — never on VISCA protocol classes,
    sockets, or concrete adapter internals.

    All command methods return CommandResult so callers can inspect
    success, timing, and error details without knowing about VISCA.

    camera_id is a stable string identifier (e.g. "cam1", "cam2") that
    the adapter maps to the concrete camera target.  Adapters own this
    mapping; callers never handle VISCA addresses or hex cam IDs.
    """

    def recall_preset(self, camera_id: str, preset: int) -> CommandResult:
        """Move camera to saved preset position."""
        ...

    def save_preset(self, camera_id: str, preset: int) -> CommandResult:
        """Save current camera position to preset slot."""
        ...

    def move(self, camera_id: str, pan_speed: int, tilt_speed: int) -> CommandResult:
        """Start continuous pan/tilt movement.

        pan_speed:  positive = right, negative = left, 0 = stop.
        tilt_speed: positive = up, negative = down, 0 = stop.
        Callers must call stop_move() when movement should end.
        """
        ...

    def stop_move(self, camera_id: str) -> CommandResult:
        """Stop any active pan/tilt movement."""
        ...

    def zoom(self, camera_id: str, speed: int) -> CommandResult:
        """Continuous zoom drive.

        positive = tele (zoom in), negative = wide (zoom out), 0 = stop.
        """
        ...

    def power_on(self, camera_id: str) -> CommandResult:
        """Power camera on."""
        ...

    def standby(self, camera_id: str) -> CommandResult:
        """Put camera into standby."""
        ...

    def home(self, camera_id: str) -> CommandResult:
        """Move camera to home position."""
        ...

    def stop_all(self) -> CommandResult:
        """Stop movement on every configured camera.

        Bypasses session guards — safe to call with no active session and
        when hardware is disconnected.  Attempts all cameras even if one fails.
        """
        ...

    def cancel_polls(self, camera_id: str) -> CommandResult:
        """Cancel any active background polling for this camera."""
        ...

    def get_status(self, camera_id: str) -> CameraStatus:
        """Return current camera status snapshot."""
        ...
