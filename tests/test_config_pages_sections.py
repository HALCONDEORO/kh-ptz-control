#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_config_pages_sections.py — ui/config_pages/sections.py had no coverage
#
# 835 lines and the largest untested module in the repo: the shared section
# builders behind four different Settings tabs. What matters here:
#
#   - Preset validation physically drives the cameras through every seat. It must
#     be locked during a live session, must confirm before moving anything, and
#     must stop the runner when the dialog goes away — a runner left alive keeps
#     recalling presets on a room nobody is looking at.
#   - Arming ATEM automation hands camera control to the switcher. Two confirms
#     (dialog + typed phrase) guard it, and it must be impossible to arm against
#     an ATEM that is not configured.
#   - The second-platform toggle must apply even when the runtime data dir is
#     read-only, and must say that it did not persist (a production Pi symptom
#     the code comment records).
#   - The status strip resolves every camera/ATEM state to an LED; a state that
#     falls through to the wrong colour misreports the room at a glance.

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from tests.config_pages_harness import (          # noqa: E402
    AtemDispatcherDouble, button_named, buttons, has_text, make_harness,
)


def sections():
    import ui.config_pages.sections as mod
    return mod


# ══════════════════════════════════════════════════════════════════════════════
#  Second platform
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def display_prefs(monkeypatch):
    """Keep the toggle away from the real display_prefs.json."""
    import application.display_prefs as prefs

    state = {"enabled": False, "persist_ok": True, "written": []}

    monkeypatch.setattr(prefs, "is_second_platform_enabled", lambda: state["enabled"])

    def _set(value):
        state["written"].append(value)
        if state["persist_ok"]:
            state["enabled"] = value
        return state["persist_ok"]

    monkeypatch.setattr(prefs, "set_second_platform_enabled", _set)
    return state


class TestSecondPlatformSection:
    def _build(self):
        dialog, mw, layout = make_harness()
        sections().build_second_platform_section(dialog, layout, mw)
        return dialog, mw, layout

    def test_disabled_state_is_shown(self, display_prefs):
        dialog, mw, layout = self._build()
        assert has_text(layout, "Second platform OFF")
        assert button_named(layout, "Enable Second Platform")

    def test_enabled_state_is_shown(self, display_prefs):
        display_prefs["enabled"] = True
        dialog, mw, layout = self._build()
        assert has_text(layout, "Second platform ON")
        assert button_named(layout, "Disable Second Platform")

    def test_the_preset_it_recalls_is_documented(self, display_prefs):
        """An installer has to know which preset slot to store."""
        dialog, mw, layout = self._build()
        assert has_text(layout, "preset 132")

    def test_enabling_persists_the_choice(self, display_prefs):
        dialog, mw, layout = self._build()
        button_named(layout, "Enable Second Platform").click()
        assert display_prefs["written"] == [True]

    def test_enabling_applies_live(self, display_prefs):
        """"sin reiniciar" is the promise in the docstring."""
        dialog, mw, layout = self._build()
        button_named(layout, "Enable Second Platform").click()
        assert mw.second_platform_visibility == [True]

    def test_the_button_flips_to_the_reverse_action(self, display_prefs):
        dialog, mw, layout = self._build()
        btn = button_named(layout, "Enable Second Platform")
        btn.click()
        assert btn.text() == "Disable Second Platform"

    def test_disabling_applies_live(self, display_prefs):
        display_prefs["enabled"] = True
        dialog, mw, layout = self._build()
        button_named(layout, "Disable Second Platform").click()
        assert mw.second_platform_visibility == [False]

    def test_success_is_confirmed(self, display_prefs):
        dialog, mw, layout = self._build()
        button_named(layout, "Enable Second Platform").click()
        assert dialog.toasts == [("Second platform enabled", "ok")]

    def test_a_read_only_data_dir_still_applies_the_change(self, display_prefs):
        """The production-Pi symptom the code comment records: refusing to apply
        left the operator unable to enable Platform 2 at all."""
        display_prefs["persist_ok"] = False
        dialog, mw, layout = self._build()
        button_named(layout, "Enable Second Platform").click()
        assert mw.second_platform_visibility == [True]

    def test_a_read_only_data_dir_is_reported_honestly(self, display_prefs):
        display_prefs["persist_ok"] = False
        dialog, mw, layout = self._build()
        button_named(layout, "Enable Second Platform").click()
        assert "could not save" in dialog.toasts[0][0]

    def test_a_failing_live_apply_does_not_lose_the_setting(self, display_prefs):
        """The live-apply hook touches the main panel's widgets; if that raises
        (torn-down panel, older main window), the preference must still be
        written and the operator must still get feedback."""
        def _boom(value):
            raise RuntimeError("right panel already destroyed")

        dialog, mw, layout = make_harness()
        mw.apply_second_platform_visibility = _boom
        sections().build_second_platform_section(dialog, layout, mw)
        button_named(layout, "Enable Second Platform").click()
        assert display_prefs["written"] == [True]
        assert dialog.toasts == [("Second platform enabled", "ok")]


# ══════════════════════════════════════════════════════════════════════════════
#  Simulation mode
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sim_mode(monkeypatch):
    """Never touch the real sim-mode marker files."""
    import ui.config_pages.sections as mod

    state = {"active": False, "activated": 0, "deactivated": 0, "error": None}

    class _SimMode:
        @staticmethod
        def is_active():
            return state["active"]

        @staticmethod
        def activate():
            if state["error"] is not None:
                raise state["error"]
            state["activated"] += 1
            state["active"] = True

        @staticmethod
        def deactivate():
            if state["error"] is not None:
                raise state["error"]
            state["deactivated"] += 1
            state["active"] = False

    monkeypatch.setattr(mod, "_sim_mode", _SimMode)
    return state


@pytest.fixture
def warnings_box(monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda parent, title, text, *a, **k: seen.append((title, text)),
    )
    return seen


class TestSimSection:
    def _build(self, *, sim_active=False, confirm=True, session_active=False):
        dialog, mw, layout = make_harness(confirm=confirm, session_active=session_active)
        sections().build_sim_section(dialog, layout, mw, sim_active)
        return dialog, mw, layout

    def test_real_hardware_is_stated(self, sim_mode):
        dialog, mw, layout = self._build(sim_active=False)
        assert has_text(layout, "Using real hardware")

    def test_simulation_is_stated(self, sim_mode):
        dialog, mw, layout = self._build(sim_active=True)
        assert has_text(layout, "Cameras simulated locally")

    def test_enabling_simulation_needs_no_confirmation(self, sim_mode):
        """Moving to fake cameras is the safe direction."""
        dialog, mw, layout = self._build(sim_active=False)
        button_named(layout, "Enable Simulation Mode").click()
        assert dialog.confirmations == []
        assert sim_mode["activated"] == 1

    def test_disabling_simulation_asks_first(self, sim_mode):
        """The app will drive live VISCA cameras after the restart."""
        sim_mode["active"] = True
        dialog, mw, layout = self._build(sim_active=True)
        button_named(layout, "Disable Simulation Mode").click()
        assert dialog.confirmations == ["Disable Simulation Mode"]

    def test_declining_leaves_simulation_on(self, sim_mode):
        sim_mode["active"] = True
        dialog, mw, layout = self._build(sim_active=True, confirm=False)
        button_named(layout, "Disable Simulation Mode").click()
        assert sim_mode["deactivated"] == 0

    def test_confirming_switches_to_hardware(self, sim_mode):
        sim_mode["active"] = True
        dialog, mw, layout = self._build(sim_active=True, confirm=True)
        button_named(layout, "Disable Simulation Mode").click()
        assert sim_mode["deactivated"] == 1

    def test_a_restart_is_required_and_said_so(self, sim_mode):
        dialog, mw, layout = self._build(sim_active=False)
        button_named(layout, "Enable Simulation Mode").click()
        assert dialog.toasts[0][0] == "Simulation mode changed — restart to apply"
        assert dialog.toasts[0][1] == "warn"

    def test_a_failed_switch_is_reported_not_raised(self, sim_mode, warnings_box):
        """sim_mode raises RuntimeError when the IP backup cannot be written."""
        sim_mode["error"] = RuntimeError("cannot write sim_ip_backup.json")
        dialog, mw, layout = self._build(sim_active=False)
        button_named(layout, "Enable Simulation Mode").click()
        assert warnings_box
        assert "sim_ip_backup" in warnings_box[0][1]

    def test_a_failed_switch_is_not_reported_as_success(self, sim_mode, warnings_box):
        sim_mode["error"] = RuntimeError("boom")
        dialog, mw, layout = self._build(sim_active=False)
        button_named(layout, "Enable Simulation Mode").click()
        assert dialog.toasts == []


class TestSimAdvancedAccordion:
    def _build(self, *, sim_active=False, session_active=False):
        dialog, mw, layout = make_harness(session_active=session_active)
        sections().build_sim_section(dialog, layout, mw, sim_active)
        return dialog, mw, layout

    def _advanced_toggle(self, layout):
        return button_named(layout, "Advanced")

    def test_advanced_starts_collapsed(self, sim_mode):
        """Restarting the appliance is not a control to leave in reach."""
        dialog, mw, layout = self._build()
        assert not self._advanced_toggle(layout).isChecked()

    def test_expanding_reveals_the_profile_controls(self, sim_mode):
        dialog, mw, layout = self._build()
        toggle = self._advanced_toggle(layout)
        toggle.setChecked(True)
        assert toggle.text().startswith("▾")

    def test_the_current_profile_is_shown(self, sim_mode, monkeypatch):
        monkeypatch.delenv("KHPTZ_PROFILE", raising=False)
        dialog, mw, layout = self._build(sim_active=False)
        assert has_text(layout, "PRODUCTION")

    def test_simulation_is_reported_as_the_runtime_profile(self, sim_mode, monkeypatch):
        monkeypatch.delenv("KHPTZ_PROFILE", raising=False)
        dialog, mw, layout = self._build(sim_active=True)
        assert has_text(layout, "SIMULATION")

    def test_the_current_profile_is_not_offered_as_a_restart_target(self, sim_mode, monkeypatch):
        monkeypatch.setenv("KHPTZ_PROFILE", "production")
        dialog, mw, layout = self._build()
        assert not any(b.text() == "Restart · Production" for b in buttons(layout))
        assert button_named(layout, "Restart · Demo")

    def test_restarting_goes_through_the_dialog_helper(self, sim_mode, monkeypatch):
        monkeypatch.setenv("KHPTZ_PROFILE", "production")
        dialog, mw, layout = self._build()
        button_named(layout, "Restart · Demo").click()
        assert dialog.restart_requests == ["demo"]

    def test_restart_is_locked_during_a_live_session(self, sim_mode, monkeypatch):
        """Restarting mid-event drops every camera."""
        monkeypatch.setenv("KHPTZ_PROFILE", "production")
        dialog, mw, layout = self._build(session_active=True)
        btn = button_named(layout, "Restart · Demo")
        assert not btn.isEnabled()
        assert "Stop the session" in btn.toolTip()


# ══════════════════════════════════════════════════════════════════════════════
#  Preset validation
# ══════════════════════════════════════════════════════════════════════════════

def make_item(label="1", preset=1, camera_role="main", assigned_name=None):
    from application.preset_test_models import PresetTestItem
    return PresetTestItem(
        item_id=f"seat-{label}", label=label, camera_role=camera_role,
        camera_index=1 if camera_role == "main" else 2,
        preset=preset, assigned_name=assigned_name,
    )


def make_summary(results=(), cancelled=False):
    from application.preset_test_models import (
        PresetTestSummary, STATUS_OK, STATUS_WARNING, STATUS_ERROR, STATUS_SKIPPED,
    )
    results = list(results)

    def count(status):
        return sum(1 for r in results if r.status == status)

    return PresetTestSummary(
        total=len(results), ok=count(STATUS_OK), warning=count(STATUS_WARNING),
        error=count(STATUS_ERROR), skipped=count(STATUS_SKIPPED),
        cancelled=cancelled, results=results,
    )


def make_result(item, status, message="", duration_ms=None):
    from application.preset_test_models import PresetTestResult
    return PresetTestResult(item=item, status=status, message=message,
                            duration_ms=duration_ms)


@pytest.fixture
def preset_env(monkeypatch):
    """Replace the item sources, the runner and the history file."""
    import application.preset_sources as sources
    import application.preset_test_history_service as history
    import application.preset_test_runner as runner_mod

    state = {
        "all_items": [make_item("1", 1)],
        "named_items": [make_item("2", 2, assigned_name="Ana")],
        "runners": [],
        "recorded": [],
        "summary_line": "Last run: never",
    }

    monkeypatch.setattr(sources, "build_items_from_config", lambda: state["all_items"])
    monkeypatch.setattr(
        sources, "build_items_from_assigned_names", lambda: state["named_items"])

    class _RunnerDouble:
        def __init__(self, items, send_fn, resolve_fn, *a, **k):
            self.items = items
            self.send_fn = send_fn
            self.resolve_fn = resolve_fn
            self.is_running = True
            self.cancelled = 0
            self.started = 0
            state["runners"].append(self)

        def start(self):
            self.started += 1

        def cancel(self):
            self.cancelled += 1

    monkeypatch.setattr(runner_mod, "PresetTestRunner", _RunnerDouble)

    class _HistoryDouble:
        def summary_line(self):
            return state["summary_line"]

        def record(self, **kwargs):
            state["recorded"].append(kwargs)

    monkeypatch.setattr(history, "PresetTestHistoryService", _HistoryDouble)
    return state


@pytest.fixture
def message_box(monkeypatch):
    """Answer the confirm/warn dialogs the section raises."""
    from PyQt5.QtWidgets import QMessageBox

    state = {"answer": QMessageBox.Yes, "questions": [], "warnings": [], "infos": []}
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda parent, title, text, *a, **k: state["questions"].append(text) or state["answer"],
    )
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda parent, title, text, *a, **k: state["warnings"].append(text),
    )
    monkeypatch.setattr(
        QMessageBox, "information",
        lambda parent, title, text, *a, **k: state["infos"].append(text),
    )
    return state


def build_presets(session_active=False):
    dialog, mw, layout = make_harness(session_active=session_active)
    sections().build_preset_validation_section(dialog, layout, mw)
    return dialog, mw, layout


def summary_box(layout):
    from PyQt5.QtWidgets import QTextEdit
    return layout.parentWidget().findChildren(QTextEdit)[0]


class TestPresetValidationLayout:
    def test_it_warns_against_running_live(self, preset_env):
        dialog, mw, layout = build_presets()
        assert has_text(layout, "Do not run during a live session")

    def test_the_last_run_is_shown(self, preset_env):
        """Answers "was this room ever validated?" without running it again."""
        preset_env["summary_line"] = "Last run: 2026-07-20 · OK 12"
        dialog, mw, layout = build_presets()
        assert has_text(layout, "Last run: 2026-07-20")

    def test_a_broken_history_file_does_not_break_the_panel(self, monkeypatch, preset_env):
        import application.preset_test_history_service as history

        class _Exploding:
            def __init__(self):
                raise OSError("history unreadable")

        monkeypatch.setattr(history, "PresetTestHistoryService", _Exploding)
        dialog, mw, layout = build_presets()      # must not raise
        assert has_text(layout, "Do not run during a live session")

    def test_cancel_starts_disabled(self, preset_env):
        dialog, mw, layout = build_presets()
        assert not button_named(layout, "Cancel").isEnabled()

    def test_running_is_locked_during_a_live_session(self, preset_env):
        """Preset tests physically move the cameras."""
        dialog, mw, layout = build_presets(session_active=True)
        for name in ("Test All Presets", "Named Seats Only"):
            btn = button_named(layout, name)
            assert not btn.isEnabled()
            assert "Stop the session" in btn.toolTip()


class TestPresetValidationStart:
    def test_no_configured_presets_is_reported(self, preset_env, message_box):
        preset_env["all_items"] = []
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        assert message_box["warnings"] == ["No configured presets found."]
        assert preset_env["runners"] == []

    def test_no_named_seats_points_at_the_alternative(self, preset_env, message_box):
        preset_env["named_items"] = []
        dialog, mw, layout = build_presets()
        button_named(layout, "Named Seats Only").click()
        assert message_box["infos"]
        assert "Test All Presets" in message_box["infos"][0]

    def test_moving_the_cameras_is_confirmed_first(self, preset_env, message_box):
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        assert message_box["questions"]
        assert "move cameras" in message_box["questions"][0]

    def test_declining_starts_nothing(self, preset_env, message_box):
        from PyQt5.QtWidgets import QMessageBox
        message_box["answer"] = QMessageBox.No
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        assert preset_env["runners"] == []

    def test_accepting_runs_every_configured_preset(self, preset_env, message_box):
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        assert len(preset_env["runners"]) == 1
        assert preset_env["runners"][0].items == preset_env["all_items"]
        assert preset_env["runners"][0].started == 1

    def test_named_only_runs_the_named_seats(self, preset_env, message_box):
        dialog, mw, layout = build_presets()
        button_named(layout, "Named Seats Only").click()
        assert preset_env["runners"][0].items == preset_env["named_items"]

    def test_the_named_confirmation_states_how_many(self, preset_env, message_box):
        preset_env["named_items"] = [make_item("2", 2), make_item("3", 3)]
        dialog, mw, layout = build_presets()
        button_named(layout, "Named Seats Only").click()
        assert "2 named seat preset(s)" in message_box["questions"][0]

    def test_starting_locks_the_run_buttons(self, preset_env, message_box):
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        assert not button_named(layout, "Test All Presets").isEnabled()
        assert not button_named(layout, "Named Seats Only").isEnabled()
        assert button_named(layout, "Cancel").isEnabled()


class TestPresetValidationRunnerWiring:
    def _runner(self, preset_env, message_box):
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        return dialog, mw, layout, preset_env["runners"][0]

    def test_preset_recall_goes_through_the_camera_service(self, preset_env, message_box):
        """ADR-001: no widget-level VISCA."""
        import config
        dialog, mw, layout, runner = self._runner(preset_env, message_box)
        runner.send_fn(config.CAM1.ip, config.CAM1.cam_id, "0A")
        assert mw._camera_svc.recalls == [(1, 10)]

    def test_a_second_camera_address_targets_camera_two(self, preset_env, message_box):
        dialog, mw, layout, runner = self._runner(preset_env, message_box)
        runner.send_fn("10.99.99.99", "01", "01")
        assert mw._camera_svc.recalls == [(2, 1)]

    def test_low_presets_resolve_to_the_platform_camera(self, preset_env, message_box):
        import config
        dialog, mw, layout, runner = self._runner(preset_env, message_box)
        assert runner.resolve_fn(3) == (config.CAM1.ip, config.CAM1.cam_id)

    def test_high_presets_resolve_to_the_comments_camera(self, preset_env, message_box):
        import config
        dialog, mw, layout, runner = self._runner(preset_env, message_box)
        assert runner.resolve_fn(4) == (config.CAM2.ip, config.CAM2.cam_id)

    def test_progress_is_reported_per_seat(self, preset_env, message_box):
        dialog, mw, layout, runner = self._runner(preset_env, message_box)
        runner.on_started(3)
        runner.on_item_started(make_item("7", 7, assigned_name="Ana"), 1, 3)
        assert has_text(layout, "Seat 7")
        assert has_text(layout, "Ana")
        assert has_text(layout, "2 / 3")

    def test_a_seat_highlight_reaches_its_button(self, preset_env, message_box):
        dialog, mw, layout, runner = self._runner(preset_env, message_box)

        class _SeatButton:
            def __init__(self):
                self.states = []

            def show_test_result(self, state):
                self.states.append(state)

        seat = _SeatButton()
        mw.Seat5 = seat
        runner.on_highlight(make_item("5", 5), "ok")
        assert seat.states == ["ok"]

    def test_a_seat_without_a_preset_highlights_nothing(self, preset_env, message_box):
        dialog, mw, layout, runner = self._runner(preset_env, message_box)
        runner.on_highlight(make_item("x", None), "ok")     # must not raise

    def test_a_missing_seat_button_is_tolerated(self, preset_env, message_box):
        """The layout may not expose every preset as a seat."""
        dialog, mw, layout, runner = self._runner(preset_env, message_box)
        runner.on_highlight(make_item("99", 99), "ok")      # must not raise


class TestPresetValidationResults:
    def _finish(self, preset_env, message_box, summary):
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        preset_env["runners"][0].on_finished(summary)
        return dialog, mw, layout

    def test_a_clean_run_is_summarised(self, preset_env, message_box):
        from application.preset_test_models import STATUS_OK
        summary = make_summary([make_result(make_item("1", 1), STATUS_OK)])
        dialog, mw, layout = self._finish(preset_env, message_box, summary)
        assert "Preset test complete" in summary_box(layout).toPlainText()
        assert has_text(layout, "OK 1")

    def test_the_buttons_come_back(self, preset_env, message_box):
        summary = make_summary([])
        dialog, mw, layout = self._finish(preset_env, message_box, summary)
        assert button_named(layout, "Test All Presets").isEnabled()
        assert not button_named(layout, "Cancel").isEnabled()

    def test_errors_are_listed_with_their_reason(self, preset_env, message_box):
        """A count alone does not tell an installer which seat to fix."""
        from application.preset_test_models import STATUS_ERROR
        item = make_item("4", 4, assigned_name="Ana")
        summary = make_summary([
            make_result(item, STATUS_ERROR, "no response", duration_ms=1200)])
        dialog, mw, layout = self._finish(preset_env, message_box, summary)
        text = summary_box(layout).toPlainText()
        assert "Seat 4 / Ana" in text
        assert "no response" in text
        assert "1200 ms" in text

    def test_warnings_explain_they_are_unverified_not_broken(self, preset_env, message_box):
        from application.preset_test_models import STATUS_WARNING
        summary = make_summary([make_result(make_item("2", 2), STATUS_WARNING)])
        dialog, mw, layout = self._finish(preset_env, message_box, summary)
        text = summary_box(layout).toPlainText()
        assert "callable but unverified" in text

    def test_skipped_seats_are_listed(self, preset_env, message_box):
        from application.preset_test_models import STATUS_SKIPPED
        summary = make_summary([
            make_result(make_item("9", 9), STATUS_SKIPPED, "no preset assigned")])
        dialog, mw, layout = self._finish(preset_env, message_box, summary)
        assert "no preset assigned" in summary_box(layout).toPlainText()

    def test_the_run_is_written_to_the_history(self, preset_env, message_box):
        from application.preset_test_models import STATUS_OK
        summary = make_summary([make_result(make_item("1", 1), STATUS_OK)])
        self._finish(preset_env, message_box, summary)
        assert preset_env["recorded"] == [{
            "total": 1, "ok": 1, "warning": 0, "error": 0,
            "skipped": 0, "cancelled": False,
        }]

    def test_a_failing_history_write_does_not_lose_the_results(self, monkeypatch,
                                                               preset_env, message_box):
        import application.preset_test_history_service as history
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()

        class _Exploding:
            def __init__(self):
                raise OSError("read-only data dir")

        monkeypatch.setattr(history, "PresetTestHistoryService", _Exploding)
        preset_env["runners"][0].on_finished(make_summary([]))
        assert "Preset test complete" in summary_box(layout).toPlainText()

    def test_a_cancelled_run_reports_partial_results(self, preset_env, message_box):
        """Presented as partial, never as a completed validation."""
        from application.preset_test_models import STATUS_OK
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        summary = make_summary([make_result(make_item("1", 1), STATUS_OK)], cancelled=True)
        preset_env["runners"][0].on_cancelled(summary)
        assert "Test cancelled — partial results:" in summary_box(layout).toPlainText()

    def test_a_cancelled_run_frees_the_buttons(self, preset_env, message_box):
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        preset_env["runners"][0].on_cancelled(make_summary([], cancelled=True))
        assert button_named(layout, "Test All Presets").isEnabled()


class TestPresetValidationStopping:
    def test_cancel_stops_the_runner(self, preset_env, message_box):
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        button_named(layout, "Cancel").click()
        assert preset_env["runners"][0].cancelled == 1

    def test_cancel_is_spent_after_one_press(self, preset_env, message_box):
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        button_named(layout, "Cancel").click()
        assert not button_named(layout, "Cancel").isEnabled()

    def test_closing_the_dialog_stops_the_runner(self, preset_env, message_box):
        """A runner left alive keeps driving cameras in an empty room."""
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        dialog.destroyed.emit()
        assert preset_env["runners"][0].cancelled == 1

    def test_closing_without_a_run_is_harmless(self, preset_env, message_box):
        dialog, mw, layout = build_presets()
        dialog.destroyed.emit()          # must not raise

    def test_a_finished_runner_is_not_cancelled_again(self, preset_env, message_box):
        dialog, mw, layout = build_presets()
        button_named(layout, "Test All Presets").click()
        preset_env["runners"][0].is_running = False
        button_named(layout, "Cancel").click()
        assert preset_env["runners"][0].cancelled == 0


# ══════════════════════════════════════════════════════════════════════════════
#  ATEM automation
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def configured_atem(monkeypatch):
    import config
    monkeypatch.setattr(config.ATEM, "ip", "172.16.1.50", raising=False)


@pytest.fixture
def arm_dialogs(monkeypatch):
    """Drive the two-step arming confirmation."""
    from PyQt5.QtWidgets import QInputDialog, QMessageBox

    state = {"answer": QMessageBox.Ok, "typed": "ENABLE ATEM", "accepted": True,
             "questions": []}
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda parent, title, text, *a, **k: state["questions"].append(text) or state["answer"],
    )
    monkeypatch.setattr(
        QInputDialog, "getText",
        lambda parent, title, label, *a, **k: (state["typed"], state["accepted"]),
    )
    return state


def build_automation(dispatcher, session_active=False):
    dialog, mw, layout = make_harness(session_active=session_active)
    mw._atem_dispatcher = dispatcher
    sections().build_atem_automation_section(dialog, layout, mw)
    return dialog, mw, layout


class TestAtemAutomationAvailability:
    def test_no_dispatcher_says_so_instead_of_rendering_controls(self):
        dialog, mw, layout = make_harness()
        mw._atem_dispatcher = None
        sections().build_atem_automation_section(dialog, layout, mw)
        assert has_text(layout, "Dispatcher no disponible")
        assert not buttons(layout)

    def test_an_unconfigured_atem_cannot_be_armed(self, monkeypatch, arm_dialogs):
        """Arming against a switcher that does not exist would hand camera
        control to a link that never connects."""
        import config
        monkeypatch.setattr(config.ATEM, "ip", "", raising=False)
        dialog, mw, layout = build_automation(AtemDispatcherDouble())
        btn = button_named(layout, "Arm ATEM Automation")
        assert not btn.isEnabled()
        assert "Configure the ATEM IP first" in btn.toolTip()

    def test_an_unconfigured_atem_explains_where_to_fix_it(self, monkeypatch, arm_dialogs):
        import config
        monkeypatch.setattr(config.ATEM, "ip", "", raising=False)
        dialog, mw, layout = build_automation(AtemDispatcherDouble())
        assert has_text(layout, "No ATEM configured")

    def test_a_configured_atem_can_be_armed(self, configured_atem, arm_dialogs):
        dialog, mw, layout = build_automation(AtemDispatcherDouble())
        assert button_named(layout, "Arm ATEM Automation").isEnabled()


class TestAtemArming:
    def test_the_disarmed_state_is_shown(self, configured_atem, arm_dialogs):
        dialog, mw, layout = build_automation(AtemDispatcherDouble(armed=False))
        assert has_text(layout, "Disarmed")

    def test_the_armed_state_is_shown(self, configured_atem, arm_dialogs):
        dialog, mw, layout = build_automation(AtemDispatcherDouble(armed=True))
        assert has_text(layout, "Armed — live")
        assert button_named(layout, "Disarm Automation")

    def test_arming_asks_before_anything_else(self, configured_atem, arm_dialogs):
        dialog, mw, layout = build_automation(AtemDispatcherDouble())
        button_named(layout, "Arm ATEM Automation").click()
        assert arm_dialogs["questions"]
        assert "triggered automatically" in arm_dialogs["questions"][0]

    def test_declining_the_first_prompt_arms_nothing(self, configured_atem, arm_dialogs):
        from PyQt5.QtWidgets import QMessageBox
        arm_dialogs["answer"] = QMessageBox.Cancel
        dispatcher = AtemDispatcherDouble()
        dialog, mw, layout = build_automation(dispatcher)
        button_named(layout, "Arm ATEM Automation").click()
        assert dispatcher.arm_calls == []

    def test_a_typo_in_the_confirmation_phrase_arms_nothing(self, configured_atem, arm_dialogs):
        """The typed phrase is the second gate on purpose."""
        arm_dialogs["typed"] = "enable atem"
        dispatcher = AtemDispatcherDouble()
        dialog, mw, layout = build_automation(dispatcher)
        button_named(layout, "Arm ATEM Automation").click()
        assert dispatcher.arm_calls == []

    def test_cancelling_the_phrase_prompt_arms_nothing(self, configured_atem, arm_dialogs):
        arm_dialogs["accepted"] = False
        dispatcher = AtemDispatcherDouble()
        dialog, mw, layout = build_automation(dispatcher)
        button_named(layout, "Arm ATEM Automation").click()
        assert dispatcher.arm_calls == []

    def test_the_exact_phrase_arms_automation(self, configured_atem, arm_dialogs):
        dispatcher = AtemDispatcherDouble()
        dialog, mw, layout = build_automation(dispatcher)
        button_named(layout, "Arm ATEM Automation").click()
        assert dispatcher.arm_calls == [True]

    def test_surrounding_whitespace_in_the_phrase_is_tolerated(self, configured_atem, arm_dialogs):
        arm_dialogs["typed"] = "  ENABLE ATEM  "
        dispatcher = AtemDispatcherDouble()
        dialog, mw, layout = build_automation(dispatcher)
        button_named(layout, "Arm ATEM Automation").click()
        assert dispatcher.arm_calls == [True]

    def test_arming_clears_a_stale_reconnect_guard(self, configured_atem, arm_dialogs):
        """Otherwise automation is armed but silently paused."""
        dispatcher = AtemDispatcherDouble(reconnect_guard=True)
        dialog, mw, layout = build_automation(dispatcher)
        button_named(layout, "Arm ATEM Automation").click()
        assert dispatcher.guard_clears >= 1

    def test_the_button_flips_after_arming(self, configured_atem, arm_dialogs):
        dispatcher = AtemDispatcherDouble()
        dialog, mw, layout = build_automation(dispatcher)
        btn = button_named(layout, "Arm ATEM Automation")
        btn.click()
        assert btn.text() == "Disarm Automation"

    def test_disarming_needs_no_confirmation(self, configured_atem, arm_dialogs):
        """Handing control back is always the safe direction."""
        dispatcher = AtemDispatcherDouble(armed=True)
        dialog, mw, layout = build_automation(dispatcher)
        button_named(layout, "Disarm Automation").click()
        assert dispatcher.arm_calls == [False]
        assert arm_dialogs["questions"] == []


class TestAtemReconnectGuard:
    def test_the_guard_is_hidden_when_inactive(self, configured_atem, arm_dialogs):
        dialog, mw, layout = build_automation(AtemDispatcherDouble(reconnect_guard=False))
        assert button_named(layout, "Clear Reconnect Guard").isHidden()

    def test_an_active_guard_is_explained(self, configured_atem, arm_dialogs):
        """Automation looks armed but is not acting — the operator must know."""
        dialog, mw, layout = build_automation(AtemDispatcherDouble(reconnect_guard=True))
        assert has_text(layout, "Reconnect guard active")
        assert not button_named(layout, "Clear Reconnect Guard").isHidden()

    def test_clearing_the_guard_resumes_automation(self, configured_atem, arm_dialogs):
        dispatcher = AtemDispatcherDouble(reconnect_guard=True)
        dialog, mw, layout = build_automation(dispatcher)
        button_named(layout, "Clear Reconnect Guard").click()
        assert dispatcher.guard_clears == 1
        assert button_named(layout, "Clear Reconnect Guard").isHidden()

    def test_a_guard_raised_while_the_dialog_is_open_appears(self, configured_atem, arm_dialogs):
        """The ATEM can reconnect at any moment."""
        from domain.atem_state import ATEMState
        dispatcher = AtemDispatcherDouble(reconnect_guard=False)
        dialog, mw, layout = build_automation(dispatcher)
        dispatcher.reconnect_guard = True
        mw.atem_state_changed.emit(ATEMState.CONNECTED)
        assert not button_named(layout, "Clear Reconnect Guard").isHidden()

    def test_it_stops_listening_once_the_dialog_is_gone(self, configured_atem, arm_dialogs):
        from domain.atem_state import ATEMState
        dispatcher = AtemDispatcherDouble(reconnect_guard=False)
        dialog, mw, layout = build_automation(dispatcher)
        dialog.destroyed.emit()
        dispatcher.reconnect_guard = True
        mw.atem_state_changed.emit(ATEMState.CONNECTED)
        assert button_named(layout, "Clear Reconnect Guard").isHidden()


# ══════════════════════════════════════════════════════════════════════════════
#  Status strip
# ══════════════════════════════════════════════════════════════════════════════

def build_strip(cam1_check="Green", cam2_check="Red", atem_state=None,
                armed=False, monkeypatch=None):
    import config
    dialog, mw, layout = make_harness()
    monkeypatch.setattr(config.CAM1, "check", cam1_check, raising=False)
    monkeypatch.setattr(config.CAM2, "check", cam2_check, raising=False)
    mw._atem_monitor.state = atem_state
    mw._atem_dispatcher = AtemDispatcherDouble(armed=armed)
    strip = sections().build_status_strip(dialog, mw)
    return dialog, mw, strip


def strip_texts(strip) -> list[str]:
    from PyQt5.QtWidgets import QLabel
    return [lb.text() for lb in strip.findChildren(QLabel)]


class TestStatusStrip:
    def test_an_online_camera_shows_its_role(self, monkeypatch):
        dialog, mw, strip = build_strip(cam1_check="Green", monkeypatch=monkeypatch)
        assert "Platform" in strip_texts(strip)

    def test_an_offline_camera_says_offline(self, monkeypatch):
        """Showing the role for an unreachable camera reads as healthy."""
        dialog, mw, strip = build_strip(cam2_check="Red", monkeypatch=monkeypatch)
        assert "Offline" in strip_texts(strip)

    def test_an_unknown_check_is_treated_as_offline(self, monkeypatch):
        """check is None before the first probe — never claim it is up."""
        dialog, mw, strip = build_strip(
            cam1_check=None, cam2_check=None, monkeypatch=monkeypatch)
        assert strip_texts(strip).count("Offline") == 2

    @pytest.mark.parametrize("state_name,label", [
        ("CONNECTED", "Linked"),
        ("CONNECTING", "Conn…"),
        ("RECONNECTING", "Recon…"),
        ("DISCONNECTED", "Down"),
        ("ERROR", "Error"),
        ("NOT_CONFIGURED", "None"),
        ("DEPENDENCY_MISSING", "No lib"),
    ])
    def test_every_atem_state_has_a_token(self, monkeypatch, state_name, label):
        from domain.atem_state import ATEMState
        dialog, mw, strip = build_strip(
            atem_state=getattr(ATEMState, state_name), monkeypatch=monkeypatch)
        assert label in strip_texts(strip)

    def test_a_missing_monitor_reads_as_unknown(self, monkeypatch):
        dialog, mw, strip = build_strip(atem_state=None, monkeypatch=monkeypatch)
        assert "Unknown" in strip_texts(strip)

    def test_armed_automation_is_visible_at_a_glance(self, monkeypatch):
        dialog, mw, strip = build_strip(armed=True, monkeypatch=monkeypatch)
        assert "Armed" in strip_texts(strip)

    def test_disarmed_automation_is_visible_at_a_glance(self, monkeypatch):
        dialog, mw, strip = build_strip(armed=False, monkeypatch=monkeypatch)
        assert "Disarmed" in strip_texts(strip)

    def test_the_runtime_profile_is_badged(self, monkeypatch):
        monkeypatch.setenv("KHPTZ_PROFILE", "demo")
        dialog, mw, strip = build_strip(monkeypatch=monkeypatch)
        assert "DEMO" in strip_texts(strip)

    def test_the_camera_indicators_are_exposed_for_live_updates(self, monkeypatch):
        """The cameras tab refreshes these after assigning a discovered IP."""
        dialog, mw, strip = build_strip(monkeypatch=monkeypatch)
        assert set(dialog._strip_cam) == {1, 2}
        assert dialog._strip_cam[1][2] == "Platform"
        assert dialog._strip_cam[2][2] == "Comments"

    def test_the_atem_token_follows_the_monitor(self, monkeypatch):
        from domain.atem_state import ATEMState
        dialog, mw, strip = build_strip(
            atem_state=ATEMState.DISCONNECTED, monkeypatch=monkeypatch)
        mw.atem_state_changed.emit(ATEMState.CONNECTED)
        assert "Linked" in strip_texts(strip)

    def test_it_stops_listening_once_the_dialog_is_gone(self, monkeypatch):
        from domain.atem_state import ATEMState
        dialog, mw, strip = build_strip(
            atem_state=ATEMState.DISCONNECTED, monkeypatch=monkeypatch)
        dialog.destroyed.emit()
        mw.atem_state_changed.emit(ATEMState.CONNECTED)
        assert "Down" in strip_texts(strip)

    def test_a_main_window_without_the_signal_is_tolerated(self, monkeypatch):
        """build_status_strip is also used from lighter hosts."""
        import config
        dialog, mw, layout = make_harness()
        monkeypatch.setattr(config.CAM1, "check", "Green", raising=False)

        class _Bare:
            _atem_monitor = None
            _atem_dispatcher = None

        strip = sections().build_status_strip(dialog, _Bare())
        assert "Unknown" in strip_texts(strip)
