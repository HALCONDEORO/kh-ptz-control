#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/preset_verification.py — Preset verification metadata model
#
# VerificationStatus and PresetVerification are pure data — no I/O, no Qt.
# Verification records live with preset/layout data (room_layout.json or a
# dedicated preset_verifications.json managed by PresetVerificationService).

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class VerificationStatus(str, Enum):
    UNKNOWN       = "unknown"
    OK            = "ok"
    WARNING       = "warning"
    FAILED        = "failed"
    NEEDS_RECHECK = "needs_recheck"


@dataclass
class PresetVerification:
    """Verification record for one preset on one camera."""
    seat_id: str
    camera_id: str
    preset: int
    status: VerificationStatus = VerificationStatus.UNKNOWN
    verified_at: Optional[str] = None
    verified_by: str = "installer"
    note: str = ""

    def mark(
        self,
        status: VerificationStatus,
        verified_by: str = "installer",
        note: str = "",
    ) -> None:
        """Update verification status with current timestamp."""
        self.status = status
        self.verified_at = _now_iso()
        self.verified_by = verified_by
        self.note = note

    @property
    def is_verified(self) -> bool:
        return self.status == VerificationStatus.OK

    def to_dict(self) -> dict:
        d = {
            "seat_id":     self.seat_id,
            "camera_id":   self.camera_id,
            "preset":      self.preset,
            "status":      self.status.value,
            "verified_by": self.verified_by,
        }
        if self.verified_at is not None:
            d["verified_at"] = self.verified_at
        if self.note:
            d["note"] = self.note
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PresetVerification":
        return cls(
            seat_id=data.get("seat_id", ""),
            camera_id=data.get("camera_id", ""),
            preset=int(data.get("preset", 0)),
            status=VerificationStatus(data.get("status", "unknown")),
            verified_at=data.get("verified_at"),
            verified_by=data.get("verified_by", "installer"),
            note=data.get("note", ""),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
