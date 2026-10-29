#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/room_layout.py — Room layout domain models
#
# Pure data structures — no I/O, no Qt, no network.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


SCHEMA_VERSION = 1


@dataclass
class SeatLayout:
    """Persistent layout record for one seat button."""
    id: str
    label: str
    preset: int
    camera_role: str
    x: int
    y: int
    row: Optional[int] = None
    column: Optional[int] = None
    type: str = "delegate"
    visible: bool = True
    locked: bool = False
    calibrated: bool = False


@dataclass
class RoomLayout:
    """Complete room layout — one file per customer site."""
    schema_version: int
    room_id: str
    room_name: str
    screen_width: int
    screen_height: int
    seats: List[SeatLayout] = field(default_factory=list)

    def visible_seats(self) -> list[SeatLayout]:
        return [s for s in self.seats if s.visible]

    def seat_by_id(self, seat_id: str) -> Optional[SeatLayout]:
        for s in self.seats:
            if s.id == seat_id:
                return s
        return None
