#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_layout_service.py — LayoutService unit tests

from __future__ import annotations

import json
from pathlib import Path

import pytest

from application.layout_service import LayoutService, LayoutError
from domain.room_layout import RoomLayout, SeatLayout, SCHEMA_VERSION


# ── Fixtures ──────────────────────────────────────────────────────────────────

_LEGACY = {
    1: (100, 200),
    2: (200, 200),
    3: (300, 300),
}


def _service(tmp_path: Path, legacy=_LEGACY) -> LayoutService:
    return LayoutService(
        layout_path=tmp_path / "room_layout.json",
        legacy_positions=legacy,
    )


# ── domain models ────────────────────────────────────────────────────────────

def test_seat_layout_defaults():
    s = SeatLayout(id="1", label="1", preset=1, camera_role="platform", x=10, y=20)
    assert s.visible is True
    assert s.locked is False
    assert s.calibrated is False
    assert s.type == "delegate"


def test_room_layout_visible_seats():
    seats = [
        SeatLayout(id="1", label="1", preset=1, camera_role="platform", x=0, y=0, visible=True),
        SeatLayout(id="2", label="2", preset=2, camera_role="platform", x=0, y=0, visible=False),
    ]
    layout = RoomLayout(
        schema_version=SCHEMA_VERSION,
        room_id="r", room_name="n",
        screen_width=1440, screen_height=1080, seats=seats,
    )
    assert len(layout.visible_seats()) == 1
    assert layout.visible_seats()[0].id == "1"


def test_room_layout_seat_by_id():
    seats = [SeatLayout(id="42", label="42", preset=42, camera_role="platform", x=0, y=0)]
    layout = RoomLayout(
        schema_version=SCHEMA_VERSION, room_id="r", room_name="n",
        screen_width=1440, screen_height=1080, seats=seats,
    )
    assert layout.seat_by_id("42").id == "42"
    assert layout.seat_by_id("99") is None


# ── load: missing file → generate default ────────────────────────────────────

def test_load_creates_file_when_missing(tmp_path):
    svc = _service(tmp_path)
    layout_path = tmp_path / "room_layout.json"

    layout = svc.load()

    assert layout_path.exists()
    assert isinstance(layout, RoomLayout)


def test_load_generates_seats_from_legacy(tmp_path):
    svc = _service(tmp_path)
    layout = svc.load()

    assert len(layout.seats) == len(_LEGACY)
    ids = {s.id for s in layout.seats}
    assert "1" in ids and "2" in ids and "3" in ids


def test_load_preserves_legacy_coordinates(tmp_path):
    svc = _service(tmp_path)
    layout = svc.load()

    seat1 = layout.seat_by_id("1")
    assert seat1.x == 100
    assert seat1.y == 200


def test_load_sets_schema_version_and_room_fields(tmp_path):
    svc = _service(tmp_path)
    layout = svc.load()

    assert layout.schema_version == SCHEMA_VERSION
    assert layout.room_id == "default"
    assert layout.room_name == "Main Chamber"
    assert layout.screen_width == 1440
    assert layout.screen_height == 1080


def test_load_no_legacy_creates_empty_layout(tmp_path):
    svc = LayoutService(layout_path=tmp_path / "room_layout.json", legacy_positions={})
    layout = svc.load()

    assert layout.seats == []


# ── load: file present ────────────────────────────────────────────────────────

def test_load_reads_existing_file(tmp_path):
    svc = _service(tmp_path)
    path = tmp_path / "room_layout.json"
    data = {
        "schema_version": 1,
        "room_id": "hall_a",
        "room_name": "Hall A",
        "screen_width": 1920,
        "screen_height": 1080,
        "seats": [
            {
                "id": "99", "label": "99", "preset": 99,
                "camera_role": "comments",
                "x": 500, "y": 300,
                "row": None, "column": None,
                "type": "delegate", "visible": True, "locked": False, "calibrated": True,
            }
        ],
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    layout = svc.load()

    assert layout.room_id == "hall_a"
    assert layout.room_name == "Hall A"
    assert len(layout.seats) == 1
    assert layout.seats[0].id == "99"
    assert layout.seats[0].calibrated is True


def test_load_keeps_label_preset_and_camera_role_decoupled(tmp_path):
    svc = _service(tmp_path)
    path = tmp_path / "room_layout.json"
    data = {
        "schema_version": 1,
        "room_id": "hall_a",
        "room_name": "Hall A",
        "screen_width": 1920,
        "screen_height": 1080,
        "seats": [
            {
                "id": "seat_037", "label": "Delegate A", "preset": 37,
                "camera_role": "comments",
                "x": 500, "y": 300,
                "row": None, "column": None,
                "type": "delegate", "visible": True, "locked": False, "calibrated": True,
            }
        ],
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    layout = svc.load()
    seat = layout.seat_by_id("seat_037")

    assert seat.label == "Delegate A"
    assert seat.preset == 37
    assert seat.camera_role == "comments"


def test_load_corrupt_file_recovers_to_default(tmp_path):
    svc = _service(tmp_path)
    (tmp_path / "room_layout.json").write_text("NOT JSON {{{", encoding="utf-8")
    layout = svc.load()
    assert svc.recovery_used is True
    assert len(layout.seats) == len(_LEGACY)


def test_load_non_dict_recovers_to_default(tmp_path):
    svc = _service(tmp_path)
    (tmp_path / "room_layout.json").write_text("[1, 2, 3]", encoding="utf-8")
    layout = svc.load()
    assert svc.recovery_used is True
    assert len(layout.seats) == len(_LEGACY)


# ── save ─────────────────────────────────────────────────────────────────────

def test_save_persists_layout(tmp_path):
    svc = _service(tmp_path)
    layout = svc.load()
    layout.room_name = "Updated Room"

    ok = svc.save(layout)

    assert ok is True
    data = json.loads((tmp_path / "room_layout.json").read_text(encoding="utf-8"))
    assert data["room_name"] == "Updated Room"


def test_save_includes_all_seat_fields(tmp_path):
    svc = _service(tmp_path)
    layout = svc.load()
    ok = svc.save(layout)

    assert ok is True
    data = json.loads((tmp_path / "room_layout.json").read_text(encoding="utf-8"))
    seat = data["seats"][0]
    for field in ("id", "label", "preset", "camera_role", "x", "y",
                  "type", "visible", "locked", "calibrated"):
        assert field in seat


# ── visible_seats / seat_by_id before load ───────────────────────────────────

def test_visible_seats_before_load_raises(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(LayoutError, match="not loaded"):
        svc.visible_seats()


def test_seat_by_id_before_load_raises(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(LayoutError, match="not loaded"):
        svc.seat_by_id("1")


# ── visible_seats after load ──────────────────────────────────────────────────

def test_visible_seats_returns_all_default_seats(tmp_path):
    svc = _service(tmp_path)
    svc.load()
    assert len(svc.visible_seats()) == len(_LEGACY)


# ── update_seat_position ──────────────────────────────────────────────────────

def test_update_seat_position_persists(tmp_path):
    svc = _service(tmp_path)
    svc.load()

    updated = svc.update_seat_position("1", x=999, y=888)

    assert updated is True
    data = json.loads((tmp_path / "room_layout.json").read_text(encoding="utf-8"))
    seat = next(s for s in data["seats"] if s["id"] == "1")
    assert seat["x"] == 999
    assert seat["y"] == 888


def test_update_seat_position_unknown_id_returns_false(tmp_path):
    svc = _service(tmp_path)
    svc.load()
    assert svc.update_seat_position("NONEXISTENT", x=0, y=0) is False


def test_update_seat_position_preserves_other_fields(tmp_path):
    svc = _service(tmp_path)
    svc.load()
    original = svc.seat_by_id("1")
    svc.update_seat_position("1", x=111, y=222)
    updated = svc.seat_by_id("1")
    assert updated.label == original.label
    assert updated.preset == original.preset
    assert updated.camera_role == original.camera_role


# ── regeneration after deletion ───────────────────────────────────────────────

def test_delete_layout_file_regenerates_from_legacy(tmp_path):
    svc = _service(tmp_path)
    layout_path = tmp_path / "room_layout.json"

    svc.load()
    assert layout_path.exists()

    layout_path.unlink()
    layout2 = svc.load()

    assert layout_path.exists()
    assert len(layout2.seats) == len(_LEGACY)


# ── data_paths integration ────────────────────────────────────────────────────

def test_room_layout_file_in_data_paths():
    from data_paths import ROOM_LAYOUT_FILE
    assert ROOM_LAYOUT_FILE.name == "room_layout.json"
