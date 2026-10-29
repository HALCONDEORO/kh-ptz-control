#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Regression tests for the external read-only safety review (26 findings)."""

from __future__ import annotations

from adapters.visca_camera_adapter import ViscaCameraAdapter
from ptz.visca import parser


class _StubWorker:
    def __init__(self):
        self.priority = []
        self.sent = []

    def send(self, cmd):
        self.sent.append(cmd)

    def send_priority(self, cmd):
        self.priority.append(cmd)


class _StubManager:
    def is_connected(self, ip: str) -> bool:
        w = self.workers.get(ip)
        return bool(w is not None and getattr(w, "connected", False))

    def __init__(self):
        self.workers: dict[str, _StubWorker] = {}

    def worker(self, ip: str) -> _StubWorker:
        self.workers.setdefault(ip, _StubWorker())
        return self.workers[ip]

    def invalidate_zoom(self, ip: str) -> None:
        pass


_TWO_CAMS = {1: ("10.0.0.1", "81"), 2: ("10.0.0.2", "82")}


def _adapter(cam_configs):
    mgr = _StubManager()
    return ViscaCameraAdapter(mgr, cam_configs=cam_configs), mgr


# Finding 7: a zoom speed cap above 7 must not corrupt the direction byte.
class TestZoomNibbleClamp:
    def test_cap_above_7_still_sends_tele(self):
        adapter, mgr = _adapter(_TWO_CAMS)
        adapter.zoom_drive_cap = 16
        adapter.zoom("cam1", 16)
        payload = mgr.workers["10.0.0.1"].sent[-1].payload
        assert payload[4] == 0x27  # 0x20 | 7, nunca 0x30 (zoom out)

    def test_cap_above_7_still_sends_wide(self):
        adapter, mgr = _adapter(_TWO_CAMS)
        adapter.zoom_drive_cap = 16
        adapter.zoom("cam1", -16)
        payload = mgr.workers["10.0.0.1"].sent[-1].payload
        assert payload[4] == 0x37  # 0x30 | 7

    def test_normal_cap_unaffected(self):
        adapter, mgr = _adapter(_TWO_CAMS)
        adapter.zoom_drive_cap = 4
        adapter.zoom("cam1", 4)
        payload = mgr.workers["10.0.0.1"].sent[-1].payload
        assert payload[4] == 0x24


# Finding 8: single-camera rooms and empty IPs.
class TestMissingSecondCamera:
    def test_stop_all_skips_unconfigured_camera(self):
        adapter, mgr = _adapter({1: ("10.0.0.1", "81")})
        result = adapter.stop_all()
        assert result.ok, result.message
        assert list(mgr.workers) == ["10.0.0.1"]

    def test_stop_all_skips_empty_ip(self):
        adapter, mgr = _adapter({1: ("10.0.0.1", "81"), 2: ("", "82")})
        result = adapter.stop_all()
        assert result.ok, result.message
        assert "" not in mgr.workers  # nunca un worker hacia localhost

    def test_stop_move_empty_ip_fails_fast(self):
        adapter, mgr = _adapter({1: ("10.0.0.1", "81"), 2: ("", "82")})
        result = adapter.stop_move("cam2")
        assert not result.ok
        assert "" not in mgr.workers


# Finding 10: PTZ Position Inquiry accepts the spec 0x50 reply and the 0x58 variant.
class TestPtzPositionReplyByte:
    def _frame(self, byte: int) -> bytes:
        return bytes([0x90, byte, 0x00, 0x01, 0x02, 0x03, 0x0F, 0x0F, 0x0F, 0x0F, 0xFF])

    def test_spec_reply_0x50(self):
        assert parser.ptz_position(self._frame(0x50)) == (0x123, -1)

    def test_variant_reply_0x58(self):
        assert parser.ptz_position(self._frame(0x58)) == (0x123, -1)


# Finding 6: get_status reports the real TCP session state.
class TestGetStatusConnected:
    def test_disconnected_by_default(self):
        adapter, mgr = _adapter(_TWO_CAMS)
        assert adapter.get_status("cam1").connected is False

    def test_connected_when_worker_is(self):
        adapter, mgr = _adapter(_TWO_CAMS)
        w = mgr.worker("10.0.0.1")
        w.connected = True
        assert adapter.get_status("cam1").connected is True
        assert adapter.get_status("cam2").connected is False
