#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_config_pages_cameras_tab.py — ui/config_pages/cameras_tab.py had no coverage
#
# Discovery and assignment on this tab is how a camera IP gets set on a customer
# site, so the untested behaviour was the part that decides whether the install
# survives a reboot:
#
#   - an assignment that could not be persisted must say so. It still applies for
#     the running session, and an installer who reads "assigned" and reboots
#     loses the camera without ever seeing an error.
#   - only one IP per role. Assigning a second discovered device to Platform has
#     to release the first, or the panel shows two cameras claiming one role.
#   - sensitive fields are locked during a live session — changing an IP mid-event
#     drops camera tracking.
#   - a scan that fails, or one that returns after the dialog is closed, must not
#     leave the Scan button dead or write into a destroyed widget tree.

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from tests.config_pages_harness import (          # noqa: E402
    button_named, buttons, has_text, label_texts, make_harness, panel_layout,
    run_threads_inline,
)


@pytest.fixture(autouse=True)
def offline_cameras(monkeypatch):
    """No sockets from a test: check_camera is what the re-check calls."""
    import config
    monkeypatch.setattr(config, "check_camera", lambda ip, cam_id: False, raising=False)
    monkeypatch.setattr(config.CAM1, "ip", "172.16.1.11", raising=False)
    monkeypatch.setattr(config.CAM2, "ip", "172.16.1.12", raising=False)
    monkeypatch.setattr(config.CAM1, "check", None, raising=False)
    monkeypatch.setattr(config.CAM2, "check", None, raising=False)


@pytest.fixture
def discovery(monkeypatch):
    """Control what a network scan finds."""
    import application.camera_discovery as camera_discovery

    state = {"found": ["172.16.1.21", "172.16.1.22"], "error": None}

    def _discover():
        if state["error"] is not None:
            raise state["error"]
        return state["found"]

    monkeypatch.setattr(camera_discovery, "discover_cameras", _discover)
    return state


def build(monkeypatch, *, is_on=False, sim_active=False, visible=True, inline=True):
    dialog, mw, layout = make_harness(visible=visible)
    import ui.config_pages.cameras_tab as tab
    if inline:
        run_threads_inline(monkeypatch, tab)
    tab.build_cameras_tab(dialog, layout, mw, is_on, sim_active, panel_layout)
    return dialog, mw, layout


def assign_buttons(dialog, role: str) -> list:
    """The per-device assign buttons for *role*, as the tab itself tracks them.

    Read from dialog._disc_buttons rather than by walking the widget tree: a
    rescan calls deleteLater() on the old rows, which only frees on the next
    event-loop pass, so a tree walk would still see the previous scan's buttons.
    """
    return list(dialog._disc_buttons[1 if role == "Platform" else 2])


def field_row_buttons(layout) -> list:
    """The edit control of every IP/VISCA field row."""
    from PyQt5.QtWidgets import QPushButton, QWidget

    found = []
    for widget in layout.parentWidget().findChildren(QWidget):
        if widget.objectName() == "FieldRow":
            found.extend(widget.findChildren(QPushButton))
    return found


class TestCameraCards:
    def test_both_cameras_are_shown(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch)
        assert has_text(layout, "Platform")
        assert has_text(layout, "Comments")

    def test_the_configured_ip_is_shown(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch)
        assert "172.16.1.11" in label_texts(layout)
        assert "172.16.1.12" in label_texts(layout)

    def test_the_ip_label_is_tracked_for_live_updates(self, monkeypatch):
        """The card must refresh in place after an assignment — no restart."""
        dialog, mw, layout = build(monkeypatch)
        assert set(dialog._cam_ip_labels) == {1, 2}


class TestLiveSessionLock:
    def test_a_banner_explains_the_lock(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch, is_on=True)
        assert has_text(layout, "Session active")
        assert has_text(layout, "Stop the session")

    def test_no_banner_when_idle(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch, is_on=False)
        assert not has_text(layout, "Session active")

    def test_edit_controls_are_disabled_during_a_session(self, monkeypatch):
        """Changing an IP mid-event drops camera tracking."""
        dialog, mw, layout = build(monkeypatch, is_on=True)
        icon_buttons = [b for b in buttons(layout) if b.toolTip().startswith("Stop the session")]
        assert icon_buttons, "no field-edit control was locked"
        assert all(not b.isEnabled() for b in icon_buttons)

    def test_edit_controls_are_enabled_when_idle(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch, is_on=False)
        edit_buttons = field_row_buttons(layout)
        assert len(edit_buttons) == 4          # IP + VISCA, per camera
        assert all(b.isEnabled() for b in edit_buttons)


class TestDiscovery:
    def test_found_devices_are_listed(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assert "172.16.1.21" in label_texts(layout)
        assert "172.16.1.22" in label_texts(layout)

    def test_the_count_is_reported(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assert has_text(layout, "2 device(s) found")

    def test_each_device_can_be_assigned_to_either_role(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assert len(assign_buttons(dialog, "Platform")) == 2
        assert len(assign_buttons(dialog, "Comments")) == 2

    def test_an_empty_network_says_so(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        discovery["found"] = []
        button_named(layout, "Scan Network").click()
        assert has_text(layout, "No VISCA devices found")

    def test_a_failing_scan_is_not_reported_as_devices(self, monkeypatch, discovery):
        """A broadcast that raises (no route, permission) must degrade to "none
        found", not crash the panel."""
        dialog, mw, layout = build(monkeypatch)
        discovery["error"] = OSError("network is unreachable")
        button_named(layout, "Scan Network").click()
        assert has_text(layout, "No VISCA devices found")

    def test_the_scan_button_always_comes_back(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        discovery["error"] = OSError("boom")
        btn = button_named(layout, "Scan Network")
        btn.click()
        assert btn.isEnabled()
        assert btn.text() == "Scan Network"

    def test_a_rescan_replaces_the_previous_results(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        discovery["found"] = ["172.16.1.30"]
        button_named(layout, "Scan Network").click()
        assert len(assign_buttons(dialog, "Platform")) == 1

    def test_nothing_is_written_to_a_closed_dialog(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch, visible=False)
        button_named(layout, "Scan Network").click()
        assert "172.16.1.21" not in label_texts(layout)

    def test_the_scan_runs_off_the_gui_thread(self, monkeypatch, discovery):
        """A VISCA broadcast blocks for seconds."""
        import ui.config_pages.cameras_tab as tab
        started = []

        class _Thread:
            def __init__(self, target=None, daemon=None):
                started.append(daemon)

            def start(self):
                pass

        monkeypatch.setattr(tab, "threading", type("T", (), {"Thread": _Thread}))
        dialog, mw, layout = make_harness()
        tab.build_cameras_tab(dialog, layout, mw, False, False, panel_layout)
        button_named(layout, "Scan Network").click()
        assert started == [True]


class TestAssignment:
    def test_the_service_owns_the_write(self, monkeypatch, discovery):
        """ADR-006 / #893: the widget never writes config.yaml itself."""
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert mw._camera_config.camera_ips == [(1, "172.16.1.21")]

    def test_comments_role_targets_camera_two(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Comments")[1].click()
        assert mw._camera_config.camera_ips == [(2, "172.16.1.22")]

    def test_a_saved_assignment_says_so(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert dialog.toasts == [("Platform camera → 172.16.1.21 assigned and saved", "ok")]

    def test_an_unpersisted_assignment_warns_that_it_is_temporary(self, monkeypatch, discovery):
        """The dangerous case: applied live but not written. Reporting it as
        saved loses the camera on the next reboot."""
        dialog, mw, layout = build(monkeypatch)
        mw._camera_config.result = type("R", (), {"ok": True, "code": "PARTIAL"})()
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert dialog.toasts == [
            ("Platform camera → 172.16.1.21 assigned (this session only)", "warn"),
        ]

    def test_a_failed_write_is_not_reported_as_saved(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        mw._camera_config.result = type("R", (), {"ok": False, "code": "OK"})()
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert dialog.toasts[0][1] == "warn"

    def test_a_missing_service_still_reports_honestly(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        mw._camera_config = None
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert dialog.toasts[0][1] == "warn"

    def test_the_card_shows_the_new_ip_without_a_restart(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert dialog._cam_ip_labels[1].text() == "172.16.1.21"

    def test_the_used_button_is_marked_and_spent(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        btn = assign_buttons(dialog, "Platform")[0]
        btn.click()
        assert btn.text() == "✓ Platform"
        assert not btn.isEnabled()

    def test_only_one_device_can_hold_a_role(self, monkeypatch, discovery):
        """Assigning the second device to Platform must release the first."""
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        first, second = assign_buttons(dialog, "Platform")
        first.click()
        second.click()
        assert first.isEnabled() and first.text() == "→ Platform"
        assert not second.isEnabled() and second.text() == "✓ Platform"

    def test_the_other_role_is_untouched(self, monkeypatch, discovery):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert all(b.isEnabled() for b in assign_buttons(dialog, "Comments"))


class TestConnectivityRecheck:
    def test_a_real_assignment_rechecks_the_link(self, monkeypatch, discovery):
        import config
        seen = []
        monkeypatch.setattr(
            config, "check_camera",
            lambda ip, cam_id: seen.append(ip) or True, raising=False,
        )
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert seen == ["172.16.1.21"]

    def test_the_recheck_result_is_recorded_on_the_camera(self, monkeypatch, discovery):
        import config
        monkeypatch.setattr(config, "check_camera", lambda ip, cam_id: True, raising=False)
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert config.CAM1.check == "Green"

    def test_an_unreachable_camera_is_recorded_as_red(self, monkeypatch, discovery):
        import config
        monkeypatch.setattr(config, "check_camera", lambda ip, cam_id: False, raising=False)
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert config.CAM1.check == "Red"

    def test_a_raising_probe_counts_as_offline(self, monkeypatch, discovery):
        import config

        def _boom(ip, cam_id):
            raise OSError("no route to host")

        monkeypatch.setattr(config, "check_camera", _boom, raising=False)
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert config.CAM1.check == "Red"

    def test_simulation_never_touches_the_network(self, monkeypatch, discovery):
        """In simulation the link is up by definition; probing a fake IP would
        just add a timeout to every assignment."""
        import config
        seen = []
        monkeypatch.setattr(
            config, "check_camera",
            lambda ip, cam_id: seen.append(ip) or True, raising=False,
        )
        dialog, mw, layout = build(monkeypatch, sim_active=True)
        button_named(layout, "Scan Network").click()
        assign_buttons(dialog, "Platform")[0].click()
        assert seen == []


class TestReconnect:
    def test_reconnect_goes_through_the_camera_manager(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch)
        button_named(layout, "Reconnect Cameras").click()
        assert mw._cameras.calls == ["reconnect_all"]

    def test_the_button_is_held_while_reconnecting(self, monkeypatch):
        """Repeated taps would tear down the sockets mid-handshake."""
        dialog, mw, layout = build(monkeypatch)
        btn = button_named(layout, "Reconnect Cameras")
        btn.click()
        assert not btn.isEnabled()
        assert btn.text() == "Reconnecting…"

    def test_a_missing_camera_manager_does_nothing(self, monkeypatch):
        dialog, mw, layout = build(monkeypatch)
        mw._cameras = None
        btn = button_named(layout, "Reconnect Cameras")
        btn.click()
        assert btn.isEnabled()
