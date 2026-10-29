#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Hardware-free MainWindow construction smoke test.

test_startup_smoke.py covers the non-UI path (bootstrap -> AppContext) but
explicitly does not build the MainWindow. This fills that gap: it constructs the
real MainWindow in simulation mode (no PTZ cameras, no ATEM, offscreen Qt) so
that every _build_* method — and, after #894, every ui/config_pages tab builder
reachable from construction — runs for real. It is the runtime net that turns
future MainWindow/ConfigDialog extraction from a static-only change into a
verifiable one: a NameError or a broken widget wiring in any build path aborts
this test instead of only surfacing on the Pi.

Per-test Qt widget cleanup comes from a conftest autouse fixture. These tests
run unforked (see the comment above the imports), so simulation mode is undone
by the sim_mode_active fixture rather than by process teardown.
"""

from __future__ import annotations

import sys

import pytest

from conftest import ensure_real_qt, is_poisoned_by_qt_stub

# NOT forked. Building a full real widget tree in a freshly forked child aborts
# (SIGABRT) inside Qt's offscreen platform init every time, even though the
# child is throwaway — the same failure that already forces
# test_setup_wizard.py and test_login_countdown_integration.py to run unforked
# (see the two pytest steps in .github/workflows/tests.yml). MainWindow builds
# the largest tree in the suite, so it runs in that second, unforked step and
# is excluded from the --forked run.

import adapters.sim_mode as sim_mode  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _real_qt():
    """Put the real PyQt5 in sys.modules before conftest's _qapp_available runs.

    That autouse fixture is a no-op when "PyQt5.QtWidgets" is not yet imported,
    and this module imports Qt lazily (inside the main_window fixture), so
    without this nothing would build a QApplication and QMainWindow.__init__
    would abort the process. It also drops any collection-time PyQt5 stub left
    by another module. Module-scoped fixtures run before function-scoped ones,
    so importing Qt here is enough for _qapp_available to do its job.
    """
    ensure_real_qt()


@pytest.fixture
def _qapp(_real_qt):
    """The process-wide QApplication, created on first use."""
    from PyQt5.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def sim_mode_active():
    """Run the body in simulation mode, then restore the previous state."""
    was_active = sim_mode.is_active()
    if not was_active:
        sim_mode.activate()
    try:
        yield
    finally:
        if not was_active:
            try:
                sim_mode.deactivate()
            except Exception:  # noqa: BLE001 — teardown must never fail the test
                pass


@pytest.fixture
def main_window(_qapp, sim_mode_active):
    """Construct the real MainWindow offscreen and close it afterwards."""
    from ui.main_window import MainWindow

    if is_poisoned_by_qt_stub(MainWindow):
        pytest.skip("ui.main_window was imported under a PyQt5 stub by another "
                    "test module — run this file in isolation")

    window = MainWindow()
    try:
        yield window
    finally:
        window.close()


def test_main_window_constructs_without_hardware(main_window):
    """All _build_* methods run during construction without raising."""
    # 475+ child widgets are built; assert the tree is non-trivial rather than
    # pinning an exact count that harmless layout tweaks would churn.
    assert len(main_window.findChildren(object)) > 100


def test_main_window_wires_the_camera_seam(main_window):
    """The #893 CameraConfigService seam and its collaborators exist."""
    assert main_window._camera_config is not None
    assert main_window._cameras is not None
    assert main_window._camera_port is not None


def test_main_window_session_starts_inactive(main_window):
    """Construction must not auto-start a session (lifecycle contract)."""
    assert main_window.session_active is False


def test_config_dialog_opens_from_main_window(main_window):
    """Building the split ConfigDialog (all ui/config_pages tabs) does not raise.

    This is the runtime check the #894 split could not get on its own: it forces
    every extracted tab builder to run against a real MainWindow.
    """
    from ui.config_dialog import ConfigDialog

    dialog = ConfigDialog(main_window)
    try:
        assert dialog.findChild(object) is not None
    finally:
        dialog.close()
