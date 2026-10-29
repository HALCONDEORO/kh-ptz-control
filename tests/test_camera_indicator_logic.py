#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_camera_indicator_logic.py — Tests for CameraIndicator blink state machine
and set_mode geometry.

All methods are exercised as unbound functions with a MagicMock stub acting as
self.  No QApplication is instantiated.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock



# ── Qt stubs ──────────────────────────────────────────────────────────────────

def _ensure_stubs() -> None:
    for mod in (
        "PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui",
    ):
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)

    qtc = sys.modules["PyQt5.QtCore"]
    for attr in ("Qt", "QTimer", "QPointF"):
        if not hasattr(qtc, attr):
            setattr(qtc, attr, MagicMock())

    qtw = sys.modules["PyQt5.QtWidgets"]
    if not hasattr(qtw, "QWidget"):
        qtw.QWidget = MagicMock  # type: ignore[attr-defined]

    qtg = sys.modules["PyQt5.QtGui"]
    for attr in (
        "QPainter", "QColor", "QLinearGradient", "QRadialGradient",
        "QPolygonF", "QBrush",
    ):
        if not hasattr(qtg, attr):
            setattr(qtg, attr, MagicMock)
    sys.modules["PyQt5"].QtGui = qtg  # type: ignore[attr-defined]


_ensure_stubs()

import ui.camera_indicator as _ci  # noqa: E402
from ui.camera_indicator import _GEO_PLATFORM, _GEO_COMMENTS  # noqa: E402


# ── Stub factory ──────────────────────────────────────────────────────────────

def _stub(mode: str = "platform", blink_on: bool = True,
          blink_count: int = 0) -> MagicMock:
    s = MagicMock()
    s._mode = mode
    s._blink_on = blink_on
    s._blink_count = blink_count
    s._BLINK_TOGGLES = _ci.CameraIndicator._BLINK_TOGGLES
    return s


# ── _toggle_blink ─────────────────────────────────────────────────────────────

class TestToggleBlink:
    def test_increments_count(self):
        s = _stub(blink_count=0)
        _ci.CameraIndicator._toggle_blink(s)
        assert s._blink_count == 1

    def test_flips_on_to_off(self):
        s = _stub(blink_on=True)
        _ci.CameraIndicator._toggle_blink(s)
        assert s._blink_on is False

    def test_flips_off_to_on(self):
        s = _stub(blink_on=False)
        _ci.CameraIndicator._toggle_blink(s)
        assert s._blink_on is True

    def test_stops_timer_at_limit(self):
        limit = _ci.CameraIndicator._BLINK_TOGGLES
        s = _stub(blink_count=limit - 1)
        _ci.CameraIndicator._toggle_blink(s)
        s._timer.stop.assert_called_once()

    def test_blink_on_fixed_true_after_stop(self):
        limit = _ci.CameraIndicator._BLINK_TOGGLES
        s = _stub(blink_count=limit - 1, blink_on=False)
        _ci.CameraIndicator._toggle_blink(s)
        assert s._blink_on is True

    def test_timer_not_stopped_before_limit(self):
        s = _stub(blink_count=0)
        _ci.CameraIndicator._toggle_blink(s)
        s._timer.stop.assert_not_called()

    def test_update_called(self):
        s = _stub()
        _ci.CameraIndicator._toggle_blink(s)
        s.update.assert_called_once()

    def test_count_below_limit_does_not_stop(self):
        limit = _ci.CameraIndicator._BLINK_TOGGLES
        s = _stub(blink_count=limit - 2)
        _ci.CameraIndicator._toggle_blink(s)
        s._timer.stop.assert_not_called()


# ── _restart_blink ────────────────────────────────────────────────────────────

class TestRestartBlink:
    def test_stops_then_restarts_timer_with_500ms(self):
        s = _stub()
        _ci.CameraIndicator._restart_blink(s)
        s._timer.stop.assert_called_once()
        s._timer.start.assert_called_once_with(500)

    def test_resets_blink_on_to_true(self):
        s = _stub(blink_on=False)
        _ci.CameraIndicator._restart_blink(s)
        assert s._blink_on is True

    def test_resets_blink_count_to_zero(self):
        s = _stub(blink_count=4)
        _ci.CameraIndicator._restart_blink(s)
        assert s._blink_count == 0


# ── set_mode ──────────────────────────────────────────────────────────────────

class TestSetMode:
    def test_platform_sets_platform_geometry(self):
        s = _stub()
        _ci.CameraIndicator.set_mode(s, "platform")
        s.setGeometry.assert_called_once_with(*_GEO_PLATFORM)

    def test_comments_sets_comments_geometry(self):
        s = _stub()
        _ci.CameraIndicator.set_mode(s, "comments")
        s.setGeometry.assert_called_once_with(*_GEO_COMMENTS)

    def test_platform_and_comments_geometries_are_different(self):
        assert _GEO_PLATFORM != _GEO_COMMENTS

    def test_mode_stored(self):
        s = _stub(mode="platform")
        _ci.CameraIndicator.set_mode(s, "comments")
        assert s._mode == "comments"

    def test_restart_blink_called(self):
        s = _stub()
        _ci.CameraIndicator.set_mode(s, "platform")
        s._restart_blink.assert_called_once()

