# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for domain/preset_verification.py and application/preset_verification_service.py (#274)."""
from __future__ import annotations

from pathlib import Path


from application.preset_verification_service import PresetVerificationService
from domain.preset_verification import (
    PresetVerification,
    VerificationStatus,
)


# ── VerificationStatus tests ──────────────────────────────────────────────────

class TestVerificationStatus:
    def test_values(self):
        assert VerificationStatus.UNKNOWN == "unknown"
        assert VerificationStatus.OK == "ok"
        assert VerificationStatus.WARNING == "warning"
        assert VerificationStatus.FAILED == "failed"
        assert VerificationStatus.NEEDS_RECHECK == "needs_recheck"


# ── PresetVerification model ──────────────────────────────────────────────────

class TestPresetVerification:
    def test_default_status_unknown(self):
        pv = PresetVerification(seat_id="A12", camera_id="comments", preset=23)
        assert pv.status == VerificationStatus.UNKNOWN

    def test_is_verified_false_by_default(self):
        pv = PresetVerification(seat_id="A12", camera_id="comments", preset=23)
        assert pv.is_verified is False

    def test_mark_ok(self):
        pv = PresetVerification(seat_id="A12", camera_id="comments", preset=23)
        pv.mark(VerificationStatus.OK, verified_by="installer")
        assert pv.status == VerificationStatus.OK
        assert pv.verified_by == "installer"
        assert pv.verified_at is not None

    def test_mark_failed(self):
        pv = PresetVerification(seat_id="B5", camera_id="platform", preset=10)
        pv.mark(VerificationStatus.FAILED, note="camera didn't frame correctly")
        assert pv.status == VerificationStatus.FAILED
        assert "camera" in pv.note

    def test_mark_needs_recheck(self):
        pv = PresetVerification(seat_id="C3", camera_id="comments", preset=7)
        pv.mark(VerificationStatus.NEEDS_RECHECK)
        assert pv.status == VerificationStatus.NEEDS_RECHECK

    def test_is_verified_after_ok(self):
        pv = PresetVerification(seat_id="A12", camera_id="comments", preset=23)
        pv.mark(VerificationStatus.OK)
        assert pv.is_verified is True

    def test_to_dict_round_trip(self):
        pv = PresetVerification(seat_id="A12", camera_id="comments", preset=23)
        pv.mark(VerificationStatus.OK, verified_by="admin", note="looks good")
        pv2 = PresetVerification.from_dict(pv.to_dict())
        assert pv2.seat_id == "A12"
        assert pv2.camera_id == "comments"
        assert pv2.preset == 23
        assert pv2.status == VerificationStatus.OK
        assert pv2.verified_by == "admin"
        assert pv2.note == "looks good"

    def test_to_dict_omits_note_when_empty(self):
        pv = PresetVerification(seat_id="x", camera_id="y", preset=1)
        assert "note" not in pv.to_dict()

    def test_from_dict_unknown_status_default(self):
        pv = PresetVerification.from_dict({
            "seat_id": "x", "camera_id": "y", "preset": 1,
        })
        assert pv.status == VerificationStatus.UNKNOWN


# ── PresetVerificationService ─────────────────────────────────────────────────

def _svc(tmp_path: Path) -> PresetVerificationService:
    return PresetVerificationService(verifications_path=tmp_path / "pv.json")


class TestPresetVerificationServiceLoad:
    def test_load_empty_when_no_file(self, tmp_path):
        assert _svc(tmp_path).load_all() == {}

    def test_get_none_when_no_record(self, tmp_path):
        assert _svc(tmp_path).get("A12", "comments") is None


class TestPresetVerificationServiceMark:
    def test_mark_creates_file(self, tmp_path):
        svc = _svc(tmp_path)
        svc.mark("A12", "comments", 23, VerificationStatus.OK)
        assert (tmp_path / "pv.json").exists()

    def test_mark_returns_record(self, tmp_path):
        svc = _svc(tmp_path)
        rec = svc.mark("A12", "comments", 23, VerificationStatus.OK)
        assert isinstance(rec, PresetVerification)
        assert rec.status == VerificationStatus.OK

    def test_get_after_mark(self, tmp_path):
        svc = _svc(tmp_path)
        svc.mark("A12", "comments", 23, VerificationStatus.OK)
        rec = svc.get("A12", "comments")
        assert rec is not None
        assert rec.status == VerificationStatus.OK

    def test_mark_updates_existing(self, tmp_path):
        svc = _svc(tmp_path)
        svc.mark("A12", "comments", 23, VerificationStatus.OK)
        svc.mark("A12", "comments", 23, VerificationStatus.NEEDS_RECHECK)
        rec = svc.get("A12", "comments")
        assert rec.status == VerificationStatus.NEEDS_RECHECK

    def test_multiple_seats_independent(self, tmp_path):
        svc = _svc(tmp_path)
        svc.mark("A12", "comments", 23, VerificationStatus.OK)
        svc.mark("B5", "platform", 10, VerificationStatus.FAILED)
        assert svc.get("A12", "comments").status == VerificationStatus.OK
        assert svc.get("B5", "platform").status == VerificationStatus.FAILED

    def test_load_all_returns_all_records(self, tmp_path):
        svc = _svc(tmp_path)
        svc.mark("A1", "comments", 1, VerificationStatus.OK)
        svc.mark("A2", "comments", 2, VerificationStatus.FAILED)
        records = svc.load_all()
        assert len(records) == 2


class TestPresetVerificationServiceDiagnostics:
    def test_coverage_summary_empty(self, tmp_path):
        summary = _svc(tmp_path).coverage_summary()
        assert summary["total"] == 0

    def test_coverage_summary_counts(self, tmp_path):
        svc = _svc(tmp_path)
        svc.mark("A1", "comments", 1, VerificationStatus.OK)
        svc.mark("A2", "comments", 2, VerificationStatus.OK)
        svc.mark("A3", "comments", 3, VerificationStatus.FAILED)
        svc.mark("A4", "comments", 4, VerificationStatus.UNKNOWN)
        summary = svc.coverage_summary()
        assert summary["total"] == 4
        assert summary["ok"] == 2
        assert summary["failed"] == 1
        assert summary["unknown"] == 1

    def test_unverified_excludes_ok(self, tmp_path):
        svc = _svc(tmp_path)
        svc.mark("A1", "comments", 1, VerificationStatus.OK)
        svc.mark("A2", "comments", 2, VerificationStatus.FAILED)
        svc.mark("A3", "comments", 3, VerificationStatus.NEEDS_RECHECK)
        unverified = svc.unverified()
        ids = {r.seat_id for r in unverified}
        assert "A1" not in ids
        assert "A2" in ids
        assert "A3" in ids

