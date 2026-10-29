# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for domain/layout_scaling.py (#257)."""
from __future__ import annotations


from domain.layout_scaling import (
    ScaledSeat,
    offscreen_seats,
    resolution_mismatch_warning,
    scale_layout,
    scale_point_to_canonical,
    scale_point_to_window,
)
from domain.room_layout import RoomLayout, SeatLayout


# ── Helpers ───────────────────────────────────────────────────────────────────

def _layout(seats=None, w=1440, h=1080) -> RoomLayout:
    return RoomLayout(
        schema_version=1,
        room_id="test",
        room_name="Test Room",
        screen_width=w,
        screen_height=h,
        seats=seats or [],
    )


def _seat(sid="A1", x=100, y=200, visible=True) -> SeatLayout:
    return SeatLayout(
        id=sid, label=sid, preset=1, camera_role="platform",
        x=x, y=y, visible=visible,
    )


# ── scale_point_to_window ─────────────────────────────────────────────────────

class TestScalePointToWindow:
    def test_identity_when_same_size(self):
        assert scale_point_to_window(100, 200, 1440, 1080, 1440, 1080) == (100, 200)

    def test_half_scale(self):
        # Window is half the canonical size → coordinates halved
        x, y = scale_point_to_window(100, 200, 1440, 1080, 720, 540)
        assert x == 50
        assert y == 100

    def test_double_scale(self):
        x, y = scale_point_to_window(100, 200, 1440, 1080, 2880, 2160)
        assert x == 200
        assert y == 400

    def test_uniform_scale_uses_min_ratio(self):
        # Width ratio = 2.0, height ratio = 1.5 → scale = 1.5
        x, y = scale_point_to_window(100, 100, 1000, 1000, 2000, 1500)
        assert x == 150
        assert y == 150

    def test_zero_canonical_returns_input(self):
        assert scale_point_to_window(50, 50, 0, 0, 800, 600) == (50, 50)

    def test_corner_origin(self):
        assert scale_point_to_window(0, 0, 1440, 1080, 720, 540) == (0, 0)

    def test_corner_opposite(self):
        x, y = scale_point_to_window(1440, 1080, 1440, 1080, 720, 540)
        assert x == 720
        assert y == 540


# ── scale_point_to_canonical ──────────────────────────────────────────────────

class TestScalePointToCanonical:
    def test_identity_when_same_size(self):
        assert scale_point_to_canonical(100, 200, 1440, 1080, 1440, 1080) == (100, 200)

    def test_half_window_doubles_canonical(self):
        # Window is half canonical → canonical coordinates are doubled
        x, y = scale_point_to_canonical(50, 100, 1440, 1080, 720, 540)
        assert x == 100
        assert y == 200

    def test_roundtrip(self):
        cx, cy = 350, 780
        can_w, can_h = 1440, 1080
        win_w, win_h = 800, 600
        wx, wy = scale_point_to_window(cx, cy, can_w, can_h, win_w, win_h)
        rx, ry = scale_point_to_canonical(wx, wy, can_w, can_h, win_w, win_h)
        assert abs(rx - cx) <= 1
        assert abs(ry - cy) <= 1

    def test_zero_window_returns_input(self):
        assert scale_point_to_canonical(50, 50, 1440, 1080, 0, 0) == (50, 50)


# ── scale_layout ──────────────────────────────────────────────────────────────

class TestScaleLayout:
    def test_returns_scaled_seats(self):
        layout = _layout(seats=[_seat("A1", x=720, y=540)])
        result = scale_layout(layout, window_w=720, window_h=540)
        assert len(result) == 1
        assert isinstance(result[0], ScaledSeat)
        assert result[0].x == 360
        assert result[0].y == 270

    def test_hidden_seats_excluded(self):
        layout = _layout(seats=[_seat("A1", visible=True), _seat("A2", visible=False)])
        result = scale_layout(layout, window_w=1440, window_h=1080)
        assert len(result) == 1
        assert result[0].seat.id == "A1"

    def test_same_size_no_change(self):
        layout = _layout(seats=[_seat("A1", x=100, y=200)])
        result = scale_layout(layout, window_w=1440, window_h=1080)
        assert result[0].x == 100
        assert result[0].y == 200

    def test_empty_layout(self):
        assert scale_layout(_layout(), window_w=1440, window_h=1080) == []

    def test_multiple_seats(self):
        seats = [_seat(f"A{i}", x=i * 100, y=i * 50) for i in range(3)]
        layout = _layout(seats=seats)
        result = scale_layout(layout, window_w=720, window_h=540)
        # Each coordinate should be halved (scale = 0.5)
        for i, scaled in enumerate(result):
            assert scaled.x == round(i * 100 * 0.5)
            assert scaled.y == round(i * 50 * 0.5)


# ── offscreen_seats ───────────────────────────────────────────────────────────

class TestOffscreenSeats:
    def test_in_bounds_seat_not_reported(self):
        layout = _layout(seats=[_seat("A1", x=100, y=100)])
        assert offscreen_seats(layout) == []

    def test_seat_at_boundary_not_reported(self):
        layout = _layout(seats=[_seat("A1", x=1440, y=1080)])
        assert offscreen_seats(layout) == []

    def test_seat_just_outside_boundary_not_reported(self):
        # Within default margin (50px)
        layout = _layout(seats=[_seat("A1", x=1450, y=100)])
        assert offscreen_seats(layout) == []

    def test_seat_far_outside_boundary_reported(self):
        layout = _layout(seats=[_seat("A1", x=1600, y=100)])
        assert offscreen_seats(layout) == ["A1"]

    def test_negative_far_seat_reported(self):
        layout = _layout(seats=[_seat("A1", x=-100, y=100)])
        assert offscreen_seats(layout) == ["A1"]

    def test_custom_margin_zero(self):
        layout = _layout(seats=[_seat("A1", x=1441, y=100)])
        assert offscreen_seats(layout, margin=0) == ["A1"]

    def test_multiple_offscreen(self):
        seats = [_seat("A1", x=2000, y=100), _seat("A2", x=100, y=2000)]
        layout = _layout(seats=seats)
        bad = offscreen_seats(layout)
        assert set(bad) == {"A1", "A2"}

    def test_mix_in_and_out(self):
        seats = [_seat("A1", x=100, y=100), _seat("A2", x=5000, y=100)]
        layout = _layout(seats=seats)
        assert offscreen_seats(layout) == ["A2"]

    def test_hidden_seats_are_still_checked(self):
        layout = _layout(seats=[_seat("A1", x=5000, y=100, visible=False)])
        assert offscreen_seats(layout) == ["A1"]


# ── resolution_mismatch_warning ───────────────────────────────────────────────

class TestResolutionMismatchWarning:
    def test_no_warning_when_same_size(self):
        layout = _layout(w=1440, h=1080)
        assert resolution_mismatch_warning(layout, 1440, 1080) == ""

    def test_warning_when_different_width(self):
        layout = _layout(w=1920, h=1080)
        msg = resolution_mismatch_warning(layout, 1440, 1080)
        assert "1920×1080" in msg
        assert "1440×1080" in msg

    def test_warning_mentions_coordinate_system(self):
        layout = _layout(w=1920, h=1080)
        msg = resolution_mismatch_warning(layout, 800, 600)
        assert "coordinate" in msg.lower() or "original" in msg.lower()

    def test_warning_when_different_height(self):
        layout = _layout(w=1440, h=900)
        msg = resolution_mismatch_warning(layout, 1440, 1080)
        assert msg != ""


# ── LayoutService integration ─────────────────────────────────────────────────

class TestLayoutServiceOffscreen:
    def test_offscreen_seat_ids_empty(self, tmp_path):
        from application.layout_service import LayoutService
        svc = LayoutService(layout_path=tmp_path / "layout.json", legacy_positions=None)
        svc.load()
        assert svc.offscreen_seat_ids() == []

    def test_offscreen_seat_ids_detects_bad_seat(self, tmp_path):
        import json
        layout_file = tmp_path / "layout.json"
        layout_file.write_text(json.dumps({
            "schema_version": 1,
            "room_id": "test", "room_name": "Test",
            "screen_width": 1440, "screen_height": 1080,
            "seats": [
                {"id": "A1", "label": "A1", "preset": 1, "camera_role": "platform",
                 "x": 5000, "y": 100, "visible": True, "locked": False, "calibrated": False,
                 "type": "delegate"},
            ],
        }), encoding="utf-8")
        from application.layout_service import LayoutService
        svc = LayoutService(layout_path=layout_file, legacy_positions=None)
        svc.load()
        assert svc.offscreen_seat_ids() == ["A1"]
