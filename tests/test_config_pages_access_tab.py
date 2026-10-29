#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_config_pages_access_tab.py — ui/config_pages/access_tab.py had no coverage
#
# This tab switches the appliance between the two visible roles and is the entry
# point to the password and auto-unlock schedule. The behaviour that had no test:
#
#   - the product exposes exactly two roles. Every legacy/internal OperatingMode
#     value has to land on one of them; a value that maps to neither leaves the
#     segmented control showing no selection and the operator unable to tell what
#     the machine currently allows.
#   - the role switch must go through AccessModeService and refresh the main
#     panel, or the ⚙ Settings button state and the actual permissions disagree.

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from tests.config_pages_harness import (          # noqa: E402
    button_named, label_texts, make_harness, panel_layout,
)


def build(mode=None, service: bool = True):
    from domain.call_set_policy import OperatingMode

    dialog, mw, layout = make_harness()
    if not service:
        mw._access_mode_svc = None
    elif mode is not None:
        mw._access_mode_svc.mode = mode
    _ = OperatingMode                             # imported for the caller's use
    from ui.config_pages.access_tab import build_access_tab
    build_access_tab(dialog, layout, mw, panel_layout)
    return dialog, mw, layout


def role_line(layout) -> str:
    for text in label_texts(layout):
        if text.startswith("Current role:") or text == "No disponible":
            return text
    raise AssertionError(f"no role label; got {label_texts(layout)}")


def notes(layout) -> str:
    return "\n".join(label_texts(layout))


class TestVisibleRoles:
    def test_only_two_roles_are_offered(self):
        """#roles-simplify: Operator and Administrator, nothing else."""
        dialog, mw, layout = build()
        assert button_named(layout, "Operator")
        assert button_named(layout, "Administrator")

    def test_operator_role_is_named(self):
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(OperatingMode.CAMERA_OPERATOR)
        assert role_line(layout) == "Current role: Operator"

    def test_admin_role_is_named(self):
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(OperatingMode.SYSTEM_ADMIN)
        assert role_line(layout) == "Current role: Administrator"

    @pytest.mark.parametrize("legacy", ["BASIC_OPERATOR", "OPERATOR"])
    def test_legacy_operator_values_read_as_operator(self, legacy):
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(getattr(OperatingMode, legacy))
        assert role_line(layout) == "Current role: Operator"

    @pytest.mark.parametrize("legacy", ["TECHNICIAN", "ADMIN_INSTALLER"])
    def test_legacy_admin_values_read_as_administrator(self, legacy):
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(getattr(OperatingMode, legacy))
        assert role_line(layout) == "Current role: Administrator"

    def test_every_operating_mode_maps_to_a_visible_role(self):
        """A mode that maps to neither would render an unselected control with
        no explanation of what the appliance currently allows."""
        from domain.call_set_policy import OperatingMode
        for mode in OperatingMode:
            dialog, mw, layout = build(mode)
            assert role_line(layout) in {
                "Current role: Operator", "Current role: Administrator",
            }, mode


class TestRoleExplanation:
    def test_operator_note_describes_the_daily_use(self):
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(OperatingMode.CAMERA_OPERATOR)
        assert "Operator: daily room use" in notes(layout)

    def test_operator_note_says_settings_are_hidden(self):
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(OperatingMode.CAMERA_OPERATOR)
        assert "hidden" in notes(layout)

    def test_admin_note_says_settings_are_visible(self):
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(OperatingMode.SYSTEM_ADMIN)
        assert "Settings button is visible" in notes(layout)


class TestSwitchingRole:
    def test_choosing_administrator_goes_through_the_service(self):
        """ADR-006: the write belongs to the application service, never to the
        widget."""
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(OperatingMode.CAMERA_OPERATOR)
        button_named(layout, "Administrator").click()
        assert mw._access_mode_svc.applied == [OperatingMode.SYSTEM_ADMIN]

    def test_choosing_operator_goes_through_the_service(self):
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(OperatingMode.SYSTEM_ADMIN)
        button_named(layout, "Operator").click()
        assert mw._access_mode_svc.applied == [OperatingMode.CAMERA_OPERATOR]

    def test_the_main_panel_is_refreshed(self):
        """Otherwise the ⚙ Settings button and the live permissions disagree."""
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(OperatingMode.CAMERA_OPERATOR)
        button_named(layout, "Administrator").click()
        assert mw._right_panel.calls == ["_update_mode_buttons"]

    def test_the_shown_role_follows_the_service(self):
        """The tab subscribes rather than assuming its own click is the only
        source of change (the login screen can elevate too)."""
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(OperatingMode.CAMERA_OPERATOR)
        mw._access_mode_svc.set_mode(OperatingMode.SYSTEM_ADMIN)
        assert role_line(layout) == "Current role: Administrator"

    def test_switching_does_not_close_the_dialog(self):
        """The operator usually continues in the newly unlocked tabs."""
        from domain.call_set_policy import OperatingMode
        dialog, mw, layout = build(OperatingMode.CAMERA_OPERATOR)
        button_named(layout, "Administrator").click()
        assert dialog.accepted_count == 0


class TestServiceUnavailable:
    def test_the_role_is_reported_as_unavailable(self):
        """A machine whose access service failed to build must not claim a role
        it cannot enforce."""
        dialog, mw, layout = build(service=False)
        assert role_line(layout) == "No disponible"

    def test_clicking_a_role_does_not_crash(self):
        dialog, mw, layout = build(service=False)
        button_named(layout, "Administrator").click()
        assert mw._right_panel.calls == ["_update_mode_buttons"]


class TestPasswordAndSchedule:
    def test_operator_password_change_is_offered(self):
        dialog, mw, layout = build()
        button_named(layout, "Change Operator Password").click()
        assert mw._dialogs.calls == ["ChangePassword"]

    def test_admin_password_change_is_offered(self):
        dialog, mw, layout = build()
        button_named(layout, "Change Admin Password").click()
        assert mw._dialogs.calls == ["ChangeAdminPassword"]

    def test_the_settings_sheet_closes_behind_the_password_dialog(self):
        """Leaving it open stacks a modal behind a modal on the touchscreen."""
        dialog, mw, layout = build()
        button_named(layout, "Change Operator Password").click()
        assert dialog.closed_count == 1

    def test_the_schedule_is_reachable(self):
        dialog, mw, layout = build()
        assert button_named(layout, "Weekly Schedule")

    def test_the_schedule_explains_it_only_covers_operators(self):
        """Admin must always type a password — an installer who believes the
        schedule bypasses that leaves the appliance open."""
        dialog, mw, layout = build()
        assert "Admin always requires password" in notes(layout)
