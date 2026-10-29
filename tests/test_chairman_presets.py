#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_chairman_presets.py — Tests for application/chairman_presets.py

from __future__ import annotations

from unittest.mock import patch


from application.chairman_presets import (
    CHAIRMAN_GENERIC_PRESET,
    CHAIRMAN_PRESET_MAX,
    CHAIRMAN_PRESET_START,
    get_preset_for_name,
    load_chairman_presets,
    next_available_preset,
    save_chairman_presets,
)
from domain.preset import PRESET_CHAIRMAN_GENERIC, PRESET_SLOT_MAX, PRESET_SLOT_MIN


# ═══════════════════════════════════════════════════════════════════════════════
# Re-exported constants
# ═══════════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_start_equals_domain_min(self):
        assert CHAIRMAN_PRESET_START == PRESET_SLOT_MIN

    def test_max_equals_domain_max(self):
        assert CHAIRMAN_PRESET_MAX == PRESET_SLOT_MAX

    def test_generic_equals_domain_generic(self):
        assert CHAIRMAN_GENERIC_PRESET == PRESET_CHAIRMAN_GENERIC


# ═══════════════════════════════════════════════════════════════════════════════
# load_chairman_presets
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoadChairmanPresets:

    def _load(self, data):
        with patch("application.chairman_presets.load_json", return_value=data):
            return load_chairman_presets()

    def test_empty_file_returns_empty_dict(self):
        assert self._load({}) == {}

    def test_valid_presets_loaded(self):
        result = self._load({"Marco": 10, "PersonC": 11})
        assert result == {"Marco": 10, "PersonC": 11}

    def test_non_dict_returns_empty(self):
        assert self._load([1, 2, 3]) == {}

    def test_null_returns_empty(self):
        assert self._load(None) == {}

    def test_non_int_string_value_skipped(self):
        result = self._load({"Marco": "ten", "PersonC": 11})
        assert "Marco" not in result
        assert result == {"PersonC": 11}

    def test_float_value_skipped(self):
        result = self._load({"Marco": 10.5})
        assert result == {}

    def test_out_of_range_below_skipped(self):
        result = self._load({"Marco": CHAIRMAN_PRESET_START - 1, "PersonC": 11})
        assert "Marco" not in result
        assert "PersonC" in result

    def test_out_of_range_above_skipped(self):
        result = self._load({"Marco": CHAIRMAN_PRESET_MAX + 1, "PersonC": 11})
        assert "Marco" not in result
        assert "PersonC" in result

    def test_boundary_min_accepted(self):
        result = self._load({"Marco": CHAIRMAN_PRESET_START})
        assert result == {"Marco": CHAIRMAN_PRESET_START}

    def test_boundary_max_accepted(self):
        result = self._load({"Marco": CHAIRMAN_PRESET_MAX})
        assert result == {"Marco": CHAIRMAN_PRESET_MAX}

    def test_duplicate_preset_first_wins(self):
        data = {"Marco": 10, "PersonC": 10}
        result = self._load(data)
        assert result == {"Marco": 10}
        assert "PersonC" not in result

    def test_duplicate_preset_second_discarded(self):
        data = {"Marco": 15, "PersonC": 15, "Gary": 20}
        result = self._load(data)
        assert result.get("Marco") == 15
        assert "PersonC" not in result
        assert result.get("Gary") == 20

    def test_mix_valid_and_invalid(self):
        data = {
            "ValidA": 10,
            "BadStr": "x",
            "BadRange": 999,
            "ValidB": 11,
            "DupA": 10,  # duplicate slot — discarded
        }
        result = self._load(data)
        assert result == {"ValidA": 10, "ValidB": 11}

    def test_result_is_dict(self):
        assert isinstance(self._load({"A": 10}), dict)


# ═══════════════════════════════════════════════════════════════════════════════
# save_chairman_presets
# ═══════════════════════════════════════════════════════════════════════════════

class TestSaveChairmanPresets:

    def test_returns_true_on_success(self):
        with patch("application.chairman_presets.save_json", return_value=True):
            assert save_chairman_presets({"Marco": 10}) is True

    def test_returns_false_on_failure(self):
        with patch("application.chairman_presets.save_json", return_value=False):
            assert save_chairman_presets({"Marco": 10}) is False

    def test_passes_data_to_save_json(self):
        presets = {"Marco": 10, "PersonC": 11}
        with patch("application.chairman_presets.save_json", return_value=True) as mock_save:
            save_chairman_presets(presets)
        mock_save.assert_called_once()
        _path, saved_data = mock_save.call_args[0]
        assert saved_data == presets

    def test_called_exactly_once(self):
        with patch("application.chairman_presets.save_json", return_value=True) as mock_save:
            save_chairman_presets({})
        assert mock_save.call_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# next_available_preset
# ═══════════════════════════════════════════════════════════════════════════════

class TestNextAvailablePreset:

    def test_empty_presets_returns_start(self):
        assert next_available_preset({}) == CHAIRMAN_PRESET_START

    def test_skips_used_leading_slots(self):
        used = {str(n): n for n in range(CHAIRMAN_PRESET_START, CHAIRMAN_PRESET_START + 5)}
        assert next_available_preset(used) == CHAIRMAN_PRESET_START + 5

    def test_finds_gap_in_middle(self):
        presets = {"A": 10, "B": 12}  # slot 11 is free
        assert next_available_preset(presets) == 11

    def test_returns_none_when_all_slots_used(self):
        used = {str(n): n for n in range(CHAIRMAN_PRESET_START, CHAIRMAN_PRESET_MAX + 1)}
        assert next_available_preset(used) is None

    def test_one_slot_remaining_at_max(self):
        used = {str(n): n for n in range(CHAIRMAN_PRESET_START, CHAIRMAN_PRESET_MAX)}
        assert next_available_preset(used) == CHAIRMAN_PRESET_MAX

    def test_returns_int_not_none_when_free(self):
        result = next_available_preset({})
        assert isinstance(result, int)

    def test_result_within_valid_range(self):
        result = next_available_preset({"A": 10, "B": 11})
        assert CHAIRMAN_PRESET_START <= result <= CHAIRMAN_PRESET_MAX


# ═══════════════════════════════════════════════════════════════════════════════
# get_preset_for_name
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetPresetForName:

    def test_known_name_returns_assigned_preset(self):
        presets = {"Marco": 10, "PersonC": 11}
        assert get_preset_for_name(presets, "Marco") == 10

    def test_second_known_name_correct(self):
        presets = {"Marco": 10, "PersonC": 11}
        assert get_preset_for_name(presets, "PersonC") == 11

    def test_unknown_name_returns_generic(self):
        presets = {"Marco": 10}
        assert get_preset_for_name(presets, "Unknown") == CHAIRMAN_GENERIC_PRESET

    def test_empty_presets_returns_generic(self):
        assert get_preset_for_name({}, "Anyone") == CHAIRMAN_GENERIC_PRESET

    def test_generic_preset_is_positive(self):
        # Preset 0 is invalid in VISCA; the generic must be a valid slot number.
        assert CHAIRMAN_GENERIC_PRESET > 0
