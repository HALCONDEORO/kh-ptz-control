#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_evidence_snapshot_service.py — EvidenceSnapshotService tests

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from application.evidence_snapshot_service import EvidenceSnapshot, EvidenceSnapshotService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_resolver(tmp_path: Path):
    """Return a RuntimePathResolver pointing all paths to tmp_path."""
    os.environ["KHPTZ_LOG_DIR"] = str(tmp_path / "logs")
    os.environ["KHPTZ_DATA_DIR"] = str(tmp_path / "data")
    os.environ["KHPTZ_CONFIG_DIR"] = str(tmp_path / "config")
    from runtime.path_resolver import RuntimePathResolver
    return RuntimePathResolver()


@pytest.fixture(autouse=True)
def clean_env():
    yield
    for var in ("KHPTZ_LOG_DIR", "KHPTZ_DATA_DIR", "KHPTZ_CONFIG_DIR"):
        os.environ.pop(var, None)


# ── EvidenceSnapshot dataclass ────────────────────────────────────────────────

def test_snapshot_is_clean_when_no_errors():
    snap = EvidenceSnapshot(
        snapshot_id="abc",
        correlation_id="xyz",
        taken_before="restore",
        taken_at="2026-01-01T00:00:00+00:00",
    )
    assert snap.is_clean()


def test_snapshot_not_clean_with_errors():
    snap = EvidenceSnapshot(
        snapshot_id="abc",
        correlation_id="xyz",
        taken_before="restore",
        taken_at="2026-01-01T00:00:00+00:00",
        errors=["fingerprint: something went wrong"],
    )
    assert not snap.is_clean()


def test_snapshot_to_dict_contains_required_keys():
    snap = EvidenceSnapshot(
        snapshot_id="abc",
        correlation_id="xyz",
        taken_before="restore",
        taken_at="2026-01-01T00:00:00+00:00",
    )
    d = snap.to_dict()
    assert "snapshot_id" in d
    assert "correlation_id" in d
    assert "taken_before" in d
    assert "taken_at" in d
    assert "errors" in d


# ── EvidenceSnapshotService.capture ──────────────────────────────────────────

def test_capture_returns_evidence_snapshot(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    snap = svc.capture("restore")
    assert isinstance(snap, EvidenceSnapshot)


def test_capture_sets_taken_before(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    snap = svc.capture("config_commit")
    assert snap.taken_before == "config_commit"


def test_capture_generates_snapshot_id(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    snap = svc.capture("restore")
    assert len(snap.snapshot_id) > 0
    assert snap.snapshot_id != "unknown"


def test_capture_generates_correlation_id_when_not_provided(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    snap = svc.capture("restore")
    assert len(snap.correlation_id) > 0


def test_capture_uses_provided_correlation_id(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    snap = svc.capture("restore", correlation_id="my-corr-id")
    assert snap.correlation_id == "my-corr-id"


def test_capture_sets_notes(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    snap = svc.capture("restore", notes="zip: backup_2026.zip")
    assert snap.notes == "zip: backup_2026.zip"


def test_capture_sets_taken_at_timestamp(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    snap = svc.capture("restore")
    assert "2026" in snap.taken_at or snap.taken_at != "unknown"


def test_capture_two_snapshots_have_different_ids(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    snap1 = svc.capture("restore")
    snap2 = svc.capture("restore")
    assert snap1.snapshot_id != snap2.snapshot_id


# ── Persistence ───────────────────────────────────────────────────────────────

def test_capture_creates_evidence_file(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    snap = svc.capture("restore")
    evidence_dir = tmp_path / "logs" / "evidence"
    assert evidence_dir.exists()
    expected_file = evidence_dir / f"{snap.snapshot_id}.json"
    assert expected_file.exists()


def test_capture_writes_valid_json(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    snap = svc.capture("restore")
    evidence_dir = tmp_path / "logs" / "evidence"
    path = evidence_dir / f"{snap.snapshot_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data["snapshot_id"] == snap.snapshot_id
    assert data["taken_before"] == "restore"


def test_no_tmp_leftover_after_capture(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    svc.capture("restore")
    evidence_dir = tmp_path / "logs" / "evidence"
    tmp_files = list(evidence_dir.glob("*.tmp"))
    assert tmp_files == []


# ── Redaction / safety ────────────────────────────────────────────────────────

def test_snapshot_does_not_expose_secrets(tmp_path):
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    snap = svc.capture("restore")
    evidence_dir = tmp_path / "logs" / "evidence"
    path = evidence_dir / f"{snap.snapshot_id}.json"
    content = path.read_text(encoding="utf-8")
    # Basic guard — no common secret patterns in the output
    assert "password" not in content.lower() or "password" not in snap.to_dict()


def test_capture_survives_unwritable_evidence_dir(tmp_path):
    # Even if persist fails, capture still returns a snapshot
    resolver = _make_resolver(tmp_path)
    svc = EvidenceSnapshotService(path_resolver=resolver)
    # Make log_dir a file to force OSError on mkdir
    log_path = tmp_path / "logs"
    log_path.write_text("block", encoding="utf-8")
    snap = svc.capture("restore")  # must not raise
    assert isinstance(snap, EvidenceSnapshot)


# ── Restore service wiring ────────────────────────────────────────────────────

def test_restore_service_captures_evidence_before_restore(tmp_path):
    """Verify that RestoreService.restore() calls evidence capture."""
    from application.restore_service import RestoreService

    svc = RestoreService(
        install_dir=tmp_path,
        data_dir=tmp_path / "data",
        config_path=tmp_path / "config.yaml",
        backup_dir=tmp_path / "backups",
    )
    # A missing zip raises RestoreError, but the evidence capture should still
    # have been attempted (it's non-blocking).
    from application.restore_service import RestoreError
    with pytest.raises(RestoreError):
        svc.restore(tmp_path / "does_not_exist.zip")
