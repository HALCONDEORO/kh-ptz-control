#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/layout_scaling.py — Canonical coordinate scaling for room layouts
#
# All seat positions are stored in canonical coordinates (the layout's own
# screen_width × screen_height).  These functions convert between canonical
# and actual window coordinates at render time, and back again when saving
# a drag-edited position.
#
# No Qt, no I/O.

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from domain.room_layout import RoomLayout, SeatLayout

# Seats more than this many canonical pixels outside the layout boundary
# are considered off-screen (not just touching the edge).
OFFSCREEN_MARGIN = 50


@dataclass(frozen=True)
class ScaledSeat:
    """A seat with its position already converted to window pixels."""
    seat: SeatLayout
    x: int
    y: int


def scale_point_to_window(
    cx: int,
    cy: int,
    canonical_w: int,
    canonical_h: int,
    window_w: int,
    window_h: int,
) -> Tuple[int, int]:
    """
    Convert a canonical (layout) coordinate to window pixels.

    Scaling is uniform — the same ratio is used for both axes so that the
    layout aspect ratio is preserved.  The layout is anchored to (0, 0).
    """
    if canonical_w <= 0 or canonical_h <= 0:
        return cx, cy
    scale = min(window_w / canonical_w, window_h / canonical_h)
    return round(cx * scale), round(cy * scale)


def scale_point_to_canonical(
    wx: int,
    wy: int,
    canonical_w: int,
    canonical_h: int,
    window_w: int,
    window_h: int,
) -> Tuple[int, int]:
    """
    Convert a window-pixel coordinate back to canonical (layout) coordinates.

    Inverse of scale_point_to_window.  Used when saving a drag-edited position
    so that edits made on a scaled display are stored at the correct scale.
    """
    if window_w <= 0 or window_h <= 0:
        return wx, wy
    scale = min(window_w / canonical_w, window_h / canonical_h)
    if scale == 0:
        return wx, wy
    return round(wx / scale), round(wy / scale)


def scale_layout(
    layout: RoomLayout,
    window_w: int,
    window_h: int,
) -> List[ScaledSeat]:
    """
    Return all visible seats with positions converted to window pixels.

    The caller uses these to position seat widgets at render time.
    """
    can_w = layout.screen_width
    can_h = layout.screen_height
    result: List[ScaledSeat] = []
    for seat in layout.visible_seats():
        wx, wy = scale_point_to_window(seat.x, seat.y, can_w, can_h, window_w, window_h)
        result.append(ScaledSeat(seat=seat, x=wx, y=wy))
    return result


def offscreen_seats(layout: RoomLayout, margin: int = OFFSCREEN_MARGIN) -> List[str]:
    """
    Return IDs of seats that fall outside the canonical boundary.

    A seat is considered off-screen if its position is more than *margin*
    pixels outside [0, screen_width] × [0, screen_height].  The caller
    should warn the installer before saving.

    Returns a list of seat IDs (empty list = all seats are within bounds).
    """
    can_w = layout.screen_width
    can_h = layout.screen_height
    bad: List[str] = []
    for seat in layout.seats:
        if (
            seat.x < -margin
            or seat.y < -margin
            or seat.x > can_w + margin
            or seat.y > can_h + margin
        ):
            bad.append(seat.id)
    return bad


def resolution_mismatch_warning(
    layout: RoomLayout,
    window_w: int,
    window_h: int,
) -> str:
    """
    Return a human-readable warning string if the window size differs from
    the canonical size stored in the layout, or an empty string if they match.

    Used when displaying an imported layout from a different screen.
    """
    can_w = layout.screen_width
    can_h = layout.screen_height
    if can_w == window_w and can_h == window_h:
        return ""
    return (
        f"Layout was created for {can_w}×{can_h}. "
        f"Displaying scaled to {window_w}×{window_h}. "
        "Drag edits will save in the original coordinate system."
    )
