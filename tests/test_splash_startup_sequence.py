#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_splash_startup_sequence.py — Tests for camera startup sequencing (#195).

Verifies that _startup_sequence() gates _run_initialization() on camera startup
completion (with a hard 10-second timeout), so the splash cannot hide before
cameras have had their startup window.

All tests call SplashScreen methods as unbound functions with a MagicMock stub as
self, avoiding real network or Qt infrastructure.
"""
from __future__ import annotations

import logging
import sys
import time
import types
from unittest.mock import MagicMock, patch



# ── Qt and hardware stubs (must come before importing splash_screen) ──────────

# Modules this test injects into sys.modules. We record the original entry
# (or its absence) so teardown_module can restore them — otherwise a stub like
# data_paths (which lacks ROOM_LAYOUT_FILE) leaks into the rest of the suite and
# breaks tests that import the real module. See #654 / startup-smoke isolation.
_INJECTED_MODULES: dict[str, object | None] = {}


def _inject_module(name: str, module: object) -> None:
    """Install a stub module, remembering the previous entry for restoration."""
    if name not in _INJECTED_MODULES:
        _INJECTED_MODULES[name] = sys.modules.get(name)
    sys.modules[name] = module


def _ensure_stubs() -> None:
    # PyQt5 core stubs
    for mod in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui"):
        if mod not in sys.modules:
            _inject_module(mod, types.ModuleType(mod))

    qtc = sys.modules["PyQt5.QtCore"]
    for name in ("Qt", "pyqtSignal", "QTimer", "QRect"):
        if not hasattr(qtc, name):
            setattr(qtc, name, MagicMock())

    qtw = sys.modules["PyQt5.QtWidgets"]
    for name in (
        "QWidget", "QVBoxLayout", "QHBoxLayout", "QLabel", "QProgressBar",
        "QFrame", "QSizePolicy", "QGraphicsDropShadowEffect",
    ):
        if not hasattr(qtw, name):
            setattr(qtw, name, MagicMock)

    qtg = sys.modules["PyQt5.QtGui"]
    for name in ("QFont", "QPainter", "QColor", "QRadialGradient", "QPen", "QBrush", "QLinearGradient"):
        if not hasattr(qtg, name):
            setattr(qtg, name, MagicMock)

    # Lightweight project dependency stubs
    for mod, attrs in [
        ("camera_discovery", {"get_camera_subnet": MagicMock(return_value="172.16.1.0"), "tcp_scan": MagicMock(), "arp_scan": MagicMock()}),
        ("data_paths", {"SCHEDULE_FILE": "schedule.json"}),
        ("sim_mode", {"is_active": MagicMock(return_value=False)}),
    ]:
        if mod not in sys.modules:
            m = types.ModuleType(mod)
            for k, v in attrs.items():
                setattr(m, k, v)
            _inject_module(mod, m)

    # config stub
    if "config" not in sys.modules:
        cfg = types.ModuleType("config")
        cfg.CAM1 = MagicMock(ip="172.16.1.11", cam_id="81")
        cfg.CAM2 = MagicMock(ip="172.16.1.12", cam_id="82")
        cfg.SOCKET_TIMEOUT = 1
        cfg.VISCA_PORT = 1259
        cfg.SEAT_POSITIONS = []
        cfg.ATEM = MagicMock()
        _inject_module("config", cfg)


def teardown_module(module) -> None:  # noqa: ARG001 — pytest module finalizer
    """Restore sys.modules so stubs (notably data_paths) don't leak into the suite."""
    for name, original in _INJECTED_MODULES.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original
    sys.modules.pop("ui.splash_screen", None)
    _INJECTED_MODULES.clear()


_ensure_stubs()

# Force fresh import so SplashScreen picks up the stubs
sys.modules.pop("splash_screen", None)
import ui.splash_screen as ss  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_stub(cam_duration: float = 0.0):
    """Return a MagicMock that records call order for _startup_cameras and _run_initialization."""
    stub = MagicMock()
    call_order: list[str] = []

    def _fake_cameras():
        time.sleep(cam_duration)
        call_order.append("camera_startup_done")

    def _fake_init():
        call_order.append("run_initialization")

    stub._startup_cameras = _fake_cameras
    stub._run_initialization = _fake_init
    stub._call_order = call_order
    return stub


# ── Tests: sequencing ─────────────────────────────────────────────────────────

class TestStartupSequenceOrdering:

    def test_initialization_runs_after_camera_startup_when_fast(self):
        stub = _make_stub(cam_duration=0.0)
        ss.SplashScreen._startup_sequence(stub)
        assert stub._call_order == ["camera_startup_done", "run_initialization"]

    def test_initialization_always_runs_even_when_camera_startup_times_out(self):
        stub = _make_stub(cam_duration=99.0)
        with patch.object(ss, "CAMERA_STARTUP_TIMEOUT_SECONDS", 0.05):
            ss.SplashScreen._startup_sequence(stub)
        assert "run_initialization" in stub._call_order

    def test_degraded_log_emitted_on_timeout(self):
        stub = _make_stub(cam_duration=99.0)
        with patch.object(ss, "CAMERA_STARTUP_TIMEOUT_SECONDS", 0.05):
            ss.SplashScreen._startup_sequence(stub)
        stub._update_log.assert_called_once()
        assert "degraded" in stub._update_log.call_args[0][0].lower()

    def test_no_degraded_log_when_startup_completes_in_time(self):
        stub = _make_stub(cam_duration=0.0)
        ss.SplashScreen._startup_sequence(stub)
        stub._update_log.assert_not_called()

    def test_degraded_status_updated_on_timeout(self):
        stub = _make_stub(cam_duration=99.0)
        with patch.object(ss, "CAMERA_STARTUP_TIMEOUT_SECONDS", 0.05):
            ss.SplashScreen._startup_sequence(stub)
        stub._update_status.assert_called_once()
        args = stub._update_status.call_args[0]
        assert "degraded" in args[0].lower()


# ── Tests: timeout constant and thread structure ──────────────────────────────

class TestStartupCameraTimeout:

    def test_timeout_constant_is_10_seconds(self):
        assert ss.CAMERA_STARTUP_TIMEOUT_SECONDS == 10

    def test_start_initialization_spawns_one_thread_targeting_startup_sequence(self):
        stub = MagicMock()
        captured: list[dict] = []

        def _capture_thread(**kwargs):
            captured.append(kwargs)
            t = MagicMock()
            t.start = MagicMock()
            return t

        with patch("ui.splash_screen.threading.Thread", side_effect=_capture_thread):
            ss.SplashScreen._start_initialization(stub)

        assert len(captured) == 1
        assert captured[0]["target"] == stub._startup_sequence


# ── Tests: _startup_cameras logs and commands ─────────────────────────────────

class TestStartupCamerasLogs:

    def test_startup_cameras_logs_each_step_when_in_standby(self, caplog):
        stub = MagicMock()
        stub._query_camera_powered.return_value = False  # cameras in standby
        with caplog.at_level(logging.INFO, logger="ui.splash_screen"):
            with patch("ui.splash_screen.time.sleep"):
                ss.SplashScreen._startup_cameras(stub)

        messages = [r.message for r in caplog.records]
        assert any("Power ON" in m and "CAM1" in m for m in messages)
        assert any("Power ON" in m and "CAM2" in m for m in messages)
        assert any("Home" in m and "CAM1" in m for m in messages)
        assert any("Home" in m and "CAM2" in m for m in messages)
        assert any("complete" in m for m in messages)

    def test_startup_cameras_sends_power_on_to_both_when_in_standby(self):
        stub = MagicMock()
        stub._query_camera_powered.return_value = False  # cameras in standby
        with patch("ui.splash_screen.time.sleep"):
            ss.SplashScreen._startup_cameras(stub)
        assert stub._power_on_camera.call_count == 2

    def test_startup_cameras_sends_home_to_both_when_in_standby(self):
        stub = MagicMock()
        stub._query_camera_powered.return_value = False  # cameras in standby
        with patch("ui.splash_screen.time.sleep"):
            ss.SplashScreen._startup_cameras(stub)
        assert stub._home_camera.call_count == 2

    def test_startup_cameras_skips_power_on_when_already_on(self):
        stub = MagicMock()
        stub._query_camera_powered.return_value = True  # cameras already on
        with patch("ui.splash_screen.time.sleep"):
            ss.SplashScreen._startup_cameras(stub)
        stub._power_on_camera.assert_not_called()

    def test_startup_cameras_skips_home_when_already_on(self):
        stub = MagicMock()
        stub._query_camera_powered.return_value = True  # cameras already on
        with patch("ui.splash_screen.time.sleep"):
            ss.SplashScreen._startup_cameras(stub)
        stub._home_camera.assert_not_called()

    def test_startup_cameras_logs_skip_when_already_on(self, caplog):
        stub = MagicMock()
        stub._query_camera_powered.return_value = True  # cameras already on
        with caplog.at_level(logging.INFO, logger="ui.splash_screen"):
            with patch("ui.splash_screen.time.sleep"):
                ss.SplashScreen._startup_cameras(stub)

        messages = [r.message for r in caplog.records]
        assert any("already powered" in m and "CAM1" in m for m in messages)
        assert any("already powered" in m and "CAM2" in m for m in messages)

