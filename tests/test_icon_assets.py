#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_icon_assets.py — Tests for UI icon asset structure (#185).

Verifies that:
- Required SVG source files exist.
- The icon loader module is importable and has the expected constants.
- get_icon() returns gracefully (empty QIcon) when PNGs are absent.
- required_png_paths() covers all P1 icons at all required sizes.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path


# ── Qt stub (no display needed) ───────────────────────────────────────────────

for mod in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtGui", "PyQt5.QtWidgets"):
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)

_qtg = sys.modules["PyQt5.QtGui"]
if not hasattr(_qtg, "QIcon"):
    class _FakeQIcon:
        def __init__(self, path: str = ""):
            self._path = path
        def isNull(self):
            return not self._path
    _qtg.QIcon = _FakeQIcon


# ── Module under test ─────────────────────────────────────────────────────────

sys.modules.pop("ui.icon_loader", None)
import ui.icon_loader as il  # noqa: E402

_SVG_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons" / "svg"
_PNG_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons" / "png"

_P1_ICONS = [
    il.ICON_SETTINGS,
    il.ICON_CAMERA,
    il.ICON_SAVE,
    il.ICON_DELETE,
    il.ICON_WARNING,
    il.ICON_REFRESH,
    il.ICON_LOCK,
    il.ICON_DATA,
]


# ── SVG source files ──────────────────────────────────────────────────────────

class TestSvgSources:

    def test_svg_directory_exists(self):
        assert _SVG_DIR.is_dir(), f"assets/icons/svg/ not found at {_SVG_DIR}"

    def test_p1_svg_files_exist(self):
        missing = [name for name in _P1_ICONS if not (_SVG_DIR / f"{name}.svg").exists()]
        assert not missing, f"Missing SVG source files: {missing}"

    def test_svg_files_are_valid_xml(self):
        import xml.etree.ElementTree as ET
        for name in _P1_ICONS:
            path = _SVG_DIR / f"{name}.svg"
            try:
                ET.parse(path)
            except ET.ParseError as exc:
                assert False, f"{path.name} is not valid XML: {exc}"


# ── Icon loader module ────────────────────────────────────────────────────────

class TestIconLoader:

    def test_icon_constants_defined(self):
        for name in _P1_ICONS:
            assert isinstance(name, str) and name, f"Expected non-empty string constant for {name}"

    def test_required_png_paths_covers_all_p1_icons(self):
        paths = il.required_png_paths()
        path_stems = {p.stem for p in paths}
        for icon in _P1_ICONS:
            for size in il.REQUIRED_SIZES:
                assert f"{icon}_{size}" in path_stems, \
                    f"required_png_paths() missing {icon}_{size}.png"

    def test_get_icon_returns_without_raising_when_png_missing(self):
        icon = il.get_icon("settings", 32)
        assert icon is not None

    def test_svg_path_returns_correct_path(self):
        p = il.svg_path("settings")
        assert p.name == "settings.svg"
        assert p.parent.name == "svg"

    def test_strict_mode_raises_on_missing_png(self, monkeypatch):
        monkeypatch.setattr(il, "_STRICT", True)
        import pytest
        with pytest.raises(FileNotFoundError):
            il.get_icon("__nonexistent_icon__", 32)
