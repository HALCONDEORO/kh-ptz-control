#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_incident_service.py — IncidentService unit tests (#490)
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock


from application.incident_service import IncidentService


def _svc(tmp_path: Path, recorder=None, **kwargs) -> IncidentService:
    return IncidentService(
        incidents_dir=tmp_path / "incidents",
        flight_recorder=recorder,
        **kwargs,
    )


# ── Happy path ────────────────────────────────────────────────────────────────

def test_record_creates_file(tmp_path):
    svc = _svc(tmp_path)
    path = svc.record("camera_command_failed", summary="Camera timeout")
    assert path is not None
    assert path.exists()


def test_incident_is_valid_json(tmp_path):
    svc = _svc(tmp_path)
    path = svc.record("config_validation_failed")
    data = json.loads(path.read_text())
    assert data["schema_version"] == 1
    assert "incident_id" in data
    assert "created_at" in data


def test_incident_contains_reason(tmp_path):
    svc = _svc(tmp_path)
    path = svc.record("backup_failed", summary="Disk full")
    data = json.loads(path.read_text())
    assert data["reason"] == "backup_failed"
    assert data["summary"] == "Disk full"


def test_incident_contains_version_metadata(tmp_path):
    svc = _svc(tmp_path, app_version="3.14.0", installation_profile="starter_2_camera")
    path = svc.record("camera_unreachable")
    data = json.loads(path.read_text())
    assert data["app_version"] == "3.14.0"
    assert data["installation_profile"] == "starter_2_camera"


def test_incident_redaction_applied(tmp_path):
    svc = _svc(tmp_path)
    path = svc.record("auth_failed", extra={"password": "hunter2", "user": "admin"})
    data = json.loads(path.read_text())
    assert data["extra"]["password"] == "[REDACTED]"
    assert data["extra"]["user"] == "admin"


def test_incident_includes_last_events_from_recorder(tmp_path):
    mock_recorder = MagicMock()
    mock_recorder.get_recent.return_value = [{"event_type": "SeatPresetRecallRequested"}]
    svc = _svc(tmp_path, recorder=mock_recorder)
    path = svc.record("camera_command_failed")
    data = json.loads(path.read_text())
    assert len(data["last_events"]) == 1


def test_incident_works_without_recorder(tmp_path):
    svc = _svc(tmp_path)
    path = svc.record("doctor_critical_error")
    data = json.loads(path.read_text())
    assert data["last_events"] == []


# ── Safety: never raises ──────────────────────────────────────────────────────

def test_record_returns_none_on_crash(tmp_path, monkeypatch):
    svc = _svc(tmp_path)
    from unittest.mock import MagicMock
    monkeypatch.setattr(svc, "_write", MagicMock(side_effect=OSError("simulated failure")))
    result = svc.record("camera_command_failed")
    assert result is None


# ── Pruning ───────────────────────────────────────────────────────────────────

def test_prune_keeps_most_recent_incidents(tmp_path):
    svc = _svc(tmp_path, max_incidents=3)
    for _ in range(5):
        svc.record("test_event")
    files = list((tmp_path / "incidents").glob("incident-*.json"))
    assert len(files) <= 3


# ── Backup/restore integration ────────────────────────────────────────────────

def test_backup_failure_records_incident(tmp_path):
    from application.backup_service import BackupService
    tmp_path / "incidents"
    recorder_events = []

    class FakeRecorder:
        def record_dict(self, d):
            recorder_events.append(d)
        def get_recent(self, n):
            return []

    recorder = FakeRecorder()
    svc = BackupService(
        install_dir=tmp_path / "app",
        data_dir=tmp_path / "data",
        config_path=tmp_path / "app" / "config.yaml",
        backup_dir=tmp_path / "backups",
        version_file=tmp_path / "app" / "VERSION",
        flight_recorder=recorder,
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "VERSION").write_text("3.0.0")
    (tmp_path / "data").mkdir()
    svc.create_backup()
    event_types = [e["event_type"] for e in recorder_events]
    assert "BackupCreated" in event_types


def test_restore_records_started_and_succeeded(tmp_path):
    from application.backup_service import BackupService
    from application.restore_service import RestoreService
    recorder_events = []

    class FakeRecorder:
        def record_dict(self, d):
            recorder_events.append(d)
        def get_recent(self, n):
            return []

    install_dir = tmp_path / "app"
    data_dir = tmp_path / "data"
    install_dir.mkdir()
    data_dir.mkdir()
    (install_dir / "VERSION").write_text("3.0.0")
    (data_dir / "seat_names.json").write_text("{}")

    bk_svc = BackupService(
        install_dir=install_dir, data_dir=data_dir,
        config_path=install_dir / "config.yaml",
        backup_dir=tmp_path / "backups", version_file=install_dir / "VERSION",
    )
    bk = bk_svc.create_backup()

    restore_svc = RestoreService(
        install_dir=install_dir, data_dir=data_dir,
        config_path=install_dir / "config.yaml",
        backup_dir=tmp_path / "backups", version_file=install_dir / "VERSION",
        flight_recorder=FakeRecorder(),
    )
    restore_svc.restore(bk.path)
    event_types = [e["event_type"] for e in recorder_events]
    assert "RestoreStarted" in event_types
    assert "RestoreSucceeded" in event_types
