#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Unit tests for domain.adaptive_speed — the pure PTZ adaptive-speed rules
extracted from ui/main_window.py. These lock in the exact behaviour the UI used
to compute inline, so the extraction is provably equivalent."""

from __future__ import annotations

import pytest

from domain.adaptive_speed import (
    zoom_to_raw_speed,
    reduced_move_caps,
    reduced_zoom_drive_cap,
    recovered_move_caps,
    recovered_zoom_drive_cap,
    evaluate_speed_error,
    fresh_channel_state,
)

# Watchdog tuning used in MainWindow (cooldown 1.5s, window 300s, 3 retries).
_WD = dict(cooldown=1.5, window_secs=300.0, max_retries=3)


def _legacy_zoom_to_raw(zoom: int) -> int:
    """The original inline lookup table from MainWindow._zoom_to_speed."""
    if zoom <= 9:
        return 20
    elif zoom <= 18:
        return 19
    elif zoom <= 27:
        return 18
    elif zoom <= 36:
        return 16
    elif zoom <= 45:
        return 15
    elif zoom <= 54:
        return 14
    elif zoom <= 63:
        return 13
    elif zoom <= 72:
        return 11
    elif zoom <= 81:
        return 10
    elif zoom <= 90:
        return 9
    else:
        return 8


class TestZoomToRawSpeed:
    @pytest.mark.parametrize("zoom", list(range(-5, 130)))
    def test_matches_legacy_table_across_full_range(self, zoom):
        assert zoom_to_raw_speed(zoom) == _legacy_zoom_to_raw(zoom)

    def test_boundary_values(self):
        assert zoom_to_raw_speed(0) == 20
        assert zoom_to_raw_speed(9) == 20
        assert zoom_to_raw_speed(10) == 19
        assert zoom_to_raw_speed(90) == 9
        assert zoom_to_raw_speed(91) == 8
        assert zoom_to_raw_speed(100) == 8


class TestReducedMoveCaps:
    def test_reduces_both_by_step(self):
        assert reduced_move_caps(24, 20) == (22, 18)

    def test_does_not_go_below_floor(self):
        assert reduced_move_caps(9, 9) == (8, 8)
        assert reduced_move_caps(8, 8) == (8, 8)

    def test_at_floor_is_unchanged(self):
        # Mirrors the legacy `if cap > 8` guard: at the floor nothing moves.
        assert reduced_move_caps(8, 8) == (8, 8)

    def test_channels_independent(self):
        assert reduced_move_caps(8, 20) == (8, 18)
        assert reduced_move_caps(24, 8) == (22, 8)


class TestReducedZoomDriveCap:
    def test_reduces_by_one(self):
        assert reduced_zoom_drive_cap(7) == 6

    def test_does_not_go_below_floor(self):
        assert reduced_zoom_drive_cap(1) == 1
        assert reduced_zoom_drive_cap(2) == 1


class TestRecoveredMoveCaps:
    def test_steps_up_by_step(self):
        assert recovered_move_caps(8, 8, pan_max=24, tilt_max=20) == (10, 10)

    def test_does_not_exceed_max(self):
        assert recovered_move_caps(24, 20, pan_max=24, tilt_max=20) == (24, 20)
        assert recovered_move_caps(23, 19, pan_max=24, tilt_max=20) == (24, 20)


class TestRecoveredZoomDriveCap:
    def test_steps_up_by_one(self):
        assert recovered_zoom_drive_cap(5, zoom_max=7) == 6

    def test_does_not_exceed_max(self):
        assert recovered_zoom_drive_cap(7, zoom_max=7) == 7


class TestEvaluateSpeedError:
    def test_does_not_mutate_input(self):
        state = fresh_channel_state()
        snapshot = dict(state)
        evaluate_speed_error(state, 100.0, **_WD)
        assert state == snapshot

    def test_first_error_applies_reduction_and_schedules_recovery(self):
        nxt, d = evaluate_speed_error(fresh_channel_state(), 100.0, **_WD)
        assert d.apply_reduction is True
        assert d.schedule_recovery is True
        assert d.now_blocked is False
        assert d.window_reset is False
        assert nxt["retries"] == 1
        assert nxt["last_reduction"] == 100.0
        assert nxt["window_start"] == 100.0

    def test_cooldown_blocks_rapid_second_error(self):
        state, _ = evaluate_speed_error(fresh_channel_state(), 100.0, **_WD)
        # 0.5s later — within the 1.5s cooldown
        nxt, d = evaluate_speed_error(state, 100.5, **_WD)
        assert d.apply_reduction is False
        assert nxt == state  # state unchanged through a cooldown hit

    def test_third_reduction_exhausts_budget_and_blocks(self):
        state = fresh_channel_state()
        # Three reductions spaced beyond the cooldown.
        state, d1 = evaluate_speed_error(state, 100.0, **_WD)
        state, d2 = evaluate_speed_error(state, 102.0, **_WD)
        state, d3 = evaluate_speed_error(state, 104.0, **_WD)
        assert (d1.schedule_recovery, d2.schedule_recovery) == (True, True)
        assert d3.apply_reduction is True
        assert d3.schedule_recovery is False
        assert d3.now_blocked is True
        assert state["retries"] == 3

    def test_blocked_channel_ignores_further_errors(self):
        state = fresh_channel_state()
        for t in (100.0, 102.0, 104.0):
            state, _ = evaluate_speed_error(state, t, **_WD)
        nxt, d = evaluate_speed_error(state, 106.0, **_WD)
        assert d.apply_reduction is False
        assert nxt["retries"] == 3

    def test_window_expiry_restarts_cycle(self):
        state = fresh_channel_state()
        for t in (100.0, 102.0, 104.0):
            state, _ = evaluate_speed_error(state, t, **_WD)
        # 301s after window_start (100.0) → window expired, fresh cycle
        nxt, d = evaluate_speed_error(state, 401.0, **_WD)
        assert d.window_reset is True
        assert d.apply_reduction is True
        assert d.schedule_recovery is True
        assert nxt["retries"] == 1
        assert nxt["window_start"] == 401.0
