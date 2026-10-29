#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_visca_errors_types.py — Contract tests for ptz/visca/errors.py and ptz/visca/types.py

from __future__ import annotations

import pytest

from ptz.visca.errors import ViscaError, ViscaNetworkError, ViscaParseError
from ptz.visca.types import ZOOM_MAX, PanDir, TiltDir


# ═══════════════════════════════════════════════════════════════════════════════
# Exception hierarchy
# ═══════════════════════════════════════════════════════════════════════════════

class TestViscaErrorHierarchy:
    def test_visca_error_is_exception(self):
        assert issubclass(ViscaError, Exception)

    def test_network_error_is_visca_error(self):
        assert issubclass(ViscaNetworkError, ViscaError)

    def test_parse_error_is_visca_error(self):
        assert issubclass(ViscaParseError, ViscaError)

    def test_network_and_parse_are_distinct_types(self):
        assert ViscaNetworkError is not ViscaParseError

    def test_network_error_not_subclass_of_parse_error(self):
        assert not issubclass(ViscaNetworkError, ViscaParseError)

    def test_parse_error_not_subclass_of_network_error(self):
        assert not issubclass(ViscaParseError, ViscaNetworkError)


class TestViscaErrorRaising:
    def test_visca_error_can_be_raised_and_caught(self):
        with pytest.raises(ViscaError, match="base error"):
            raise ViscaError("base error")

    def test_network_error_caught_as_visca_error(self):
        with pytest.raises(ViscaError):
            raise ViscaNetworkError("connection lost")

    def test_parse_error_caught_as_visca_error(self):
        with pytest.raises(ViscaError):
            raise ViscaParseError("unexpected byte sequence")

    def test_network_error_not_caught_as_parse_error(self):
        with pytest.raises(ViscaNetworkError):
            try:
                raise ViscaNetworkError("timeout")
            except ViscaParseError:
                pytest.fail("ViscaNetworkError should not be caught by ViscaParseError handler")

    def test_parse_error_not_caught_as_network_error(self):
        with pytest.raises(ViscaParseError):
            try:
                raise ViscaParseError("bad frame")
            except ViscaNetworkError:
                pytest.fail("ViscaParseError should not be caught by ViscaNetworkError handler")

    def test_message_preserved_in_network_error(self):
        exc = ViscaNetworkError("timeout after 3s")
        assert "timeout after 3s" in str(exc)

    def test_message_preserved_in_parse_error(self):
        exc = ViscaParseError("got 0xFF, expected 0x90")
        assert "0xFF" in str(exc)
        assert "0x90" in str(exc)


# ═══════════════════════════════════════════════════════════════════════════════
# PanDir
# ═══════════════════════════════════════════════════════════════════════════════

class TestPanDir:
    def test_left_value_is_0x01(self):
        assert PanDir.LEFT == 0x01

    def test_right_value_is_0x02(self):
        assert PanDir.RIGHT == 0x02

    def test_stop_value_is_0x03(self):
        assert PanDir.STOP == 0x03

    def test_left_and_right_are_distinct(self):
        assert PanDir.LEFT != PanDir.RIGHT

    def test_stop_differs_from_left(self):
        assert PanDir.STOP != PanDir.LEFT

    def test_stop_differs_from_right(self):
        assert PanDir.STOP != PanDir.RIGHT

    def test_all_values_fit_in_single_visca_byte(self):
        for direction in PanDir:
            assert 0x00 <= int(direction) <= 0xFF

    def test_three_members(self):
        assert len(list(PanDir)) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# TiltDir
# ═══════════════════════════════════════════════════════════════════════════════

class TestTiltDir:
    def test_up_value_is_0x01(self):
        assert TiltDir.UP == 0x01

    def test_down_value_is_0x02(self):
        assert TiltDir.DOWN == 0x02

    def test_stop_value_is_0x03(self):
        assert TiltDir.STOP == 0x03

    def test_up_and_down_are_distinct(self):
        assert TiltDir.UP != TiltDir.DOWN

    def test_stop_differs_from_up(self):
        assert TiltDir.STOP != TiltDir.UP

    def test_stop_differs_from_down(self):
        assert TiltDir.STOP != TiltDir.DOWN

    def test_all_values_fit_in_single_visca_byte(self):
        for direction in TiltDir:
            assert 0x00 <= int(direction) <= 0xFF

    def test_three_members(self):
        assert len(list(TiltDir)) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# Pan / Tilt symmetry (VISCA protocol encodes both axes in the same command)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPanTiltSymmetry:
    def test_stop_byte_is_same_for_both_axes(self):
        assert int(PanDir.STOP) == int(TiltDir.STOP)

    def test_same_number_of_members(self):
        assert len(list(PanDir)) == len(list(TiltDir))


# ═══════════════════════════════════════════════════════════════════════════════
# ZOOM_MAX
# ═══════════════════════════════════════════════════════════════════════════════

class TestZoomMax:
    def test_value_is_0x4000(self):
        assert ZOOM_MAX == 0x4000

    def test_value_is_16384_decimal(self):
        assert ZOOM_MAX == 16384

    def test_is_int(self):
        assert isinstance(ZOOM_MAX, int)

    def test_is_positive(self):
        assert ZOOM_MAX > 0

    def test_fits_in_two_bytes(self):
        assert ZOOM_MAX <= 0xFFFF
