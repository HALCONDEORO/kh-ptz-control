#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/ptz_camera_state.py — Runtime PTZ camera state model

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class PTZCameraState(str, Enum):
    UNKNOWN = "unknown"
    IDLE = "idle"
    MOVING = "moving"
    ZOOMING = "zooming"
    PRESET_RECALLING = "preset_recalling"
    PRESET_POLLING = "preset_polling"
    STOPPING = "stopping"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    ERROR = "error"
    SIMULATED = "simulated"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class PTZCameraRuntimeState:
    camera_id: str
    camera_role: str
    state: PTZCameraState
    connected: bool
    current_command_id: Optional[str] = None
    current_command_type: Optional[str] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    last_error: Optional[str] = None
    queue_depth: Optional[int] = None
    recent_latency_ms: Optional[int] = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
