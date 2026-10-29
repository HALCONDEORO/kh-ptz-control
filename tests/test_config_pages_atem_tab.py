#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_config_pages_atem_tab.py — ui/config_pages/atem_tab.py had no coverage
#
# The ATEM tab is where a switcher gets found, assigned and re-checked on site.
# The untested behaviour that matters:
#
#   - an assignment that could not be persisted must be reported as temporary,
#     exactly like the camera tab: the switcher works until the next reboot.
#   - the reachability probe must never run on the GUI thread (a TCP connect to
#     an absent switcher blocks for the full timeout) and must report failure
#     with the address it tried, which is the only clue an installer gets.
#   - the status pill must follow the monitor, including the states it reaches on
#     its own after the tab was built.
#   - assigning is locked during a live session, and the tab must stop listening
#     to the main window once the dialog is destroyed.

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from tests.config_pages_harness import (          # noqa: E402
    button_named, buttons, has_text, label_texts, make_harness, panel_layout,
    run_threads_inline,
)


@pytest.fixture(autouse=True)
def configured_atem(monkeypatch):
    import config
    monkeypatch.setattr(config.ATEM, "ip", "172.16.1.50", raising=False)


@pytest.fixture
def discovery(monkeypatch):
    import application.camera_discovery as camera_discovery

    state = {"found": ["172.16.1.51", "172.16.1.52"], "error": None}

    def _discover():
        if state["error"] is not None:
            raise state["error"]
        return state["found"]

    monkeypatch.setattr(camera_discovery, "discover_atem_switchers", _discover)
    return state


@pytest.fixture
def no_socket(monkeypatch):
    """Answer the reachability probe without touching the network."""
    import ui.config_pages.atem_tab as tab

    state = {"reachable": True, "targets": []}

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _create_connection(address, timeout=None):
        state["targets"].append(address)
        if not state["reachable"]:
            raise OSError("timed out")
        return _Conn()

    monkeypatch.setattr(tab.socket, "create_connection", _create_connection)
    return state


def build(monkeypatch, *, is_on=False, sim_active=False, visible=True,
          state=None, last_error="", inline=True):
    dialog, mw, layout = make_harness(visible=visible)
    mw._atem_monitor.state = state
    mw._atem_monitor.last_error = last_error
    import ui.config_pages.atem_tab as tab
    if inline:
        run_threads_inline(monkeypatch, tab)
    tab.build_atem_tab(dialog, layout, mw, is_on, sim_active, panel_layout)
    return dialog, mw, layout


def use_buttons(layout) -> list:
    return [b for b in buttons(layout) if b.text() in {"→ Use", "✓ Set"}]


def pill_text(layout) -> str:
    """The connection-status pill's text.

    Matched exactly, not by substring: "Disconnected" contains "connected", so a
    loose check would report a broken switcher as a healthy one.
    """
    for text in label_texts(layout):
        if text.strip().startswith("●"):
            return text.strip()
    raise AssertionError(f"no status pill; got {label_texts(layout)}")


def error_label(layout):
    """The "Last error:" line — hidden rather than emptied when it goes stale."""
    from PyQt5.QtWidgets import QLabel

    for label in layout.parentWidget().findChildren(QLabel):
        if label.text().startswith("Last error"):
            return label
    raise AssertionError("no 'Last error' label found")


class TestSwitcherCard:
    def test_the_configured_ip_is_shown(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch)
        assert "172.16.1.50" in label_texts(layout)

    def test_discovery_is_offered_for_an_unknown_switcher(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch)
        assert button_named(layout, "Discover switchers")

    def test_a_reachability_probe_is_offered(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch)
        assert button_named(layout, "Scan").isEnabled()


class TestStatusPill:
    def test_connected_state_is_shown(self, monkeypatch):
        from domain.atem_state import ATEMState
        dialog, mw, layout = build(monkeypatch, state=ATEMState.CONNECTED)
        assert pill_text(layout) == "● Connected"

    def test_disconnected_state_is_shown(self, monkeypatch):
        from domain.atem_state import ATEMState
        dialog, mw, layout = build(monkeypatch, state=ATEMState.DISCONNECTED)
        assert pill_text(layout) == "● Disconnected"

    def test_a_missing_dependency_is_named(self, monkeypatch):
        """python-atem absent is a different fix from a cable problem."""
        from domain.atem_state import ATEMState
        dialog, mw, layout = build(monkeypatch, state=ATEMState.DEPENDENCY_MISSING)
        assert pill_text(layout) == "● Library missing"

    def test_an_unknown_state_does_not_claim_a_connection(self, monkeypatch):
        """No monitor yet — the pill must not read "Connected"."""
        dialog, mw, layout = build(monkeypatch, state=None)
        assert pill_text(layout) == "● Unknown"

    def test_every_state_has_a_label(self, monkeypatch):
        from domain.atem_state import ATEMState
        for state in ATEMState:
            dialog, mw, layout = build(monkeypatch, state=state)
            assert pill_text(layout) != "● Unknown", state

    def test_the_last_error_is_shown_when_there_is_one(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch, last_error="connection refused")
        assert has_text(layout, "connection refused")

    def test_no_error_line_when_healthy(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch, last_error="")
        assert not has_text(layout, "Last error")


class TestDiscovery:
    def test_found_switchers_are_listed(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Discover switchers").click()
        assert "172.16.1.51" in label_texts(layout)
        assert has_text(layout, "2 switcher(s) found")

    def test_an_empty_network_says_so(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        discovery["found"] = []
        button_named(layout, "Discover switchers").click()
        assert has_text(layout, "No ATEM switchers found")

    def test_a_failing_scan_degrades_to_none_found(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        discovery["error"] = OSError("network is unreachable")
        button_named(layout, "Discover switchers").click()
        assert has_text(layout, "No ATEM switchers found")

    def test_the_button_always_comes_back(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        discovery["error"] = OSError("boom")
        btn = button_named(layout, "Discover switchers")
        btn.click()
        assert btn.isEnabled()
        assert btn.text() == "Discover switchers"

    def test_nothing_is_written_to_a_closed_dialog(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch, visible=False)
        button_named(layout, "Discover switchers").click()
        assert "172.16.1.51" not in label_texts(layout)

    def test_discovery_is_locked_during_a_live_session(self, monkeypatch, discovery):
        """Repointing the switcher mid-event cuts the program feed the
        automation follows."""
        dialog, mw, layout = build(monkeypatch, is_on=True)
        assert not button_named(layout, "Discover switchers").isEnabled()

    def test_the_scan_runs_off_the_gui_thread(self, monkeypatch, discovery):
        import ui.config_pages.atem_tab as tab
        started = []

        class _Thread:
            def __init__(self, target=None, daemon=None):
                started.append(daemon)

            def start(self):
                pass

        monkeypatch.setattr(tab, "threading", type("T", (), {"Thread": _Thread}))
        dialog, mw, layout = make_harness()
        tab.build_atem_tab(dialog, layout, mw, False, False, panel_layout)
        button_named(layout, "Discover switchers").click()
        assert started == [True]


class TestAssignment:
    def test_the_service_owns_the_write(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Discover switchers").click()
        use_buttons(layout)[0].click()
        assert mw._camera_config.atem_ips == ["172.16.1.51"]

    def test_a_saved_assignment_says_so(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Discover switchers").click()
        use_buttons(layout)[0].click()
        assert dialog.toasts == [("ATEM → 172.16.1.51 assigned and saved", "ok")]

    def test_an_unpersisted_assignment_warns_that_it_is_temporary(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        mw._camera_config.result = type("R", (), {"ok": True, "code": "PARTIAL"})()
        button_named(layout, "Discover switchers").click()
        use_buttons(layout)[0].click()
        assert dialog.toasts == [("ATEM → 172.16.1.51 assigned (this session only)", "warn")]

    def test_a_missing_service_still_reports_honestly(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        mw._camera_config = None
        button_named(layout, "Discover switchers").click()
        use_buttons(layout)[0].click()
        assert dialog.toasts[0][1] == "warn"

    def test_the_card_shows_the_new_ip(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Discover switchers").click()
        use_buttons(layout)[0].click()
        assert "172.16.1.51" in label_texts(layout)

    def test_the_monitor_is_restarted_on_the_new_address(self, monkeypatch, discovery):
        """Without this the panel shows a switcher it is not talking to."""
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Discover switchers").click()
        use_buttons(layout)[0].click()
        assert mw.restarts == 1

    def test_the_pill_moves_to_connecting(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Discover switchers").click()
        use_buttons(layout)[0].click()
        assert pill_text(layout) == "● Connecting…"

    def test_the_used_button_is_marked_and_spent(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Discover switchers").click()
        btn = use_buttons(layout)[0]
        btn.click()
        assert btn.text() == "✓ Set"
        assert not btn.isEnabled()


class TestReachabilityProbe:
    def test_disabled_without_a_configured_switcher(self, monkeypatch):
        """There is nothing to probe, and the reason must be visible."""
        import config
        monkeypatch.setattr(config.ATEM, "ip", "", raising=False)
        dialog, mw, layout = build(monkeypatch)
        btn = button_named(layout, "Scan")
        assert not btn.isEnabled()
        assert "Configure the ATEM IP" in btn.toolTip()

    def test_it_probes_the_control_port(self, monkeypatch, no_socket):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan").click()
        assert no_socket["targets"] == [("172.16.1.50", 9910)]

    def test_a_reachable_switcher_restarts_the_monitor(self, monkeypatch, no_socket):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan").click()
        assert mw.restarts == 1
        assert pill_text(layout) == "● Connecting…"

    def test_an_unreachable_switcher_is_reported_with_its_address(self, monkeypatch, no_socket):
        """The address is the whole diagnostic value of the probe."""
        dialog, mw, layout = build(monkeypatch)
        no_socket["reachable"] = False
        button_named(layout, "Scan").click()
        assert has_text(layout, "No response from 172.16.1.50:9910")
        assert pill_text(layout) == "● Disconnected"

    def test_an_unreachable_switcher_does_not_restart_the_monitor(self, monkeypatch, no_socket):
        dialog, mw, layout = build(monkeypatch)
        no_socket["reachable"] = False
        button_named(layout, "Scan").click()
        assert mw.restarts == 0

    def test_the_button_always_comes_back(self, monkeypatch, no_socket):
        dialog, mw, layout = build(monkeypatch)
        no_socket["reachable"] = False
        btn = button_named(layout, "Scan")
        btn.click()
        assert btn.isEnabled()
        assert btn.text() == "Scan"

    def test_simulation_never_touches_the_network(self, monkeypatch, no_socket):
        dialog, mw, layout = build(monkeypatch, sim_active=True)
        button_named(layout, "Scan").click()
        assert no_socket["targets"] == []
        assert mw.restarts == 1

    def test_the_probe_runs_off_the_gui_thread(self, monkeypatch, no_socket):
        """socket.create_connection blocks for the full 3 s timeout."""
        import ui.config_pages.atem_tab as tab
        started = []

        class _Thread:
            def __init__(self, target=None, daemon=None):
                started.append(daemon)

            def start(self):
                pass

        monkeypatch.setattr(tab, "threading", type("T", (), {"Thread": _Thread}))
        dialog, mw, layout = make_harness()
        tab.build_atem_tab(dialog, layout, mw, False, False, panel_layout)
        button_named(layout, "Scan").click()
        assert started == [True]


class TestReconnect:
    def test_it_restarts_the_monitor(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Reconnect ATEM").click()
        assert mw.restarts == 1

    def test_the_button_is_held_while_reconnecting(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch)
        btn = button_named(layout, "Reconnect ATEM")
        btn.click()
        assert not btn.isEnabled()
        assert btn.text() == "Reconnecting…"

    def test_the_stale_error_is_cleared(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch, last_error="connection refused")
        button_named(layout, "Reconnect ATEM").click()
        assert error_label(layout).isHidden()


class TestMonitorUpdates:
    def test_the_pill_follows_the_monitor(self, monkeypatch):
        """The monitor reaches CONNECTED on its own, after the tab was built."""
        from domain.atem_state import ATEMState
        dialog, mw, layout = build(monkeypatch, state=ATEMState.DISCONNECTED)
        mw.atem_state_changed.emit(ATEMState.CONNECTED)
        assert pill_text(layout) == "● Connected"

    def test_a_new_error_is_surfaced(self, monkeypatch):
        from domain.atem_state import ATEMState
        dialog, mw, layout = build(monkeypatch)
        mw._atem_monitor.last_error = "no route to host"
        mw.atem_state_changed.emit(ATEMState.ERROR)
        assert has_text(layout, "no route to host")

    def test_the_reconnect_button_is_released(self, monkeypatch):
        from domain.atem_state import ATEMState
        dialog, mw, layout = build(monkeypatch)
        btn = button_named(layout, "Reconnect ATEM")
        btn.click()
        mw.atem_state_changed.emit(ATEMState.CONNECTED)
        assert btn.isEnabled()
        assert btn.text() == "Reconnect ATEM"

    def test_it_stops_listening_once_the_dialog_is_gone(self, monkeypatch):
        """A slot still bound to a deleted widget tree crashes the app the next
        time the monitor changes state."""
        from domain.atem_state import ATEMState
        dialog, mw, layout = build(monkeypatch, state=ATEMState.DISCONNECTED)
        dialog.destroyed.emit()          # what Qt emits when the dialog dies
        mw.atem_state_changed.emit(ATEMState.CONNECTED)
        assert pill_text(layout) == "● Disconnected"


class TestControlPanelButton:
    def test_absent_when_there_is_no_panel(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch)
        assert not any("Control Panel" in b.text() for b in buttons(layout))

    def test_opens_the_panel_and_closes_the_settings_sheet(self, monkeypatch):
        dialog, mw, layout = make_harness()
        mw._atem_panel = object()
        import ui.config_pages.atem_tab as tab
        tab.build_atem_tab(dialog, layout, mw, False, False, panel_layout)
        button_named(layout, "Control Panel").click()
        assert mw.panel_toggles == 1
        assert dialog.accepted_count == 1
