#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# adapters/fake_camera_port.py — Fake CameraPort adapter for tests and demo mode.
#
# FakeCameraPort implements the ports.camera_port.CameraPort Protocol
# without opening any sockets, sending VISCA bytes, or requiring hardware.
# Application services can substitute this adapter to run fully offline.
#
# Usage in tests::
#
#     port = FakeCameraPort()
#     result = port.recall_preset("cam1", 5)
#     assert result.ok
#     assert port.current_preset("cam1") == 5

from __future__ import annotations

import logging
from typing import Optional

from domain.ports import CameraStatus
from domain.supportability import CommandResult
from ports.camera_port import make_command_result

logger = logging.getLogger(__name__)


class FakeCameraPort:
    """Deterministic fake CameraPort adapter.

    Satisfies the ports.camera_port.CameraPort Protocol.  All commands
    succeed immediately (no threads, no delays) so tests run fast.
    Use move_delay_s > 0 in integration tests that need async feedback.

    Camera IDs are registered automatically on first use.  Pass
    known_cameras to pre-declare roles for get_status().
    """

    def __init__(
        self,
        known_cameras: dict[str, str] | None = None,
    ) -> None:
        # camera_id -> role label
        self._known: dict[str, str] = dict(known_cameras or {})

        # Per-camera state
        self._connected: dict[str, bool] = {}
        self._powered: dict[str, bool] = {}
        self._current_preset: dict[str, Optional[int]] = {}
        self._moving: dict[str, bool] = {}
        self._backlight_on: dict[str, bool] = {}

        # Call log for assertions in tests
        self.calls: list[str] = []

    # ── State inspection helpers (test API) ───────────────────────────────────

    def current_preset(self, camera_id: str) -> Optional[int]:
        """Return the last recalled preset for camera_id, or None."""
        return self._current_preset.get(camera_id)

    def is_powered(self, camera_id: str) -> bool:
        return self._powered.get(camera_id, False)

    def is_moving(self, camera_id: str) -> bool:
        return self._moving.get(camera_id, False)

    # ── CameraPort implementation ─────────────────────────────────────────────

    def recall_preset(self, camera_id: str, preset: int) -> CommandResult:
        self._ensure(camera_id)
        self._current_preset[camera_id] = preset
        self._moving[camera_id] = False
        self.calls.append(f"recall_preset:{camera_id}:{preset}")
        logger.debug("[FAKE] %s recall_preset %d", camera_id, preset)
        return make_command_result(ok=True, command="recall_preset", camera_id=camera_id)

    def save_preset(self, camera_id: str, preset: int) -> CommandResult:
        self._ensure(camera_id)
        self.calls.append(f"save_preset:{camera_id}:{preset}")
        logger.debug("[FAKE] %s save_preset %d", camera_id, preset)
        return make_command_result(ok=True, command="save_preset", camera_id=camera_id)

    def move(self, camera_id: str, pan_speed: int, tilt_speed: int) -> CommandResult:
        self._ensure(camera_id)
        moving = pan_speed != 0 or tilt_speed != 0
        self._moving[camera_id] = moving
        self.calls.append(f"move:{camera_id}:{pan_speed}:{tilt_speed}")
        logger.debug("[FAKE] %s move pan=%d tilt=%d", camera_id, pan_speed, tilt_speed)
        return make_command_result(ok=True, command="move", camera_id=camera_id)

    def stop_move(self, camera_id: str) -> CommandResult:
        self._ensure(camera_id)
        self._moving[camera_id] = False
        self.calls.append(f"stop_move:{camera_id}")
        logger.debug("[FAKE] %s stop_move", camera_id)
        return make_command_result(ok=True, command="stop_move", camera_id=camera_id)

    def stop_all(self) -> CommandResult:
        """Stop all registered cameras. Records each stop_move call individually.

        Tolerates individual failures: attempts every camera and reports
        overall success only if all cameras stopped cleanly.
        Bypasses session guards — safe to call with no active session.
        """
        self.calls.append("stop_all")
        camera_ids = list(self._known) or list(self._connected)
        for cam_id in camera_ids:
            self.stop_move(cam_id)
        logger.debug("[FAKE] stop_all → %d cameras", len(camera_ids))
        return make_command_result(ok=True, command="stop_all", camera_id="all")

    def zoom(self, camera_id: str, speed: int) -> CommandResult:
        self._ensure(camera_id)
        self.calls.append(f"zoom:{camera_id}:{speed}")
        logger.debug("[FAKE] %s zoom %d", camera_id, speed)
        return make_command_result(ok=True, command="zoom", camera_id=camera_id)

    def power_on(self, camera_id: str) -> CommandResult:
        self._ensure(camera_id)
        self._powered[camera_id] = True
        self.calls.append(f"power_on:{camera_id}")
        logger.debug("[FAKE] %s power_on", camera_id)
        return make_command_result(ok=True, command="power_on", camera_id=camera_id)

    def standby(self, camera_id: str) -> CommandResult:
        self._ensure(camera_id)
        self._powered[camera_id] = False
        self._moving[camera_id] = False
        self.calls.append(f"standby:{camera_id}")
        logger.debug("[FAKE] %s standby", camera_id)
        return make_command_result(ok=True, command="standby", camera_id=camera_id)

    def home(self, camera_id: str) -> CommandResult:
        self._ensure(camera_id)
        self._current_preset[camera_id] = 0
        self._moving[camera_id] = False
        self.calls.append(f"home:{camera_id}")
        logger.debug("[FAKE] %s home", camera_id)
        return make_command_result(ok=True, command="home", camera_id=camera_id)

    def focus_auto(self, camera_id: str) -> CommandResult:
        self._ensure(camera_id)
        self.calls.append(f"focus_auto:{camera_id}")
        logger.debug("[FAKE] %s focus_auto", camera_id)
        return make_command_result(ok=True, command="focus_auto", camera_id=camera_id)

    def focus_manual(self, camera_id: str) -> CommandResult:
        self._ensure(camera_id)
        self.calls.append(f"focus_manual:{camera_id}")
        logger.debug("[FAKE] %s focus_manual", camera_id)
        return make_command_result(ok=True, command="focus_manual", camera_id=camera_id)

    def one_push_af(self, camera_id: str) -> CommandResult:
        self._ensure(camera_id)
        self.calls.append(f"one_push_af:{camera_id}")
        logger.debug("[FAKE] %s one_push_af", camera_id)
        return make_command_result(ok=True, command="one_push_af", camera_id=camera_id)

    def brightness_up(self, camera_id: str) -> CommandResult:
        self._ensure(camera_id)
        self.calls.append(f"brightness_up:{camera_id}")
        logger.debug("[FAKE] %s brightness_up", camera_id)
        return make_command_result(ok=True, command="brightness_up", camera_id=camera_id)

    def brightness_down(self, camera_id: str) -> CommandResult:
        self._ensure(camera_id)
        self.calls.append(f"brightness_down:{camera_id}")
        logger.debug("[FAKE] %s brightness_down", camera_id)
        return make_command_result(ok=True, command="brightness_down", camera_id=camera_id)

    def backlight_toggle(self, camera_id: str) -> CommandResult:
        self._ensure(camera_id)
        current = self._backlight_on.get(camera_id, False)
        self._backlight_on[camera_id] = not current
        self.calls.append(f"backlight_toggle:{camera_id}")
        logger.debug("[FAKE] %s backlight_toggle → %s", camera_id, self._backlight_on[camera_id])
        return make_command_result(ok=True, command="backlight_toggle", camera_id=camera_id)

    def zoom_absolute(self, camera_id: str, position: int) -> CommandResult:
        self._ensure(camera_id)
        self.calls.append(f"zoom_absolute:{camera_id}:{position}")
        logger.debug("[FAKE] %s zoom_absolute %d", camera_id, position)
        return make_command_result(ok=True, command="zoom_absolute", camera_id=camera_id)

    def cancel_polls(self, camera_id: str) -> CommandResult:
        self._ensure(camera_id)
        self.calls.append(f"cancel_polls:{camera_id}")
        logger.debug("[FAKE] %s cancel_polls", camera_id)
        return make_command_result(ok=True, command="cancel_polls", camera_id=camera_id)

    def get_status(self, camera_id: str) -> CameraStatus:
        self._ensure(camera_id)
        return CameraStatus(
            camera_id=camera_id,
            role=self._known.get(camera_id, "unknown"),
            adapter_type="fake",
            connected=self._connected.get(camera_id, True),
            moving=self._moving.get(camera_id, False),
            current_preset=self._current_preset.get(camera_id),
            last_error="",
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _ensure(self, camera_id: str) -> None:
        """Auto-register a camera_id on first use."""
        if camera_id not in self._connected:
            self._connected[camera_id] = True
            self._powered[camera_id] = False
            self._current_preset[camera_id] = None
            self._moving[camera_id] = False
            self._backlight_on[camera_id] = False
