#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_support_bundle_service.py — SupportBundleService unit tests (#491)
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock


from application.support_bundle_service import SupportBundleService


def _svc(tmp_path: Path, recorder=None, incidents_dir=None, **kwargs) -> SupportBundleService:
    return SupportBundleService(
        output_dir=tmp_path / "bundles",
        flight_recorder=recorder,
        incidents_dir=incidents_dir,
        app_version="3.14.0",
        installation_id="test-install-01",
        installation_profile="starter_2_camera",
        **kwargs,
    )


def _fake_recorder(events: list[dict] | None = None):
    rec = MagicMock()
    rec.export_for_support.return_value = events or [{"event_type": "DoctorRun", "status": "ok"}]
    return rec


# ── Happy path ────────────────────────────────────────────────────────────────

def test_create_returns_path(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    assert path is not None
    assert path.suffix == ".zip"
    assert path.exists()


def test_bundle_is_valid_zip(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    assert zipfile.is_zipfile(path)


def test_bundle_contains_manifest(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
    assert "manifest.json" in names


def test_manifest_is_never_restore_capable(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["restore_capable"] is False
    assert manifest["bundle_purpose"] == "support"


def test_manifest_contains_version_and_id(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["app_version"] == "3.14.0"
    assert manifest["installation_id"] == "test-install-01"
    assert manifest["profile"] == "starter_2_camera"


def test_bundle_includes_readme(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
    assert "blackbox/README.txt" in names


# ── Events ────────────────────────────────────────────────────────────────────

def test_bundle_includes_recent_events(tmp_path):
    rec = _fake_recorder([{"event_type": "DoctorRun"}, {"event_type": "BackupCreated"}])
    svc = _svc(tmp_path, recorder=rec)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        assert "blackbox/recent_events.jsonl" in zf.namelist()
        content = zf.read("blackbox/recent_events.jsonl").decode("utf-8")
    lines = [line for line in content.splitlines() if line.strip()]
    event_types = [json.loads(line)["event_type"] for line in lines]
    assert "DoctorRun" in event_types
    assert "BackupCreated" in event_types


def test_recorder_called_with_max_events(tmp_path):
    rec = _fake_recorder([{"event_type": "DoctorRun"}])
    svc = _svc(tmp_path, recorder=rec, max_events=17)

    svc.create()

    rec.export_for_support.assert_called_once_with(17)


def test_recorder_error_omits_events_and_warns(tmp_path):
    rec = MagicMock()
    rec.export_for_support.side_effect = RuntimeError("blackbox unavailable")
    svc = _svc(tmp_path, recorder=rec)

    path = svc.create()

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))
    assert "blackbox/recent_events.jsonl" not in names
    assert any("blackbox_events: error" in w for w in manifest["redaction_warnings"])


def test_bundle_without_recorder_omits_events(tmp_path):
    svc = _svc(tmp_path, recorder=None)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
    assert "blackbox/recent_events.jsonl" not in names


def test_events_warning_in_manifest_when_no_recorder(tmp_path):
    svc = _svc(tmp_path, recorder=None)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert any("blackbox_events" in w for w in manifest["redaction_warnings"])


# ── Incidents ─────────────────────────────────────────────────────────────────

def _write_incident(incidents_dir: Path, name: str, reason: str = "test_event") -> None:
    incidents_dir.mkdir(parents=True, exist_ok=True)
    (incidents_dir / name).write_text(
        json.dumps({"schema_version": 1, "reason": reason, "last_events": [], "extra": {}})
    )


def test_bundle_includes_incidents(tmp_path):
    idir = tmp_path / "incidents"
    _write_incident(idir, "incident-20260101-120000-abcd1234.json", "camera_failed")
    svc = _svc(tmp_path, incidents_dir=idir)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
    incident_files = [n for n in names if n.startswith("blackbox/incidents/")]
    assert len(incident_files) == 1


def test_incidents_are_redacted_in_bundle(tmp_path):
    idir = tmp_path / "incidents"
    _write_incident_with_secret(idir)
    svc = _svc(tmp_path, incidents_dir=idir)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        for name in names:
            if name.startswith("blackbox/incidents/"):
                content = zf.read(name).decode("utf-8")
                assert "hunter2" not in content


def _write_incident_with_secret(incidents_dir: Path) -> None:
    incidents_dir.mkdir(parents=True, exist_ok=True)
    (incidents_dir / "incident-20260101-120000-aaaa0000.json").write_text(
        json.dumps({
            "schema_version": 1, "reason": "test", "last_events": [],
            "extra": {"password": "hunter2", "user": "admin"},
        })
    )


def test_bundle_without_incidents_dir_still_creates(tmp_path):
    svc = _svc(tmp_path, incidents_dir=None)
    path = svc.create()
    assert path is not None and path.exists()


def test_incidents_unavailable_warning_in_manifest(tmp_path):
    svc = _svc(tmp_path, incidents_dir=tmp_path / "nonexistent_incidents")
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert any("incidents" in w for w in manifest["redaction_warnings"])


def test_bundle_excludes_max_incidents(tmp_path):
    idir = tmp_path / "incidents"
    for i in range(25):
        _write_incident(idir, f"incident-20260101-12000{i:02d}-abcd{i:04d}.json")
    svc = _svc(tmp_path, incidents_dir=idir, max_incidents=10)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        incident_files = [n for n in zf.namelist() if n.startswith("blackbox/incidents/")]
    assert len(incident_files) <= 10


def test_bundle_keeps_newest_incidents_by_mtime(tmp_path):
    import os

    idir = tmp_path / "incidents"
    old_name = "incident-20260101-120000-old00001.json"
    new_name = "incident-20260101-120001-new00001.json"
    _write_incident(idir, old_name, "old")
    _write_incident(idir, new_name, "new")
    os.utime(idir / old_name, (1000, 1000))
    os.utime(idir / new_name, (2000, 2000))
    svc = _svc(tmp_path, incidents_dir=idir, max_incidents=1)

    path = svc.create()

    with zipfile.ZipFile(path) as zf:
        incident_files = [n for n in zf.namelist() if n.startswith("blackbox/incidents/")]
    assert incident_files == [f"blackbox/incidents/{new_name}"]


# ── Secret exclusion ──────────────────────────────────────────────────────────

def test_bundle_excludes_listed_secret_files(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    excluded = manifest["excluded_files"]
    assert any("password" in e.lower() for e in excluded)


def test_events_secrets_are_redacted(tmp_path):
    rec = _fake_recorder([{"event_type": "AuthEvent", "password": "s3cr3t"}])
    svc = _svc(tmp_path, recorder=rec)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        content = zf.read("blackbox/recent_events.jsonl").decode("utf-8")
    assert "s3cr3t" not in content


# ── Pruning ───────────────────────────────────────────────────────────────────

def test_prune_keeps_most_recent_bundles(tmp_path):
    svc = _svc(tmp_path, max_bundles=3)
    for _ in range(5):
        svc.create()
    files = list((tmp_path / "bundles").glob("support-*.zip"))
    assert len(files) <= 3


# ── Safety ────────────────────────────────────────────────────────────────────

def test_create_returns_none_on_internal_error(tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    svc = _svc(tmp_path)
    monkeypatch.setattr(svc, "_create_inner", MagicMock(side_effect=OSError("fail")))
    result = svc.create()
    assert result is None


def test_create_removes_tmp_file_when_zip_write_fails(tmp_path, monkeypatch):
    svc = _svc(tmp_path)

    class BrokenZip:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            raise OSError("zip failed")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(zipfile, "ZipFile", BrokenZip)

    result = svc.create()

    assert result is None
    assert list((tmp_path / "bundles").glob("*.tmp")) == []


def test_partial_corrupt_incidents_included_with_warning(tmp_path):
    idir = tmp_path / "incidents"
    idir.mkdir()
    (idir / "incident-20260101-120000-good0001.json").write_text(
        json.dumps({"schema_version": 1, "reason": "ok", "last_events": []})
    )
    (idir / "incident-20260101-120001-bad00001.json").write_text("not valid json{{")
    svc = _svc(tmp_path, incidents_dir=idir)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        incident_files = [n for n in zf.namelist() if n.startswith("blackbox/incidents/")]
    assert len(incident_files) == 1
    assert any("partial" in w for w in manifest["redaction_warnings"])


def test_all_corrupt_incidents_warning_in_manifest(tmp_path):
    idir = tmp_path / "incidents"
    idir.mkdir()
    (idir / "incident-20260101-120000-badbad01.json").write_text("garbage{{{")
    svc = _svc(tmp_path, incidents_dir=idir)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert any("corrupt" in w for w in manifest["redaction_warnings"])


# ── Hardened bundle content (#532 Block C) ───────────────────────────────────

def test_bundle_includes_version_txt(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        assert "version.txt" in zf.namelist()
        content = zf.read("version.txt").decode("utf-8")
    assert len(content.strip()) > 0


def test_bundle_version_txt_contains_version_info(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        content = zf.read("version.txt").decode("utf-8")
    assert "app_version" in content


def test_bundle_includes_doctor_txt(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        assert "doctor.txt" in zf.namelist()
        content = zf.read("doctor.txt").decode("utf-8")
    assert len(content.strip()) > 0


def test_bundle_includes_install_summary_json(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        assert "install_summary.json" in zf.namelist()
        data = json.loads(zf.read("install_summary.json"))
    assert isinstance(data, dict)


def test_bundle_includes_config_summary_json(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        assert "config_summary.json" in zf.namelist()
        data = json.loads(zf.read("config_summary.json"))
    assert isinstance(data, dict)


def test_config_summary_has_no_raw_secret_values(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        content = zf.read("config_summary.json").decode("utf-8")
    assert "password" not in content.lower() or '"password"' not in content


def test_new_files_in_manifest_included_list(tmp_path):
    svc = _svc(tmp_path)
    path = svc.create()
    with zipfile.ZipFile(path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    included = manifest["included_files"]
    assert "version.txt" in included
    assert "doctor.txt" in included
    assert "install_summary.json" in included
    assert "config_summary.json" in included

