#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_visca_pure.py — Tests unitarios para ptz.visca.commands y ptz.visca.parser
#
# No requiere Qt ni red: todo es lógica pura sobre bytes.
# Ejecutar con:   pytest tests/test_visca_pure.py -v

from __future__ import annotations


from ptz.visca.types import PanDir, TiltDir, ZOOM_MAX
from ptz.visca import commands as vcmd, parser as vparse


# ─────────────────────────────────────────────────────────────────────────────
#  types
# ─────────────────────────────────────────────────────────────────────────────

class TestTypes:
    def test_pan_dir_values(self):
        assert PanDir.LEFT  == 0x01
        assert PanDir.RIGHT == 0x02
        assert PanDir.STOP  == 0x03

    def test_tilt_dir_values(self):
        assert TiltDir.UP   == 0x01
        assert TiltDir.DOWN == 0x02
        assert TiltDir.STOP == 0x03

    def test_zoom_max(self):
        assert ZOOM_MAX == 0x4000


# ─────────────────────────────────────────────────────────────────────────────
#  commands — pan/tilt
# ─────────────────────────────────────────────────────────────────────────────

CAM_ID = "8101"  # dirección de cámara de ejemplo

class TestPanTiltCommands:
    def test_pan_tilt_bytes_length(self):
        b = vcmd.pan_tilt(CAM_ID, 10, 8, PanDir.LEFT, TiltDir.UP)
        assert isinstance(b, bytes)
        assert b[-1] == 0xFF

    def test_pan_tilt_encodes_directions(self):
        b = vcmd.pan_tilt(CAM_ID, 0x0A, 0x08, PanDir.RIGHT, TiltDir.DOWN)
        # estructura: <2 cam_id bytes> 01 06 01 <pan_spd> <tilt_spd> <pan_dir> <tilt_dir> FF
        # desde el final: FF, tilt_dir, pan_dir, tilt_spd, pan_spd
        assert b[-5] == 0x0A   # pan_spd
        assert b[-4] == 0x08   # tilt_spd
        assert b[-3] == PanDir.RIGHT
        assert b[-2] == TiltDir.DOWN

    def test_pan_tilt_stop(self):
        b = vcmd.pan_tilt_stop(CAM_ID)
        # velocidad cero, STOP en ambos ejes
        assert b[-5] == 0x00   # pan_spd = 0
        assert b[-4] == 0x00   # tilt_spd = 0
        assert b[-3] == PanDir.STOP
        assert b[-2] == TiltDir.STOP
        assert b[-1] == 0xFF

    def test_home(self):
        b = vcmd.home(CAM_ID)
        assert b[-1] == 0xFF
        assert 0x04 in b  # opcode de home


# ─────────────────────────────────────────────────────────────────────────────
#  commands — zoom
# ─────────────────────────────────────────────────────────────────────────────

class TestZoomCommands:
    def test_zoom_absolute_wide(self):
        b = vcmd.zoom_absolute(CAM_ID, 0)
        # pct=0 → pos=0 → los 4 nibbles de zoom son cero
        assert b[-1] == 0xFF
        assert b[-5] == 0x00  # p=0
        assert b[-4] == 0x00  # q=0

    def test_zoom_absolute_tele(self):
        b = vcmd.zoom_absolute(CAM_ID, 100)
        # pct=100 → pos=ZOOM_MAX=0x4000 → p=(0x4000>>12)&0xF = 4
        assert b[-5] == 0x04

    def test_zoom_absolute_50pct_roundtrips(self):
        """Construir al 50% y parsear debe recuperar ~50%."""
        pct = 50
        raw_cmd = vcmd.zoom_absolute(CAM_ID, pct)
        # Nibbles del zoom están en b[-5...-2] (antes del terminador FF)
        p, q, r, s = raw_cmd[-5], raw_cmd[-4], raw_cmd[-3], raw_cmd[-2]
        fake_response = bytes([0x90, 0x50, p, q, r, s, 0xFF])
        recovered = vparse.zoom(fake_response)
        assert recovered is not None
        assert abs(vparse.zoom_to_pct(recovered) - pct) <= 1

    def test_zoom_inquiry_ends_with_ff(self):
        b = vcmd.zoom_inquiry(CAM_ID)
        assert b[-1] == 0xFF

    def test_ptz_position_inquiry_ends_with_ff(self):
        b = vcmd.ptz_position_inquiry(CAM_ID)
        assert b[-1] == 0xFF


# ─────────────────────────────────────────────────────────────────────────────
#  commands — focus, brightness, backlight, preset
# ─────────────────────────────────────────────────────────────────────────────

class TestOtherCommands:
    def test_focus_auto_manual_differ(self):
        assert vcmd.focus_auto(CAM_ID) != vcmd.focus_manual(CAM_ID)

    def test_one_push_af(self):
        b = vcmd.one_push_af(CAM_ID)
        assert b[-1] == 0xFF

    def test_brightness_up_down_differ(self):
        assert vcmd.brightness_up_direct(CAM_ID) != vcmd.brightness_down_direct(CAM_ID)
        assert vcmd.exp_comp_up(CAM_ID) != vcmd.exp_comp_down(CAM_ID)

    def test_backlight_on_off_differ(self):
        assert vcmd.backlight_on(CAM_ID) != vcmd.backlight_off(CAM_ID)

    def test_preset_recall_save_differ(self):
        assert vcmd.preset_recall(CAM_ID, "05") != vcmd.preset_save(CAM_ID, "05")

    def test_preset_recall_encodes_number(self):
        b = vcmd.preset_recall(CAM_ID, "0a")
        assert b[-1] == 0xFF
        # byte ante-penúltimo (antes de FF) debe ser el preset number
        assert b[-2] == 0x0A

    def test_ae_mode_inquiry_ends_with_ff(self):
        b = vcmd.ae_mode_inquiry(CAM_ID)
        assert b[-1] == 0xFF

    def test_exp_comp_inquiry_ends_with_ff(self):
        b = vcmd.exp_comp_inquiry(CAM_ID)
        assert b[-1] == 0xFF


# ─────────────────────────────────────────────────────────────────────────────
#  parser — zoom
# ─────────────────────────────────────────────────────────────────────────────

class TestParserZoom:
    def test_valid_zoom_response(self):
        # y0=0x90, 50, 0p=0x02, 0q=0x00, 0r=0x00, 0s=0x00, FF → 0x2000 = 50%
        data = bytes([0x90, 0x50, 0x02, 0x00, 0x00, 0x00, 0xFF])
        val = vparse.zoom(data)
        assert val == 0x2000

    def test_zoom_zero(self):
        data = bytes([0x90, 0x50, 0x00, 0x00, 0x00, 0x00, 0xFF])
        assert vparse.zoom(data) == 0

    def test_zoom_max(self):
        data = bytes([0x90, 0x50, 0x04, 0x00, 0x00, 0x00, 0xFF])
        assert vparse.zoom(data) == ZOOM_MAX

    def test_zoom_short_data_returns_none(self):
        assert vparse.zoom(bytes([0x90, 0x50])) is None

    def test_zoom_wrong_header_returns_none(self):
        data = bytes([0x90, 0x58, 0x04, 0x00, 0x00, 0x00, 0xFF])
        assert vparse.zoom(data) is None

    def test_zoom_to_pct(self):
        assert vparse.zoom_to_pct(0) == 0
        assert vparse.zoom_to_pct(ZOOM_MAX) == 100
        assert vparse.zoom_to_pct(ZOOM_MAX // 2) == 50


# ─────────────────────────────────────────────────────────────────────────────
#  parser — ptz_position
# ─────────────────────────────────────────────────────────────────────────────

class TestParserPTZPosition:
    def _make_ptz_response(self, pan: int, tilt: int) -> bytes:
        """Construye respuesta VISCA PTZ Position (y0 58 0p…0w FF)."""
        def nibbles(v):
            return bytes([
                (v >> 12) & 0xF,
                (v >>  8) & 0xF,
                (v >>  4) & 0xF,
                 v        & 0xF,
            ])
        return bytes([0x90, 0x58]) + nibbles(pan) + nibbles(tilt) + bytes([0xFF])

    def test_parses_pan_tilt(self):
        data = self._make_ptz_response(0x1234, 0x5678)
        result = vparse.ptz_position(data)
        assert result == (0x1234, 0x5678)

    def test_zero_position(self):
        data = self._make_ptz_response(0, 0)
        assert vparse.ptz_position(data) == (0, 0)

    def test_short_data_returns_none(self):
        assert vparse.ptz_position(bytes(5)) is None

    def test_wrong_header_returns_none(self):
        data = self._make_ptz_response(0x1234, 0x5678)
        bad = bytes([0x90, 0x50]) + data[2:]
        assert vparse.ptz_position(bad) is None

    # Signed two's-complement tests (#189)
    def test_negative_pan_ffff_equals_minus_one(self):
        data = self._make_ptz_response(0xFFFF, 0)
        pan, tilt = vparse.ptz_position(data)
        assert pan == -1
        assert tilt == 0

    def test_negative_tilt_ffff_equals_minus_one(self):
        data = self._make_ptz_response(0, 0xFFFF)
        pan, tilt = vparse.ptz_position(data)
        assert pan == 0
        assert tilt == -1

    def test_min_signed_value_8000(self):
        data = self._make_ptz_response(0x8000, 0x8000)
        pan, tilt = vparse.ptz_position(data)
        assert pan == -32768
        assert tilt == -32768

    def test_max_positive_value_7fff(self):
        data = self._make_ptz_response(0x7FFF, 0x7FFF)
        pan, tilt = vparse.ptz_position(data)
        assert pan == 32767
        assert tilt == 32767

    def test_positive_values_unchanged(self):
        data = self._make_ptz_response(0x1234, 0x5678)
        pan, tilt = vparse.ptz_position(data)
        assert pan == 0x1234
        assert tilt == 0x5678


# ─────────────────────────────────────────────────────────────────────────────
#  parser — inquiry_frame
# ─────────────────────────────────────────────────────────────────────────────

class TestParserInquiryFrame:
    def test_finds_simple_frame(self):
        # 9x 50 <1 byte payload> FF
        data = bytes([0x90, 0x50, 0x03, 0xFF])
        frame = vparse.inquiry_frame(data, payload_len=1)
        assert frame == data

    def test_finds_frame_after_ack(self):
        # ACK: 9x 4y FF  +  Completion: 9x 50 <payload> FF
        ack  = bytes([0x90, 0x41, 0xFF])
        comp = bytes([0x90, 0x50, 0x0D, 0xFF])
        frame = vparse.inquiry_frame(ack + comp, payload_len=1)
        assert frame == comp

    def test_returns_none_if_not_found(self):
        data = bytes([0x90, 0x41, 0xFF])
        assert vparse.inquiry_frame(data, payload_len=1) is None

    def test_four_byte_payload(self):
        payload = bytes([0x00, 0x00, 0x00, 0x07])
        data = bytes([0x90, 0x50]) + payload + bytes([0xFF])
        frame = vparse.inquiry_frame(data, payload_len=4)
        assert frame == data


# ─────────────────────────────────────────────────────────────────────────────
#  parser — ae_mode
# ─────────────────────────────────────────────────────────────────────────────

class TestParserAEMode:
    def _frame(self, pp: int) -> bytes:
        return bytes([0x90, 0x50, pp, 0xFF])

    def test_manual(self):
        assert vparse.ae_mode(self._frame(0x03)) == 'manual'

    def test_bright(self):
        assert vparse.ae_mode(self._frame(0x0D)) == 'bright'

    def test_unknown_is_auto(self):
        assert vparse.ae_mode(self._frame(0x00)) == 'auto'
        assert vparse.ae_mode(self._frame(0xFF)) == 'auto'


# ─────────────────────────────────────────────────────────────────────────────
#  parser — exp_comp_level
# ─────────────────────────────────────────────────────────────────────────────

class TestParserExpCompLevel:
    def _frame(self, val: int) -> bytes:
        # val es el valor VISCA raw (0-14); se empaqueta en 4 nibbles
        return bytes([
            0x90, 0x50,
            (val >> 12) & 0x0F,
            (val >>  8) & 0x0F,
            (val >>  4) & 0x0F,
             val        & 0x0F,
            0xFF,
        ])

    def test_neutral(self):
        # val=7 → level=0
        assert vparse.exp_comp_level(self._frame(7)) == 0

    def test_min(self):
        # val=0 → level=-7
        assert vparse.exp_comp_level(self._frame(0)) == -7

    def test_max(self):
        # val=14 → level=+7
        assert vparse.exp_comp_level(self._frame(14)) == 7

    def test_clamped_high(self):
        # val=30 → would be +23, clamped to +7
        assert vparse.exp_comp_level(self._frame(30)) == 7
