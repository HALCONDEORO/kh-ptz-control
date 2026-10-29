#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_preset_brightness.py — Tests para preset_brightness.py

from __future__ import annotations

import json

import pytest


# ─────────────────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Redirige _brightness_file a un directorio temporal y resetea el módulo."""
    pb_path = tmp_path / "preset_brightness.json"

    import ui.preset_brightness as preset_brightness
    monkeypatch.setattr(preset_brightness, "_brightness_file", lambda: pb_path)
    monkeypatch.setattr(preset_brightness, "_cache",  {})
    monkeypatch.setattr(preset_brightness, "_loaded", False)

    return pb_path


# ─────────────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_get_returns_none_when_no_file():
    import ui.preset_brightness as preset_brightness
    assert preset_brightness.get_entry(1) is None


def test_save_and_get_roundtrip():
    import ui.preset_brightness as preset_brightness
    preset_brightness.save_brightness(1, 12, "bright")
    entry = preset_brightness.get_entry(1)
    assert entry == {"level": 12, "mode": "bright"}


def test_save_auto_mode():
    import ui.preset_brightness as preset_brightness
    preset_brightness.save_brightness(2, -3, "auto")
    entry = preset_brightness.get_entry(2)
    assert entry == {"level": -3, "mode": "auto"}


def test_save_persists_to_disk(isolated_store):
    import ui.preset_brightness as preset_brightness
    preset_brightness.save_brightness(10, 8, "manual")
    raw = json.loads(isolated_store.read_text())
    assert raw["10"] == {"level": 8, "mode": "manual"}


def test_multiple_slots_independent():
    import ui.preset_brightness as preset_brightness
    preset_brightness.save_brightness(1,  5, "bright")
    preset_brightness.save_brightness(2,  15, "manual")
    preset_brightness.save_brightness(10, -2, "auto")
    assert preset_brightness.get_entry(1)["level"]  == 5
    assert preset_brightness.get_entry(2)["level"]  == 15
    assert preset_brightness.get_entry(10)["level"] == -2
    assert preset_brightness.get_entry(10)["mode"]  == "auto"


def test_overwrite_slot():
    import ui.preset_brightness as preset_brightness
    preset_brightness.save_brightness(1, 10, "bright")
    preset_brightness.save_brightness(1, 18, "manual")
    entry = preset_brightness.get_entry(1)
    assert entry["level"] == 18
    assert entry["mode"]  == "manual"


def test_load_from_existing_file(isolated_store):
    """El módulo carga datos previos del disco al arrancar."""
    isolated_store.write_text(
        json.dumps({"1": {"level": 7, "mode": "bright"}, "2": {"level": -3, "mode": "auto"}}),
        encoding="utf-8",
    )
    import ui.preset_brightness as preset_brightness
    preset_brightness._loaded = False
    preset_brightness._cache.clear()

    assert preset_brightness.get_entry(1) == {"level": 7,  "mode": "bright"}
    assert preset_brightness.get_entry(2) == {"level": -3, "mode": "auto"}


def test_legacy_int_format_migrated(isolated_store):
    """Formato antiguo (solo entero) se migra a dict con mode='auto'."""
    isolated_store.write_text(json.dumps({"5": 12}), encoding="utf-8")
    import ui.preset_brightness as preset_brightness
    preset_brightness._loaded = False
    preset_brightness._cache.clear()

    entry = preset_brightness.get_entry(5)
    assert entry["level"] == 12
    assert entry["mode"]  == "auto"


def test_corrupt_file_returns_none(isolated_store):
    """Si el JSON está corrupto, get_entry devuelve None sin lanzar."""
    isolated_store.write_text("!!invalid json!!", encoding="utf-8")
    import ui.preset_brightness as preset_brightness
    assert preset_brightness.get_entry(1) is None
