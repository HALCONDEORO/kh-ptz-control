#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# application/preset_test_models.py — Data models for the preset test runner.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

STATUS_OK = "OK"
STATUS_WARNING = "WARNING"
STATUS_ERROR = "ERROR"
STATUS_SKIPPED = "SKIPPED"
STATUS_CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class PresetTestItem:
    item_id: str
    label: str
    camera_role: str       # "main" | "comments"
    camera_index: int      # 1 or 2
    preset: Optional[int]
    enabled: bool = True
    assigned_name: Optional[str] = None   # seat attendee name if available
    has_verified_ptz: Optional[bool] = None  # True=green, False/None=yellow when recall ok


@dataclass(frozen=True)
class PresetTestResult:
    item: PresetTestItem
    status: str            # STATUS_* constant
    message: str
    duration_ms: Optional[int] = None


@dataclass(frozen=True)
class PresetTestSummary:
    total: int
    ok: int
    warning: int
    error: int
    skipped: int
    cancelled: bool
    results: list[PresetTestResult] = field(default_factory=list)
