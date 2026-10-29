#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Tests de servicios de aplicacion: presets, camaras y ciclo de sesion.
"""


from application.session_service import SessionService
from domain.preset import PRESET_SLOT_MIN, PRESET_SLOT_MAX


class TestPresetService:

    def _service(self, monkeypatch, initial=None, saved=None):
        import application.preset_service as ps

        if initial is None:
            initial = {}
        if saved is None:
            saved = []

        monkeypatch.setattr(ps, "load_chairman_presets", lambda: dict(initial))
        monkeypatch.setattr(ps, "save_chairman_presets", lambda data: saved.append(dict(data)) or True)
        return ps.PresetService()

    def test_assign_slot_starts_at_minimum_and_marks_new(self, monkeypatch):
        svc = self._service(monkeypatch)

        assert svc.assign_slot("PersonA") == (PRESET_SLOT_MIN, True)
        assert svc.snapshot() == {"PersonA": PRESET_SLOT_MIN}

    def test_assign_slot_skips_used_slots(self, monkeypatch):
        svc = self._service(monkeypatch, {"PersonA": PRESET_SLOT_MIN})

        assert svc.assign_slot("PersonB") == (PRESET_SLOT_MIN + 1, True)

    def test_assign_existing_slot_is_not_new(self, monkeypatch):
        svc = self._service(monkeypatch, {"PersonA": 12})

        assert svc.assign_slot("PersonA") == (12, False)

    def test_assign_slot_returns_none_when_range_is_full(self, monkeypatch):
        full = {f"Person{slot}": slot for slot in range(PRESET_SLOT_MIN, PRESET_SLOT_MAX + 1)}
        svc = self._service(monkeypatch, full)

        assert svc.assign_slot("Extra") == (None, False)

    def test_snapshot_is_a_copy(self, monkeypatch):
        svc = self._service(monkeypatch, {"PersonA": 10})

        snap = svc.snapshot()
        snap["PersonB"] = 11

        assert svc.snapshot() == {"PersonA": 10}

    def test_persist_saves_current_snapshot(self, monkeypatch):
        saved = []
        svc = self._service(monkeypatch, {"PersonA": 10}, saved)
        svc.assign_slot("PersonB")

        svc.persist()

        assert saved == [{"PersonA": 10, "PersonB": 11}]

    def test_release_slot_is_idempotent(self, monkeypatch):
        svc = self._service(monkeypatch, {"PersonA": 10})

        svc.release_slot("PersonA")
        svc.release_slot("PersonA")

        assert svc.snapshot() == {}

    def test_rename_migrates_and_persists_when_target_is_free(self, monkeypatch):
        saved = []
        svc = self._service(monkeypatch, {"PersonA": 10}, saved)

        result = svc.rename("PersonA", "Alicia")

        assert result is True
        assert svc.snapshot() == {"Alicia": 10}
        assert saved == [{"Alicia": 10}]

    def test_rename_does_nothing_when_target_exists(self, monkeypatch):
        saved = []
        svc = self._service(monkeypatch, {"PersonA": 10, "PersonB": 11}, saved)

        result = svc.rename("PersonA", "PersonB")

        assert result is False
        assert svc.snapshot() == {"PersonA": 10, "PersonB": 11}
        assert saved == []

    def test_rename_conflict_logs_warning(self, monkeypatch, caplog):
        import logging
        svc = self._service(monkeypatch, {"PersonA": 10, "PersonB": 11})

        with caplog.at_level(logging.WARNING, logger="application.preset_service"):
            svc.rename("PersonA", "PersonB")

        assert any("PersonB" in r.message and "PersonA" in r.message for r in caplog.records)
    def test_get_preset_for_name_falls_back_to_generic(self, monkeypatch):
        svc = self._service(monkeypatch, {"PersonA": 10})

        assert svc.get_preset_for_name("PersonA") == 10
        assert svc.get_preset_for_name("Unknown") == 1

    def test_has_preset_tracks_current_state(self, monkeypatch):
        svc = self._service(monkeypatch, {"PersonA": 10})

        assert svc.has_preset("PersonA") is True
        assert svc.has_preset("PersonB") is False

    def test_rename_missing_source_does_not_persist(self, monkeypatch):
        saved = []
        svc = self._service(monkeypatch, {"PersonA": 10}, saved)

        result = svc.rename("Missing", "PersonB")

        assert result is False
        assert svc.snapshot() == {"PersonA": 10}
        assert saved == []


class _Worker:
    def __init__(self):
        self.sent = []
        self.priority = []

    def send(self, cmd):
        self.sent.append(cmd)
        return True

    def send_priority(self, cmd):
        self.priority.append(cmd)
        return True


class _Manager:
    def __init__(self):
        self.workers = {}
        self.invalidated = []

    def worker(self, ip):
        self.workers.setdefault(ip, _Worker())
        return self.workers[ip]

    def invalidate_zoom(self, ip):
        self.invalidated.append(ip)


class TestViscaCameraAdapterCommands:

    def _adapter(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {10: "0A", 11: "0B"})
        mgr = _Manager()
        adapter = mod.ViscaCameraAdapter(mgr, cam_configs={1: ("10.0.0.11", "81"), 2: ("10.0.0.12", "82")})
        return adapter, mgr

    def test_recall_and_save_preset_send_expected_confirmed_hex(self, monkeypatch):
        adapter, _mgr = self._adapter(monkeypatch)
        calls = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: calls.append((ip, cam_id, cmd)) or True

        assert adapter.recall_preset("cam1", 10).ok is True
        assert adapter.save_preset("cam2", 11).ok is True

        assert calls == [
            ("10.0.0.11", "81", "01043f020Aff"),
            ("10.0.0.12", "82", "01043f010Bff"),
        ]

    def test_invalid_preset_slot_does_not_send(self, monkeypatch):
        adapter, _mgr = self._adapter(monkeypatch)
        calls = []
        adapter._send_confirmed = lambda *args: calls.append(args) or True

        assert adapter.recall_preset("cam1", 99).ok is False
        assert adapter.save_preset("cam1", 99).ok is False
        assert calls == []

    def test_power_commands_use_selected_camera(self, monkeypatch):
        adapter, _mgr = self._adapter(monkeypatch)
        calls = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: calls.append((ip, cam_id, cmd)) or True

        adapter.power_on("cam1")
        adapter.standby("cam2")

        assert calls == [
            ("10.0.0.11", "81", "01040002FF"),
            ("10.0.0.12", "82", "01040003FF"),
        ]

    def test_home_uses_priority_queue_not_confirmed(self, monkeypatch):
        adapter, mgr = self._adapter(monkeypatch)

        adapter.home("cam1")

        worker = mgr.workers["10.0.0.11"]
        assert worker.sent == []
        assert worker.priority[0].payload.hex().upper() == "81010604FF"

    def test_move_clamps_speeds_and_encodes_directions(self, monkeypatch):
        adapter, mgr = self._adapter(monkeypatch)
        adapter.pan_cap = 4
        adapter.tilt_cap = 3

        adapter.move("cam1", pan_speed=-99, tilt_speed=99)

        cmd = mgr.workers["10.0.0.11"].sent[0]
        assert cmd.camera == 1
        assert cmd.payload.hex().upper() == "8101060104030101FF"

    def test_stop_uses_priority_queue(self, monkeypatch):
        adapter, mgr = self._adapter(monkeypatch)

        adapter.stop_move("cam2")

        worker = mgr.workers["10.0.0.12"]
        assert worker.sent == []
        assert worker.priority[0].payload.hex().upper() == "8201060100000303FF"

    def test_zoom_encodes_tele_wide_and_stop(self, monkeypatch):
        adapter, mgr = self._adapter(monkeypatch)
        adapter.zoom_drive_cap = 5

        adapter.zoom("cam1", 99)
        adapter.zoom("cam1", -99)
        adapter.zoom("cam1", 0)

        payloads = [cmd.payload.hex().upper() for cmd in mgr.workers["10.0.0.11"].sent]
        assert payloads == ["8101040725FF", "8101040735FF", "8101040700FF"]

    def test_invalidate_zoom_delegates_to_manager_ip(self, monkeypatch):
        adapter, mgr = self._adapter(monkeypatch)

        adapter.invalidate_zoom(2)

        assert mgr.invalidated == ["10.0.0.12"]

    def test_send_confirmed_sends_full_frame_and_reads_until_completion(self, monkeypatch):
        import adapters.visca_camera_adapter as mod

        adapter, _mgr = self._adapter(monkeypatch)
        socket_calls = []

        class FakeSocket:
            # ACK and Completion arrive in separate TCP segments; the adapter
            # must keep reading past the ACK until the terminal Completion frame.
            def __init__(self):
                self._chunks = [b"\x90\x41\xff", b"\x90\x51\xff"]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                socket_calls.append(("close",))
                return False

            def settimeout(self, timeout):
                socket_calls.append(("settimeout", timeout))

            def connect(self, address):
                socket_calls.append(("connect", address))

            def sendall(self, payload):
                socket_calls.append(("send", payload.hex().upper()))

            def recv(self, size):
                socket_calls.append(("recv", size))
                return self._chunks.pop(0) if self._chunks else b""

        monkeypatch.setattr(mod.socket, "socket", lambda *_args, **_kwargs: FakeSocket())
        monkeypatch.setattr(mod, "VISCA_PORT", 5678)
        monkeypatch.setattr(mod, "SOCKET_TIMEOUT", 0.5)

        assert adapter._send_confirmed("10.0.0.11", "81", "01040002FF") is True
        assert socket_calls == [
            ("settimeout", 0.5),
            ("connect", ("10.0.0.11", 5678)),
            ("send", "8101040002FF"),
            ("recv", 64),
            ("recv", 64),
            ("close",),
        ]

    def test_send_confirmed_returns_false_on_invalid_hex(self, monkeypatch):
        adapter, _mgr = self._adapter(monkeypatch)

        assert adapter._send_confirmed("127.0.0.1", "not-hex", "01040002FF") is False


class _Port:
    """Minimal CameraPort stub for SessionService tests."""

    def __init__(self):
        self.calls = []

    def power_on(self, camera_id: str):
        self.calls.append(("power_on", camera_id))

    def standby(self, camera_id: str):
        self.calls.append(("standby", camera_id))

    def home(self, camera_id: str):
        self.calls.append(("home", camera_id))

    def cancel_polls(self, camera_id: str):
        self.calls.append(("cancel_polls", camera_id))


class TestSessionService:

    def test_start_powers_both_cameras_and_marks_active(self):
        port = _Port()
        svc = SessionService(port)

        svc.start()

        assert svc.active is True
        assert port.calls == [("power_on", "cam1"), ("power_on", "cam2")]

    def test_home_both_sends_home_to_both_cameras(self):
        port = _Port()
        svc = SessionService(port)

        svc.home_both()

        assert port.calls == [("home", "cam1"), ("home", "cam2")]

    def test_end_standbys_both_cameras_and_clears_state(self):
        port = _Port()
        svc = SessionService(port)
        svc.set_chairman("PersonA")
        svc.start()
        port.calls.clear()

        svc.end()

        assert svc.active is False
        assert svc._chairman is None
        assert port.calls == [
            ("cancel_polls", "cam1"), ("cancel_polls", "cam2"),
            ("standby", "cam1"), ("standby", "cam2"),
        ]
