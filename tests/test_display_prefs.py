#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_display_prefs.py — application/display_prefs unit tests

from __future__ import annotations

import application.display_prefs as dp


def _redirect(monkeypatch, tmp_path):
    target = tmp_path / "display_prefs.json"
    monkeypatch.setattr(dp, "_path", lambda: target)
    return target


def test_default_is_false_when_file_missing(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    assert dp.is_second_platform_enabled() is False


def test_enable_then_read_true(monkeypatch, tmp_path):
    target = _redirect(monkeypatch, tmp_path)
    assert dp.set_second_platform_enabled(True) is True
    assert target.exists()
    assert dp.is_second_platform_enabled() is True


def test_disable_then_read_false(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    dp.set_second_platform_enabled(True)
    dp.set_second_platform_enabled(False)
    assert dp.is_second_platform_enabled() is False


def test_preserves_other_keys(monkeypatch, tmp_path):
    target = _redirect(monkeypatch, tmp_path)
    from core.json_io import save_json, load_json
    save_json(target, {"some_other_pref": 7})
    dp.set_second_platform_enabled(True)
    data = load_json(target, default={})
    assert data["some_other_pref"] == 7
    assert data["second_platform"] is True


def test_corrupt_file_defaults_false(monkeypatch, tmp_path):
    target = _redirect(monkeypatch, tmp_path)
    target.write_text("{ not valid json", encoding="utf-8")
    assert dp.is_second_platform_enabled() is False
