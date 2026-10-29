#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# adapters/fake_camera.py — Fake PTZ camera adapter for demo and simulation mode
#
# FakeCamera implements CameraPort without opening sockets, sending VISCA bytes,
# or requiring hardware. The application service path is identical to production.
#
# Movement simulation:
#   move_delay_s controls how long moving=True lasts before the camera "arrives".
#   Set to 0.0 in tests for instant results; leave at default for UI feedback.

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from domain.ports import CameraPort, CameraStatus

logger = logging.getLogger(__name__)

_DEFAULT_MOVE_DELAY = 0.5   # seconds


class FakeCamera(CameraPort):
    """
    Deterministic fake camera adapter for demo and simulation mode.

    Fulfils the CameraPort contract. Selected by the demo profile instead of
    the real VISCA-over-IP adapter — UI and application code call identical APIs.
    """

    def __init__(
        self,
        camera_id: str,
        role: str,
        move_delay_s: float = _DEFAULT_MOVE_DELAY,
    ) -> None:
        self._camera_id = camera_id
        self._role = role
        self._move_delay = move_delay_s

        self._connected = True
        self._moving = False
        self._powered = False
        self._current_preset: Optional[int] = None
        self._saved_presets: set[int] = set()
        self._last_error = ""
        self._lock = threading.Lock()

    # ── CameraPort implementation ─────────────────────────────────────────────

    def power_on(self) -> bool:
        with self._lock:
            self._powered = True
            self._last_error = ""
        logger.info("[DEMO] FakeCamera %s power_on", self._camera_id)
        return True

    def standby(self) -> bool:
        with self._lock:
            self._powered = False
            self._moving = False
            self._last_error = ""
        logger.info("[DEMO] FakeCamera %s standby", self._camera_id)
        return True

    def recall_preset(self, preset: int) -> bool:
        logger.info("[DEMO] FakeCamera %s recall_preset %d", self._camera_id, preset)
        self._start_move(preset)
        return True

    def save_preset(self, preset: int) -> bool:
        with self._lock:
            self._saved_presets.add(preset)
            self._last_error = ""
        logger.info("[DEMO] FakeCamera %s save_preset %d", self._camera_id, preset)
        return True

    def go_home(self) -> bool:
        logger.info("[DEMO] FakeCamera %s go_home", self._camera_id)
        self._start_move(preset=0)
        return True

    def stop(self) -> bool:
        with self._lock:
            self._moving = False
            self._last_error = ""
        logger.info("[DEMO] FakeCamera %s stop", self._camera_id)
        return True

    def get_status(self) -> CameraStatus:
        with self._lock:
            return CameraStatus(
                camera_id=self._camera_id,
                role=self._role,
                adapter_type="fake",
                connected=self._connected,
                moving=self._moving,
                current_preset=self._current_preset,
                last_error=self._last_error,
            )

    # ── State inspection (test helper) ────────────────────────────────────────

    @property
    def saved_presets(self) -> frozenset[int]:
        with self._lock:
            return frozenset(self._saved_presets)

    @property
    def powered(self) -> bool:
        with self._lock:
            return self._powered

    # ── Internal ──────────────────────────────────────────────────────────────

    def _start_move(self, preset: int) -> None:
        """Set moving=True, then after move_delay_s set current_preset and moving=False."""
        if self._move_delay <= 0.0:
            with self._lock:
                self._moving = False
                self._current_preset = preset
            return

        with self._lock:
            self._moving = True

        def _arrive():
            time.sleep(self._move_delay)
            with self._lock:
                self._moving = False
                self._current_preset = preset

        t = threading.Thread(target=_arrive, daemon=True)
        t.start()
