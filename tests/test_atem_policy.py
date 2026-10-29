#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_atem_policy.py — Single-source-of-truth ATEM live-switch rule (#atem-policy)

from __future__ import annotations

from domain.atem_policy import LIVE_SWITCH_ROLES, can_live_switch
from domain.call_set_policy import OperatingMode


def test_admin_and_technician_may_live_switch():
    assert can_live_switch(OperatingMode.SYSTEM_ADMIN)
    assert can_live_switch(OperatingMode.TECHNICIAN)


def test_everyday_operators_may_not_live_switch():
    assert not can_live_switch(OperatingMode.CAMERA_OPERATOR)
    assert not can_live_switch(OperatingMode.BASIC_OPERATOR)
    assert not can_live_switch(OperatingMode.SUPPORT)
    assert not can_live_switch(OperatingMode.DEMO)


def test_live_switch_roles_is_exactly_admin_and_technician():
    assert LIVE_SWITCH_ROLES == frozenset(
        {OperatingMode.TECHNICIAN, OperatingMode.SYSTEM_ADMIN}
    )


def test_command_service_guard_uses_same_rule():
    """The command service must block exactly the roles the policy blocks."""
    from application.atem_command_service import AtemCommandService

    class _FakePort:
        def cut(self):  # pragma: no cover - only reached for allowed roles
            raise AssertionError("cut() should not run for blocked roles")

        def auto(self):  # pragma: no cover
            raise AssertionError("auto() should not run for blocked roles")

    svc = AtemCommandService(_FakePort())
    for role in OperatingMode:
        if can_live_switch(role):
            continue
        assert not svc.cut(role=role).ok
        assert not svc.auto(role=role).ok
