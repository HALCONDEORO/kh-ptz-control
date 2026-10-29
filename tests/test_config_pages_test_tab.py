#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_config_pages_test_tab.py — ui/config_pages/test_tab.py had no coverage
#
# The Test tab runs `khptz doctor` from the touchscreen so a technician on a
# customer site never needs a terminal. It is the in-app diagnostics path, so:
#
#   - a probe that fails must say so. Silently showing nothing looks like a
#     healthy system, which is the worst possible outcome for a diagnostics page.
#   - the button must always come back. Diagnostics can block on network
#     reachability; a control stuck on "Running…" means no second attempt.
#   - results must never be written into a dialog the operator already closed.

from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from tests.config_pages_harness import (          # noqa: E402
    button_named, labels, make_harness, panel_layout, run_threads_inline,
)


class _View:
    def __init__(self, overall="OK", summary="8 checks passed", text_lines=("a", "b")):
        self.overall = overall
        self.summary = summary
        self.text_lines = list(text_lines)


@pytest.fixture
def diagnostics(monkeypatch):
    """Replace the diagnostics service/presenter and record how it was called."""
    import application.diagnostics_presenter as presenter
    import application.diagnostics_service as service

    state = {"modes": [], "view": _View(), "raise_on_run": None}

    class _Service:
        def __init__(self, mode=None):
            state["modes"].append(mode)

        def run(self):
            if state["raise_on_run"] is not None:
                raise state["raise_on_run"]
            return "report"

    monkeypatch.setattr(service, "DiagnosticsService", _Service)
    monkeypatch.setattr(presenter, "build_view", lambda report: state["view"])
    return state


def build(**kwargs):
    dialog, mw, layout = make_harness(**kwargs)
    from ui.config_pages.test_tab import build_test_tab
    build_test_tab(dialog, layout, panel_layout)
    return dialog, mw, layout


def status_text(layout) -> str:
    """The first status label the tab creates."""
    return labels(layout)[0].text()


def results_label(layout):
    """The monospace results block — the only selectable label on the page.

    Visibility is asserted with isHidden(), not isVisible(): the harness never
    shows the dialog, so isVisible() is False for every widget and would make
    those assertions pass no matter what the tab did.
    """
    from PyQt5.QtCore import Qt
    for label in labels(layout):
        if label.textInteractionFlags() & Qt.TextSelectableByMouse:
            return label
    raise AssertionError("results label not found")


class TestInitialState:
    def test_offers_to_run_the_checks(self):
        dialog, mw, layout = build()
        assert button_named(layout, "Run Diagnostics").isEnabled()

    def test_explains_what_the_button_does(self):
        dialog, mw, layout = build()
        assert "health checks" in status_text(layout)

    def test_results_start_hidden(self):
        dialog, mw, layout = build()
        assert results_label(layout).isHidden()


class TestRunning:
    def test_the_button_reports_progress(self, monkeypatch, diagnostics):
        """The probe can block for seconds on an unreachable camera; without
        this the touchscreen looks unresponsive."""
        import ui.config_pages.test_tab as tab

        seen = {}

        class _Thread:
            def __init__(self, target=None, daemon=None):
                self._target = target

            def start(self):
                seen["text"] = btn.text()
                seen["enabled"] = btn.isEnabled()
                self._target()

        monkeypatch.setattr(tab, "threading", type("T", (), {"Thread": _Thread}))
        dialog, mw, layout = build()
        btn = button_named(layout, "Run Diagnostics")
        btn.click()
        assert seen == {"text": "Running…", "enabled": False}

    def test_the_probe_is_handed_to_a_background_thread(self, monkeypatch, diagnostics):
        """A blocking reachability check run on the GUI thread freezes the
        touchscreen, so the click handler must only start a worker."""
        import ui.config_pages.test_tab as tab

        started = []

        class _Thread:
            def __init__(self, target=None, daemon=None):
                started.append({"target": target, "daemon": daemon})

            def start(self):
                started[-1]["started"] = True

        monkeypatch.setattr(tab, "threading", type("T", (), {"Thread": _Thread}))
        dialog, mw, layout = build()
        button_named(layout, "Run Diagnostics").click()
        assert len(started) == 1
        assert started[0]["daemon"] is True      # never blocks shutdown
        assert started[0]["started"] is True


class TestResults:
    def test_success_shows_the_overall_verdict(self, monkeypatch, diagnostics):
        import ui.config_pages.test_tab as tab
        run_threads_inline(monkeypatch, tab)
        diagnostics["view"] = _View(overall="WARNING", summary="1 warning")
        dialog, mw, layout = build()
        button_named(layout, "Run Diagnostics").click()
        assert "WARNING" in status_text(layout)
        assert "1 warning" in status_text(layout)

    def test_success_shows_every_check_line(self, monkeypatch, diagnostics):
        import ui.config_pages.test_tab as tab
        run_threads_inline(monkeypatch, tab)
        diagnostics["view"] = _View(text_lines=["camera 1: OK", "disk: 42% free"])
        dialog, mw, layout = build()
        button_named(layout, "Run Diagnostics").click()
        results = results_label(layout)
        assert results.text() == "camera 1: OK\ndisk: 42% free"
        assert not results.isHidden()

    def test_the_button_comes_back(self, monkeypatch, diagnostics):
        import ui.config_pages.test_tab as tab
        run_threads_inline(monkeypatch, tab)
        dialog, mw, layout = build()
        btn = button_named(layout, "Run Diagnostics")
        btn.click()
        assert btn.isEnabled()
        assert btn.text() == "Run Diagnostics"

    def test_a_failing_probe_is_reported(self, monkeypatch, diagnostics):
        """Not silence: the operator must know the checks did not run."""
        import ui.config_pages.test_tab as tab
        run_threads_inline(monkeypatch, tab)
        diagnostics["raise_on_run"] = RuntimeError("no runtime paths")
        dialog, mw, layout = build()
        button_named(layout, "Run Diagnostics").click()
        assert "failed to run" in status_text(layout)
        assert results_label(layout).isHidden()

    def test_a_failing_probe_still_frees_the_button(self, monkeypatch, diagnostics):
        import ui.config_pages.test_tab as tab
        run_threads_inline(monkeypatch, tab)
        diagnostics["raise_on_run"] = RuntimeError("boom")
        dialog, mw, layout = build()
        btn = button_named(layout, "Run Diagnostics")
        btn.click()
        assert btn.isEnabled()

    def test_nothing_is_written_to_a_closed_dialog(self, monkeypatch, diagnostics):
        """The result arrives asynchronously; by then the operator may have
        dismissed the settings sheet."""
        import ui.config_pages.test_tab as tab
        run_threads_inline(monkeypatch, tab)
        dialog, mw, layout = build(visible=False)
        button_named(layout, "Run Diagnostics").click()
        assert results_label(layout).isHidden()
        assert "health checks" in status_text(layout) or "Running" in status_text(layout)


class TestRuntimeProfile:
    def test_the_configured_profile_is_used(self, monkeypatch, diagnostics):
        import ui.config_pages.test_tab as tab
        from domain.runtime_mode import RuntimeMode
        run_threads_inline(monkeypatch, tab)
        monkeypatch.setenv("KHPTZ_PROFILE", "demo")
        dialog, mw, layout = build()
        button_named(layout, "Run Diagnostics").click()
        assert diagnostics["modes"] == [RuntimeMode.DEMO]

    def test_an_unknown_profile_falls_back_to_production(self, monkeypatch, diagnostics):
        """A typo in KHPTZ_PROFILE must not stop a technician from running the
        checks — production is the safe reading."""
        import ui.config_pages.test_tab as tab
        from domain.runtime_mode import RuntimeMode
        run_threads_inline(monkeypatch, tab)
        monkeypatch.setenv("KHPTZ_PROFILE", "produciton")
        dialog, mw, layout = build()
        button_named(layout, "Run Diagnostics").click()
        assert diagnostics["modes"] == [RuntimeMode.PRODUCTION]

    def test_no_profile_means_production(self, monkeypatch, diagnostics):
        import ui.config_pages.test_tab as tab
        from domain.runtime_mode import RuntimeMode
        run_threads_inline(monkeypatch, tab)
        monkeypatch.delenv("KHPTZ_PROFILE", raising=False)
        dialog, mw, layout = build()
        button_named(layout, "Run Diagnostics").click()
        assert diagnostics["modes"] == [RuntimeMode.PRODUCTION]
