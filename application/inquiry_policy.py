#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
"""
PTZ inquiry and polling priority policy.

Priority order (highest first):
  1. Emergency STOP / stop_all (bypasses everything)
  2. Manual movement / zoom drive
  3. Preset recall / save
  4. Session safety commands (standby, home)
  5. Status inquiries / preset polling
  6. Diagnostics-only inquiries

Inquiry rules:
  - Only one zoom inquiry per camera at a time (inflight guard in CameraManager).
  - Only one AE inquiry per camera at a time (inflight guard in CameraManager).
  - STOP / Safety Reset cancel / bypass pending inquiries via priority queue drain.
  - Session end calls cancel_polls() on each camera.
  - Inquiries must not block or delay STOP.
"""

from __future__ import annotations

from enum import IntEnum


class InquiryPriority(IntEnum):
    EMERGENCY_STOP  = 0
    MOVEMENT        = 1
    PRESET          = 2
    SESSION_SAFETY  = 3
    STATUS_INQUIRY  = 4
    DIAGNOSTICS     = 5


# Maximum seconds an inquiry should wait before giving up
INQUIRY_TIMEOUT_S: float = 5.0

# Maximum seconds between polling cycles
POLLING_INTERVAL_S: float = 2.0
