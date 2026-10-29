#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_schedule_config.py — schedule_config module unit tests

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

import application.schedule_config as sc


# ── is_clock_plausible ────────────────────────────────────────────────────────

def _mock_now(year: int, month: int = 6, day: int = 15, hour: int = 10, minute: int = 0):
    return datetime(year, month, day, hour, minute)


def test_clock_plausible_for_current_year():
    with patch("application.schedule_config.datetime") as m:
        m.now.return_value = _mock_now(2026)
        assert sc.is_clock_plausible()


def test_clock_not_plausible_for_1970():
    with patch("application.schedule_config.datetime") as m:
        m.now.return_value = _mock_now(1970)
        assert not sc.is_clock_plausible()


def test_clock_not_plausible_above_max_year():
    with patch("application.schedule_config.datetime") as m:
        m.now.return_value = _mock_now(2101)
        assert not sc.is_clock_plausible()


def test_clock_plausible_at_boundary_min():
    with patch("application.schedule_config.datetime") as m:
        m.now.return_value = _mock_now(2024)
        assert sc.is_clock_plausible()


def test_clock_plausible_at_boundary_max():
    with patch("application.schedule_config.datetime") as m:
        m.now.return_value = _mock_now(2100)
        assert sc.is_clock_plausible()


# ── _parse_bool_strict ────────────────────────────────────────────────────────

def test_parse_bool_strict_real_true():
    assert sc._parse_bool_strict(True, "ctx") is True


def test_parse_bool_strict_real_false():
    assert sc._parse_bool_strict(False, "ctx") is False


@pytest.mark.parametrize("val", ["true", "True", "TRUE", "yes", "YES", "1"])
def test_parse_bool_strict_truthy_strings(val):
    assert sc._parse_bool_strict(val, "ctx") is True


@pytest.mark.parametrize("val", ["false", "False", "FALSE", "no", "NO", "0"])
def test_parse_bool_strict_falsy_strings(val):
    assert sc._parse_bool_strict(val, "ctx") is False


def test_parse_bool_strict_unrecognised_string_returns_false():
    assert sc._parse_bool_strict("maybe", "ctx") is False


def test_parse_bool_strict_int_zero():
    assert sc._parse_bool_strict(0, "ctx") is False


def test_parse_bool_strict_int_one():
    assert sc._parse_bool_strict(1, "ctx") is True


def test_parse_bool_strict_unexpected_type_returns_false():
    assert sc._parse_bool_strict(None, "ctx") is False
    assert sc._parse_bool_strict([], "ctx") is False


# ── _parse_minutes ────────────────────────────────────────────────────────────

def test_parse_minutes_valid():
    assert sc._parse_minutes({"start": "09:30"}, "start") == 9 * 60 + 30


def test_parse_minutes_midnight():
    assert sc._parse_minutes({"start": "00:00"}, "start") == 0


def test_parse_minutes_end_of_day():
    assert sc._parse_minutes({"end": "23:59"}, "end") == 23 * 60 + 59


def test_parse_minutes_missing_key_returns_none():
    assert sc._parse_minutes({}, "start") is None


def test_parse_minutes_invalid_format_returns_none():
    assert sc._parse_minutes({"start": "not-a-time"}, "start") is None


def test_parse_minutes_out_of_range_hour_returns_none():
    assert sc._parse_minutes({"start": "25:00"}, "start") is None


def test_parse_minutes_out_of_range_minute_returns_none():
    assert sc._parse_minutes({"start": "09:60"}, "start") is None


# ── _entry_active_at ──────────────────────────────────────────────────────────

def test_entry_active_at_within_normal_window():
    entry = {"enabled": True, "start": "09:00", "end": "17:00"}
    assert sc._entry_active_at(entry, 10 * 60) is True  # 10:00


def test_entry_active_at_before_window():
    entry = {"enabled": True, "start": "09:00", "end": "17:00"}
    assert sc._entry_active_at(entry, 8 * 60) is False  # 08:00


def test_entry_active_at_after_window():
    entry = {"enabled": True, "start": "09:00", "end": "17:00"}
    assert sc._entry_active_at(entry, 17 * 60) is False  # 17:00 (exclusive end)


def test_entry_active_at_start_is_inclusive():
    entry = {"enabled": True, "start": "09:00", "end": "17:00"}
    assert sc._entry_active_at(entry, 9 * 60) is True


def test_entry_active_at_disabled_entry():
    entry = {"enabled": False, "start": "09:00", "end": "17:00"}
    assert sc._entry_active_at(entry, 10 * 60) is False


def test_entry_active_at_overnight_window_past_midnight():
    # 22:00 → 06:00, check at 02:00
    entry = {"enabled": True, "start": "22:00", "end": "06:00"}
    assert sc._entry_active_at(entry, 2 * 60) is True  # 02:00 < 06:00


def test_entry_active_at_overnight_window_before_midnight():
    # 22:00 → 06:00, check at 23:00
    entry = {"enabled": True, "start": "22:00", "end": "06:00"}
    assert sc._entry_active_at(entry, 23 * 60) is True  # 23:00 >= 22:00


def test_entry_active_at_overnight_window_outside():
    # 22:00 → 06:00, check at 12:00
    entry = {"enabled": True, "start": "22:00", "end": "06:00"}
    assert sc._entry_active_at(entry, 12 * 60) is False


def test_entry_active_at_invalid_times_returns_false():
    entry = {"enabled": True, "start": "bad", "end": "also_bad"}
    assert sc._entry_active_at(entry, 10 * 60) is False


# ── load_schedule ─────────────────────────────────────────────────────────────

def test_load_schedule_returns_defaults_when_no_file():
    with patch("application.schedule_config.load_json", return_value=None):
        result = sc.load_schedule()
    for day in sc.DAYS:
        assert result[day]["enabled"] is False
        assert result[day]["start"] == "09:00"
        assert result[day]["end"] == "17:00"
    assert result["always_bypass"] is False


def test_load_schedule_parses_always_bypass():
    data = {"always_bypass": True, **{day: {"enabled": False, "start": "09:00", "end": "17:00"} for day in sc.DAYS}}
    with patch("application.schedule_config.load_json", return_value=data):
        result = sc.load_schedule()
    assert result["always_bypass"] is True


def test_load_schedule_parses_day_entries():
    data = {
        "always_bypass": False,
        "monday": {"enabled": True, "start": "08:00", "end": "18:00"},
        **{day: {"enabled": False, "start": "09:00", "end": "17:00"} for day in sc.DAYS if day != "monday"},
    }
    with patch("application.schedule_config.load_json", return_value=data):
        result = sc.load_schedule()
    assert result["monday"]["enabled"] is True
    assert result["monday"]["start"] == "08:00"


def test_load_schedule_handles_corrupt_data():
    with patch("application.schedule_config.load_json", return_value="not_a_dict"):
        result = sc.load_schedule()
    assert result["always_bypass"] is False


def test_load_schedule_missing_day_uses_default():
    with patch("application.schedule_config.load_json", return_value={"always_bypass": False}):
        result = sc.load_schedule()
    assert result["monday"]["enabled"] is False


# ── save_schedule ─────────────────────────────────────────────────────────────

def test_save_schedule_delegates_to_save_json():
    data = {"always_bypass": False}
    with patch("application.schedule_config.save_json", return_value=True) as mock_save:
        result = sc.save_schedule(data)
    assert result
    mock_save.assert_called_once_with(sc.SCHEDULE_FILE, data)


def test_save_schedule_returns_false_on_failure():
    with patch("application.schedule_config.save_json", return_value=False):
        assert not sc.save_schedule({})


# ── is_within_schedule ────────────────────────────────────────────────────────

def test_is_within_schedule_always_bypass_true():
    sched = {"always_bypass": True, **{day: {"enabled": False, "start": "09:00", "end": "17:00"} for day in sc.DAYS}}
    with patch("application.schedule_config.load_schedule", return_value=sched):
        assert sc.is_within_schedule() is True


def test_is_within_schedule_implausible_clock_returns_false():
    sched = {"always_bypass": False, **{day: {"enabled": True, "start": "00:00", "end": "23:59"} for day in sc.DAYS}}
    with patch("application.schedule_config.load_schedule", return_value=sched), \
         patch("application.schedule_config.is_clock_plausible", return_value=False):
        assert sc.is_within_schedule() is False


def test_is_within_schedule_active_today():
    # Monday 10:00, schedule: monday 09:00-17:00 enabled
    sched = {
        "always_bypass": False,
        **{day: {"enabled": False, "start": "09:00", "end": "17:00"} for day in sc.DAYS},
    }
    sched["monday"] = {"enabled": True, "start": "09:00", "end": "17:00"}
    with patch("application.schedule_config.load_schedule", return_value=sched), \
         patch("application.schedule_config.is_clock_plausible", return_value=True), \
         patch("application.schedule_config.datetime") as m:
        m.now.return_value = _mock_now(2026, 1, 5, 10, 0)  # Monday
        assert sc.is_within_schedule() is True


def test_is_within_schedule_outside_window():
    sched = {
        "always_bypass": False,
        **{day: {"enabled": False, "start": "09:00", "end": "17:00"} for day in sc.DAYS},
    }
    sched["monday"] = {"enabled": True, "start": "09:00", "end": "17:00"}
    with patch("application.schedule_config.load_schedule", return_value=sched), \
         patch("application.schedule_config.is_clock_plausible", return_value=True), \
         patch("application.schedule_config.datetime") as m:
        m.now.return_value = _mock_now(2026, 1, 5, 20, 0)  # Monday 20:00
        assert sc.is_within_schedule() is False


def test_is_within_schedule_overnight_window_from_previous_day():
    # Sunday has overnight window 22:00→06:00; check Monday at 02:00
    sched = {
        "always_bypass": False,
        **{day: {"enabled": False, "start": "09:00", "end": "17:00"} for day in sc.DAYS},
    }
    sched["sunday"] = {"enabled": True, "start": "22:00", "end": "06:00"}
    with patch("application.schedule_config.load_schedule", return_value=sched), \
         patch("application.schedule_config.is_clock_plausible", return_value=True), \
         patch("application.schedule_config.datetime") as m:
        m.now.return_value = _mock_now(2026, 1, 5, 2, 0)  # Monday 02:00
        assert sc.is_within_schedule() is True


def test_is_within_schedule_no_active_day_returns_false():
    sched = {
        "always_bypass": False,
        **{day: {"enabled": False, "start": "09:00", "end": "17:00"} for day in sc.DAYS},
    }
    with patch("application.schedule_config.load_schedule", return_value=sched), \
         patch("application.schedule_config.is_clock_plausible", return_value=True), \
         patch("application.schedule_config.datetime") as m:
        m.now.return_value = _mock_now(2026, 1, 5, 10, 0)  # Monday
        assert sc.is_within_schedule() is False
