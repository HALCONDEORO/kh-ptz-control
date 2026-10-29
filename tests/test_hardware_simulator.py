#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_hardware_simulator.py — Tests for adapters/hardware_simulator.py

from __future__ import annotations


from adapters.hardware_simulator import SimCamera, handle_visca, _nibbles_to_bytes, _bytes_to_val


# ═══════════════════════════════════════════════════════════════════════════════
# SimCamera initial state
# ═══════════════════════════════════════════════════════════════════════════════

class TestSimCamera:
    def test_initial_zoom_zero(self):
        cam = SimCamera("test")
        assert cam.zoom == 0

    def test_initial_pan_zero(self):
        cam = SimCamera("test")
        assert cam.pan == 0

    def test_initial_tilt_zero(self):
        cam = SimCamera("test")
        assert cam.tilt == 0

    def test_initial_focus_auto(self):
        cam = SimCamera("test")
        assert cam.focus_auto is True

    def test_initial_backlight_off(self):
        cam = SimCamera("test")
        assert cam.backlight is False

    def test_initial_presets_empty(self):
        cam = SimCamera("test")
        assert cam.presets == {}

    def test_initial_cmd_count_zero(self):
        cam = SimCamera("test")
        assert cam.cmd_count == 0

    def test_name_stored(self):
        cam = SimCamera("cam1")
        assert cam.name == "cam1"

    def test_zoom_pct_zero_at_init(self):
        cam = SimCamera("test")
        assert cam.zoom_pct() == 0

    def test_zoom_pct_100_at_max(self):
        cam = SimCamera("test")
        cam.zoom = 0x4000
        assert cam.zoom_pct() == 100

    def test_zoom_pct_50_at_half(self):
        cam = SimCamera("test")
        cam.zoom = 0x2000
        assert cam.zoom_pct() == 50


# ═══════════════════════════════════════════════════════════════════════════════
# Nibble helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestNibbleHelpers:
    def test_nibbles_roundtrip_zero(self):
        assert _bytes_to_val(_nibbles_to_bytes(0), 0) == 0

    def test_nibbles_roundtrip_max(self):
        val = 0x4000
        assert _bytes_to_val(_nibbles_to_bytes(val), 0) == val

    def test_nibbles_roundtrip_arbitrary(self):
        for val in (1, 255, 0x1234, 0x3FFF, 0x4000):
            assert _bytes_to_val(_nibbles_to_bytes(val), 0) == val

    def test_nibbles_produces_four_bytes(self):
        assert len(_nibbles_to_bytes(0x1234)) == 4

    def test_nibbles_each_byte_low_nibble_only(self):
        for b in _nibbles_to_bytes(0xABCD):
            assert b <= 0x0F


# ═══════════════════════════════════════════════════════════════════════════════
# handle_visca — short / malformed frames
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleViscaMalformed:
    def test_empty_frame_returns_empty(self):
        cam = SimCamera("t")
        assert handle_visca(b"", cam) == b""

    def test_two_byte_frame_returns_empty(self):
        cam = SimCamera("t")
        assert handle_visca(b"\x81\xFF", cam) == b""

    def test_unknown_msg_type_returns_syntax_error(self):
        cam = SimCamera("t")
        resp = handle_visca(b"\x81\x05\x04\x00\xFF", cam)
        assert resp == bytes([0x90, 0x60, 0x02, 0xFF])

    def test_each_call_increments_cmd_count(self):
        cam = SimCamera("t")
        handle_visca(b"\x81\x01\x04\x07\xFF", cam)  # ZoomStop
        handle_visca(b"\x81\x01\x04\x07\xFF", cam)
        assert cam.cmd_count == 2


# ═══════════════════════════════════════════════════════════════════════════════
# handle_visca — inquiries (0x09)
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleViscaInquiries:
    def test_power_status_inquiry(self):
        cam = SimCamera("t")
        resp = handle_visca(b"\x81\x09\x04\x00\xFF", cam)
        assert resp == bytes([0x90, 0x50, 0x02, 0xFF])

    def test_zoom_inquiry_returns_current_zoom(self):
        cam = SimCamera("t")
        cam.zoom = 0x2000
        resp = handle_visca(b"\x81\x09\x04\x47\xFF", cam)
        assert resp[0] == 0x90
        assert resp[1] == 0x50
        decoded = _bytes_to_val(resp, 2)
        assert decoded == 0x2000

    def test_zoom_inquiry_zero(self):
        cam = SimCamera("t")
        resp = handle_visca(b"\x81\x09\x04\x47\xFF", cam)
        decoded = _bytes_to_val(resp, 2)
        assert decoded == 0

    def test_focus_mode_inquiry_auto(self):
        cam = SimCamera("t")
        cam.focus_auto = True
        resp = handle_visca(b"\x81\x09\x04\x38\xFF", cam)
        assert resp[2] == 0x02

    def test_focus_mode_inquiry_manual(self):
        cam = SimCamera("t")
        cam.focus_auto = False
        resp = handle_visca(b"\x81\x09\x04\x38\xFF", cam)
        assert resp[2] == 0x03

    def test_backlight_inquiry_off(self):
        cam = SimCamera("t")
        cam.backlight = False
        resp = handle_visca(b"\x81\x09\x04\x33\xFF", cam)
        assert resp[2] == 0x03

    def test_backlight_inquiry_on(self):
        cam = SimCamera("t")
        cam.backlight = True
        resp = handle_visca(b"\x81\x09\x04\x33\xFF", cam)
        assert resp[2] == 0x02

    def test_unknown_inquiry_returns_error(self):
        cam = SimCamera("t")
        resp = handle_visca(b"\x81\x09\x04\xFF\xFF", cam)
        assert resp == bytes([0x90, 0x60, 0x02, 0xFF])

    def test_ptz_position_inquiry_zero(self):
        cam = SimCamera("t")
        resp = handle_visca(b"\x81\x09\x06\x12\xFF", cam)
        assert resp[0] == 0x90
        assert resp[1] == 0x58
        pan_val = _bytes_to_val(resp, 2)
        tilt_val = _bytes_to_val(resp, 6)
        assert pan_val == 0
        assert tilt_val == 0


# ═══════════════════════════════════════════════════════════════════════════════
# handle_visca — zoom commands
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleViscaZoom:
    def _zoom_abs_frame(self, zoom_val: int) -> bytes:
        nibs = _nibbles_to_bytes(zoom_val)
        return bytes([0x81, 0x01, 0x04, 0x47]) + nibs + bytes([0xFF])

    def test_zoom_absolute_sets_zoom(self):
        cam = SimCamera("t")
        handle_visca(self._zoom_abs_frame(0x2000), cam)
        assert cam.zoom == 0x2000

    def test_zoom_absolute_returns_ack_comp(self):
        cam = SimCamera("t")
        resp = handle_visca(self._zoom_abs_frame(0x1000), cam)
        assert resp == bytes([0x90, 0x41, 0xFF, 0x90, 0x51, 0xFF])

    def test_zoom_stop_returns_ack_comp(self):
        cam = SimCamera("t")
        resp = handle_visca(b"\x81\x01\x04\x07\xFF", cam)
        assert resp == bytes([0x90, 0x41, 0xFF, 0x90, 0x51, 0xFF])

    def test_zoom_set_and_query_roundtrip(self):
        cam = SimCamera("t")
        handle_visca(self._zoom_abs_frame(0x3000), cam)
        resp = handle_visca(b"\x81\x09\x04\x47\xFF", cam)
        assert _bytes_to_val(resp, 2) == 0x3000


# ═══════════════════════════════════════════════════════════════════════════════
# handle_visca — pan/tilt commands
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleViscaPanTilt:
    def _pt_frame(self, pan_spd, tilt_spd, pan_dir, tilt_dir) -> bytes:
        return bytes([0x81, 0x01, 0x06, 0x01, pan_spd, tilt_spd, pan_dir, tilt_dir, 0xFF])

    def test_move_right_increases_pan(self):
        cam = SimCamera("t")
        handle_visca(self._pt_frame(5, 0, 0x02, 0x03), cam)
        assert cam.pan > 0

    def test_move_left_decreases_pan(self):
        cam = SimCamera("t")
        handle_visca(self._pt_frame(5, 0, 0x01, 0x03), cam)
        assert cam.pan < 0

    def test_move_up_increases_tilt(self):
        cam = SimCamera("t")
        handle_visca(self._pt_frame(0, 5, 0x03, 0x01), cam)
        assert cam.tilt > 0

    def test_move_down_decreases_tilt(self):
        cam = SimCamera("t")
        handle_visca(self._pt_frame(0, 5, 0x03, 0x02), cam)
        assert cam.tilt < 0

    def test_stop_clears_speeds(self):
        cam = SimCamera("t")
        handle_visca(self._pt_frame(5, 3, 0x02, 0x01), cam)
        handle_visca(self._pt_frame(0, 0, 0x03, 0x03), cam)
        assert cam.pan_spd == 0
        assert cam.tilt_spd == 0

    def test_move_returns_ack_comp(self):
        cam = SimCamera("t")
        resp = handle_visca(self._pt_frame(3, 3, 0x01, 0x02), cam)
        assert resp == bytes([0x90, 0x41, 0xFF, 0x90, 0x51, 0xFF])

    def test_home_resets_pan_tilt(self):
        cam = SimCamera("t")
        cam.pan = 100
        cam.tilt = -50
        handle_visca(b"\x81\x01\x06\x04\xFF", cam)
        assert cam.pan == 0
        assert cam.tilt == 0

    def test_home_returns_ack_comp(self):
        cam = SimCamera("t")
        resp = handle_visca(b"\x81\x01\x06\x04\xFF", cam)
        assert resp == bytes([0x90, 0x41, 0xFF, 0x90, 0x51, 0xFF])


# ═══════════════════════════════════════════════════════════════════════════════
# handle_visca — preset recall / save
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleViscaPresets:
    def _save_frame(self, preset: int) -> bytes:
        return bytes([0x81, 0x01, 0x04, 0x3F, 0x01, preset, 0xFF])

    def _recall_frame(self, preset: int) -> bytes:
        return bytes([0x81, 0x01, 0x04, 0x3F, 0x02, preset, 0xFF])

    def test_save_stores_position(self):
        cam = SimCamera("t")
        cam.zoom = 0x1000
        cam.pan = 50
        cam.tilt = -20
        handle_visca(self._save_frame(3), cam)
        assert 3 in cam.presets
        assert cam.presets[3] == (0x1000, 50, -20)

    def test_recall_restores_position(self):
        cam = SimCamera("t")
        cam.presets[5] = (0x2000, 30, 10)
        handle_visca(self._recall_frame(5), cam)
        assert cam.zoom == 0x2000
        assert cam.pan == 30
        assert cam.tilt == 10

    def test_recall_unknown_preset_leaves_state_unchanged(self):
        cam = SimCamera("t")
        cam.zoom = 0x1111
        handle_visca(self._recall_frame(99), cam)
        assert cam.zoom == 0x1111

    def test_save_returns_ack_comp(self):
        cam = SimCamera("t")
        resp = handle_visca(self._save_frame(1), cam)
        assert resp == bytes([0x90, 0x41, 0xFF, 0x90, 0x51, 0xFF])

    def test_recall_returns_ack_comp(self):
        cam = SimCamera("t")
        cam.presets[1] = (0, 0, 0)
        resp = handle_visca(self._recall_frame(1), cam)
        assert resp == bytes([0x90, 0x41, 0xFF, 0x90, 0x51, 0xFF])

    def test_save_then_recall_roundtrip(self):
        cam = SimCamera("t")
        cam.zoom = 0x3000
        cam.pan = -100
        cam.tilt = 200
        handle_visca(self._save_frame(7), cam)
        cam.zoom = 0
        cam.pan = 0
        cam.tilt = 0
        handle_visca(self._recall_frame(7), cam)
        assert cam.zoom == 0x3000
        assert cam.pan == -100
        assert cam.tilt == 200


# ═══════════════════════════════════════════════════════════════════════════════
# handle_visca — focus commands
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleViscaFocus:
    def test_set_focus_auto(self):
        cam = SimCamera("t")
        cam.focus_auto = False
        handle_visca(b"\x81\x01\x04\x38\x02\xFF", cam)
        assert cam.focus_auto is True

    def test_set_focus_manual(self):
        cam = SimCamera("t")
        cam.focus_auto = True
        handle_visca(b"\x81\x01\x04\x38\x03\xFF", cam)
        assert cam.focus_auto is False

    def test_focus_onepush_returns_ack_comp(self):
        cam = SimCamera("t")
        resp = handle_visca(b"\x81\x01\x04\x18\xFF", cam)
        assert resp == bytes([0x90, 0x41, 0xFF, 0x90, 0x51, 0xFF])


# ═══════════════════════════════════════════════════════════════════════════════
# handle_visca — backlight and brightness
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleViscaBacklightBrightness:
    def test_backlight_on(self):
        cam = SimCamera("t")
        handle_visca(b"\x81\x01\x04\x33\x02\xFF", cam)
        assert cam.backlight is True

    def test_backlight_off(self):
        cam = SimCamera("t")
        cam.backlight = True
        handle_visca(b"\x81\x01\x04\x33\x03\xFF", cam)
        assert cam.backlight is False

    def test_brightness_up_increments(self):
        cam = SimCamera("t")
        handle_visca(b"\x81\x01\x04\x0E\x02\xFF", cam)
        assert cam.exposure == 1

    def test_brightness_down_decrements(self):
        cam = SimCamera("t")
        handle_visca(b"\x81\x01\x04\x0E\x03\xFF", cam)
        assert cam.exposure == -1


# ═══════════════════════════════════════════════════════════════════════════════
# handle_visca — set address / IF_Clear (broadcast frames)
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleViscaBroadcast:
    def test_set_address_response(self):
        cam = SimCamera("t")
        resp = handle_visca(b"\x88\x01\x30\x01\xFF", cam)
        assert resp == bytes([0x90, 0x30, 0x02, 0xFF])

    def test_if_clear_response(self):
        cam = SimCamera("t")
        resp = handle_visca(b"\x88\x01\x01\x00\xFF", cam)
        assert resp == bytes([0x90, 0x01, 0xFF])

