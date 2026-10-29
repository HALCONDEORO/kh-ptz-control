#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_atem_constants.py — Guard tests for domain/atem_constants.py.

These tests protect the canonical ATEM input label definitions against
accidental renames, reorders, or deletions that would silently break
the UI, dispatcher, and other consumers.
"""
from __future__ import annotations


from domain.atem_constants import (
    ATEM_DEFAULT_MAPPING,
    ATEM_INPUT_LABELS,
    ATEM_INPUT_LABELS_LIST,
)


class TestAtemInputLabels:
    """ATEM_INPUT_LABELS: canonical int → string mapping for all 4 inputs."""

    def test_has_exactly_four_entries(self):
        assert len(ATEM_INPUT_LABELS) == 4

    def test_input_1_is_pc(self):
        assert ATEM_INPUT_LABELS[1] == "PC"

    def test_input_2_is_platform(self):
        assert ATEM_INPUT_LABELS[2] == "Platform"

    def test_input_3_is_comments(self):
        assert ATEM_INPUT_LABELS[3] == "Comments"

    def test_input_4_is_none(self):
        assert ATEM_INPUT_LABELS[4] == "None"

    def test_all_keys_are_integers(self):
        assert all(isinstance(k, int) for k in ATEM_INPUT_LABELS)

    def test_all_values_are_non_empty_strings(self):
        assert all(isinstance(v, str) and v for v in ATEM_INPUT_LABELS.values())


class TestAtemInputLabelsList:
    """ATEM_INPUT_LABELS_LIST: ordered (input_id, label) pairs."""

    def test_has_same_length_as_dict(self):
        assert len(ATEM_INPUT_LABELS_LIST) == len(ATEM_INPUT_LABELS)

    def test_is_sorted_by_input_id(self):
        ids = [item[0] for item in ATEM_INPUT_LABELS_LIST]
        assert ids == sorted(ids)

    def test_first_entry_is_input_1(self):
        assert ATEM_INPUT_LABELS_LIST[0][0] == 1

    def test_last_entry_is_input_4(self):
        assert ATEM_INPUT_LABELS_LIST[-1][0] == 4

    def test_matches_dict_values(self):
        for input_id, label in ATEM_INPUT_LABELS_LIST:
            assert ATEM_INPUT_LABELS[input_id] == label

    def test_all_items_are_tuples_of_two(self):
        for item in ATEM_INPUT_LABELS_LIST:
            assert isinstance(item, tuple) and len(item) == 2


class TestAtemDefaultMapping:
    """ATEM_DEFAULT_MAPPING: canonical dispatcher action mapping."""

    def test_is_a_dict(self):
        assert isinstance(ATEM_DEFAULT_MAPPING, dict)

    def test_comments_to_platform_transition_triggers_home(self):
        """3→2 (Comments→Platform) must trigger comments_home action."""
        assert ATEM_DEFAULT_MAPPING.get("3->2") == "comments_home"

    def test_all_values_are_non_empty_strings(self):
        assert all(isinstance(v, str) and v for v in ATEM_DEFAULT_MAPPING.values())

    def test_all_keys_follow_transition_format(self):
        """All keys must be 'A->B' or 'N' (entry) format strings."""
        import re
        pattern = re.compile(r"^\d+->\d+$|^N$")
        for key in ATEM_DEFAULT_MAPPING:
            assert pattern.match(key), f"Key {key!r} does not match expected format"
