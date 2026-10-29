#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_platform_icons.py — Verifies that all SVG icon strings are present,
non-empty, contain a valid <svg> root element, and lack an XML declaration
(which breaks QSvgRenderer).
"""
from __future__ import annotations

import pytest

from ui.platform_icons import SVG_LEFT, SVG_CHAIRMAN, SVG_RIGHT, SVG_WHEELCHAIR


_ICONS = [
    ("SVG_LEFT",       SVG_LEFT),
    ("SVG_CHAIRMAN",   SVG_CHAIRMAN),
    ("SVG_RIGHT",      SVG_RIGHT),
    ("SVG_WHEELCHAIR", SVG_WHEELCHAIR),
]


class TestPlatformIconsContent:
    @pytest.mark.parametrize("name,svg", _ICONS)
    def test_non_empty_string(self, name, svg):
        assert isinstance(svg, str) and svg.strip(), \
            f"{name} must be a non-empty string"

    @pytest.mark.parametrize("name,svg", _ICONS)
    def test_has_opening_svg_tag(self, name, svg):
        assert "<svg" in svg, f"{name} must contain an opening <svg> tag"

    @pytest.mark.parametrize("name,svg", _ICONS)
    def test_has_closing_svg_tag(self, name, svg):
        assert "</svg>" in svg, f"{name} must contain a closing </svg> tag"

    @pytest.mark.parametrize("name,svg", _ICONS)
    def test_no_xml_declaration(self, name, svg):
        # QSvgRenderer rejects SVGs with an <?xml ...?> header
        assert not svg.strip().startswith("<?xml"), \
            f"{name} must not begin with an XML declaration (breaks QSvgRenderer)"

    @pytest.mark.parametrize("name,svg", _ICONS)
    def test_viewbox_present(self, name, svg):
        assert "viewBox" in svg or "viewbox" in svg.lower(), \
            f"{name} should have a viewBox attribute for correct scaling"

    def test_all_four_names_exported(self):
        from ui import platform_icons as _pi
        assert hasattr(_pi, "SVG_LEFT")
        assert hasattr(_pi, "SVG_CHAIRMAN")
        assert hasattr(_pi, "SVG_RIGHT")
        assert hasattr(_pi, "SVG_WHEELCHAIR")

    def test_icons_are_distinct(self):
        svgs = [svg for _, svg in _ICONS]
        assert len(set(svgs)) == len(svgs), \
            "Every platform icon must have unique SVG content"

    def test_wheelchair_uses_stroke_not_fill(self):
        # The wheelchair icon uses stroke-based paths (line art style)
        assert 'stroke=' in SVG_WHEELCHAIR

    def test_left_chairman_right_use_fill(self):
        # The preset icons (potrace output) use filled paths
        for name, svg in [("SVG_LEFT", SVG_LEFT), ("SVG_CHAIRMAN", SVG_CHAIRMAN),
                          ("SVG_RIGHT", SVG_RIGHT)]:
            assert 'fill=' in svg, f"{name} should use fill-based paths"
