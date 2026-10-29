#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_layout_export_import.py — LayoutExportImportService tests

from __future__ import annotations

import json
from pathlib import Path

import pytest

from application.layout_export_import import LayoutExportImportService, ImportResult
from domain.room_layout import SCHEMA_VERSION


# ── Helpers ───────────────────────────────────────────────────────────────────

def _svc(layout_path: Path) -> LayoutExportImportService:
    return LayoutExportImportService(layout_path=layout_path)


def _valid_layout(seats: list | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "room_id": "test",
        "room_name": "Test Room",
        "screen_width": 1440,
        "screen_height": 1080,
        "seats": seats or [
            {
                "id": "1", "label": "A", "preset": 1,
                "camera_role": "platform", "x": 100, "y": 200,
                "row": None, "column": None, "type": "delegate",
                "visible": True, "locked": False, "calibrated": False,
            }
        ],
    }


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


# ── export_layout ────────────────────────────────────────────────────────────

def test_export_copies_file(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    _write(layout_path, _valid_layout())
    svc = _svc(layout_path)

    dest = tmp_path / "exported.json"
    ok = svc.export_layout(dest)

    assert ok is True
    assert dest.exists()
    assert json.loads(dest.read_text()) == _valid_layout()


def test_export_creates_parent_dirs(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    _write(layout_path, _valid_layout())
    svc = _svc(layout_path)

    dest = tmp_path / "subdir" / "deeper" / "layout.json"
    svc.export_layout(dest)

    assert dest.exists()


def test_export_raises_when_no_current_layout(tmp_path):
    svc = _svc(tmp_path / "room_layout.json")
    with pytest.raises(FileNotFoundError):
        svc.export_layout(tmp_path / "dest.json")


def test_export_does_not_modify_source(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    _write(layout_path, _valid_layout())
    original_mtime = layout_path.stat().st_mtime
    svc = _svc(layout_path)

    svc.export_layout(tmp_path / "out.json")

    assert layout_path.stat().st_mtime == original_mtime


# ── import_layout: happy path ────────────────────────────────────────────────

def test_import_valid_layout(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    src = tmp_path / "template.json"
    _write(src, _valid_layout())
    svc = _svc(layout_path)

    result = svc.import_layout(src)

    assert isinstance(result, ImportResult)
    assert result.imported is True
    assert layout_path.exists()


def test_import_replaces_current_layout(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    _write(layout_path, _valid_layout(seats=[
        {"id": "old", "label": "old", "preset": 0, "camera_role": "platform",
         "x": 0, "y": 0, "row": None, "column": None,
         "type": "delegate", "visible": True, "locked": False, "calibrated": False},
    ]))
    src = tmp_path / "new.json"
    _write(src, _valid_layout(seats=[
        {"id": "new", "label": "new", "preset": 99, "camera_role": "comments",
         "x": 500, "y": 300, "row": None, "column": None,
         "type": "delegate", "visible": True, "locked": False, "calibrated": False},
    ]))
    svc = _svc(layout_path)

    svc.import_layout(src)

    imported = json.loads(layout_path.read_text())
    assert imported["seats"][0]["id"] == "new"


def test_import_creates_pre_import_backup(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    _write(layout_path, _valid_layout())
    src = tmp_path / "src.json"
    _write(src, _valid_layout())
    svc = _svc(layout_path)

    result = svc.import_layout(src)

    assert result.pre_import_backup is not None
    assert result.pre_import_backup.exists()


def test_import_no_backup_when_no_current_layout(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    src = tmp_path / "src.json"
    _write(src, _valid_layout())
    svc = _svc(layout_path)

    result = svc.import_layout(src)

    assert result.pre_import_backup is None


def test_import_result_summary_on_success(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    src = tmp_path / "src.json"
    _write(src, _valid_layout())
    svc = _svc(layout_path)

    result = svc.import_layout(src)
    assert "imported" in result.summary().lower() or "Layout" in result.summary()


# ── import_layout: validation failures ───────────────────────────────────────

def test_import_missing_file_rejected(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    svc = _svc(layout_path)

    result = svc.import_layout(tmp_path / "nonexistent.json")

    assert result.imported is False
    assert result.reason is not None
    assert not layout_path.exists()


def test_import_corrupt_json_rejected(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    _write(layout_path, _valid_layout())  # current layout
    src = tmp_path / "bad.json"
    src.write_text("NOT JSON {{{{", encoding="utf-8")
    svc = _svc(layout_path)

    result = svc.import_layout(src)

    assert result.imported is False
    existing = json.loads(layout_path.read_text())
    assert "seats" in existing  # original not overwritten


def test_import_non_dict_rejected(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    src = tmp_path / "array.json"
    src.write_text("[1, 2, 3]", encoding="utf-8")
    svc = _svc(layout_path)

    result = svc.import_layout(src)

    assert result.imported is False
    assert "JSON object" in result.reason


def test_import_future_schema_version_rejected(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    src = tmp_path / "future.json"
    future = _valid_layout()
    future["schema_version"] = SCHEMA_VERSION + 99
    _write(src, future)
    svc = _svc(layout_path)

    result = svc.import_layout(src)

    assert result.imported is False
    assert "schema version" in result.reason.lower()


def test_import_missing_schema_version_rejected(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    src = tmp_path / "no_ver.json"
    data = _valid_layout()
    del data["schema_version"]
    _write(src, data)
    svc = _svc(layout_path)

    result = svc.import_layout(src)

    assert result.imported is False
    assert "schema_version" in result.reason


def test_import_duplicate_seat_ids_rejected(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    seat = {
        "id": "dupe", "label": "dupe", "preset": 1, "camera_role": "platform",
        "x": 0, "y": 0, "row": None, "column": None,
        "type": "delegate", "visible": True, "locked": False, "calibrated": False,
    }
    src = tmp_path / "dupe.json"
    _write(src, _valid_layout(seats=[seat, dict(seat)]))
    svc = _svc(layout_path)

    result = svc.import_layout(src)

    assert result.imported is False
    assert "Duplicate" in result.reason


def test_import_empty_seat_id_rejected(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    src = tmp_path / "empty_id.json"
    _write(src, _valid_layout(seats=[
        {"id": "", "label": "A", "preset": 1, "camera_role": "platform",
         "x": 0, "y": 0, "row": None, "column": None,
         "type": "delegate", "visible": True, "locked": False, "calibrated": False},
    ]))
    svc = _svc(layout_path)

    result = svc.import_layout(src)

    assert result.imported is False
    assert "non-empty" in result.reason


def test_import_does_not_touch_other_files(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    seat_names = tmp_path / "seat_names.json"
    seat_names.write_text('{"seats": {"1": "PersonA"}}', encoding="utf-8")

    src = tmp_path / "src.json"
    _write(src, _valid_layout())
    svc = _svc(layout_path)
    svc.import_layout(src)

    assert seat_names.read_text() == '{"seats": {"1": "PersonA"}}'


def test_import_no_tmp_leftover_after_success(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    src = tmp_path / "src.json"
    _write(src, _valid_layout())
    svc = _svc(layout_path)
    svc.import_layout(src)

    import_tmp = tmp_path / "room_layout.json.import.tmp"
    assert not import_tmp.exists()


# ── round-trip export → import ────────────────────────────────────────────────

def test_export_then_import_round_trip(tmp_path):
    layout_path = tmp_path / "room_layout.json"
    _write(layout_path, _valid_layout())
    svc = _svc(layout_path)

    exported = tmp_path / "template.json"
    svc.export_layout(exported)

    # modify layout on disk
    _write(layout_path, _valid_layout(seats=[
        {"id": "temp", "label": "temp", "preset": 999,
         "camera_role": "platform", "x": 0, "y": 0,
         "row": None, "column": None, "type": "delegate",
         "visible": True, "locked": False, "calibrated": False},
    ]))

    result = svc.import_layout(exported)

    assert result.imported is True
    restored = json.loads(layout_path.read_text())
    assert restored["seats"][0]["id"] == "1"
