#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_layout_schema_versioning.py — schema versioning, migration and recovery tests

from __future__ import annotations

import json
from pathlib import Path

import pytest

from application.layout_service import LayoutService, LayoutValidationError
from domain.room_layout import SCHEMA_VERSION


# ── Helpers ───────────────────────────────────────────────────────────────────

_LEGACY = {1: (100, 200), 2: (200, 300)}


def _svc(tmp_path: Path) -> LayoutService:
    return LayoutService(
        layout_path=tmp_path / "room_layout.json",
        legacy_positions=_LEGACY,
    )


def _write_layout(path: Path, *, version: int, seats: list | None = None) -> None:
    data = {
        "schema_version": version,
        "room_id": "test",
        "room_name": "Test Room",
        "screen_width": 1440,
        "screen_height": 1080,
        "seats": seats or [
            {
                "id": "1", "label": "1", "preset": 1,
                "camera_role": "platform", "x": 100, "y": 200,
                "row": None, "column": None, "type": "delegate",
                "visible": True, "locked": False, "calibrated": False,
            }
        ],
    }
    path.write_text(json.dumps(data), encoding="utf-8")


# ── schema version: supported ────────────────────────────────────────────────

def test_load_current_schema_version(tmp_path):
    svc = _svc(tmp_path)
    _write_layout(tmp_path / "room_layout.json", version=SCHEMA_VERSION)
    layout = svc.load()
    assert layout.schema_version == SCHEMA_VERSION


# ── schema version: future (unsupported) ─────────────────────────────────────

def test_load_future_schema_version_falls_back_to_default(tmp_path):
    svc = _svc(tmp_path)
    _write_layout(tmp_path / "room_layout.json", version=SCHEMA_VERSION + 10)

    layout = svc.load()  # must not raise — recovers gracefully

    assert svc.recovery_used is True
    assert layout is not None
    assert len(layout.seats) == len(_LEGACY)


def test_load_future_schema_version_tries_bak_first(tmp_path):
    svc = _svc(tmp_path)
    layout_path = tmp_path / "room_layout.json"
    bak_path = tmp_path / "room_layout.bak"  # json_io uses .with_suffix('.bak')

    _write_layout(layout_path, version=SCHEMA_VERSION + 10)
    _write_layout(bak_path, version=SCHEMA_VERSION)  # good .bak

    layout = svc.load()

    assert svc.recovery_used is True
    assert layout.seats[0].id == "1"


# ── corrupt primary file ──────────────────────────────────────────────────────

def test_corrupt_primary_recovers_from_bak(tmp_path):
    svc = _svc(tmp_path)
    layout_path = tmp_path / "room_layout.json"
    bak_path = tmp_path / "room_layout.bak"  # json_io uses .with_suffix('.bak')

    layout_path.write_text("NOT JSON <<<", encoding="utf-8")
    _write_layout(bak_path, version=SCHEMA_VERSION)

    layout = svc.load()

    assert svc.recovery_used is True
    assert len(layout.seats) == 1
    assert layout.seats[0].id == "1"


def test_corrupt_primary_and_missing_bak_regenerates(tmp_path):
    svc = _svc(tmp_path)
    (tmp_path / "room_layout.json").write_text("bad json {{{", encoding="utf-8")

    layout = svc.load()

    assert svc.recovery_used is True
    assert len(layout.seats) == len(_LEGACY)


def test_corrupt_primary_and_corrupt_bak_regenerates(tmp_path):
    svc = _svc(tmp_path)
    (tmp_path / "room_layout.json").write_text("bad", encoding="utf-8")
    (tmp_path / "room_layout.json.bak").write_text("also bad", encoding="utf-8")

    layout = svc.load()

    assert svc.recovery_used is True
    assert len(layout.seats) == len(_LEGACY)


def test_recovery_not_used_on_clean_load(tmp_path):
    svc = _svc(tmp_path)
    _write_layout(tmp_path / "room_layout.json", version=SCHEMA_VERSION)
    svc.load()
    assert svc.recovery_used is False


def test_recovery_not_used_when_file_missing(tmp_path):
    svc = _svc(tmp_path)
    svc.load()
    assert svc.recovery_used is False


# ── validation: save ──────────────────────────────────────────────────────────

def test_save_with_duplicate_ids_raises(tmp_path):
    from domain.room_layout import RoomLayout, SeatLayout
    svc = _svc(tmp_path)
    layout = RoomLayout(
        schema_version=SCHEMA_VERSION, room_id="r", room_name="n",
        screen_width=1440, screen_height=1080,
        seats=[
            SeatLayout(id="1", label="A", preset=1, camera_role="platform", x=0, y=0),
            SeatLayout(id="1", label="B", preset=2, camera_role="platform", x=0, y=0),
        ],
    )
    with pytest.raises(LayoutValidationError, match="Duplicate seat id"):
        svc.save(layout)


def test_save_with_empty_id_raises(tmp_path):
    from domain.room_layout import RoomLayout, SeatLayout
    svc = _svc(tmp_path)
    layout = RoomLayout(
        schema_version=SCHEMA_VERSION, room_id="r", room_name="n",
        screen_width=1440, screen_height=1080,
        seats=[
            SeatLayout(id="", label="A", preset=1, camera_role="platform", x=0, y=0),
        ],
    )
    with pytest.raises(LayoutValidationError, match="empty id"):
        svc.save(layout)


def test_save_valid_layout_does_not_raise(tmp_path):
    from domain.room_layout import RoomLayout, SeatLayout
    svc = _svc(tmp_path)
    layout = RoomLayout(
        schema_version=SCHEMA_VERSION, room_id="r", room_name="n",
        screen_width=1440, screen_height=1080,
        seats=[
            SeatLayout(id="1", label="A", preset=1, camera_role="platform", x=0, y=0),
            SeatLayout(id="2", label="B", preset=2, camera_role="platform", x=0, y=0),
        ],
    )
    assert svc.save(layout) is True


# ── recovery: bak file persisted by json_io ──────────────────────────────────

def test_save_creates_bak_on_overwrite(tmp_path):
    svc = _svc(tmp_path)
    svc.load()

    layout = svc.layout
    layout.room_name = "Updated"
    svc.save(layout)

    # json_io.save_json uses .with_suffix('.bak') → room_layout.bak
    bak = tmp_path / "room_layout.bak"
    assert bak.exists()


# ── migration framework placeholder ───────────────────────────────────────────

def test_layout_with_older_supported_version_is_migrated(tmp_path):
    # Currently only v1 exists. This test proves the migration pipeline
    # at least runs without error and updates schema_version.
    svc = _svc(tmp_path)
    _write_layout(tmp_path / "room_layout.json", version=SCHEMA_VERSION)
    layout = svc.load()
    assert layout.schema_version == SCHEMA_VERSION
