#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for domain/installation_id.py and config loading of site.installation_id."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from domain.installation_id import generate_installation_id, is_valid_installation_id
from config.loader import load_config


# ── generate_installation_id ──────────────────────────────────────────────────

class TestGenerateInstallationId:

    def test_format_matches_pattern(self):
        iid = generate_installation_id(2026)
        assert is_valid_installation_id(iid), f"invalid format: {iid}"

    def test_contains_year(self):
        iid = generate_installation_id(2026)
        assert "2026" in iid

    def test_different_year(self):
        iid = generate_installation_id(2030)
        assert "2030" in iid

    def test_generates_different_values(self):
        ids = {generate_installation_id(2026) for _ in range(50)}
        # With 9999 possible suffixes, 50 draws should almost always give >1 unique ID
        assert len(ids) > 1

    def test_suffix_is_four_digits(self):
        for _ in range(20):
            iid = generate_installation_id(2026)
            suffix = iid.split("-")[-1]
            assert len(suffix) == 4
            assert suffix.isdigit()

    def test_result_is_filename_safe(self):
        iid = generate_installation_id(2026)
        forbidden = set(' /\\:*?"<>|')
        assert not (set(iid) & forbidden), f"unsafe chars in: {iid}"


# ── is_valid_installation_id ──────────────────────────────────────────────────

class TestIsValidInstallationId:

    @pytest.mark.parametrize("value", [
        "hallptz-2026-0001",
        "hallptz-2026-9999",
        "hallptz-2030-0042",
    ])
    def test_valid(self, value):
        assert is_valid_installation_id(value)

    @pytest.mark.parametrize("value", [
        "",
        "HALLPTZ-2026-0001",   # uppercase not accepted
        "hallptz-26-0001",     # year too short
        "hallptz-2026-001",    # suffix too short
        "hallptz-2026-00001",  # suffix too long
        "hallptz_2026_0001",   # underscores not accepted
        "abc-2026-0001",
        "hallptz-2026",
    ])
    def test_invalid(self, value):
        assert not is_valid_installation_id(value)


# ── Config loading ────────────────────────────────────────────────────────────

class TestConfigInstallationId:

    def _write_config(self, tmp_path: Path, site: dict) -> Path:
        config = {
            "site": site,
            "cameras": [
                {"id": "platform", "role": "platform", "ip": "172.16.1.11", "visca_id": "81"}
            ],
        }
        p = tmp_path / "config.yaml"
        p.write_text(yaml.dump(config), encoding="utf-8")
        return p

    def test_installation_id_loaded(self, tmp_path):
        p = self._write_config(tmp_path, {"installation_id": "hallptz-2026-0007"})
        settings = load_config(p)
        assert settings.site.installation_id == "hallptz-2026-0007"

    def test_installation_id_defaults_to_empty(self, tmp_path):
        p = self._write_config(tmp_path, {})
        settings = load_config(p)
        assert settings.site.installation_id == ""

    def test_installation_id_with_other_site_fields(self, tmp_path):
        p = self._write_config(tmp_path, {
            "name": "Dail Eireann",
            "contact": "ops@example.com",
            "installation_id": "hallptz-2026-0099",
        })
        settings = load_config(p)
        assert settings.site.name == "Dail Eireann"
        assert settings.site.installation_id == "hallptz-2026-0099"
