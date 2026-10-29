#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_validate_rpi_deployment_script.py — contract for the #890/#892 evidence run
#
# scripts/validate_rpi_deployment.sh is what docs/INSTALL_RPI.md tells the
# installer to run on the physical appliance to collect closure evidence. It had
# no tests at all. Two properties carry the whole value of the script:
#
#   - it must stay READ-ONLY. It runs on a customer Pi that is meant to be
#     validated, not modified; a script that repairs what it measures produces
#     evidence for a machine nobody will ever ship.
#   - its verdict must be trustworthy in both directions. A false FAIL sends an
#     installer chasing a healthy machine; a false PASS closes a release gate on
#     an appliance that is actually broken.

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "validate_rpi_deployment.sh"
STATE_LIB = REPO_ROOT / "scripts" / "lib" / "install_state.sh"
DOCS = REPO_ROOT / "docs" / "INSTALL_RPI.md"


@pytest.fixture(scope="module")
def text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def active_lines(text: str, needle: str) -> list[str]:
    return [
        line for line in text.splitlines()
        if needle in line and not line.lstrip().startswith("#")
    ]


def command_lines(text: str, command: str) -> list[str]:
    """Active lines where *command* is actually invoked.

    A plain substring search is useless here: the validator's own messages quote
    the commands it is looking for ("no global 'xhost +'"), and words like
    "platform" contain "rm ". Anchor on a statement boundary instead.
    """
    pattern = re.compile(
        r"(?:^|[;&|(]|\$\(|\bthen\b|\bdo\b|\belse\b|\|\|)\s*" + re.escape(command)
    )
    return [
        line for line in text.splitlines()
        if not line.lstrip().startswith("#") and pattern.search(line)
    ]


class TestShipped:
    def test_script_exists(self):
        assert SCRIPT.is_file()

    def test_documented_invocation_still_matches_the_script(self):
        """docs/INSTALL_RPI.md is what the installer follows on site."""
        assert "validate_rpi_deployment.sh" in DOCS.read_text(encoding="utf-8")

    def test_strict_mode(self, text):
        assert "set -Eeuo pipefail" in text


class TestReadOnly:
    """It measures the appliance; it must never change it."""

    @pytest.mark.parametrize("forbidden", [
        "systemctl enable",
        "systemctl disable",
        "systemctl start",
        "systemctl stop",
        "systemctl restart",
        "systemctl daemon-reload",
        "rm ",
        "mv ",
        "chmod ",
        "chown ",
        "tee /",
    ])
    def test_does_not_mutate_the_appliance(self, text, forbidden):
        assert not command_lines(text, forbidden), \
            f"the validator would run '{forbidden}'"

    def test_xhost_is_only_ever_queried(self, text):
        """`xhost` with an argument grants or revokes access. The validator
        checks that access control is scoped — granting it would both change the
        machine and hide the very problem it is looking for."""
        for line in command_lines(text, "xhost"):
            assert not re.search(r"xhost\s+[-+]", line), line

    def test_the_legacy_cleanup_only_ever_runs_dry(self, text):
        """cleanup_legacy_rpi_autostart.sh quarantines startup entries for
        real without --dry-run."""
        for line in active_lines(text, "CLEANUP_ARGS=("):
            assert "--dry-run" in line
        assert not [
            line for line in active_lines(text, "${CLEANUP}")
            if "bash" in line and "CLEANUP_ARGS" not in line
        ]

    def test_backup_is_never_taken(self, text):
        """`khptz backup` writes a ZIP — a write on a read-only run."""
        assert not active_lines(text, "khptz backup")
        assert not active_lines(text, "run_khptz backup")

    def test_only_the_report_directory_is_created(self, text):
        for line in active_lines(text, "install -d"):
            assert "LOG_DIR" in line, line


class TestArgumentHandling:
    def test_desktop_user_defaults_to_the_sudo_invoker(self, text):
        assert 'DESKTOP_USER="${SUDO_USER:-}"' in text

    def test_display_defaults_to_zero(self, text):
        assert 'TARGET_DISPLAY="${DISPLAY:-:0}"' in text

    @pytest.mark.parametrize("flag", ["--wizard-user", "--display", "--legacy-pattern"])
    def test_value_flags_reject_a_missing_value(self, text, flag):
        """Without the arity check the next flag becomes the value and the run
        silently validates the wrong user."""
        assert f'{flag}) [[ $# -ge 2 ]] || fail' in text

    def test_unknown_options_are_rejected(self, text):
        assert 'fail "Unknown option: $1"' in text

    def test_requires_root(self, text):
        assert '[[ "$(id -u)" -eq 0 ]] || fail "Run this script with sudo."' in text

    def test_requires_a_resolvable_desktop_user(self, text):
        assert 'id "${DESKTOP_USER}"' in text


class TestReportFile:
    def test_report_is_written_next_to_the_production_logs(self, text):
        assert 'LOG_DIR="/var/log/khptz/validation"' in text

    def test_falls_back_when_the_log_directory_is_not_writable(self, text):
        """#884: read-only diagnostics must never abort over their own output
        path."""
        assert '[[ -w "${LOG_DIR}" ]]' in text
        assert "khptz-validation" in text
        assert 'LOG_DIR="/tmp"' in text

    def test_report_name_is_unique_per_run(self, text):
        """The two-reboot criterion needs both runs kept side by side."""
        assert 'REPORT="${LOG_DIR}/validation-${TIMESTAMP}.txt"' in text

    def test_output_is_mirrored_to_the_report(self, text):
        assert 'tee -a "${REPORT}"' in text

    def test_report_location_is_printed(self, text):
        assert active_lines(text, "Report saved to")


class TestVerdict:
    def test_failures_and_warnings_are_counted_separately(self, text):
        """A warning must not fail the run, and a failure must not be reported
        as a warning."""
        assert "((WARNINGS += 1))" in text
        assert "((FAILURES += 1))" in text

    def test_a_failure_exits_non_zero(self, text):
        assert '[[ "${FAILURES}" -gt 0 ]]' in text
        assert "exit 1" in text

    def test_usage_errors_use_a_distinct_exit_code(self, text):
        """exit 2 for "could not run" vs exit 1 for "ran and failed"."""
        assert "exit 2" in active_lines(text, "fail()")[0]

    def test_a_clean_run_exits_zero(self, text):
        assert text.rstrip().endswith("exit 0")

    def test_the_verdict_names_the_release_gates(self, text):
        assert "#890" in text and "#892" in text


class TestChecksThatMustExist:
    """Each assertion here is a closure criterion from #885/#886/#890/#892. A
    check silently dropped turns the run into a rubber stamp."""

    @pytest.mark.parametrize("needle,why", [
        ("/opt/khptz/main.py", "exactly one GUI process"),
        ("expected exactly one", "duplicate-GUI detection (#885)"),
        ("KHPTZ|khptz", "legacy controller still running"),
        ("Conflicting entries matched: 0", "no legacy autostart left (#892)"),
        ("Could not parse stylesheet", "Qt 5.15 QSS regression (#886)"),
        ("Profile mismatch", "config contradiction (#886)"),
        ("ATEM enabled but IP not configured", "config contradiction (#886)"),
        ("XDG_RUNTIME_DIR not set", "session handoff (#885)"),
        ("No protocol specified", "X11 auth (#885)"),
        ("could not connect to display", "display handoff (#885)"),
        ("Read-only file system", "path/permission regression (#885)"),
        ("start-limit-hit", "restart loop (#885)"),
        ("access control enabled", "scoped X11 grants, not xhost + (#885)"),
        ("verify-install", "installed-tree verification"),
        ("doctor", "diagnostics"),
    ])
    def test_check_is_present(self, text, needle, why):
        assert needle in text, f"check dropped: {why}"

    def test_the_gui_must_not_run_as_root(self, text):
        assert "is running as root" in text

    def test_missing_cli_degrades_to_a_warning(self, text):
        """A validator that dies because `khptz` is not on PATH produces no
        evidence at all."""
        assert "khptz CLI not found" in text

    def test_absent_journalctl_degrades_to_a_warning(self, text):
        assert active_lines(text, "journalctl unavailable")

    def test_cli_output_encoding_is_forced(self, text):
        """#884: a non-ASCII glyph under a C locale must not abort the run."""
        assert 'PYTHONIOENCODING="utf-8"' in text


class TestPathResolution:
    def test_repo_root_is_derived_from_the_script_location(self, text):
        """#883: operators run it with a relative path from odd directories."""
        assert 'SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")"' in text
        assert 'REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.."' in text

    def test_cli_falls_back_to_the_checkout_module(self, text):
        assert "python3 -m runtime.cli" in text


@pytest.mark.xfail(
    strict=True,
    reason="Known gap: this validator predates --gui-mode user (#885) and is "
           "not GUI-mode aware. On a session-owned install khptz-control is "
           "deliberately disabled, so 'is not active' is reported as a FAILURE, "
           "and every journal check reads an empty khptz-control journal and "
           "reports OK. scripts/validate_rpi_acceptance.sh (#890) already "
           "sources scripts/lib/install_state.sh; this one must too. Remove "
           "this marker together with the fix.",
)
class TestGuiModeAwareness:
    def test_consults_the_shared_install_state_reader(self, text):
        assert "lib/install_state.sh" in text
        assert "khptz_gui_mode" in text

    def test_does_not_require_the_system_service_in_user_mode(self, text):
        """`khptz-control.service is not active` is the correct, installed state
        of a --gui-mode user appliance — not a failure."""
        failing = [
            line for line in active_lines(text, 'bad "${SERVICE} is not active')
        ]
        assert not failing, (
            "the system service is required unconditionally: a session-owned "
            "install fails validation while working correctly"
        )

    def test_checks_the_user_units_in_user_mode(self, text):
        """In user mode the GUI lives in khptz-gui.service and its log is the
        user journal — the unit the journal checks must follow the mode."""
        assert "khptz-gui" in text


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="WSL bash cannot resolve a C:/ path; runs on Linux CI and the Pi",
)
class TestExecutable:
    """Only the paths that change nothing are executed here."""

    def _run(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(SCRIPT), *args], capture_output=True, text=True,
        )

    def test_help_exits_zero_and_documents_every_flag(self):
        result = self._run("--help")
        assert result.returncode == 0
        for flag in ("--wizard-user", "--display", "--legacy-pattern"):
            assert flag in result.stdout

    def test_unknown_option_is_rejected(self):
        result = self._run("--not-a-flag")
        assert result.returncode == 2
        assert "Unknown option" in result.stderr

    def test_a_value_flag_without_a_value_is_rejected(self):
        result = self._run("--wizard-user")
        assert result.returncode == 2

    def test_help_is_answered_before_the_root_check(self):
        """Reading the usage text must not require sudo."""
        assert self._run("-h").returncode == 0

    def test_the_shared_state_library_it_should_use_is_shipped(self):
        assert STATE_LIB.is_file()
