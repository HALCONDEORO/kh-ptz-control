#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_atem_signal_bindings.py — Guards against connect/disconnect drift for the
ATEMMonitor signals wired by MainWindow.

MainWindow._start_atem_monitor (connect) and _disconnect_atem_monitor_signals
(disconnect) used to keep two hand-maintained lists of (signal, slot) pairs.
They drifted: the pip_nudge_svc binding was connected but never disconnected.
Both now derive from the single _atem_monitor_signal_bindings(), and these tests
lock that single source in place.

The import is done inside the tests and skipped if another test module has
already injected Qt stubs into sys.modules (those stubs lack QThread, which
adapters.atem_monitor needs), so this file never breaks suite collection.
"""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest


def _load_main_window():
    try:
        from ui.main_window import MainWindow
    except ImportError as exc:  # Qt stubbed by another test module → skip
        pytest.skip(f"ui.main_window not importable in this run: {exc}")
    return MainWindow


def _stub(monitor, *, panel_has_update: bool):
    """A minimal self with the collaborators _atem_monitor_signal_bindings reads."""
    return NS(
        _atem_dispatcher=NS(on_program_changed="d_prog", on_pip_changed="d_pip"),
        _right_panel=NS(
            set_atem_program="rp_prog",
            set_atem_input_names="rp_names",
            set_pip_state="rp_pip",
        ),
        _pip_nudge_svc=NS(on_pip_changed="nudge_pip"),
        _atem_panel=NS(update_input_names="panel_names", on_program_changed="panel_prog") if panel_has_update else NS(),
        _cache_atem_program="cache",
        _on_atem_state_changed="on_state",
        _on_pip_state_changed="on_pip",
    )


def _monitor():
    return NS(program_changed="P", state_changed="S", input_names_ready="I", pip_changed="Z")


def test_pip_nudge_binding_is_included():
    """The previously-missing pip_changed → pip_nudge_svc.on_pip_changed pair
    must be in the single binding list (so disconnect covers it too)."""
    MainWindow = _load_main_window()
    mon = _monitor()
    self_ = _stub(mon, panel_has_update=True)
    bindings = MainWindow._atem_monitor_signal_bindings(self_, mon)
    assert (mon.pip_changed, self_._pip_nudge_svc.on_pip_changed) in bindings


def test_binding_count_with_and_without_panel_update():
    MainWindow = _load_main_window()
    mon = _monitor()
    with_update = MainWindow._atem_monitor_signal_bindings(_stub(mon, panel_has_update=True), mon)
    without_update = MainWindow._atem_monitor_signal_bindings(_stub(mon, panel_has_update=False), mon)
    assert len(with_update) == 11   # +1: program_changed → atem_panel.on_program_changed
    assert len(without_update) == 9


def test_every_binding_is_signal_slot_pair():
    MainWindow = _load_main_window()
    mon = _monitor()
    self_ = _stub(mon, panel_has_update=True)
    bindings = MainWindow._atem_monitor_signal_bindings(self_, mon)
    known_signals = {mon.program_changed, mon.state_changed, mon.input_names_ready, mon.pip_changed}
    for signal, slot in bindings:
        assert signal in known_signals
        assert slot is not None
    # No duplicate (signal, slot) pairs — a duplicate would double-connect.
    assert len(bindings) == len(set(bindings))
