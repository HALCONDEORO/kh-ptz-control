#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/preset_verification_service.py — Preset verification persistence
#
# Reads/writes preset_verifications.json using atomic writes (.tmp → os.replace).
# Key: "{seat_id}:{camera_id}" — one record per seat/camera combination.
#
# Phase 1 (this issue): metadata store and manual mark OK/failed/needs_recheck.
# Phase 2 (future):     test-all workflow, grouped by zone, stop/cancel support.

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from core.atomic_write import write_text_atomic

from domain.preset_verification import (
    PresetVerification,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

_VERIFICATIONS_FILENAME = "preset_verifications.json"


def _default_path() -> Path:
    from runtime.path_resolver import RuntimePathResolver
    return RuntimePathResolver().data_dir / _VERIFICATIONS_FILENAME


class PresetVerificationService:
    """
    Stores and retrieves preset verification records.

    Records are keyed by "{seat_id}:{camera_id}" and persisted to
    preset_verifications.json in the user data directory.
    """

    def __init__(self, verifications_path: Optional[Path] = None) -> None:
        self._path = verifications_path or _default_path()

    # ── Read ──────────────────────────────────────────────────────────────────

    def load_all(self) -> Dict[str, PresetVerification]:
        """Return all records keyed by '{seat_id}:{camera_id}'."""
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            records: Dict[str, PresetVerification] = {}
            for key, data in raw.items():
                try:
                    records[key] = PresetVerification.from_dict(data)
                except (KeyError, ValueError) as exc:
                    logger.warning("Skipping corrupt verification record %r: %s", key, exc)
            return records
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load verifications: %s", exc)
            return {}

    def get(self, seat_id: str, camera_id: str) -> Optional[PresetVerification]:
        """Return the record for one seat/camera pair, or None if not found."""
        return self.load_all().get(_key(seat_id, camera_id))

    # ── Write ─────────────────────────────────────────────────────────────────

    def mark(
        self,
        seat_id: str,
        camera_id: str,
        preset: int,
        status: VerificationStatus,
        verified_by: str = "installer",
        note: str = "",
    ) -> PresetVerification:
        """
        Create or update a verification record. Returns the updated record.

        Writes atomically (.tmp → os.replace). Non-fatal: logs and returns the
        record even if the write fails.
        """
        records = self.load_all()
        key = _key(seat_id, camera_id)
        rec = records.get(key) or PresetVerification(
            seat_id=seat_id,
            camera_id=camera_id,
            preset=preset,
        )
        rec.mark(status=status, verified_by=verified_by, note=note)
        records[key] = rec
        self._save(records)
        return rec

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def coverage_summary(self) -> dict:
        """
        Return a summary of verification coverage for diagnostics.

        Example: {"total": 20, "ok": 15, "failed": 2, "unknown": 3}
        """
        records = self.load_all()
        summary: dict = {"total": len(records)}
        for status in VerificationStatus:
            summary[status.value] = sum(
                1 for r in records.values() if r.status == status
            )
        return summary

    def unverified(self) -> List[PresetVerification]:
        """Return records not yet verified (status != ok)."""
        return [
            r for r in self.load_all().values()
            if r.status != VerificationStatus.OK
        ]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _save(self, records: Dict[str, PresetVerification]) -> bool:
        try:
            payload = {k: v.to_dict() for k, v in records.items()}
            write_text_atomic(
                self._path,
                json.dumps(payload, indent=2, ensure_ascii=False),
            )
            return True
        except OSError as exc:
            logger.warning("Could not save verifications: %s", exc)
            return False


def _key(seat_id: str, camera_id: str) -> str:
    return f"{seat_id}:{camera_id}"
