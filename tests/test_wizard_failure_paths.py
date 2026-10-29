#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_wizard_failure_paths.py — the wizard explains failures instead of dying
#
# QWizardPage.initializePage is a Qt slot. An exception raised there does not
# surface as an error dialog: PyQt5 passes it to sys.excepthook and then calls
# qFatal()/abort(), so the operator simply watches the wizard vanish mid-setup.
#
# Two reachable cases were unguarded:
#
#   1. InstallingPage.initializePage calls handoff.begin(), which writes into
#      /run/khptz. The desktop user cannot create that directory, and install.sh
#      deliberately tolerates `systemd-tmpfiles --create` failing with a warning
#      ("/run/khptz will be created on next boot") — so an operator who runs
#      setup before rebooting hit an OSError and lost the wizard.
#
#   2. DeviceCheckPage.initializePage calls run_preflight(), which measured disk
#      usage of the current working directory and collected Raspberry Pi
#      advisories, neither guarded. That page is the first real step, so a probe
#      failure killed setup before any input was entered.

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from application import preflight


class TestPreflightDegradesInsteadOfRaising:
    def test_unreadable_working_directory_becomes_a_warning(self):
        with patch.object(preflight.shutil, "disk_usage", side_effect=OSError("gone")):
            checks = preflight.run_preflight(include_rpi_advisories=False)
        disk = [c for c in checks if c.key == "disk_space"]
        assert disk, "no disk check reported at all"
        assert disk[0].warn_only is True
        assert not preflight.has_blocking(checks)

    def test_failing_rpi_advisories_become_a_warning(self):
        with patch.object(
            preflight, "_rpi_advisory_checks", side_effect=RuntimeError("probe failed")
        ):
            checks = preflight.run_preflight(free_bytes=10**10)
        advisory = [c for c in checks if c.key == "rpi_advisories"]
        assert advisory and advisory[0].warn_only is True
        assert not preflight.has_blocking(checks)

    def test_core_checks_still_run_when_a_probe_fails(self):
        """A broken probe must not hide the checks that did work."""
        with patch.object(preflight.shutil, "disk_usage", side_effect=OSError("gone")):
            checks = preflight.run_preflight(include_rpi_advisories=False)
        keys = {c.key for c in checks}
        assert "python" in keys or any("python" in k for k in keys)
        assert len(checks) >= 3

    def test_real_low_disk_is_still_blocking(self):
        """Degrading on error must not weaken the genuine check."""
        checks = preflight.run_preflight(free_bytes=1, include_rpi_advisories=False)
        assert preflight.has_blocking(checks)

    def test_healthy_run_reports_no_synthetic_warnings(self):
        checks = preflight.run_preflight(free_bytes=10**10, include_rpi_advisories=False)
        assert not any(c.key == "rpi_advisories" for c in checks)
        assert not preflight.has_blocking(checks)


class TestInstallingPageHandlesAnUnreachableChannel:
    """Asserted on the source: constructing the page needs a real QWizard, and
    these tests must stay meaningful in the headless suite."""

    @pytest.fixture(scope="class")
    def source(self) -> str:
        return (
            Path(__file__).resolve().parent.parent
            / "ui" / "setup_wizard" / "pages.py"
        ).read_text(encoding="utf-8")

    def test_begin_is_guarded(self, source):
        block = source[source.index("class InstallingPage"):]
        begin = block.index("handoff.begin(self.answers)")
        preceding = block[:begin]
        assert "try:" in preceding[-200:], "handoff.begin() is not inside a try block"

    def test_failure_is_reported_through_the_normal_result_path(self, source):
        """Reusing _apply_result keeps Next disabled and shows the message in
        the same place as any other failure."""
        block = source[source.index("class InstallingPage"):]
        assert "HandoffResult(" in block
        assert "_apply_result(" in block

    def test_message_names_the_likely_cause_and_the_fix(self, source):
        block = source[source.index("class InstallingPage"):]
        assert "rebooted" in block.lower()

    def test_timer_is_not_started_after_a_failed_begin(self, source):
        """Polling for a result that can never arrive would leave the operator
        watching a spinner until the 660s timeout."""
        block = source[source.index("class InstallingPage"):]
        guard = block.index("except OSError")
        start = block.index("self._timer.start(")
        assert guard < start, "the timer starts before the failure path returns"
        between = block[guard:start]
        assert "return" in between
