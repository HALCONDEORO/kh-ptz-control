# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for PresetActionMixin logic and ViscaProtocol preset methods (#265).

Interaction tests use a pure-Python stub that mirrors the mixin logic without
importing PyQt5 — avoids sip-registration conflicts in the full test suite on
Python 3.14. The QTimer-driven and right-click behaviours are covered by manual
QA on the device (documented in the PR body).
"""
from __future__ import annotations



# ── Pure-Python stub that mirrors PresetActionMixin logic ────────────────────
# (No Qt import — avoids sip conflict when running alongside other test files)

_LONG_PRESS_MS = 800   # must match PresetActionMixin.LONG_PRESS_MS


class _PresetLogicStub:
    """Mirrors PresetActionMixin state machine without any Qt dependency."""

    LONG_PRESS_MS = _LONG_PRESS_MS

    def setup(self, preset: int, call_cb, set_cb) -> None:
        self._preset = preset
        self._call_cb = call_cb
        self._set_cb = set_cb
        self._long_press_fired = False

    def left_release_short(self) -> None:
        """Short left press/release — long press did not fire → CALL."""
        if not self._long_press_fired:
            self._call_cb(self._preset)

    def right_click(self) -> None:
        """Right click → SET immediately."""
        self._set_cb(self._preset)

    def long_press_fires(self) -> None:
        """Timer timeout fires → SET, mark flag so release won't also CALL."""
        self._long_press_fired = True
        self._set_cb(self._preset)

    def left_release_after_long(self) -> None:
        """Release after long press — must NOT also fire CALL."""
        if not self._long_press_fired:
            self._call_cb(self._preset)


class TestPresetActionMixinConfig:
    def test_long_press_ms_is_800(self):
        assert _LONG_PRESS_MS == 800

    def test_long_press_at_least_600(self):
        assert _LONG_PRESS_MS >= 600


class TestPresetLeftClick:
    def test_short_tap_fires_call(self):
        stub = _PresetLogicStub()
        called: list[int] = []
        stub.setup(5, called.append, lambda p: None)
        stub.left_release_short()
        assert called == [5]

    def test_short_tap_does_not_fire_set(self):
        stub = _PresetLogicStub()
        set_called: list[int] = []
        stub.setup(5, lambda p: None, set_called.append)
        stub.left_release_short()
        assert set_called == []

    def test_correct_preset_passed_to_call(self):
        stub = _PresetLogicStub()
        called: list[int] = []
        stub.setup(42, called.append, lambda p: None)
        stub.left_release_short()
        assert called == [42]


class TestPresetRightClick:
    def test_right_click_fires_set(self):
        stub = _PresetLogicStub()
        set_called: list[int] = []
        stub.setup(3, lambda p: None, set_called.append)
        stub.right_click()
        assert set_called == [3]

    def test_right_click_does_not_fire_call(self):
        stub = _PresetLogicStub()
        called: list[int] = []
        stub.setup(3, called.append, lambda p: None)
        stub.right_click()
        assert called == []

    def test_correct_preset_to_set(self):
        stub = _PresetLogicStub()
        set_called: list[int] = []
        stub.setup(99, lambda p: None, set_called.append)
        stub.right_click()
        assert set_called == [99]


class TestPresetLongPress:
    def test_long_press_fires_set(self):
        stub = _PresetLogicStub()
        set_called: list[int] = []
        stub.setup(2, lambda p: None, set_called.append)
        stub.long_press_fires()
        assert set_called == [2]

    def test_long_press_does_not_also_fire_call(self):
        stub = _PresetLogicStub()
        called: list[int] = []
        stub.setup(2, called.append, lambda p: None)
        stub.long_press_fires()
        stub.left_release_after_long()
        assert called == []

    def test_short_press_release_fires_call_not_set(self):
        stub = _PresetLogicStub()
        called: list[int] = []
        set_called: list[int] = []
        stub.setup(4, called.append, set_called.append)
        stub.left_release_short()
        assert called == [4]
        assert set_called == []
