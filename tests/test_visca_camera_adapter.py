#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_visca_camera_adapter.py — Tests for adapters/visca_camera_adapter.py

from __future__ import annotations

import pytest

from adapters.visca_camera_adapter import ViscaCameraAdapter
from domain.ports import CameraStatus
from domain.supportability import CommandResult


class _StubWorker:
    def __init__(self):
        self.sent = []
        self.priority = []

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
        self.invalidated: list[str] = []

    def worker(self, ip: str) -> _StubWorker:
        self.workers.setdefault(ip, _StubWorker())
        return self.workers[ip]

    def invalidate_zoom(self, ip: str) -> None:
        self.invalidated.append(ip)


_CAM_CONFIGS = {1: ("10.0.0.1", "81"), 2: ("10.0.0.2", "82")}


def _make_adapter(confirmed_ok: bool = True) -> tuple[ViscaCameraAdapter, _StubManager]:
    mgr = _StubManager()
    adapter = ViscaCameraAdapter(mgr, cam_configs=_CAM_CONFIGS)
    adapter._send_confirmed = lambda ip, cam_id, cmd: confirmed_ok
    return adapter, mgr


# ═══════════════════════════════════════════════════════════════════════════════
# Camera ID → config mapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestCameraIndex:
    def test_cam1_maps_to_ip_1(self):
        adapter, _ = _make_adapter()
        captured = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: captured.append(ip) or True
        adapter.power_on("cam1")
        assert captured == ["10.0.0.1"]

    def test_cam2_maps_to_ip_2(self):
        adapter, _ = _make_adapter()
        captured = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: captured.append(ip) or True
        adapter.power_on("cam2")
        assert captured == ["10.0.0.2"]

    def test_cam1_uses_cam_id_hex_81(self):
        adapter, _ = _make_adapter()
        captured = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: captured.append(cam_id) or True
        adapter.power_on("cam1")
        assert captured == ["81"]

    def test_cam2_uses_cam_id_hex_82(self):
        adapter, _ = _make_adapter()
        captured = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: captured.append(cam_id) or True
        adapter.power_on("cam2")
        assert captured == ["82"]

    def test_unknown_camera_raises_value_error(self):
        adapter, _ = _make_adapter()
        with pytest.raises(ValueError, match="unknown camera_id"):
            adapter.recall_preset("cam3", 5)

    def test_error_message_lists_known_ids(self):
        adapter, _ = _make_adapter()
        with pytest.raises(ValueError) as exc_info:
            adapter.recall_preset("invalid", 1)
        assert "cam1" in str(exc_info.value)
        assert "cam2" in str(exc_info.value)


# ═══════════════════════════════════════════════════════════════════════════════
# recall_preset
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecallPreset:
    def test_returns_command_result(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter()
        result = adapter.recall_preset("cam1", 5)
        assert isinstance(result, CommandResult)

    def test_ok_when_confirmed_returns_true(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter(confirmed_ok=True)
        assert adapter.recall_preset("cam1", 5).ok is True

    def test_not_ok_when_confirmed_returns_false(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter(confirmed_ok=False)
        assert adapter.recall_preset("cam1", 5).ok is False

    def test_not_ok_when_preset_not_in_map(self):
        adapter, _ = _make_adapter()
        assert adapter.recall_preset("cam1", 999).ok is False

    def test_error_code_none_when_ok(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter(confirmed_ok=True)
        result = adapter.recall_preset("cam1", 5)
        assert result.error_code is None

    def test_error_code_set_when_not_ok(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter(confirmed_ok=False)
        result = adapter.recall_preset("cam1", 5)
        assert result.error_code == "CAMERA_ERROR"

    def test_command_field(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter()
        result = adapter.recall_preset("cam1", 5)
        assert result.command == "recall_preset"

    def test_target_is_camera_id(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter()
        result = adapter.recall_preset("cam2", 5)
        assert result.target == "cam2"

    def test_duration_ms_is_non_negative_int(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter()
        result = adapter.recall_preset("cam1", 5)
        assert isinstance(result.duration_ms, int)
        assert result.duration_ms >= 0

    def test_correlation_id_present(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter()
        result = adapter.recall_preset("cam1", 5)
        assert result.correlation_id

    def test_two_calls_have_different_correlation_ids(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter()
        r1 = adapter.recall_preset("cam1", 5)
        r2 = adapter.recall_preset("cam1", 5)
        assert r1.correlation_id != r2.correlation_id


# ═══════════════════════════════════════════════════════════════════════════════
# save_preset
# ═══════════════════════════════════════════════════════════════════════════════

class TestSavePreset:
    def test_sends_to_cam1_ip(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {7: "06"})
        adapter, _ = _make_adapter()
        captured = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: captured.append(ip) or True
        adapter.save_preset("cam1", 7)
        assert captured == ["10.0.0.1"]

    def test_sends_to_cam2_ip(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {3: "02"})
        adapter, _ = _make_adapter()
        captured = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: captured.append(ip) or True
        adapter.save_preset("cam2", 3)
        assert captured == ["10.0.0.2"]

    def test_returns_command_result(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter()
        assert isinstance(adapter.save_preset("cam1", 5), CommandResult)

    def test_ok_reflects_confirmed_result(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _ = _make_adapter(confirmed_ok=False)
        assert adapter.save_preset("cam1", 5).ok is False


# ═══════════════════════════════════════════════════════════════════════════════
# move / stop_move (fire-and-forget — always ok)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMove:
    def test_enqueues_to_cam1_worker(self):
        adapter, mgr = _make_adapter()
        adapter.move("cam1", 3, 2)
        assert "10.0.0.1" in mgr.workers
        assert mgr.workers["10.0.0.1"].sent

    def test_always_returns_ok(self):
        adapter, _ = _make_adapter()
        assert adapter.move("cam1", 5, 0).ok is True

    def test_duration_ms_is_none_for_fire_and_forget(self):
        adapter, _ = _make_adapter()
        result = adapter.move("cam1", 3, 0)
        assert result.duration_ms is None


class TestStopMove:
    def test_enqueues_priority_for_cam1(self):
        adapter, mgr = _make_adapter()
        adapter.stop_move("cam1")
        worker = mgr.workers.get("10.0.0.1")
        assert worker is not None and worker.priority

    def test_always_returns_ok(self):
        adapter, _ = _make_adapter()
        assert adapter.stop_move("cam1").ok is True


# ═══════════════════════════════════════════════════════════════════════════════
# zoom (fire-and-forget)
# ═══════════════════════════════════════════════════════════════════════════════

class TestZoom:
    def test_enqueues_to_cam2_worker(self):
        adapter, mgr = _make_adapter()
        adapter.zoom("cam2", 50)
        assert "10.0.0.2" in mgr.workers
        assert mgr.workers["10.0.0.2"].sent

    def test_always_returns_ok(self):
        adapter, _ = _make_adapter()
        assert adapter.zoom("cam2", 30).ok is True


# ═══════════════════════════════════════════════════════════════════════════════
# power_on / standby
# ═══════════════════════════════════════════════════════════════════════════════

class TestPowerOn:
    def test_sends_to_cam1_ip(self):
        adapter, _ = _make_adapter()
        captured = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: captured.append(ip) or True
        adapter.power_on("cam1")
        assert captured == ["10.0.0.1"]

    def test_ok_reflects_confirmed(self):
        adapter, _ = _make_adapter(confirmed_ok=False)
        assert adapter.power_on("cam1").ok is False

    def test_duration_measured(self):
        adapter, _ = _make_adapter()
        result = adapter.power_on("cam1")
        assert result.duration_ms is not None and result.duration_ms >= 0


class TestStandby:
    def test_sends_to_cam2_ip(self):
        adapter, _ = _make_adapter()
        captured = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: captured.append(ip) or True
        adapter.standby("cam2")
        assert captured == ["10.0.0.2"]

    def test_ok_reflects_confirmed(self):
        adapter, _ = _make_adapter(confirmed_ok=False)
        assert adapter.standby("cam2").ok is False


# ═══════════════════════════════════════════════════════════════════════════════
# home (fire-and-forget, priority queue)
# ═══════════════════════════════════════════════════════════════════════════════

class TestHome:
    def test_enqueues_to_priority_queue(self):
        adapter, mgr = _make_adapter()
        adapter.home("cam1")
        worker = mgr.workers.get("10.0.0.1")
        assert worker is not None and worker.priority
        assert worker.sent == []

    def test_always_returns_ok(self):
        adapter, _ = _make_adapter()
        assert adapter.home("cam1").ok is True


# ═══════════════════════════════════════════════════════════════════════════════
# _recv_visca_response — reads until a terminal VISCA frame (Completion/Error)
# ═══════════════════════════════════════════════════════════════════════════════

class _FakeSocket:
    """Socket stub that yields pre-scripted recv chunks, then b'' (EOF)."""
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def recv(self, _n):
        return self._chunks.pop(0) if self._chunks else b""


class TestRecvViscaResponse:
    def _adapter(self):
        return ViscaCameraAdapter(_StubManager(), cam_configs=_CAM_CONFIGS)

    def test_keeps_reading_past_ack_until_completion(self):
        # ACK and Completion arrive in separate TCP segments.
        sock = _FakeSocket([bytes([0x90, 0x41, 0xFF]), bytes([0x90, 0x51, 0xFF])])
        buf = self._adapter()._recv_visca_response(sock)
        from ptz.visca.parser import validate_visca_response
        ok, _ = validate_visca_response(buf)
        assert ok is True

    def test_detects_error_after_ack(self):
        # The critical case: ACK first, Error second. A single recv would have
        # confirmed the command on the ACK and missed the Error.
        sock = _FakeSocket([bytes([0x90, 0x41, 0xFF]), bytes([0x90, 0x61, 0x04, 0xFF])])
        buf = self._adapter()._recv_visca_response(sock)
        from ptz.visca.parser import validate_visca_response
        ok, reason = validate_visca_response(buf)
        assert ok is False
        assert "error" in reason.lower()

    def test_stops_on_eof_without_final_frame(self):
        sock = _FakeSocket([bytes([0x90, 0x41, 0xFF])])  # only ACK, then EOF
        buf = self._adapter()._recv_visca_response(sock)
        assert buf == bytes([0x90, 0x41, 0xFF])


# ═══════════════════════════════════════════════════════════════════════════════
# get_status
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetStatus:
    def test_returns_camera_status(self):
        adapter, _ = _make_adapter()
        assert isinstance(adapter.get_status("cam1"), CameraStatus)

    def test_cam1_role_is_main(self):
        adapter, _ = _make_adapter()
        assert adapter.get_status("cam1").role == "main"

    def test_cam2_role_is_comments(self):
        adapter, _ = _make_adapter()
        assert adapter.get_status("cam2").role == "comments"

    def test_adapter_type_is_visca(self):
        adapter, _ = _make_adapter()
        assert adapter.get_status("cam1").adapter_type == "visca"

    def test_camera_id_preserved(self):
        adapter, _ = _make_adapter()
        assert adapter.get_status("cam2").camera_id == "cam2"

    def test_unknown_camera_raises(self):
        adapter, _ = _make_adapter()
        with pytest.raises(ValueError):
            adapter.get_status("cam99")


# ═══════════════════════════════════════════════════════════════════════════════
# Runtime IP reconfiguration (update_camera_ip)
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpdateCameraIp:
    def _adapter(self):
        # Own dict per test — update_camera_ip mutates it in place.
        mgr = _StubManager()
        adapter = ViscaCameraAdapter(mgr, cam_configs={1: ("10.0.0.1", "81"),
                                                       2: ("10.0.0.2", "82")})
        return adapter

    def test_commands_route_to_new_ip_after_update(self):
        adapter = self._adapter()
        captured = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: captured.append((ip, cam_id)) or True

        adapter.update_camera_ip(1, "192.168.1.55")
        adapter.power_on("cam1")

        assert captured == [("192.168.1.55", "81")]  # new IP, VISCA id preserved

    def test_other_camera_is_unaffected(self):
        adapter = self._adapter()
        captured = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: captured.append(ip) or True

        adapter.update_camera_ip(1, "192.168.1.55")
        adapter.power_on("cam2")

        assert captured == ["10.0.0.2"]

    def test_noop_when_cam_configs_is_none(self):
        # Live-config mode: no snapshot to update, must not raise.
        adapter = ViscaCameraAdapter(_StubManager(), cam_configs=None)
        adapter.update_camera_ip(1, "192.168.1.55")  # should be a silent no-op

