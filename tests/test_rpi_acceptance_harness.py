#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_rpi_acceptance_harness.py — contract for the #890 acceptance harness
#
# scripts/validate_rpi_acceptance.sh runs on the physical Pi during hardware
# acceptance. Two properties matter most and are easy to regress:
#   - it must stay READ-ONLY (#890: any manual patch during the run is a failed
#     acceptance result, so the harness itself must not repair anything);
#   - it must scan for every error #890 says must not return, or a regression
#     passes acceptance unnoticed.

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "validate_rpi_acceptance.sh"


@pytest.fixture(scope="module")
def text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


class TestExists:
    def test_harness_is_shipped(self):
        assert SCRIPT.is_file()


class TestForbiddenErrorsAreScanned:
    """Every failure #890 lists under "Errors that must not return"."""

    @pytest.mark.parametrize("pattern", [
        "could not connect to display",                    # XCB
        "No protocol specified",                           # X11 auth
        "Could not load the Qt platform plugin",            # Qt platform
        "XDG_RUNTIME_DIR not set",                         # session runtime
        "Failed to start message bus",                     # session D-Bus
        "Not running on a RPi",                            # optional GPIO (#882)
        "QThread: Destroyed while thread is still running",
        "status=6/ABRT",                                   # process abort
        "Could not parse stylesheet",                      # wizard QSS (#886)
        "UnicodeEncodeError",                              # CLI encoding (#884)
    ])
    def test_pattern_is_scanned(self, text, pattern):
        assert pattern in text, f"the harness never looks for: {pattern}"

    def test_permission_regressions_are_detected(self, text):
        assert "Permission denied" in text


class TestReadOnlyByDefault:
    """The harness inspects; it must never repair. A harness that fixes the
    appliance mid-run invalidates the acceptance it is supposed to prove."""

    @pytest.mark.parametrize("forbidden", [
        "xhost",
        "systemctl enable",
        "systemctl start",
        "systemctl disable",
        "daemon-reload",
    ])
    def test_does_not_mutate_the_appliance(self, text, forbidden):
        active = [
            line for line in text.splitlines()
            if forbidden in line and not line.lstrip().startswith("#")
        ]
        assert not active, f"harness would run '{forbidden}': {active}"

    def test_backup_is_opt_in(self, text):
        """`hallptz backup` writes a ZIP, so it must not run unless asked."""
        assert "--with-backup" in text
        assert 'WITH_BACKUP=false' in text


class TestReporting:
    def test_maps_every_doctor_exit_code(self, text):
        """Exit codes come from domain/doctor_outcome.py (#887)."""
        for code in ("0)", "10)", "20)", "30)"):
            assert code in text

    def test_checks_json_agrees_with_human_output(self, text):
        assert "--json" in text
        assert "disagrees" in text

    def test_is_gui_mode_aware(self, text):
        """Under --gui-mode user, hallptz-control is meant to be disabled (#885)."""
        assert "HALLPTZ_GUI_MODE" in text
        assert "two guis would compete" in text.lower()

    def test_surfaces_manual_checks_rather_than_hiding_them(self, text):
        """Physical checks cannot be automated; silently dropping them would
        make a partial run look complete."""
        assert "MANUAL" in text
        for physical in ("Platform camera", "Audience camera", "presets", "STOP"):
            assert physical in text

    def test_emits_a_result_record_for_the_issue(self, text):
        assert "paste into #890" in text


class TestRuntimePathPermissions:
    """Acceptance must assert the modes the appliance actually depends on.

    Three components write these modes in sequence — install.sh,
    runtime/provision.py and scripts/repair_rpi_runtime.sh — and the last one
    to run decides. When repair_rpi_runtime.sh asserted a flat 0750 it undid
    the other two on every session-owned install, and this harness passed the
    appliance anyway: the GUI came up, looked healthy, and could not persist a
    single preset. A mode the product depends on has to be checked here.
    """

    @pytest.mark.parametrize("path", [
        "/var/lib/hallptz",
        "/var/log/hallptz",
        "/var/backups/hallptz",
        "/etc/hallptz",
    ])
    def test_directory_is_inspected(self, text, path):
        assert path in text, f"acceptance never inspects {path}"

    def test_expected_mode_follows_the_gui_mode(self, text):
        """0750 in both modes would pass a session-owned install that cannot
        write; 2770 in both would pass a system install that is too open."""
        assert '_expect_runtime_mode="2770"' in text
        assert '_expect_runtime_mode="0750"' in text

    def test_application_code_is_asserted_read_only_for_the_service(self, text):
        assert "0750 root:hallptz" in text

    def test_secret_modes_are_asserted(self, text):
        """The key is derived from the world-readable /etc/machine-id, so a
        group-readable secret is effectively plaintext to the hallptz group."""
        assert "password.enc" in text
        assert "admin.enc" in text

    def test_permission_section_stays_read_only(self, text):
        """It reports modes; repairing them mid-run would invalidate the
        acceptance result the same way any other patch does."""
        section = text[text.index("Runtime path permissions"):text.index("Boot journal scan")]
        for mutating in ("chmod ", "chown ", "install -d"):
            active = [
                line for line in section.splitlines()
                if mutating in line
                and not line.lstrip().startswith("#")
                and "say " not in line
            ]
            assert not active, f"permission section would run '{mutating}': {active}"
