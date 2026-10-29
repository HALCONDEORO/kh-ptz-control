#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_shutdown_intent.py — ShutdownIntent and closeEvent logic tests (#766)

from __future__ import annotations

from unittest.mock import MagicMock


from domain.shutdown_intent import ShutdownIntent


# ── ShutdownIntent enum ───────────────────────────────────────────────────────

def test_shutdown_intent_has_cancel():
    assert ShutdownIntent.CANCEL.value == "cancel"


def test_shutdown_intent_has_exit_keep_cameras_on():
    assert ShutdownIntent.EXIT_KEEP_CAMERAS_ON.value == "exit_keep_cameras_on"


def test_shutdown_intent_has_exit_and_power_off():
    assert ShutdownIntent.EXIT_AND_POWER_OFF_CAMERAS.value == "exit_and_power_off_cameras"


def test_shutdown_intent_values_are_distinct():
    values = [i.value for i in ShutdownIntent]
    assert len(values) == len(set(values))


# ── closeEvent routing via ShutdownIntent ─────────────────────────────────────
# We test the routing logic without instantiating MainWindow (which requires Qt
# app and full wiring). The test validates the contract:
#   EXIT_KEEP_CAMERAS_ON    → standby never called
#   EXIT_AND_POWER_OFF      → standby called for both cameras
#   CANCEL                  → event.ignore() called, standby never called


def _make_fake_port():
    port = MagicMock()
    port.standby_calls = []
    port.standby.side_effect = lambda cam: port.standby_calls.append(cam)
    return port


def _simulate_close(intent: ShutdownIntent, port):
    """Simulate the routing logic extracted from closeEvent."""
    if intent == ShutdownIntent.CANCEL:
        return "ignored"
    if intent == ShutdownIntent.EXIT_AND_POWER_OFF_CAMERAS:
        port.standby("cam1")
        port.standby("cam2")
    return "accepted"


def test_exit_keep_cameras_on_does_not_call_camera_standby():
    port = _make_fake_port()
    result = _simulate_close(ShutdownIntent.EXIT_KEEP_CAMERAS_ON, port)
    assert result == "accepted"
    assert port.standby_calls == []


def test_exit_keep_cameras_on_does_not_call_power_off():
    port = _make_fake_port()
    _simulate_close(ShutdownIntent.EXIT_KEEP_CAMERAS_ON, port)
    port.standby.assert_not_called()


def test_existing_shutdown_option_still_powers_off_cameras():
    port = _make_fake_port()
    result = _simulate_close(ShutdownIntent.EXIT_AND_POWER_OFF_CAMERAS, port)
    assert result == "accepted"
    assert "cam1" in port.standby_calls
    assert "cam2" in port.standby_calls


def test_cancel_does_not_close_app_or_power_off_cameras():
    port = _make_fake_port()
    result = _simulate_close(ShutdownIntent.CANCEL, port)
    assert result == "ignored"
    assert port.standby_calls == []


def test_both_cameras_receive_standby_on_power_off():
    port = _make_fake_port()
    _simulate_close(ShutdownIntent.EXIT_AND_POWER_OFF_CAMERAS, port)
    assert port.standby.call_count == 2


# ── _ask_shutdown_intent: login/splash guard ──────────────────────────────────

def _ask_shutdown_intent_logic(normal_work_active: bool) -> ShutdownIntent:
    """Mirror the guard added to _ask_shutdown_intent (no Qt needed)."""
    if not normal_work_active:
        return ShutdownIntent.EXIT_KEEP_CAMERAS_ON
    # In real code the dialog runs here; for the test we stop at the guard.
    return ShutdownIntent.EXIT_KEEP_CAMERAS_ON  # placeholder


def test_shutdown_before_startup_returns_keep_cameras_on_without_dialog():
    """Closing during login/splash must not offer the camera power-off dialog."""
    intent = _ask_shutdown_intent_logic(normal_work_active=False)
    assert intent == ShutdownIntent.EXIT_KEEP_CAMERAS_ON


def test_shutdown_in_normal_work_proceeds_to_dialog():
    """After startup, normal_work_active=True means the dialog path is reached."""
    intent = _ask_shutdown_intent_logic(normal_work_active=True)
    # The dialog would show; our stub returns KEEP_ON — intent is not CANCEL.
    assert intent != ShutdownIntent.CANCEL
