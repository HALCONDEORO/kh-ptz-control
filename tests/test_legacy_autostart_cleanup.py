#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_legacy_autostart_cleanup.py — legacy startup migration contract (#892)
#
# A Pi upgraded in place can still carry the pre-HALLPTZ HallPTZ/PTZ controller's
# startup entries. If one survives it can cover the HALLPTZ interface, open a second
# full-screen app and drive the same cameras with conflicting VISCA commands —
# while hallptz-control.service looks perfectly healthy.
#
# The cleanup script needs root, a Pi and an installed product, so its
# classification logic is exercised directly by
# tests/installer/legacy_match_harness.sh; these tests pin the surrounding
# contract and drive that harness.

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "cleanup_legacy_rpi_autostart.sh"
HARNESS = (REPO_ROOT / "tests" / "installer" / "legacy_match_harness.sh").as_posix()


@pytest.fixture(scope="module")
def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def assert_defined_and_called(script_text: str, func: str) -> None:
    """Assert a shell function both exists and is actually invoked.

    A plain `assert "name" in text` is not load-bearing: deleting the function
    and leaving its name in a comment keeps such a test green. Verified by
    removing scan_cron entirely — the whole cron scan #892 asks for — and
    watching the suite stay green.
    """
    assert re.search(rf"^{func}\(\)\s*\{{", script_text, re.MULTILINE), (
        f"{func} is not defined (a comment mentioning it is not enough)"
    )
    invocations = [
        line for line in script_text.splitlines()
        if line.strip() == func or line.strip().startswith(f"{func} ")
    ]
    assert invocations, f"{func} is defined but never called"


class TestScanCoverage:
    """#892 lists the startup mechanisms an upgraded Pi can carry. Each must be
    scanned, or a legacy controller quietly survives the migration."""

    @pytest.mark.parametrize("location", [
        ".config/autostart",          # XDG autostart (user)
        "/etc/xdg/autostart",         # XDG autostart (system)
        "lxsession",                  # LXDE session autostart
        "openbox",
        "rc.local",
        ".config/systemd/user",       # user units
    ])
    def test_known_startup_location_is_scanned(self, script_text, location):
        assert location in script_text, f"{location} is never scanned"

    def test_cron_reboot_jobs_are_scanned(self, script_text):
        """Explicitly listed in #892 and previously not covered.

        Checks the function is defined AND invoked, not merely named: deleting
        the whole cron scan while leaving its name in a comment used to keep
        this test green.
        """
        assert_defined_and_called(script_text, "scan_cron")
        assert "crontab -u" in script_text, "no crontab is ever read"

    def test_shell_profiles_are_scanned(self, script_text):
        """Explicitly listed in #892 and previously not covered."""
        assert_defined_and_called(script_text, "scan_shell_profiles")
        for profile in (".bashrc", ".profile", ".xsessionrc"):
            assert profile in script_text, f"{profile} is never scanned"

    def test_system_units_are_scanned(self, script_text):
        assert "list-unit-files" in script_text


class TestSafetyContract:
    def test_dry_run_mode_exists(self, script_text):
        """#892 requires showing every candidate before changing anything."""
        assert "--dry-run" in script_text

    def test_changes_are_backed_up(self, script_text):
        assert "backup()" in script_text
        assert "BACKUP_DIR" in script_text

    def test_quarantine_renames_rather_than_deletes(self, script_text):
        """'Legacy program files are never deleted' — recovery must stay possible."""
        assert "disabled-by-hallptz-" in script_text

    def test_roots_crontab_is_reported_not_rewritten(self, script_text):
        """Root's crontab may carry unrelated site automation."""
        assert "REVIEW MANUALLY" in script_text

    def test_matching_is_not_broad_main_py_only(self, script_text):
        """#892: avoid broad `main.py`-only matching. The fallback also requires
        a home-directory path and a camera-domain term."""
        assert "Conservative fallback" in script_text
        assert "ptz|visca|atem|camera|joystick|dublin|hallptz" in script_text


class TestGuiModeAwareness:
    """The script predates the session-owned GUI (#885). Under --gui-mode user
    the display-ready chain does not exist, and demanding it would abort the
    migration on a perfectly healthy appliance."""

    def test_reads_the_recorded_gui_mode(self, script_text):
        """Via the shared reader (scripts/lib/install_state.sh) rather than a
        private parse — components disagreeing about the mode is what let the
        provisioning chain re-arm a second launcher."""
        assert "lib/install_state.sh" in script_text
        assert "hallptz_gui_mode" in script_text

    def test_does_not_require_the_display_chain_in_user_mode(self, script_text):
        assert "/etc/systemd/user/hallptz-gui.service" in script_text

    def test_refuses_to_leave_two_launchers_enabled(self, script_text):
        """System service enabled alongside the session GUI is the two-GUI bug."""
        assert "Two GUIs would compete" in script_text

    def test_protects_the_session_gui_artifacts(self, script_text):
        for artifact in ("hallptz-gui.service", "hallptz-gui.desktop", "hallptz-gui-session"):
            assert artifact in script_text


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "the `bash` on PATH under Windows is typically WSL's, which cannot "
        "resolve a C:/ path; these run on Linux CI and on the Pi"
    ),
)
class TestClassifierBehaviour:
    """Drives legacy_match_harness.sh, which sources the real is_conflict /
    is_canonical functions and classifies concrete inputs."""

    def test_classifier_harness_passes(self):
        result = subprocess.run([
            "bash", HARNESS,
        ], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "classification checks passed" in result.stdout
