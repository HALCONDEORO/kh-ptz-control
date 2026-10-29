#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
domain/adaptive_speed.py — Pure adaptive-speed rules for PTZ motion.

These are the side-effect-free decision functions behind the "Adaptive Control"
behaviour that used to live inline in ui/main_window.py:

  - zoom_to_raw_speed(zoom): map a zoom percentage to a raw pan/tilt speed.
  - reduced_move_caps / reduced_zoom_drive_cap: how far to back off a speed cap
    after a VISCA speed error (watchdog reduction step).
  - recovered_move_caps / recovered_zoom_drive_cap: how far to step a cap back
    up when probing whether the camera tolerates more speed again.

No PyQt, no I/O, no time — the state machine (cooldown windows, retry counts,
QTimer scheduling) and the camera-port writes stay in the UI layer. This module
only answers "given these numbers, what are the new numbers?".
"""

from __future__ import annotations

from dataclasses import dataclass

# Zoom% (inclusive upper bound) → raw pan/tilt speed. Mirrors the original
# lookup table; the final entry (>90 %) falls through to MIN_RAW_SPEED.
_ZOOM_SPEED_TABLE: tuple[tuple[int, int], ...] = (
    (9, 20),
    (18, 19),
    (27, 18),
    (36, 16),
    (45, 15),
    (54, 14),
    (63, 13),
    (72, 11),
    (81, 10),
    (90, 9),
)
MIN_RAW_SPEED = 8

# Default watchdog step/floor sizes (kept here so the rule and its constants
# live together; the UI may still pass explicit values).
MOVE_CAP_STEP = 2
MOVE_CAP_FLOOR = 8
ZOOM_DRIVE_CAP_STEP = 1
ZOOM_DRIVE_CAP_FLOOR = 1


def zoom_to_raw_speed(zoom: int) -> int:
    """Return the raw pan/tilt speed for a zoom percentage (before cap clamp)."""
    for upper, speed in _ZOOM_SPEED_TABLE:
        if zoom <= upper:
            return speed
    return MIN_RAW_SPEED


def reduced_move_caps(
    pan_cap: int,
    tilt_cap: int,
    *,
    floor: int = MOVE_CAP_FLOOR,
    step: int = MOVE_CAP_STEP,
) -> tuple[int, int]:
    """Back off pan and tilt caps by one step each, not below ``floor``."""
    new_pan = max(floor, pan_cap - step) if pan_cap > floor else pan_cap
    new_tilt = max(floor, tilt_cap - step) if tilt_cap > floor else tilt_cap
    return new_pan, new_tilt


def reduced_zoom_drive_cap(
    cap: int,
    *,
    floor: int = ZOOM_DRIVE_CAP_FLOOR,
    step: int = ZOOM_DRIVE_CAP_STEP,
) -> int:
    """Back off the zoom-drive cap by one step, not below ``floor``."""
    return cap - step if cap > floor else cap


def recovered_move_caps(
    pan_cap: int,
    tilt_cap: int,
    *,
    pan_max: int,
    tilt_max: int,
    step: int = MOVE_CAP_STEP,
) -> tuple[int, int]:
    """Step pan and tilt caps back up by one step, not above their maxima."""
    return min(pan_max, pan_cap + step), min(tilt_max, tilt_cap + step)


def recovered_zoom_drive_cap(
    cap: int,
    *,
    zoom_max: int,
    step: int = ZOOM_DRIVE_CAP_STEP,
) -> int:
    """Step the zoom-drive cap back up by one step, not above ``zoom_max``."""
    return min(zoom_max, cap + step)


# ── Watchdog decision state machine ─────────────────────────────────────────
#
# Per-channel state is a plain dict {last_reduction, window_start, retries} of
# monotonic timestamps and a retry counter — the same shape MainWindow already
# keeps. evaluate_speed_error() is pure: it takes the current state plus the
# current monotonic time and returns the *next* state and a decision describing
# the side effects the caller must perform (apply a reduction, schedule a
# recovery probe, or log that the cap is now blocked). The actual reduction,
# the QTimer scheduling and the logging stay in the UI layer.

def fresh_channel_state() -> dict:
    """A pristine per-channel watchdog state."""
    return {"last_reduction": 0.0, "window_start": 0.0, "retries": 0}


@dataclass(frozen=True)
class SpeedErrorDecision:
    """What the caller should do in response to one VISCA speed error."""
    window_reset: bool        # the 5-min window had expired and was restarted
    apply_reduction: bool     # caller should back off the caps for this channel
    schedule_recovery: bool   # caller should arm a recovery probe (retries left)
    now_blocked: bool         # this reduction exhausted the retry budget


def evaluate_speed_error(
    state: dict,
    now: float,
    *,
    cooldown: float,
    window_secs: float,
    max_retries: int,
) -> tuple[dict, SpeedErrorDecision]:
    """Decide how to react to a speed error, returning (next_state, decision).

    Pure: ``state`` is not mutated. Mirrors the original MainWindow logic —
    expire the window, gate on retry budget and cooldown, otherwise record the
    reduction and advance the retry counter.
    """
    last = state["last_reduction"]
    start = state["window_start"]
    retries = state["retries"]

    window_reset = False
    if start > 0 and (now - start) > window_secs:
        last, start, retries = 0.0, 0.0, 0
        window_reset = True

    # Blocked: retry budget for this window is spent.
    if retries >= max_retries:
        nxt = {"last_reduction": last, "window_start": start, "retries": retries}
        return nxt, SpeedErrorDecision(window_reset, False, False, True)

    # Cooldown: avoid a cascade of reductions from rapid consecutive errors.
    if (now - last) < cooldown:
        nxt = {"last_reduction": last, "window_start": start, "retries": retries}
        return nxt, SpeedErrorDecision(window_reset, False, False, False)

    last = now
    if start == 0.0:
        start = now
    retries += 1
    schedule_recovery = retries < max_retries
    nxt = {"last_reduction": last, "window_start": start, "retries": retries}
    return nxt, SpeedErrorDecision(window_reset, True, schedule_recovery, not schedule_recovery)
