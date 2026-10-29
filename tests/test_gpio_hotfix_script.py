#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_gpio_hotfix_script.py — contract for the #882 field hotfix
#
# scripts/fix_optional_gpio_abort.sh replaces one installed file on a customer
# appliance and restarts the service. It is run by hand, under sudo, on a
# machine that is already failing — so the only acceptable shape is:
# back up first, install with the product's own file mode, verify, and if the
# service does not come back, tell the operator exactly how to undo it.
#
# Nothing else tested this script. A silent regression here (an overwrite with
# no backup, a world-readable install, a missing restore hint) is only
# discovered on a customer's Pi, mid-incident.

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "fix_optional_gpio_abort.sh"


@pytest.fixture(scope="module")
def text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def active_lines(text: str, needle: str) -> list[str]:
    return [
        line for line in text.splitlines()
        if needle in line and not line.lstrip().startswith("#")
    ]


class TestShipped:
    def test_script_exists(self):
        assert SCRIPT.is_file()

    def test_fails_fast_and_loud(self, text):
        """Half-applying a hotfix is worse than not applying it."""
        assert "set -Eeuo pipefail" in text

    def test_patches_the_file_the_issue_is_about(self, text):
        assert "adapters/gpio_monitor.py" in text


class TestPreconditions:
    def test_requires_root(self, text):
        assert '[[ "$(id -u)" -eq 0 ]] || fail' in text

    def test_refuses_when_the_source_file_is_missing(self, text):
        assert '[[ -f "${SOURCE_FILE}" ]] || fail' in text

    def test_refuses_when_there_is_no_installation_to_patch(self, text):
        """Run from a checkout on a machine with no /opt/hallptz, the script must
        stop rather than create a stray file."""
        assert '[[ -f "${TARGET_FILE}" ]] || fail' in text

    def test_requires_the_tools_it_uses(self, text):
        assert "command -v python3" in text
        assert "command -v systemctl" in text

    def test_source_is_resolved_from_the_checkout_not_the_cwd(self, text):
        """It is documented as `sudo bash scripts/...`, but operators run it
        from anywhere."""
        assert 'BASH_SOURCE[0]' in text


class TestBackupBeforeOverwrite:
    def test_a_backup_is_taken(self, text):
        assert active_lines(text, 'cp -a "${TARGET_FILE}" "${BACKUP}"')

    def test_backup_happens_before_the_install(self, text):
        backup_at = text.index('cp -a "${TARGET_FILE}"')
        install_at = text.index('install -m 0640')
        assert backup_at < install_at, "the original would be lost on failure"

    def test_backup_name_is_unique_per_run(self, text):
        """Running the hotfix twice must not overwrite the pristine copy."""
        assert "STAMP=" in text
        assert "${STAMP}" in text

    def test_backup_is_never_deleted(self, text):
        assert not active_lines(text, "rm ")
        assert not active_lines(text, "rm -")

    def test_failure_tells_the_operator_how_to_restore(self, text):
        """The last line an operator sees when it goes wrong."""
        assert "Restore with:" in text
        assert '${BACKUP}' in text.split("Restore with:")[1]


class TestInstalledFilePolicy:
    def test_mode_and_ownership_match_the_product(self, text):
        """0640 root:hallptz is the installer's own policy — a hotfix must not
        widen access to application code on a customer appliance."""
        assert "install -m 0640 -o root -g hallptz" in text

    def test_no_world_readable_mode_is_used(self, text):
        for bad_mode in ("0644", "0664", "0666", "0777", "a+r", "o+r"):
            assert not active_lines(text, bad_mode), f"{bad_mode} would widen access"

    def test_syntax_is_verified_after_installing(self, text):
        """py_compile catches a truncated copy before the service is asked to
        import it."""
        compile_at = text.index("py_compile")
        install_at = text.index('install -m 0640')
        start_at = text.index('systemctl start')
        assert install_at < compile_at < start_at


class TestServiceHandling:
    def test_service_is_stopped_before_the_file_changes(self, text):
        stop_at = text.index('systemctl stop')
        install_at = text.index('install -m 0640')
        assert stop_at < install_at

    def test_a_stopped_service_is_not_an_error(self, text):
        """The appliance is usually already down when this is run."""
        assert 'systemctl stop "${SERVICE}" || true' in text

    def test_previous_failures_are_cleared_before_starting(self, text):
        """Without reset-failed a start-limit-hit unit refuses to start and the
        hotfix looks like it did not work."""
        assert "systemctl reset-failed" in text

    def test_the_service_is_confirmed_active_not_just_started(self, text):
        assert "systemctl is-active --quiet" in text

    def test_it_waits_rather_than_checking_once(self, text):
        assert "seq 1 15" in text
        assert "sleep 1" in text

    def test_diagnostics_are_printed_when_it_does_not_come_back(self, text):
        assert "systemctl status" in text
        assert "journalctl -u" in text

    def test_it_targets_the_product_service(self, text):
        assert 'SERVICE="hallptz-control.service"' in text


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="WSL bash cannot resolve a C:/ path; runs on Linux CI and the Pi",
)
@pytest.mark.skipif(
    getattr(os, "geteuid", lambda: 1)() == 0,
    reason="the root guard cannot be observed while running as root",
)
class TestRefusesWithoutRoot:
    """The one path safe to execute here: it must bail before touching
    anything."""

    def test_exits_non_zero_without_sudo(self):
        result = subprocess.run(
            ["bash", str(SCRIPT)], capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "sudo" in result.stderr.lower()
