#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/movement_coordinator.py — Smart movement handler for PTZ cameras
#
# Policy: "last click wins"
#   If a new target is requested while a camera is moving, the latest target
#   replaces the previous pending target. No queue is maintained.
#
# Debounce: duplicate same-target clicks within DEBOUNCE_MS are ignored.
#   Default: 500 ms.  Configurable per coordinator instance.
#
# Manual control priority: requesting manual control cancels any pending
#   preset movement. Preset movement is blocked while manual control is active.
#
# Thread-safe for single-writer / multiple-reader use (Lock per camera slot).
# No Qt dependency — wiring to signals/timers is done in the application layer.

from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from domain.movement import MovementState

logger = logging.getLogger(__name__)

_DEBOUNCE_MS_DEFAULT = 500


@dataclass
class MovementSlot:
    """Runtime state for one camera."""
    camera_id: str
    state: MovementState = MovementState.IDLE
    pending_preset: Optional[int] = None
    last_target: Optional[int] = None
    last_target_ts: float = 0.0
    error_message: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock, compare=False, repr=False)


class MovementCoordinator:
    """
    Coordinates PTZ camera movement requests across one or more cameras.

    Usage:
        coord = MovementCoordinator(camera_ids=["platform", "comments"])
        coord.request_preset("platform", 5, execute_cb=camera.recall_preset)
        status = coord.get_status("platform")
    """

    def __init__(
        self,
        camera_ids: list[str],
        debounce_ms: int = _DEBOUNCE_MS_DEFAULT,
    ) -> None:
        self._debounce_s = debounce_ms / 1000.0
        self._slots: dict[str, MovementSlot] = {
            cid: MovementSlot(camera_id=cid) for cid in camera_ids
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def request_preset(
        self,
        camera_id: str,
        preset: int,
        execute_cb: Optional[Callable[[int], bool]] = None,
    ) -> bool:
        """
        Request a preset move for *camera_id*.

        Returns False if:
          - camera_id is unknown
          - manual control is active
          - duplicate same-target within debounce window

        Calls execute_cb(preset) synchronously if provided and request is accepted.
        """
        slot = self._slots.get(camera_id)
        if slot is None:
            logger.warning("MovementCoordinator: unknown camera %r", camera_id)
            return False

        with slot.lock:
            if slot.state == MovementState.MANUAL_ACTIVE:
                logger.debug("Preset request blocked: manual control active on %s", camera_id)
                return False

            now = time.monotonic()
            if (slot.last_target == preset and
                    (now - slot.last_target_ts) < self._debounce_s):
                logger.debug("Preset request debounced: camera=%s preset=%d", camera_id, preset)
                return False

            # Last click wins — replace any pending target
            slot.pending_preset = preset
            slot.last_target = preset
            slot.last_target_ts = now
            slot.state = MovementState.MOVING_TO_PRESET
            slot.error_message = ""

        logger.info("Camera %s moving to preset %d", camera_id, preset)

        if execute_cb is not None:
            try:
                execute_cb(preset)
            except Exception as exc:
                self.mark_error(camera_id, str(exc))
                return False

        return True

    def mark_arrived(self, camera_id: str) -> None:
        """Signal that a camera has completed its movement (idle)."""
        slot = self._slots.get(camera_id)
        if slot is None:
            return
        with slot.lock:
            slot.state = MovementState.IDLE
            slot.pending_preset = None
        logger.info("Camera %s arrived — idle", camera_id)

    def mark_error(self, camera_id: str, message: str = "") -> None:
        """Mark a camera as unreachable/errored."""
        slot = self._slots.get(camera_id)
        if slot is None:
            return
        with slot.lock:
            slot.state = MovementState.ERROR
            slot.error_message = message
            slot.pending_preset = None
        logger.warning("Camera %s error: %s", camera_id, message)

    def start_manual(self, camera_id: str) -> bool:
        """
        Activate manual joystick control for *camera_id*.

        Cancels any pending preset movement. Returns False if camera unknown.
        """
        slot = self._slots.get(camera_id)
        if slot is None:
            return False
        with slot.lock:
            slot.state = MovementState.MANUAL_ACTIVE
            slot.pending_preset = None
        logger.info("Camera %s manual control active", camera_id)
        return True

    def stop_manual(self, camera_id: str) -> bool:
        """Deactivate manual control and return to idle."""
        slot = self._slots.get(camera_id)
        if slot is None:
            return False
        with slot.lock:
            if slot.state == MovementState.MANUAL_ACTIVE:
                slot.state = MovementState.IDLE
        logger.info("Camera %s manual control released — idle", camera_id)
        return True

    def get_status(self, camera_id: str) -> Optional[MovementSlot]:
        """Return a snapshot of the movement slot for *camera_id*."""
        slot = self._slots.get(camera_id)
        if slot is None:
            return None
        with slot.lock:
            return MovementSlot(
                camera_id=slot.camera_id,
                state=slot.state,
                pending_preset=slot.pending_preset,
                last_target=slot.last_target,
                last_target_ts=slot.last_target_ts,
                error_message=slot.error_message,
            )

    def feedback_message(self, camera_id: str) -> str:
        """
        Human-readable operator feedback string for the given camera.

        Returns one of:
            "Camera <id> moving to <preset>..."
            "Camera <id> ready"
            "Camera <id> unreachable"
            "Camera <id> manual control active"
        """
        slot = self.get_status(camera_id)
        if slot is None:
            return f"Camera {camera_id} unknown"
        if slot.state == MovementState.MOVING_TO_PRESET:
            target = slot.pending_preset
            return f"Camera {camera_id} moving to {target}..."
        if slot.state == MovementState.MANUAL_ACTIVE:
            return f"Camera {camera_id} manual control active"
        if slot.state == MovementState.ERROR:
            return f"Camera {camera_id} unreachable"
        return f"Camera {camera_id} ready"
