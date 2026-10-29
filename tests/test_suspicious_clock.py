#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_suspicious_clock.py — Tests for schedule_config.is_clock_plausible() (#121).
"""
from __future__ import annotations

import logging
from unittest.mock import patch


from application.schedule_config import (
    DAYS,
    _CLOCK_MAX_YEAR,
    _CLOCK_MIN_YEAR,
    is_clock_plausible,
    is_within_schedule,
)


class TestIsClockPlausible:

    def test_current_year_is_plausible(self):
        assert is_clock_plausible() is True

    def test_min_year_boundary_is_plausible(self):
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value.year = _CLOCK_MIN_YEAR
            assert is_clock_plausible() is True

    def test_max_year_boundary_is_plausible(self):
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value.year = _CLOCK_MAX_YEAR
            assert is_clock_plausible() is True

    def test_epoch_year_not_plausible(self):
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value.year = 1970
            assert is_clock_plausible() is False

    def test_year_below_min_not_plausible(self):
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value.year = _CLOCK_MIN_YEAR - 1
            assert is_clock_plausible() is False

    def test_year_above_max_not_plausible(self):
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value.year = _CLOCK_MAX_YEAR + 1
            assert is_clock_plausible() is False

    def test_year_2000_not_plausible(self):
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value.year = 2000
            assert is_clock_plausible() is False

    def test_implausible_clock_logs_warning(self, caplog):
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value.year = 1970
            with caplog.at_level(logging.WARNING, logger="application.schedule_config"):
                is_clock_plausible()
        assert any("clock" in r.message.lower() or "1970" in r.message
                   for r in caplog.records)

    def test_plausible_clock_no_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="application.schedule_config"):
            is_clock_plausible()
        assert not caplog.records


class TestIsWithinScheduleClockGuard:

    def _active_schedule(self) -> dict:
        """Return a schedule with every day enabled all day."""
        return {day: {"enabled": True, "start": "00:00", "end": "23:59"} for day in DAYS}

    def test_implausible_clock_blocks_bypass_even_when_schedule_matches(self):
        schedule = self._active_schedule()
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value.year = 1970
            mock_dt.now.return_value.weekday.return_value = 0
            mock_dt.now.return_value.hour = 12
            mock_dt.now.return_value.minute = 0
            with patch("application.schedule_config.load_schedule", return_value=schedule):
                assert is_within_schedule() is False

    def test_plausible_clock_allows_bypass_when_schedule_matches(self):
        schedule = self._active_schedule()
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value.year = 2026
            mock_dt.now.return_value.weekday.return_value = 0
            mock_dt.now.return_value.hour = 12
            mock_dt.now.return_value.minute = 0
            with patch("application.schedule_config.load_schedule", return_value=schedule):
                assert is_within_schedule() is True

    def test_implausible_clock_logs_warning_in_is_within_schedule(self, caplog):
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value.year = 1970
            mock_dt.now.return_value.weekday.return_value = 0
            mock_dt.now.return_value.hour = 12
            mock_dt.now.return_value.minute = 0
            with caplog.at_level(logging.WARNING, logger="application.schedule_config"):
                is_within_schedule()
        assert any("clock" in r.message.lower() or "1970" in r.message
                   for r in caplog.records)
