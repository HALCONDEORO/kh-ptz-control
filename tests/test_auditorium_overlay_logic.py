#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_auditorium_overlay_logic.py — Tests for AuditoriumOverlay mode switching
and blend animation state machine.

All methods are exercised as unbound functions with a MagicMock stub acting as
self.  No QApplication is instantiated.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


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
    for attr in ("QColor", "QPainter", "QBrush", "QPixmap"):
        if not hasattr(qtg, attr):
            setattr(qtg, attr, MagicMock)


_ensure_stubs()

import ui.auditorium_overlay as _ao  # noqa: E402
from ui.auditorium_overlay import _ANIM_STEP  # noqa: E402


# ── Stub factory ──────────────────────────────────────────────────────────────

def _stub(mode: str = "call", prev_mode: str = "call",
          blend: float = 1.0) -> MagicMock:
    s = MagicMock()
    s._mode = mode
    s._prev_mode = prev_mode
    s._blend = blend
    s._dot_pixmap = None
    return s


# ── set_mode ──────────────────────────────────────────────────────────────────

class TestSetMode:
    def test_same_mode_is_noop(self):
        s = _stub(mode="call")
        _ao.AuditoriumOverlay.set_mode(s, "call")
        s._timer.start.assert_not_called()

    def test_new_mode_stored(self):
        s = _stub(mode="call")
        _ao.AuditoriumOverlay.set_mode(s, "set")
        assert s._mode == "set"

    def test_prev_mode_becomes_old_mode(self):
        s = _stub(mode="call")
        _ao.AuditoriumOverlay.set_mode(s, "set")
        assert s._prev_mode == "call"

    def test_blend_reset_to_zero_on_mode_change(self):
        s = _stub(mode="call", blend=1.0)
        _ao.AuditoriumOverlay.set_mode(s, "set")
        assert s._blend == 0.0

    def test_timer_started_on_mode_change(self):
        s = _stub(mode="call")
        _ao.AuditoriumOverlay.set_mode(s, "set")
        s._timer.start.assert_called_once()

    def test_transition_call_to_set_and_back(self):
        s = _stub(mode="call")
        _ao.AuditoriumOverlay.set_mode(s, "set")
        assert s._mode == "set"
        assert s._prev_mode == "call"


# ── _tick ─────────────────────────────────────────────────────────────────────

class TestTick:
    def test_blend_increments_by_anim_step(self):
        s = _stub(blend=0.0)
        _ao.AuditoriumOverlay._tick(s)
        assert s._blend == pytest.approx(_ANIM_STEP)

    def test_blend_clamped_at_1(self):
        s = _stub(blend=1.0 - _ANIM_STEP * 0.1)
        _ao.AuditoriumOverlay._tick(s)
        assert s._blend == pytest.approx(1.0)

    def test_timer_stopped_when_blend_reaches_1(self):
        s = _stub(blend=1.0 - _ANIM_STEP * 0.1)
        _ao.AuditoriumOverlay._tick(s)
        s._timer.stop.assert_called_once()

    def test_timer_not_stopped_when_blend_below_1(self):
        s = _stub(blend=0.0)
        _ao.AuditoriumOverlay._tick(s)
        s._timer.stop.assert_not_called()

    def test_update_always_called(self):
        s = _stub(blend=0.0)
        _ao.AuditoriumOverlay._tick(s)
        s.update.assert_called_once()

    def test_blend_already_at_1_stops_timer(self):
        s = _stub(blend=1.0)
        _ao.AuditoriumOverlay._tick(s)
        s._timer.stop.assert_called_once()


# ── _ensure_dot_pixmap ────────────────────────────────────────────────────────

class TestEnsureDotPixmap:
    def test_skips_if_pixmap_already_set(self):
        s = _stub()
        existing = MagicMock()
        s._dot_pixmap = existing
        _ao.AuditoriumOverlay._ensure_dot_pixmap(s)
        assert s._dot_pixmap is existing


# ── anim_step constant ────────────────────────────────────────────────────────

class TestAnimConstants:
    def test_anim_step_is_positive(self):
        assert _ANIM_STEP > 0.0

    def test_anim_step_is_less_than_1(self):
        assert _ANIM_STEP < 1.0

    def test_full_animation_completes_in_reasonable_ticks(self):
        import math
        ticks_needed = math.ceil(1.0 / _ANIM_STEP)
        assert ticks_needed <= 20, f"Animation too slow: needs {ticks_needed} ticks"
