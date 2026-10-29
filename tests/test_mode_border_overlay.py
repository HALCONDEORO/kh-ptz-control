#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_mode_border_overlay.py — Unit tests for ModeBorderOverlay state logic.

Tests cover set_mode(), _tick() and the animation state machine.
All methods are exercised as unbound functions; no QApplication required.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock



# ── Qt stubs ──────────────────────────────────────────────────────────────────

def _ensure_stubs() -> None:
    for mod in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui"):
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)

    qtc = sys.modules["PyQt5.QtCore"]
    for a in ("Qt", "QTimer"):
        if not hasattr(qtc, a):
            setattr(qtc, a, MagicMock())

    qtw = sys.modules["PyQt5.QtWidgets"]
    if not hasattr(qtw, "QWidget"):
        qtw.QWidget = MagicMock  # type: ignore[attr-defined]

    qtg = sys.modules["PyQt5.QtGui"]
    for a in ("QColor", "QPainter"):
        if not hasattr(qtg, a):
            setattr(qtg, a, MagicMock)


_ensure_stubs()

import ui.mode_border_overlay as _mbo  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _stub(mode: str = "call", blend: float = 1.0, prev_mode: str = "call") -> MagicMock:
    stub = MagicMock()
    stub._mode      = mode
    stub._prev_mode = prev_mode
    stub._blend     = blend
    return stub


# ══════════════════════════════════════════════════════════════════════════════
#  set_mode()
# ══════════════════════════════════════════════════════════════════════════════

class TestSetMode:
    """set_mode() starts animation when the mode changes."""

    def test_same_mode_is_noop(self):
        stub = _stub(mode="call")
        _mbo.ModeBorderOverlay.set_mode(stub, "call")
        stub._timer.start.assert_not_called()

    def test_different_mode_starts_timer(self):
        stub = _stub(mode="call")
        _mbo.ModeBorderOverlay.set_mode(stub, "set")
        stub._timer.start.assert_called_once()

    def test_mode_updated_to_new_value(self):
        stub = _stub(mode="call")
        _mbo.ModeBorderOverlay.set_mode(stub, "set")
        assert stub._mode == "set"

    def test_prev_mode_stores_old_value(self):
        stub = _stub(mode="call")
        _mbo.ModeBorderOverlay.set_mode(stub, "set")
        assert stub._prev_mode == "call"

    def test_blend_reset_to_zero_on_mode_change(self):
        stub = _stub(mode="call", blend=0.8)
        _mbo.ModeBorderOverlay.set_mode(stub, "set")
        assert stub._blend == 0.0

    def test_blend_unchanged_when_same_mode(self):
        stub = _stub(mode="call", blend=0.5)
        _mbo.ModeBorderOverlay.set_mode(stub, "call")
        assert stub._blend == 0.5


# ══════════════════════════════════════════════════════════════════════════════
#  _tick()
# ══════════════════════════════════════════════════════════════════════════════

class TestTick:
    """_tick() advances the blend animation and stops at completion."""

    def test_blend_increments(self):
        stub = _stub(blend=0.0)
        _mbo.ModeBorderOverlay._tick(stub)
        assert stub._blend > 0.0

    def test_blend_clamped_at_one(self):
        stub = _stub(blend=0.99)
        _mbo.ModeBorderOverlay._tick(stub)
        assert stub._blend <= 1.0

    def test_timer_stopped_when_blend_reaches_one(self):
        stub = _stub(blend=0.99)
        _mbo.ModeBorderOverlay._tick(stub)
        stub._timer.stop.assert_called_once()

    def test_timer_not_stopped_before_blend_reaches_one(self):
        stub = _stub(blend=0.0)
        _mbo.ModeBorderOverlay._tick(stub)
        stub._timer.stop.assert_not_called()

    def test_update_called_each_tick(self):
        stub = _stub(blend=0.3)
        _mbo.ModeBorderOverlay._tick(stub)
        stub.update.assert_called_once()

    def test_full_animation_sequence_completes(self):
        """Simulate many ticks until blend reaches 1.0."""
        stub = _stub(blend=0.0)
        for _ in range(100):
            _mbo.ModeBorderOverlay._tick(stub)
            if stub._blend >= 1.0:
                break
        assert stub._blend >= 1.0
        stub._timer.stop.assert_called()


# ══════════════════════════════════════════════════════════════════════════════
#  Module-level constants
# ══════════════════════════════════════════════════════════════════════════════

class TestModuleConstants:
    def test_border_px_positive(self):
        assert _mbo._BORDER_PX > 0

    def test_anim_step_positive(self):
        assert _mbo._ANIM_STEP > 0

    def test_anim_step_less_than_one(self):
        """Step < 1 ensures animation takes multiple frames."""
        assert _mbo._ANIM_STEP < 1.0

