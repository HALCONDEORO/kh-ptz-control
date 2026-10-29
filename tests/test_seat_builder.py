#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_seat_builder.py — Tests for seat_builder factory and SVG pixmap loader.

build_special_seat_button() is tested via a fake SpecialDragButton so that
the geometry, icon-loading and key-lookup paths are exercised without a
real QApplication.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ── Qt stubs ──────────────────────────────────────────────────────────────────

def _ensure_stubs() -> None:
    for mod in (
        "PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets",
        "PyQt5.QtGui", "PyQt5.QtSvg",
    ):
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)

    qtc = sys.modules["PyQt5.QtCore"]
    for attr in ("Qt", "QByteArray", "QRectF", "QSize"):
        if not hasattr(qtc, attr):
            setattr(qtc, attr, MagicMock())
    sys.modules["PyQt5"].QtCore = qtc  # type: ignore[attr-defined]

    qtg = sys.modules["PyQt5.QtGui"]
    for attr in ("QIcon",):
        if not hasattr(qtg, attr):
            setattr(qtg, attr, MagicMock)
    # QPainter and QPixmap must NOT be bare MagicMock classes because Python
    # mock treats the first positional argument as `spec`; use a factory lambda.
    if not hasattr(qtg, "QPixmap"):
        qtg.QPixmap = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    if not hasattr(qtg, "QPainter"):
        qtg.QPainter = lambda *a, **kw: MagicMock()  # type: ignore[attr-defined]
    sys.modules["PyQt5"].QtGui = qtg  # type: ignore[attr-defined]

    qtsvg = sys.modules["PyQt5.QtSvg"]
    if not hasattr(qtsvg, "QSvgRenderer"):
        qtsvg.QSvgRenderer = MagicMock  # type: ignore[attr-defined]

    qtw = sys.modules["PyQt5.QtWidgets"]
    if not hasattr(qtw, "QWidget"):
        qtw.QWidget = MagicMock  # type: ignore[attr-defined]


_ensure_stubs()

# ── Minimal SpecialDragButton stand-in ────────────────────────────────────────

class _FakeDragButton:
    """Records calls to the geometry/icon methods exercised by build_special_seat_button."""

    def __init__(self, seat_id=None, default_label=None, parent=None):
        self.seat_id = seat_id
        self.default_label = default_label
        self.parent = parent
        self.moved_to = None
        self.resized_to = None
        self.icon_size = None
        self.icon_set = None
        self.tool_button_style = None
        self._style_applied = False

    def move(self, x, y):          self.moved_to = (x, y)
    def resize(self, w, h):        self.resized_to = (w, h)
    def setToolButtonStyle(self, s): self.tool_button_style = s
    def _apply_style(self):        self._style_applied = True
    def setIcon(self, icon):       self.icon_set = icon
    def setIconSize(self, size):   self.icon_size = size


# Inject stubs for seat_builder's dependencies before import.
# We patch at the sys.modules level so seat_builder.py picks up our fakes
# without needing a real QApplication or real widget hierarchy.
_injected_widgets_stub = "ui.widgets" not in sys.modules
if _injected_widgets_stub:
    _widgets_mod = types.ModuleType("ui.widgets")
    _widgets_mod.SpecialDragButton = _FakeDragButton  # type: ignore[attr-defined]
    sys.modules["ui.widgets"] = _widgets_mod

_injected_icons_stub = "ui.platform_icons" not in sys.modules
if _injected_icons_stub:
    _icons_mod = types.ModuleType("ui.platform_icons")
    _icons_mod.SVG_WHEELCHAIR = "<svg xmlns='http://www.w3.org/2000/svg'></svg>"  # type: ignore[attr-defined]
    sys.modules["ui.platform_icons"] = _icons_mod


import ui.seat_builder as _sb  # noqa: E402

# ui.seat_builder's `from ui.widgets import SpecialDragButton` already bound the
# fake into its own namespace above — sys.modules doesn't need to stay stubbed
# after that. Pop what we injected so we don't poison any other test file
# collected afterward in the same process that needs the real ui.widgets (e.g.
# test_seat_names_mixin.py, alphabetically right after this file).
if _injected_widgets_stub:
    sys.modules.pop("ui.widgets", None)
if _injected_icons_stub:
    sys.modules.pop("ui.platform_icons", None)


# ── _load_svg_pixmap ──────────────────────────────────────────────────────────

class TestLoadSvgPixmap:
    def test_returns_none_when_no_source(self):
        result = _sb._load_svg_pixmap(None, None, 40, 40)
        assert result is None

    def test_returns_none_for_invalid_renderer(self):
        invalid_renderer = MagicMock()
        invalid_renderer.isValid.return_value = False
        renderer_cls = MagicMock()
        renderer_cls.return_value = invalid_renderer

        orig = _sb.QSvgRenderer
        _sb.QSvgRenderer = renderer_cls
        try:
            result = _sb._load_svg_pixmap(None, "missing.svg", 40, 40)
        finally:
            _sb.QSvgRenderer = orig
        assert result is None

    def test_svg_data_path_takes_priority_over_file(self):
        # When svg_data is provided, only the svg_data branch runs — the svg_file
        # path is ignored.  We verify by injecting an invalid renderer when the
        # file path would be used.  Since svg_data is checked first, the file path
        # is never opened.
        invalid_renderer = MagicMock()
        invalid_renderer.isValid.return_value = False
        renderer_cls = MagicMock()
        renderer_cls.return_value = invalid_renderer

        orig = _sb.QSvgRenderer
        _sb.QSvgRenderer = renderer_cls
        try:
            # svg_data is non-empty → svg_file "should_be_ignored.svg" is never opened
            _sb._load_svg_pixmap("<svg></svg>", "should_be_ignored.svg", 40, 40)
        finally:
            _sb.QSvgRenderer = orig

        # QSvgRenderer was called exactly once — with the svg_data bytes, not file path
        renderer_cls.assert_called_once()


# ── build_special_seat_button ─────────────────────────────────────────────────

class TestBuildSpecialSeatButton:
    def _build(self, seat: int, x: int = 10, y: int = 20) -> _FakeDragButton:
        with patch.object(_sb, "SpecialDragButton", _FakeDragButton), \
             patch.object(_sb, "_load_svg_pixmap", return_value=None):
            return _sb.build_special_seat_button(seat, x=x, y=y, parent=None)

    def test_known_seats_return_a_button(self):
        for seat in (128, 129, 130, 131):
            btn = self._build(seat)
            assert btn is not None

    def test_unknown_seat_raises_key_error(self):
        with pytest.raises(KeyError):
            self._build(999)

    def test_button_positioned_correctly(self):
        btn = self._build(128, x=5, y=15)
        assert btn.moved_to == (5, 15)

    def test_button_resized(self):
        btn = self._build(128)
        assert btn.resized_to is not None
        w, h = btn.resized_to
        assert w > 0 and h > 0

    def test_apply_style_called(self):
        btn = self._build(128)
        assert btn._style_applied

    def test_seat_128_is_wheelchair(self):
        btn = self._build(128)
        assert btn.default_label == "Wheelchair"

    def test_seat_129_is_second_room(self):
        btn = self._build(129)
        assert btn.default_label == "2nd Room"

    def test_seat_130_is_wheelchair(self):
        btn = self._build(130)
        assert btn.default_label == "Wheelchair"

    def test_seat_131_is_library(self):
        btn = self._build(131)
        assert btn.default_label == "Library"

    def test_seat_id_stored(self):
        btn = self._build(128)
        assert btn.seat_id == 128

    def test_all_special_seat_numbers_defined(self):
        assert set(_sb._SPECIAL_SEAT_DEFS.keys()) == {128, 129, 130, 131}
