#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_domain.py — Tests de los modelos de dominio (lógica pura, sin I/O).
"""

import pytest
from domain.camera import Camera
from domain.seat import Seat
from domain.preset import (
    PRESET_SLOT_MIN, PRESET_SLOT_MAX,
    PRESET_CHAIRMAN_GENERIC, PRESET_LEFT, PRESET_RIGHT, PRESET_PLATFORM_2,
    PLATFORM_PRESETS,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Camera
# ═══════════════════════════════════════════════════════════════════════════════

class TestCamera:

    def _make(self, index=1, ip="10.0.0.1", cam_id="81", label="Platform"):
        return Camera(index=index, ip=ip, cam_id=cam_id, label=label)

    def test_fields_accessible(self):
        cam = self._make()
        assert cam.index == 1
        assert cam.ip == "10.0.0.1"
        assert cam.cam_id == "81"
        assert cam.label == "Platform"

    def test_equality(self):
        a = self._make()
        b = self._make()
        assert a == b

    def test_inequality_by_ip(self):
        a = self._make(ip="10.0.0.1")
        b = self._make(ip="10.0.0.2")
        assert a != b

    def test_inequality_by_index(self):
        assert self._make(index=1) != self._make(index=2)

    def test_immutable(self):
        cam = self._make()
        with pytest.raises(AttributeError):  # FrozenInstanceError hereda de AttributeError
            cam.ip = "9.9.9.9"

    def test_hashable(self):
        cam = self._make()
        s = {cam}
        assert cam in s

    def test_two_cameras_in_set(self):
        cam1 = self._make(index=1, ip="10.0.0.1", cam_id="81", label="Platform")
        cam2 = self._make(index=2, ip="10.0.0.2", cam_id="82", label="Comments")
        assert len({cam1, cam2}) == 2

    def test_repr_contains_ip(self):
        cam = self._make(ip="172.16.1.11")
        assert "172.16.1.11" in repr(cam)


# ═══════════════════════════════════════════════════════════════════════════════
#  Seat
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeat:

    def test_name_defaults_to_none(self):
        seat = Seat(number=1, x=100, y=200)
        assert seat.name is None

    def test_name_can_be_set(self):
        seat = Seat(number=3, x=50, y=75, name="PersonA")
        assert seat.name == "PersonA"

    def test_equality_without_name(self):
        assert Seat(1, 10, 20) == Seat(1, 10, 20)

    def test_equality_with_name(self):
        assert Seat(1, 10, 20, "PersonA") == Seat(1, 10, 20, "PersonA")

    def test_inequality_different_name(self):
        assert Seat(1, 10, 20, "PersonA") != Seat(1, 10, 20, "PersonB")

    def test_inequality_different_position(self):
        assert Seat(1, 10, 20) != Seat(1, 10, 21)

    def test_immutable(self):
        seat = Seat(1, 10, 20, "PersonA")
        with pytest.raises(AttributeError):
            seat.name = "PersonB"

    def test_hashable(self):
        seat = Seat(1, 10, 20, "PersonA")
        assert seat in {seat}

    def test_unicode_name(self):
        seat = Seat(2, 30, 40, name="María José")
        assert seat.name == "María José"


# ═══════════════════════════════════════════════════════════════════════════════
#  Preset constants
# ═══════════════════════════════════════════════════════════════════════════════

class TestPresetConstants:

    def test_slot_range(self):
        assert PRESET_SLOT_MIN == 10
        assert PRESET_SLOT_MAX == 89

    def test_min_less_than_max(self):
        assert PRESET_SLOT_MIN < PRESET_SLOT_MAX

    def test_capacity(self):
        # Hay 80 slots disponibles (10 a 89 inclusive)
        assert PRESET_SLOT_MAX - PRESET_SLOT_MIN + 1 == 80

    def test_platform_preset_values(self):
        assert PRESET_CHAIRMAN_GENERIC == 1
        assert PRESET_LEFT == 2
        assert PRESET_RIGHT == 3
        assert PRESET_PLATFORM_2 == 132

    def test_platform_presets_frozenset(self):
        assert isinstance(PLATFORM_PRESETS, frozenset)
        assert PLATFORM_PRESETS == {1, 2, 3, 132}

    def test_platform_presets_outside_personal_range(self):
        # Los presets de plataforma no deben colisionar con el rango personal
        for p in PLATFORM_PRESETS:
            assert not (PRESET_SLOT_MIN <= p <= PRESET_SLOT_MAX)

    def test_personal_range_does_not_overlap_platform(self):
        # Verifica que ningún preset de plataforma puede colisionar con uno personal
        personal_range = set(range(PRESET_SLOT_MIN, PRESET_SLOT_MAX + 1))
        assert PLATFORM_PRESETS.isdisjoint(personal_range)
