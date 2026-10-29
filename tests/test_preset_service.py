#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_preset_service.py — PresetService unit tests

from __future__ import annotations

from unittest.mock import patch


from domain.preset import PRESET_SLOT_MIN, PRESET_SLOT_MAX, PRESET_CHAIRMAN_GENERIC


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_service(initial_presets: dict | None = None):
    """Build a PresetService with pre-loaded presets (no disk I/O)."""
    from application.preset_service import PresetService
    with patch("application.preset_service.load_chairman_presets", return_value=initial_presets or {}):
        return PresetService()


def _save_ok():
    return patch("application.preset_service.save_chairman_presets", return_value=True)


def _save_fail():
    return patch("application.preset_service.save_chairman_presets", return_value=False)


# ── get_preset_for_name ───────────────────────────────────────────────────────

def test_get_preset_returns_slot_for_known_name():
    svc = _make_service({"PersonA": 15})
    assert svc.get_preset_for_name("PersonA") == 15


def test_get_preset_returns_generic_for_unknown_name():
    svc = _make_service()
    assert svc.get_preset_for_name("Unknown") == PRESET_CHAIRMAN_GENERIC


# ── has_preset ────────────────────────────────────────────────────────────────

def test_has_preset_true_for_known():
    svc = _make_service({"PersonA": 10})
    assert svc.has_preset("PersonA")


def test_has_preset_false_for_unknown():
    svc = _make_service()
    assert not svc.has_preset("PersonB")


# ── snapshot ──────────────────────────────────────────────────────────────────

def test_snapshot_returns_copy():
    svc = _make_service({"PersonA": 10})
    snap = svc.snapshot()
    snap["Mutator"] = 99
    assert "Mutator" not in svc.snapshot()


def test_snapshot_reflects_current_state():
    svc = _make_service({"PersonA": 10, "PersonB": 11})
    assert svc.snapshot() == {"PersonA": 10, "PersonB": 11}


# ── assign_slot ───────────────────────────────────────────────────────────────

def test_assign_slot_new_name_reserves_next_free_slot():
    svc = _make_service()
    slot, is_new = svc.assign_slot("PersonA")
    assert is_new
    assert PRESET_SLOT_MIN <= slot <= PRESET_SLOT_MAX
    assert svc.has_preset("PersonA")


def test_assign_slot_existing_name_returns_same_slot():
    svc = _make_service({"PersonA": 15})
    slot, is_new = svc.assign_slot("PersonA")
    assert not is_new
    assert slot == 15


def test_assign_slot_picks_lowest_free_slot():
    svc = _make_service()
    slot, _ = svc.assign_slot("First")
    assert slot == PRESET_SLOT_MIN


def test_assign_slot_skips_occupied_slots():
    existing = {f"Person{i}": PRESET_SLOT_MIN + i for i in range(3)}
    svc = _make_service(existing)
    slot, _ = svc.assign_slot("New")
    assert slot == PRESET_SLOT_MIN + 3


def test_assign_slot_returns_none_when_range_exhausted():
    full = {f"P{i}": PRESET_SLOT_MIN + i for i in range(PRESET_SLOT_MAX - PRESET_SLOT_MIN + 1)}
    svc = _make_service(full)
    slot, is_new = svc.assign_slot("Overflow")
    assert slot is None
    assert not is_new


def test_assign_slot_does_not_persist_automatically():
    svc = _make_service()
    with patch("application.preset_service.save_chairman_presets") as mock_save:
        svc.assign_slot("PersonA")
        mock_save.assert_not_called()


# ── persist ───────────────────────────────────────────────────────────────────

def test_persist_calls_save_with_current_state():
    svc = _make_service({"PersonA": 10})
    with patch("application.preset_service.save_chairman_presets", return_value=True) as mock_save:
        result = svc.persist()
    assert result
    mock_save.assert_called_once_with({"PersonA": 10})


def test_persist_returns_false_on_save_failure():
    svc = _make_service()
    with _save_fail():
        result = svc.persist()
    assert not result


# ── release_slot ──────────────────────────────────────────────────────────────

def test_release_slot_removes_from_memory():
    svc = _make_service({"PersonA": 10})
    svc.release_slot("PersonA")
    assert not svc.has_preset("PersonA")


def test_release_slot_unknown_name_is_silent():
    svc = _make_service()
    svc.release_slot("Nobody")  # should not raise


def test_release_slot_does_not_write_to_disk():
    svc = _make_service({"PersonA": 10})
    with patch("application.preset_service.save_chairman_presets") as mock_save:
        svc.release_slot("PersonA")
        mock_save.assert_not_called()


def test_assign_and_release_rollback_frees_slot():
    svc = _make_service()
    slot, is_new = svc.assign_slot("PersonA")
    assert is_new
    svc.release_slot("PersonA")
    # The same slot should be available again for the next assign
    slot2, is_new2 = svc.assign_slot("PersonA")
    assert is_new2
    assert slot2 == slot


# ── rename ────────────────────────────────────────────────────────────────────

def test_rename_returns_false_when_old_name_not_found():
    svc = _make_service()
    with _save_ok():
        result = svc.rename("Ghost", "NewGhost")
    assert not result


def test_rename_returns_false_when_new_name_already_exists():
    svc = _make_service({"PersonA": 10, "PersonB": 11})
    with _save_ok():
        result = svc.rename("PersonA", "PersonB")
    assert not result
    assert svc.get_preset_for_name("PersonA") == 10  # unchanged


def test_rename_preserves_slot_number():
    svc = _make_service({"PersonA": 15})
    with _save_ok():
        result = svc.rename("PersonA", "Alicia")
    assert result
    assert not svc.has_preset("PersonA")
    assert svc.get_preset_for_name("Alicia") == 15


def test_rename_persists_to_disk():
    svc = _make_service({"PersonA": 15})
    with patch("application.preset_service.save_chairman_presets", return_value=True) as mock_save:
        svc.rename("PersonA", "Alicia")
    mock_save.assert_called_once_with({"Alicia": 15})


def test_rename_returns_false_on_save_failure():
    svc = _make_service({"PersonA": 15})
    with _save_fail():
        result = svc.rename("PersonA", "Alicia")
    assert not result
