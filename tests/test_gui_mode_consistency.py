#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_gui_mode_consistency.py — every component agrees on who owns the GUI (#885)
#
# The bug these exist for: install.sh --gui-mode user disables khptz-control, but
# the wizard's provisioning chain (khptz-provision.service ->
# provision_with_rpi_integration.sh -> repair_rpi_runtime.sh) re-enabled it
# unconditionally. Completing the wizard therefore re-armed a second launcher,
# and the next boot opened two full-screen GUIs driving the same cameras — the
# exact failure #885 exists to prevent, caused by the provisioning chain itself.
#
# Nothing caught it because each component parsed KHPTZ_GUI_MODE on its own (or
# not at all). These tests assert the shared reader is used and that no
# component activates a launcher without consulting it.

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB = REPO_ROOT / "scripts" / "lib" / "install_state.sh"
REPAIR = REPO_ROOT / "scripts" / "repair_rpi_runtime.sh"
CLEANUP = REPO_ROOT / "scripts" / "cleanup_legacy_rpi_autostart.sh"
ACCEPTANCE = REPO_ROOT / "scripts" / "validate_rpi_acceptance.sh"
BOOTSTRAP = REPO_ROOT / "install_khptz_rpi.sh"
INSTALLER = REPO_ROOT / "runtime" / "installer" / "install.sh"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def active_lines(text: str, needle: str) -> list[str]:
    """Lines containing *needle* that are not shell comments."""
    return [
        line for line in text.splitlines()
        if needle in line and not line.lstrip().startswith("#")
    ]


class TestSharedReaderExists:
    def test_library_is_shipped(self):
        assert LIB.is_file()

    def test_library_is_sourced_not_executed(self):
        assert "shellcheck shell=bash" in read(LIB)

    @pytest.mark.parametrize("script", [REPAIR, CLEANUP, ACCEPTANCE])
    def test_component_uses_the_shared_reader(self, script):
        text = read(script)
        assert "lib/install_state.sh" in text, f"{script.name} parses state on its own"

    @pytest.mark.parametrize("script", [REPAIR, CLEANUP])
    def test_component_tolerates_a_missing_library(self, script):
        """A partially deployed tree must not break the script outright."""
        text = read(script)
        assert "khptz_gui_mode() { printf 'system\\n'; }" in text


class TestProvisioningNeverArmsASecondLauncher:
    """The regression that motivated this file."""

    def test_repair_reads_the_gui_mode(self):
        assert "khptz_gui_mode" in read(REPAIR)

    def test_repair_does_not_enable_the_service_unconditionally(self):
        """`systemctl enable khptz-control` must be reachable only inside a
        system-mode branch."""
        text = read(REPAIR)
        enables = active_lines(text, 'systemctl enable "${SERVICE_NAME}"')
        assert enables, "expected the system-mode enable to still exist"
        # Every enable must sit after a GUI_MODE guard.
        guard = text.index('GUI_MODE}" == "user"')
        for line in enables:
            assert text.index(line) > guard, (
                "khptz-control is enabled before the GUI mode is consulted"
            )

    def test_repair_disables_the_service_in_user_mode(self):
        """Not merely 'does not enable': a machine switched to user mode after a
        system-mode install must be actively corrected."""
        text = read(REPAIR)
        assert active_lines(text, 'systemctl disable --now "${SERVICE_NAME}"')

    def test_repair_does_not_wait_for_the_service_in_user_mode(self):
        """Waiting for a deliberately-disabled service aborted the wizard's
        provisioning with 'khptz-control did not become active'."""
        text = read(REPAIR)
        wait = text.index("did not become active")
        guard = text.index('GUI_MODE}" == "user"')
        assert guard < wait, "the activation wait is not behind a GUI-mode guard"


class TestRollbackSurvivesDamagedMetadata:
    """Rollback is the recovery path. install.sh rejects an unknown
    --gui-mode with exit 1, so forwarding a corrupt recorded value blindly
    would abort the very operation being used to recover."""

    def test_normalises_an_unrecognised_mode(self):
        text = read(REPO_ROOT / "runtime" / "installer" / "rollback.sh")
        block = text[text.index("Normalise the recorded mode"):]
        assert 'GUI_MODE="system"' in block

    def test_warns_rather_than_failing(self):
        text = read(REPO_ROOT / "runtime" / "installer" / "rollback.sh")
        block = text[text.index("Normalise the recorded mode"):]
        assert "WARNING: unrecognised KHPTZ_GUI_MODE" in block
        assert "fail " not in block.split("REDEPLOY_ARGS")[0]

    def test_empty_value_still_means_default(self):
        """Installs predating the flag must keep working untouched."""
        text = read(REPO_ROOT / "runtime" / "installer" / "rollback.sh")
        block = text[text.index("Normalise the recorded mode"):]
        assert '"")' in block


class TestBootstrapKnowsTheInstallLayout:
    def test_dev_mode_is_tracked_not_only_forwarded(self):
        text = read(BOOTSTRAP)
        assert "DEV_MODE=true" in text
        assert "DEV_MODE=false" in text

    def test_readiness_check_receives_dev(self):
        """--check validated the product layout while installing the developer
        one, so a check could pass and the install then fail."""
        text = read(BOOTSTRAP)
        assert "_CHECK_ARGS" in text

    def test_verification_skips_product_wiring_in_dev_mode(self):
        """--dev --gui-mode user reported a fatal failure for an install that
        did exactly what was asked."""
        text = read(BOOTSTRAP)
        assert "Developer install" in text


class TestCommitIdentityIsReadable:
    """Under sudo the checkout belongs to the desktop user; git refuses to read
    it without safe.directory. Every git call in the entry point failed, so the
    commit was reported as 'unknown' and the dirty guard never fired."""

    def test_bootstrap_uses_safe_directory(self):
        text = read(BOOTSTRAP)
        assert "safe.directory" in text

    def test_no_bare_git_c_calls_remain(self):
        text = read(BOOTSTRAP)
        bare = [
            line for line in active_lines(text, "git -C")
            if "safe.directory" not in line
        ]
        assert not bare, f"git calls without safe.directory: {bare}"

    def test_installer_and_rollback_still_use_it(self):
        """Guard the precedent this fix was derived from."""
        assert "safe.directory" in read(INSTALLER)
        assert "safe.directory" in read(REPO_ROOT / "runtime" / "installer" / "rollback.sh")


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="WSL bash cannot resolve a C:/ path; runs on Linux CI and the Pi",
)
class TestSharedReaderBehaviour:
    """Execute the reader rather than only inspecting it."""

    def _mode(self, tmp_path, contents: str | None) -> str:
        # `export` on its own statement, not `VAR=x source lib`: an assignment
        # prefix to a special builtin does not persist past it in bash, so the
        # library saw the variable while sourcing and lost it before the reader
        # ran — every case then fell back to "system" and the parity this class
        # exists to prove was never actually exercised.
        state = tmp_path / "install-state.env"
        if contents is not None:
            state.write_text(contents, encoding="utf-8")
        result = subprocess.run(
            ["bash", "-c",
             f'export KHPTZ_INSTALL_STATE="{state.as_posix()}"; '
             f'source "{LIB.as_posix()}"; khptz_gui_mode'],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    def test_reads_user(self, tmp_path):
        assert self._mode(tmp_path, 'KHPTZ_GUI_MODE="user"\n') == "user"

    def test_reads_system(self, tmp_path):
        assert self._mode(tmp_path, 'KHPTZ_GUI_MODE="system"\n') == "system"

    def test_unquoted_value(self, tmp_path):
        assert self._mode(tmp_path, "KHPTZ_GUI_MODE=user\n") == "user"

    def test_unknown_value_falls_back_to_system(self, tmp_path):
        """Never invent a third mode, and never guess 'user' — that would
        disable the only launcher a legacy machine has."""
        assert self._mode(tmp_path, 'KHPTZ_GUI_MODE="banana"\n') == "system"

    def test_missing_key_falls_back_to_system(self, tmp_path):
        assert self._mode(tmp_path, 'KHPTZ_WIZARD_USER="khptz"\n') == "system"

    def test_missing_file_falls_back_to_system(self, tmp_path):
        assert self._mode(tmp_path, None) == "system"

    def test_picks_the_key_out_of_a_full_state_file(self, tmp_path):
        contents = "\n".join([
            'KHPTZ_INSTALL_MODE="product"',
            'KHPTZ_WIZARD_USER="khptz"',
            'KHPTZ_GUI_MODE="user"',
            'KHPTZ_INSTALLED_AT="2026-07-26T00:00:00Z"',
        ]) + "\n"
        assert self._mode(tmp_path, contents) == "user"
