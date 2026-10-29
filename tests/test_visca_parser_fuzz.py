#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_visca_parser_fuzz.py — Pruebas fuzz y de frames malformados para ptz.visca.parser (#133).

Cubre:
- buffers vacíos o parciales
- ACK parcial sin completion
- ACK + completion combinados en un único paquete TCP
- bytes aleatorios terminados en 0xFF
- prefijo válido con longitud incorrecta
- buffers excesivamente largos
- tipos de respuesta no relacionados o desconocidos
- frames válidos conocidos que deben seguir parseando correctamente
"""
from __future__ import annotations

import random

import pytest

from ptz.visca import parser


# ── Helpers ───────────────────────────────────────────────────────────────────

def _zoom_completion(cam: int = 1, p=0, q=0, r=0, s=0) -> bytes:
    """Construye un frame VISCA válido de completion para consulta de zoom."""
    return bytes([0x90 | cam, 0x50, p & 0x0F, q & 0x0F, r & 0x0F, s & 0x0F, 0xFF])


def _ptz_completion(cam: int = 1, pan: int = 0, tilt: int = 0) -> bytes:
    """Construye un frame VISCA válido de completion para posición PTZ."""
    def nibbles(v: int) -> tuple[int, int, int, int]:
        v &= 0xFFFF
        return (v >> 12) & 0xF, (v >> 8) & 0xF, (v >> 4) & 0xF, v & 0xF

    pp, pq, pr, ps = nibbles(pan)
    tp, tq, tr, ts = nibbles(tilt)
    return bytes([0x90 | cam, 0x58, pp, pq, pr, ps, tp, tq, tr, ts, 0xFF])


def _ack_frame(cam: int = 1) -> bytes:
    """Construye un frame VISCA ACK sin payload."""
    return bytes([0x90 | cam, 0x41, 0xFF])


RANDOM_SEED = 42


# ── Buffers vacíos o cortos ───────────────────────────────────────────────────

class TestEmptyAndShortBuffers:

    def test_zoom_empty_bytes(self):
        assert parser.zoom(b"") is None

    def test_zoom_single_byte(self):
        assert parser.zoom(b"\x90") is None

    def test_zoom_two_bytes(self):
        assert parser.zoom(b"\x90\x50") is None

    def test_zoom_partial_frame_no_terminator(self):
        assert parser.zoom(b"\x90\x50\x00\x00\x00") is None

    def test_ptz_position_empty_bytes(self):
        assert parser.ptz_position(b"") is None

    def test_ptz_position_single_byte(self):
        assert parser.ptz_position(b"\x90") is None

    def test_ptz_position_partial_frame(self):
        assert parser.ptz_position(b"\x90\x58\x00\x00\x00\x00") is None


# ── Frames solo ACK, sin datos de completion ─────────────────────────────────

class TestAckOnly:

    def test_zoom_ack_only_returns_none(self):
        assert parser.zoom(_ack_frame()) is None

    def test_ptz_ack_only_returns_none(self):
        assert parser.ptz_position(_ack_frame()) is None

    def test_zoom_multiple_ack_no_completion(self):
        data = _ack_frame() + _ack_frame()
        assert parser.zoom(data) is None


# ── ACK + completion combinados ───────────────────────────────────────────────

class TestAckPlusCompletion:

    def test_zoom_ack_then_completion_extracts_value(self):
        completion = _zoom_completion(p=0x01, q=0x02, r=0x03, s=0x04)
        data = _ack_frame() + completion
        result = parser.zoom(data)
        assert result == 0x1234

    def test_ptz_ack_then_completion_extracts_position(self):
        completion = _ptz_completion(pan=0x0100, tilt=0x0200)
        data = _ack_frame() + completion
        pan, tilt = parser.ptz_position(data)
        assert pan == 0x0100
        assert tilt == 0x0200

    def test_zoom_completion_then_ack_extracts_value(self):
        completion = _zoom_completion(p=0x00, q=0x04, r=0x00, s=0x00)
        data = completion + _ack_frame()
        result = parser.zoom(data)
        assert result == 0x0400


# ── Bytes aleatorios terminados en 0xFF ──────────────────────────────────────

class TestRandomBytesEndingWithFF:

    def _random_bytes(self, length: int, seed: int) -> bytes:
        rng = random.Random(seed)
        return bytes([rng.randint(0, 255) for _ in range(length - 1)] + [0xFF])

    @pytest.mark.parametrize("seed", range(20))
    def test_zoom_random_does_not_crash(self, seed):
        data = self._random_bytes(16, seed)
        result = parser.zoom(data)
        assert result is None or isinstance(result, int)

    @pytest.mark.parametrize("seed", range(20))
    def test_ptz_random_does_not_crash(self, seed):
        data = self._random_bytes(20, seed)
        result = parser.ptz_position(data)
        assert result is None or (isinstance(result, tuple) and len(result) == 2)


# ── Prefijo válido con longitud incorrecta ───────────────────────────────────

class TestValidPrefixWrongLength:

    def test_zoom_completion_missing_last_nibble(self):
        # 9x 50 0p 0q 0r FF  (solo 3 nibbles en lugar de 4)
        data = bytes([0x90, 0x50, 0x01, 0x02, 0x03, 0xFF])
        assert parser.zoom(data) is None

    def test_zoom_completion_extra_nibble(self):
        # 9x 50 0p 0q 0r 0s 0t FF (5 nibbles en lugar de 4)
        data = bytes([0x90, 0x50, 0x01, 0x02, 0x03, 0x04, 0x05, 0xFF])
        assert parser.zoom(data) is None

    def test_ptz_completion_too_short_payload(self):
        # 9x 58 + 4 bytes + FF (requiere 8 bytes de payload)
        data = bytes([0x90, 0x58, 0x01, 0x02, 0x03, 0x04, 0xFF])
        assert parser.ptz_position(data) is None


# ── Buffers excesivamente largos ──────────────────────────────────────────────

class TestOverlyLongBuffers:

    def test_zoom_100_bytes_of_zeros_returns_none(self):
        data = b"\x00" * 100
        assert parser.zoom(data) is None

    def test_zoom_1024_bytes_random_does_not_crash(self):
        rng = random.Random(RANDOM_SEED)
        data = bytes(rng.randint(0, 255) for _ in range(1024))
        result = parser.zoom(data)
        assert result is None or isinstance(result, int)

    def test_zoom_completion_buried_at_offset_50(self):
        prefix = bytes([rng_byte for rng_byte in (random.Random(1).randint(0, 0x8F) for _ in range(50))])
        completion = _zoom_completion(p=0x03, q=0x04, r=0x05, s=0x06)
        data = prefix + completion + b"\x00" * 10
        result = parser.zoom(data)
        assert result == 0x3456


# ── Tipos de respuesta no relacionados o desconocidos ────────────────────────

class TestUnrelatedResponseTypes:

    def test_zoom_parser_ignores_ptz_completion(self):
        data = _ptz_completion()
        assert parser.zoom(data) is None

    def test_ptz_parser_ignores_zoom_completion(self):
        data = _zoom_completion()
        assert parser.ptz_position(data) is None

    def test_zoom_error_response_returns_none(self):
        # Error VISCA: 90 60 02 FF (comando no ejecutable)
        data = bytes([0x90, 0x60, 0x02, 0xFF])
        assert parser.zoom(data) is None

    def test_ptz_error_response_returns_none(self):
        data = bytes([0x90, 0x60, 0x41, 0xFF])
        assert parser.ptz_position(data) is None


# ── Límites y enmascarado de nibbles ─────────────────────────────────────────

class TestNibbleMasking:

    def test_zoom_high_nibbles_rejected(self):
        # Nibbles altos presentes: el parser debe rechazar y devolver None.
        data = bytes([0x91, 0x50, 0x40, 0x40, 0x40, 0x40, 0xFF])
        result = parser.zoom(data)
        assert result is None

    def test_zoom_all_nibbles_full(self):
        data = _zoom_completion(p=0xF, q=0xF, r=0xF, s=0xF)
        result = parser.zoom(data)
        assert result == 0xFFFF

    def test_zoom_value_within_valid_range(self):
        data = _zoom_completion(p=0x04, q=0x00, r=0x00, s=0x00)
        result = parser.zoom(data)
        assert 0 <= result <= 0xFFFF

    def test_ptz_high_nibbles_rejected(self):
        # PTZ with non-zero high nibble in pan bytes → None
        data = bytes([0x91, 0x58, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF])
        assert parser.ptz_position(data) is None

    def test_zoom_single_bad_nibble_rejected(self):
        # Only one byte has a bad high nibble — still rejected
        data = bytes([0x91, 0x50, 0x00, 0x00, 0xA0, 0x00, 0xFF])
        assert parser.zoom(data) is None


# ── Frames válidos conocidos que siguen parseando correctamente ──────────────

class TestValidKnownFrames:

    def test_zoom_zero(self):
        data = _zoom_completion(p=0, q=0, r=0, s=0)
        assert parser.zoom(data) == 0x0000

    def test_zoom_max_0x4000(self):
        data = _zoom_completion(p=0x4, q=0x0, r=0x0, s=0x0)
        assert parser.zoom(data) == 0x4000

    def test_zoom_mid_value(self):
        data = _zoom_completion(p=0x2, q=0x0, r=0x0, s=0x0)
        assert parser.zoom(data) == 0x2000

    def test_ptz_origin(self):
        data = _ptz_completion(pan=0, tilt=0)
        assert parser.ptz_position(data) == (0, 0)

    def test_ptz_positive_pan_tilt(self):
        data = _ptz_completion(pan=0x0ABC, tilt=0x0123)
        pan, tilt = parser.ptz_position(data)
        assert pan == 0x0ABC
        assert tilt == 0x0123

    def test_ptz_negative_pan(self):
        # 0xFFFF → -1 con signo.
        data = _ptz_completion(pan=0xFFFF, tilt=0)
        pan, tilt = parser.ptz_position(data)
        assert pan == -1
        assert tilt == 0

    def test_ptz_cam_address_2(self):
        data = bytes([0x92, 0x58, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0xFF])
        pan, tilt = parser.ptz_position(data)
        assert pan == 0x0100
        assert tilt == 0x0100


# ── Contrato público de inquiry_frame / _find_completion_frame ───────────────

class TestInquiryFrameContract:

    def test_returns_none_for_empty(self):
        assert parser.inquiry_frame(b"", payload_len=4) is None

    def test_returns_frame_slice_at_correct_offset(self):
        prefix = b"\x00" * 5
        frame = _zoom_completion()
        result = parser.inquiry_frame(prefix + frame, payload_len=4)
        assert result == frame

    def test_returns_first_match_when_multiple_present(self):
        frame_a = _zoom_completion(p=1)
        frame_b = _zoom_completion(p=2)
        result = parser.inquiry_frame(frame_a + frame_b, payload_len=4)
        assert result == frame_a
