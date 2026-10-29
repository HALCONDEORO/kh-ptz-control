#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_sim_debug_panel.py — simulation/debug_panel.py had no coverage
#
# The sim debug label is the only readout of what the simulated cameras are
# doing, so it is what a developer trusts when checking a VISCA change without
# hardware. Worth pinning down:
#
#   - it reads the camera under the simulator's lock. The mock server mutates
#     pan/tilt/zoom from its own socket thread, so an unlocked read can show a
#     half-applied move and send someone chasing a protocol bug that is not there.
#   - it follows the camera selection, and tolerates a simulator that has not
#     published a camera yet (a server that failed to bind) instead of raising
#     inside a timer callback, where an exception has nowhere to go.

from __future__ import annotations

import sys
import threading

import pytest

pytest.importorskip("PyQt5")

from conftest import ensure_real_qt        # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _real_qt():
    ensure_real_qt()


@pytest.fixture
def qapp(_real_qt):
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


class _LockSpy:
    """A real lock that records whether it was held."""

    def __init__(self):
        self._lock = threading.RLock()
        self.entered = 0
        self.held_now = False

    def __enter__(self):
        self._lock.acquire()
        self.entered += 1
        self.held_now = True
        return self

    def __exit__(self, *exc):
        self.held_now = False
        self._lock.release()
        return False


class _SimCameraDouble:
    def __init__(self, zoom=0, pan=0, tilt=0, pan_spd=0, tilt_spd=0, last_cmd=""):
        self.zoom = zoom
        self.pan = pan
        self.tilt = tilt
        self.pan_spd = pan_spd
        self.tilt_spd = tilt_spd
        self.last_cmd = last_cmd
        self._lock = _LockSpy()


class _MainWindowDouble:
    def __init__(self, cam1_selected: bool = True):
        self.Cam1 = type("Toggle", (), {"isChecked": lambda _self: cam1_selected})()


@pytest.fixture
def panel(qapp, monkeypatch):
    """Attach the panel to a throwaway layout and expose its parts."""
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

    import adapters.hardware_simulator as hw
    import simulation.debug_panel as debug_panel

    def _attach(main_window, cam1=None, cam2=None):
        monkeypatch.setattr(hw, "active_cam1", cam1, raising=False)
        monkeypatch.setattr(hw, "active_cam2", cam2, raising=False)
        host = QWidget()
        layout = QVBoxLayout(host)
        debug_panel.attach_sim_debug_panel(layout, main_window)
        label = host.findChildren(QLabel)[-1]
        timer = host.findChild(QTimer)
        return host, label, timer

    return _attach


class TestAttachment:
    def test_a_label_is_added(self, panel):
        host, label, timer = panel(_MainWindowDouble())
        assert label is not None

    def test_the_label_starts_empty(self, panel):
        """Nothing is known until the first refresh."""
        host, label, timer = panel(_MainWindowDouble())
        assert label.text() == ""

    def test_a_refresh_timer_is_running(self, panel):
        host, label, timer = panel(_MainWindowDouble())
        assert timer is not None
        assert timer.isActive()

    def test_the_refresh_rate_stays_readable(self, panel):
        """Fast enough to follow a PTZ move, slow enough not to spin the GUI
        thread on a Pi."""
        host, label, timer = panel(_MainWindowDouble())
        assert timer.interval() == 150

    def test_the_timer_is_owned_by_the_panel(self, panel):
        """An unparented QTimer is collected as soon as the local goes out of
        scope and the readout silently stops updating."""
        host, label, timer = panel(_MainWindowDouble())
        assert timer.parent() is not None


class TestReadout:
    def test_zoom_is_shown_as_a_percentage(self, panel):
        cam = _SimCameraDouble(zoom=0x2000)          # half of 0x4000
        host, label, timer = panel(_MainWindowDouble(), cam1=cam)
        timer.timeout.emit()
        assert "zoom   50%" in label.text()

    def test_pan_and_tilt_are_signed(self, panel):
        """The sign is the direction — an unsigned readout is useless."""
        cam = _SimCameraDouble(pan=-1200, tilt=340)
        host, label, timer = panel(_MainWindowDouble(), cam1=cam)
        timer.timeout.emit()
        text = label.text()
        assert "-1200" in text
        assert "+340" in text

    def test_speeds_are_shown(self, panel):
        cam = _SimCameraDouble(pan_spd=12, tilt_spd=3)
        host, label, timer = panel(_MainWindowDouble(), cam1=cam)
        timer.timeout.emit()
        assert "spd 12" in label.text()
        assert "spd  3" in label.text()

    def test_the_last_command_is_shown(self, panel):
        cam = _SimCameraDouble(last_cmd="8101040702FF")
        host, label, timer = panel(_MainWindowDouble(), cam1=cam)
        timer.timeout.emit()
        assert "8101040702FF" in label.text()

    def test_no_command_yet_is_shown_as_a_dash(self, panel):
        """An empty line reads as a broken panel."""
        cam = _SimCameraDouble(last_cmd="")
        host, label, timer = panel(_MainWindowDouble(), cam1=cam)
        timer.timeout.emit()
        assert "cmd   -" in label.text()

    def test_the_readout_follows_the_camera(self, panel):
        cam = _SimCameraDouble(zoom=0)
        host, label, timer = panel(_MainWindowDouble(), cam1=cam)
        timer.timeout.emit()
        cam.zoom = 0x4000
        timer.timeout.emit()
        assert "zoom  100%" in label.text()


class TestCameraSelection:
    def test_the_selected_camera_is_read(self, panel):
        cam1 = _SimCameraDouble(last_cmd="FROM-CAM1")
        cam2 = _SimCameraDouble(last_cmd="FROM-CAM2")
        host, label, timer = panel(_MainWindowDouble(cam1_selected=True), cam1, cam2)
        timer.timeout.emit()
        assert "FROM-CAM1" in label.text()

    def test_deselecting_camera_one_reads_camera_two(self, panel):
        cam1 = _SimCameraDouble(last_cmd="FROM-CAM1")
        cam2 = _SimCameraDouble(last_cmd="FROM-CAM2")
        host, label, timer = panel(_MainWindowDouble(cam1_selected=False), cam1, cam2)
        timer.timeout.emit()
        assert "FROM-CAM2" in label.text()


class TestThreadSafety:
    def test_the_camera_is_read_under_its_lock(self, panel):
        """The mock server mutates this state from its socket thread."""
        cam = _SimCameraDouble(pan=5)
        host, label, timer = panel(_MainWindowDouble(), cam1=cam)
        timer.timeout.emit()
        assert cam._lock.entered == 1

    def test_the_lock_is_released_again(self, panel):
        cam = _SimCameraDouble()
        host, label, timer = panel(_MainWindowDouble(), cam1=cam)
        timer.timeout.emit()
        timer.timeout.emit()
        assert cam._lock.held_now is False
        assert cam._lock.entered == 2


class TestMissingSimulator:
    def test_no_published_camera_leaves_the_label_alone(self, panel):
        """A sim server that failed to bind publishes nothing; raising here
        would raise inside a Qt timer callback, where nothing can handle it."""
        host, label, timer = panel(_MainWindowDouble(), cam1=None)
        timer.timeout.emit()
        assert label.text() == ""

    def test_a_missing_second_camera_is_also_tolerated(self, panel):
        host, label, timer = panel(_MainWindowDouble(cam1_selected=False), cam1=None, cam2=None)
        timer.timeout.emit()
        assert label.text() == ""

    def test_a_later_publication_is_picked_up(self, panel):
        """attach happens at UI build time, which can precede the sim servers."""
        import adapters.hardware_simulator as hw
        host, label, timer = panel(_MainWindowDouble(), cam1=None)
        timer.timeout.emit()
        hw.active_cam1 = _SimCameraDouble(last_cmd="LATE")
        try:
            timer.timeout.emit()
            assert "LATE" in label.text()
        finally:
            hw.active_cam1 = None


class TestProductionIsolation:
    def test_the_simulator_is_not_imported_by_the_production_panel(self):
        """The reason this module exists: ui/right_panel.py must not pull
        hardware_simulator into a production install."""
        from pathlib import Path
        source = Path(__file__).resolve().parent.parent / "ui" / "right_panel.py"
        text = source.read_text(encoding="utf-8")
        offending = [
            line for line in text.splitlines()
            if "hardware_simulator" in line and not line.lstrip().startswith("#")
        ]
        assert not offending, offending
