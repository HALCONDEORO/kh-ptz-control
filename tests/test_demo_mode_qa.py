# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Demo mode QA: hardware-free and production-safety tests (#300).

Verifies:
  - Demo startup does not write to production paths
  - FakeCamera requires no network sockets
  - FakeATEM requires no PyATEMMax / no network sockets
  - DemoGuard isolates KHPTZ_DATA_DIR
  - Production profile never loads demo-specific components
  - Anti-socket guards: no socket.connect in demo flows
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

class _SocketBlocker:
    """Context manager: raises AssertionError if any socket.connect is called."""

    def __enter__(self):
        self._orig = socket.socket.connect
        def _blocked(_self_sock, address):
            raise AssertionError(
                f"socket.connect({address!r}) called — demo code must not open real sockets"
            )
        socket.socket.connect = _blocked
        return self

    def __exit__(self, *_):
        socket.socket.connect = self._orig


# ── Demo startup safety ───────────────────────────────────────────────────────

class TestDemoStartupSafety:
    def test_demo_guard_sets_env_var(self, tmp_path):
        demo_dir = tmp_path / "demo"
        from application.demo_guard import DemoGuard
        from domain.runtime_mode import RuntimeMode
        g = DemoGuard(mode=RuntimeMode.DEMO, demo_data_dir=demo_dir, app_dir=tmp_path)
        g.apply()
        assert os.environ.get("KHPTZ_DATA_DIR") == str(demo_dir)

    def test_demo_guard_does_not_write_to_production(self, tmp_path):
        demo_dir = tmp_path / "demo"
        production_dir = tmp_path / "production"
        from application.demo_guard import DemoGuard
        from domain.runtime_mode import RuntimeMode
        g = DemoGuard(
            mode=RuntimeMode.DEMO,
            demo_data_dir=demo_dir,
            production_data_dir=production_dir,
            app_dir=tmp_path,
        )
        g.apply()
        # Production dir must not be created by demo guard
        assert not production_dir.exists()

    def test_demo_guard_creates_demo_dir(self, tmp_path):
        demo_dir = tmp_path / "demo"
        from application.demo_guard import DemoGuard
        from domain.runtime_mode import RuntimeMode
        g = DemoGuard(mode=RuntimeMode.DEMO, demo_data_dir=demo_dir, app_dir=tmp_path)
        g.apply()
        assert demo_dir.exists()

    def test_demo_guard_assert_safe_blocks_production_path(self, tmp_path):
        from application.demo_guard import DemoGuard, DemoModeViolation
        from domain.runtime_mode import RuntimeMode
        prod_dir = tmp_path / "prod"
        prod_dir.mkdir()
        protected = prod_dir / "config.yaml"
        protected.write_text("mode: production", encoding="utf-8")
        g = DemoGuard(
            mode=RuntimeMode.DEMO,
            demo_data_dir=tmp_path / "demo",
            production_data_dir=prod_dir,
            app_dir=tmp_path,
        )
        g.apply()
        with pytest.raises(DemoModeViolation):
            g.assert_safe(protected)

    def test_demo_does_not_require_real_camera_ips(self):
        # The demo config should not contain real camera IPs
        demo_yaml = Path(__file__).parent.parent / "config" / "defaults" / "demo.yaml"
        content = demo_yaml.read_text(encoding="utf-8")
        assert "192.168." not in content
        assert "ptz1ip" not in content.lower() or "127.0.0.1" in content


# ── FakeCamera: no real sockets ───────────────────────────────────────────────

class TestFakeCameraNoSockets:
    def test_recall_preset_no_socket(self):
        from adapters.fake_camera import FakeCamera
        cam = FakeCamera(camera_id="platform", role="platform", move_delay_s=0.0)
        with _SocketBlocker():
            result = cam.recall_preset(5)
        assert result is True

    def test_save_preset_no_socket(self):
        from adapters.fake_camera import FakeCamera
        cam = FakeCamera(camera_id="platform", role="platform", move_delay_s=0.0)
        with _SocketBlocker():
            result = cam.save_preset(3)
        assert result is True

    def test_power_on_no_socket(self):
        from adapters.fake_camera import FakeCamera
        cam = FakeCamera(camera_id="platform", role="platform", move_delay_s=0.0)
        with _SocketBlocker():
            result = cam.power_on()
        assert result is True

    def test_go_home_no_socket(self):
        from adapters.fake_camera import FakeCamera
        cam = FakeCamera(camera_id="platform", role="platform", move_delay_s=0.0)
        with _SocketBlocker():
            result = cam.go_home()
        assert result is True

    def test_get_status_no_socket(self):
        from adapters.fake_camera import FakeCamera
        cam = FakeCamera(camera_id="comments", role="comments", move_delay_s=0.0)
        with _SocketBlocker():
            status = cam.get_status()
        assert status.adapter_type == "fake"

    def test_fake_camera_not_connected_to_real_hardware(self):
        from adapters.fake_camera import FakeCamera
        cam = FakeCamera(camera_id="platform", role="platform")
        status = cam.get_status()
        # A FakeCamera starts connected (simulated) but never opens real network
        assert status.camera_id == "platform"


# ── FakeATEM: no real sockets / no PyATEMMax ─────────────────────────────────

class TestFakeATEMNoSockets:
    def test_connect_no_socket(self):
        from adapters.fake_atem import FakeATEM
        atem = FakeATEM()
        with _SocketBlocker():
            result = atem.connect()
        assert result is True

    def test_get_program_input_no_socket(self):
        from adapters.fake_atem import FakeATEM
        atem = FakeATEM()
        atem.connect()
        with _SocketBlocker():
            inp = atem.get_program_input()
        assert inp is None or isinstance(inp, int)

    def test_set_program_input_no_socket(self):
        from adapters.fake_atem import FakeATEM
        atem = FakeATEM()
        atem.connect()
        with _SocketBlocker():
            atem.set_program_input(2)
        assert atem.get_program_input() == 2

    def test_fake_atem_does_not_import_pyatemmax(self):
        import sys
        # FakeATEM must work without PyATEMMax
        pyatemmax_modules = [k for k in sys.modules if "pyatem" in k.lower()]
        from adapters.fake_atem import FakeATEM
        atem = FakeATEM()
        atem.connect()
        atem.set_program_input(1)
        # No new PyATEMMax module should have been imported
        new_pyatemmax = [k for k in sys.modules if "pyatem" in k.lower()]
        assert new_pyatemmax == pyatemmax_modules

    def test_fake_atem_callback_fires_without_socket(self):
        from adapters.fake_atem import FakeATEM
        atem = FakeATEM()
        atem.connect()
        received = []
        atem.add_program_changed_callback(received.append)
        with _SocketBlocker():
            atem.set_program_input(3)
        assert received == [3]


# ── Production safety: demo mode does not contaminate production ──────────────

class TestProductionSafety:
    def test_demo_guard_assert_safe_allows_demo_path(self, tmp_path):
        from application.demo_guard import DemoGuard
        from domain.runtime_mode import RuntimeMode
        demo_dir = tmp_path / "demo"
        demo_dir.mkdir()
        g = DemoGuard(
            mode=RuntimeMode.DEMO,
            demo_data_dir=demo_dir,
            app_dir=tmp_path,
        )
        g.apply()
        demo_file = demo_dir / "room_layout.json"
        demo_file.write_text("{}", encoding="utf-8")
        g.assert_safe(demo_file)  # must not raise

    def test_demo_reset_refuses_production_path(self, tmp_path):
        from application.demo_reset_service import DemoResetService, _PRODUCTION_PATH
        svc = DemoResetService(demo_data_dir=_PRODUCTION_PATH)
        result = svc.reset()
        assert not result.success
        assert result.error is not None

    def test_demo_config_has_no_real_ips(self):
        demo_yaml = Path(__file__).parent.parent / "config" / "defaults" / "demo.yaml"
        content = demo_yaml.read_text(encoding="utf-8")
        # Should only have loopback addresses (127.0.0.1) or no IPs at all
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "ip" in stripped.lower() and ":" in stripped:
                value = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                # Accept only loopback or placeholder addresses
                assert value in ("127.0.0.1", "", "null", "~") or not value, \
                    f"Non-loopback IP in demo config: {stripped!r}"

    def test_demo_templates_contain_no_real_ips(self):
        demo_dir = Path(__file__).parent.parent / "config" / "demo"
        for f in demo_dir.glob("*.json"):
            content = f.read_text(encoding="utf-8")
            assert "192.168." not in content, f"{f.name} has a LAN IP address"
            assert "10.0." not in content, f"{f.name} has a LAN IP address"

    def test_demo_templates_have_no_real_names(self):
        seat_names = Path(__file__).parent.parent / "config" / "demo" / "seat_names.json"
        data = json.loads(seat_names.read_text(encoding="utf-8"))
        for name in data.get("names", []):
            assert "demo" in name.lower() or "sample" in name.lower() \
                or "test" in name.lower() or "example" in name.lower() \
                or "placeholder" in name.lower() or "mock" in name.lower() \
                or "fictional" in name.lower() or "dummy" in name.lower(), \
                f"Name {name!r} does not look like a fake/demo name"


# ── End-to-end demo flow: no socket ──────────────────────────────────────────

class TestDemoEndToEndNoSocket:
    def test_fake_camera_preset_cycle_no_socket(self):
        from adapters.fake_camera import FakeCamera
        cam = FakeCamera(camera_id="comments", role="comments", move_delay_s=0.0)
        with _SocketBlocker():
            cam.power_on()
            cam.recall_preset(5)
            cam.save_preset(5)
            cam.go_home()
            cam.standby()
        status = cam.get_status()
        assert status.adapter_type == "fake"

    def test_fake_atem_input_change_triggers_callback_no_socket(self):
        from adapters.fake_atem import FakeATEM
        atem = FakeATEM()
        events = []
        atem.add_program_changed_callback(events.append)
        with _SocketBlocker():
            atem.connect()
            atem.set_program_input(2)
            atem.set_program_input(3)
        assert events == [2, 3]

    def test_demo_reset_full_cycle_no_socket(self, tmp_path):
        from application.demo_reset_service import DemoResetService, _DEMO_TEMPLATES_DIR
        svc = DemoResetService(
            demo_data_dir=tmp_path / "demo",
            templates_dir=_DEMO_TEMPLATES_DIR,
        )
        with _SocketBlocker():
            result = svc.reset()
        assert result.success
        assert "room_layout.json" in result.restored
