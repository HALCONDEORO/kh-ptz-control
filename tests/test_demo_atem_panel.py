#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_demo_atem_panel.py — Tests for DemoAtemPanel helper functions
#
# All tests here exercise the pure (non-Qt) helper functions extracted from
# demo_atem_panel.py.  No QApplication or Qt widget is instantiated, so these
# tests are safe in headless CI environments.
#
# Any test that actually needs a Qt display is skipped under offscreen.

import os

import pytest

from ui.demo_atem_panel import _format_automation_state, _format_input_label

# The two widget smoke tests below instantiate a real DemoAtemPanel. Under the
# offscreen platform that leaves shared Qt state which segfaults later real-Qt
# test modules (e.g. the setup wizard) at module transition. They genuinely
# require a real display, so skip them headlessly instead of xfailing.
_NEEDS_DISPLAY = pytest.mark.skipif(
    os.environ.get("QT_QPA_PLATFORM", "") == "offscreen",
    reason="requires a real Qt display; unstable under the offscreen platform",
)


# ── _format_input_label ────────────────────────────────────────────────────────

class TestFormatInputLabel:
    def test_none_returns_none_string(self):
        assert _format_input_label(None) == "None"

    def test_input_1_pc(self):
        result = _format_input_label(1)
        assert "1" in result
        assert "PC" in result

    def test_input_2_platform(self):
        result = _format_input_label(2)
        assert "2" in result
        assert "Platform" in result

    def test_input_3_comments(self):
        result = _format_input_label(3)
        assert "3" in result
        assert "Comments" in result

    def test_input_4_none_label(self):
        result = _format_input_label(4)
        assert "4" in result
        assert "None" in result

    def test_unmapped_input_fallback(self):
        result = _format_input_label(99)
        assert "99" in result

    def test_unmapped_input_contains_input_word(self):
        result = _format_input_label(42)
        assert "Input" in result or "42" in result

    def test_all_mapped_ids_contain_id(self):
        for input_id in (1, 2, 3, 4):
            result = _format_input_label(input_id)
            assert str(input_id) in result


# ── _format_automation_state ──────────────────────────────────────────────────

class TestFormatAutomationState:
    def test_disarmed_returns_disarmed(self):
        result = _format_automation_state(armed=False, log_only=False, reconnect_guard=False)
        assert result == "DISARMED"

    def test_disarmed_overrides_log_only(self):
        # Even if log_only is True, disarmed takes priority
        result = _format_automation_state(armed=False, log_only=True, reconnect_guard=False)
        assert result == "DISARMED"

    def test_disarmed_overrides_reconnect_guard(self):
        result = _format_automation_state(armed=False, log_only=False, reconnect_guard=True)
        assert result == "DISARMED"

    def test_armed_no_flags(self):
        result = _format_automation_state(armed=True, log_only=False, reconnect_guard=False)
        assert result == "ARMED"

    def test_log_only_when_armed(self):
        result = _format_automation_state(armed=True, log_only=True, reconnect_guard=False)
        assert result == "LOG-ONLY"

    def test_reconnect_guard_when_armed(self):
        result = _format_automation_state(armed=True, log_only=False, reconnect_guard=True)
        assert "ARMED" in result
        assert "reconnect" in result.lower()

    def test_log_only_takes_priority_over_reconnect_guard(self):
        # log_only is evaluated before reconnect_guard in the dispatcher
        result = _format_automation_state(armed=True, log_only=True, reconnect_guard=True)
        assert result == "LOG-ONLY"

    def test_result_is_string(self):
        for armed in (True, False):
            for log_only in (True, False):
                for reconnect_guard in (True, False):
                    result = _format_automation_state(armed, log_only, reconnect_guard)
                    assert isinstance(result, str)
                    assert result  # non-empty

    def test_pip_automation_disabled_appends_suffix(self):
        result = _format_automation_state(armed=True, log_only=False,
                                          reconnect_guard=False, pip_automation_enabled=False)
        assert "PiP OFF" in result

    def test_pip_automation_enabled_no_suffix(self):
        result = _format_automation_state(armed=True, log_only=False,
                                          reconnect_guard=False, pip_automation_enabled=True)
        assert "PiP" not in result

    def test_pip_automation_disabled_with_disarmed(self):
        result = _format_automation_state(armed=False, log_only=False,
                                          reconnect_guard=False, pip_automation_enabled=False)
        assert "DISARMED" in result
        assert "PiP OFF" in result

    def test_pip_automation_defaults_to_enabled(self):
        # Should not show PiP suffix when not specified
        result = _format_automation_state(armed=True, log_only=False, reconnect_guard=False)
        assert "PiP" not in result


# ── Qt widget smoke test (requires display) ───────────────────────────────────

@_NEEDS_DISPLAY
def test_demo_atem_panel_instantiates():
    """Smoke test: DemoAtemPanel can be instantiated with fake dependencies."""
    from PyQt5.QtWidgets import QApplication
    import sys

    from adapters.fake_atem import FakeATEM
    from adapters.atem_dispatcher import ATEMDispatcher
    from ui.demo_atem_panel import DemoAtemPanel

    QApplication.instance() or QApplication(sys.argv)
    fake_atem = FakeATEM()
    dispatcher = ATEMDispatcher(session_provider=lambda: True)
    panel = DemoAtemPanel(fake_atem=fake_atem, dispatcher=dispatcher)
    assert panel is not None
    panel.refresh()  # must not raise


@_NEEDS_DISPLAY
def test_demo_atem_panel_refresh_after_input_change():
    """Panel reflects input change after set_program_input is called."""
    from PyQt5.QtWidgets import QApplication
    import sys

    from adapters.fake_atem import FakeATEM
    from adapters.atem_dispatcher import ATEMDispatcher
    from ui.demo_atem_panel import DemoAtemPanel

    QApplication.instance() or QApplication(sys.argv)
    fake_atem = FakeATEM()
    fake_atem.connect()
    dispatcher = ATEMDispatcher(session_provider=lambda: True)
    panel = DemoAtemPanel(fake_atem=fake_atem, dispatcher=dispatcher)

    fake_atem.set_program_input(2)
    panel.refresh()
    assert "2" in panel._lbl_program.text()
    assert "Platform" in panel._lbl_program.text()  # input 2 = Platform
