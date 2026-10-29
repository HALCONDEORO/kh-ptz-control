#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_config_pages_session_tab.py — ui/config_pages/session_tab.py had no coverage
#
# This tab holds the one control that turns a room live. Two behaviours in it are
# safety-relevant and were untested:
#
#   - Start Session is gated on a configured camera. Without the gate the
#     operator starts a session that powers and queries nothing, and the only
#     feedback is cameras that never respond.
#   - End Session is destructive mid-event, so it must ask first and must not act
#     when the operator declines.

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from tests.config_pages_harness import (          # noqa: E402
    button_named, has_text, make_harness, panel_layout,
)


@pytest.fixture
def valid_cameras(monkeypatch):
    import config
    monkeypatch.setattr(config.CAM1, "ip", "172.16.1.11", raising=False)
    monkeypatch.setattr(config.CAM2, "ip", "172.16.1.12", raising=False)


@pytest.fixture
def no_cameras(monkeypatch):
    import config
    monkeypatch.setattr(config.CAM1, "ip", "", raising=False)
    monkeypatch.setattr(config.CAM2, "ip", "", raising=False)


def build(dialog, mw, layout, sim_active: bool = False):
    from ui.config_pages.session_tab import build_session_tab
    build_session_tab(dialog, layout, mw, sim_active, panel_layout)


class TestIdleSession:
    def test_offers_to_start(self, valid_cameras):
        dialog, mw, layout = make_harness(session_active=False)
        build(dialog, mw, layout)
        assert button_named(layout, "Start Session").isEnabled()

    def test_reports_no_session_running(self, valid_cameras):
        dialog, mw, layout = make_harness(session_active=False)
        build(dialog, mw, layout)
        assert has_text(layout, "No session active")

    def test_starting_needs_no_confirmation(self, valid_cameras):
        """Only the destructive direction asks."""
        dialog, mw, layout = make_harness(session_active=False)
        build(dialog, mw, layout)
        button_named(layout, "Start Session").click()
        assert dialog.confirmations == []

    def test_starting_goes_through_the_session_owner(self, valid_cameras):
        """ADR-003: the lifecycle belongs to SessionService, reached here via
        the main window's session facade — never to a direct camera call."""
        dialog, mw, layout = make_harness(session_active=False)
        build(dialog, mw, layout)
        button_named(layout, "Start Session").click()
        assert mw._session.calls == ["ToggleSession"]

    def test_dialog_closes_after_starting(self, valid_cameras):
        """The operator needs the main panel, not the settings sheet."""
        dialog, mw, layout = make_harness(session_active=False)
        build(dialog, mw, layout)
        button_named(layout, "Start Session").click()
        assert dialog.accepted_count == 1


class TestCameraGate:
    def test_start_is_disabled_without_a_camera(self, no_cameras):
        dialog, mw, layout = make_harness(session_active=False)
        build(dialog, mw, layout)
        assert not button_named(layout, "Start Session").isEnabled()

    def test_the_reason_is_shown_not_only_in_a_tooltip(self, no_cameras):
        """On a touchscreen there is no hover, so a disabled button with only a
        tooltip is a dead end."""
        dialog, mw, layout = make_harness(session_active=False)
        build(dialog, mw, layout)
        assert has_text(layout, "No camera configured")

    def test_the_reason_names_where_to_fix_it(self, no_cameras):
        dialog, mw, layout = make_harness(session_active=False)
        build(dialog, mw, layout)
        assert has_text(layout, "Cameras tab")
        assert "Cameras tab" in button_named(layout, "Start Session").toolTip()

    def test_one_configured_camera_is_enough(self, monkeypatch):
        """A single-camera room is a supported install."""
        import config
        monkeypatch.setattr(config.CAM1, "ip", "172.16.1.11", raising=False)
        monkeypatch.setattr(config.CAM2, "ip", "", raising=False)
        dialog, mw, layout = make_harness(session_active=False)
        build(dialog, mw, layout)
        assert button_named(layout, "Start Session").isEnabled()

    def test_a_malformed_ip_does_not_open_the_gate(self, monkeypatch):
        import config
        monkeypatch.setattr(config.CAM1, "ip", "999.1.1", raising=False)
        monkeypatch.setattr(config.CAM2, "ip", "not-an-ip", raising=False)
        dialog, mw, layout = make_harness(session_active=False)
        build(dialog, mw, layout)
        assert not button_named(layout, "Start Session").isEnabled()

    def test_the_gate_does_not_apply_to_ending_a_session(self, no_cameras):
        """A live session must always be stoppable, whatever the config says."""
        dialog, mw, layout = make_harness(session_active=True)
        build(dialog, mw, layout)
        assert button_named(layout, "End Session").isEnabled()


class TestLiveSession:
    def test_offers_to_end(self, valid_cameras):
        dialog, mw, layout = make_harness(session_active=True)
        build(dialog, mw, layout)
        assert has_text(layout, "Session running")

    def test_ending_asks_first(self, valid_cameras):
        dialog, mw, layout = make_harness(session_active=True)
        build(dialog, mw, layout)
        button_named(layout, "End Session").click()
        assert dialog.confirmations == ["End Session"]

    def test_declining_changes_nothing(self, valid_cameras):
        """The stray-tap case: the session must survive it."""
        dialog, mw, layout = make_harness(session_active=True, confirm=False)
        build(dialog, mw, layout)
        button_named(layout, "End Session").click()
        assert mw._session.calls == []
        assert dialog.accepted_count == 0

    def test_confirming_ends_the_session(self, valid_cameras):
        dialog, mw, layout = make_harness(session_active=True, confirm=True)
        build(dialog, mw, layout)
        button_named(layout, "End Session").click()
        assert mw._session.calls == ["ToggleSession"]
        assert dialog.accepted_count == 1


class TestSimulationPanel:
    def test_simulation_state_is_shown(self, valid_cameras):
        dialog, mw, layout = make_harness()
        build(dialog, mw, layout, sim_active=True)
        assert has_text(layout, "Cameras simulated locally")

    def test_real_hardware_state_is_shown(self, valid_cameras):
        dialog, mw, layout = make_harness()
        build(dialog, mw, layout, sim_active=False)
        assert has_text(layout, "Using real hardware")
