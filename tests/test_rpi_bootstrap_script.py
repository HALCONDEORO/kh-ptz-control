#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_rpi_bootstrap_script.py — Contract tests for install_hallptz_rpi.sh (#883)
#
# The bootstrap script cannot be executed end-to-end in CI (it needs root, a
# Raspberry Pi and an X session), so these tests pin the properties that the
# first real installation showed to matter: it must be findable from any
# directory, must not ask the operator to run xhost or edit systemd files by
# hand, and must report a single unambiguous next action.

from __future__ import annotations

import re
import shutil
import sys
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "install_hallptz_rpi.sh"

#: Git Bash on Windows mangles backslash paths ("C:UsersmarcoDesktop..."), so
#: always hand bash a forward-slash path. On Linux this is the normal form.
SCRIPT_ARG = SCRIPT.as_posix()


@pytest.fixture(scope="module")
def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


class TestScriptExists:
    def test_bootstrap_script_is_at_the_repository_root(self):
        """Documented as `sudo bash install_hallptz_rpi.sh` — it must be here."""
        assert SCRIPT.is_file()

    def test_has_a_bash_shebang(self, script_text):
        assert script_text.startswith("#!/usr/bin/env bash")

    def test_uses_strict_mode(self, script_text):
        assert "set -euo pipefail" in script_text


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "the `bash` on PATH under Windows is typically WSL's, which cannot "
        "resolve a C:/ path; these run on Linux CI and on the Pi, where the "
        "script actually ships"
    ),
)
class TestScriptIsValidBash:
    def test_parses_without_syntax_errors(self):
        result = subprocess.run(
            ["bash", "-n", SCRIPT_ARG],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_help_works_without_root_and_without_arguments(self):
        result = subprocess.run(
            ["bash", SCRIPT_ARG, "--help"],
            capture_output=True, text=True, cwd=str(REPO_ROOT.parent),
        )
        assert result.returncode == 0
        assert "install_hallptz_rpi.sh" in result.stdout

    def test_unknown_option_is_rejected_clearly(self):
        result = subprocess.run(
            ["bash", SCRIPT_ARG, "--definitely-not-a-flag"],
            capture_output=True, text=True,
        )
        assert result.returncode == 30
        assert "Unknown option" in result.stderr

    def test_wizard_user_without_a_value_is_rejected(self):
        result = subprocess.run(
            ["bash", SCRIPT_ARG, "--wizard-user"],
            capture_output=True, text=True,
        )
        assert result.returncode == 30
        assert "--wizard-user" in result.stderr

    def test_runs_from_any_directory(self, tmp_path):
        """`sudo: ./runtime/installer/install.sh: command not found` came from
        running the installer from the wrong directory."""
        result = subprocess.run(
            ["bash", SCRIPT_ARG, "--definitely-not-a-flag"],
            capture_output=True, text=True, cwd=str(tmp_path),
        )
        # It got far enough to parse arguments rather than failing to locate itself.
        assert "Unknown option" in result.stderr

    def test_allow_dirty_is_a_recognised_flag(self):
        """--allow-dirty must parse; only an unknown flag exits 30 here."""
        result = subprocess.run(
            ["bash", SCRIPT_ARG, "--allow-dirty", "--definitely-not-a-flag"],
            capture_output=True, text=True,
        )
        # It rejected the *unknown* flag, meaning --allow-dirty was accepted first.
        assert "--definitely-not-a-flag" in result.stderr


class TestCleanCheckoutGuard:
    """A customer appliance must not be installed from an unidentifiable,
    modified checkout (CLAUDE.md). The bootstrap already computes a `-dirty`
    marker; it must act on it rather than only printing it."""

    def test_blocks_a_dirty_checkout_by_default(self, script_text):
        assert "-dirty" in script_text
        assert "--allow-dirty" in script_text
        # The dirty branch must reach fatal(), not merely annotate the commit.
        assert re.search(r"-dirty.*\n(.*\n)*?.*ALLOW_DIRTY", script_text)

    def test_documents_the_escape_hatch(self, script_text):
        assert "--allow-dirty" in script_text


class TestServiceStartVerification:
    """SUCCESS must not be printed while the service is dead or crash-looping —
    the first install reported progress while systemd was in a restart loop."""

    def test_checks_the_unit_is_enabled(self, script_text):
        assert "is-enabled" in script_text

    def test_detects_a_restart_loop(self, script_text):
        assert "NRestarts" in script_text

    def test_does_not_hard_fail_on_inactive_at_install_time(self, script_text):
        """The unit is normally inactive at install (starts after login), so a
        bare is-active check must not gate SUCCESS."""
        # is-active is only used to detect the 'failed' state, alongside NRestarts.
        assert "is-active" in script_text
        assert "failed" in script_text


class TestOperatorNeverRunsManualCommands:
    def test_does_not_instruct_the_operator_to_run_xhost(self, script_text):
        """`xhost: bad hostname "sudo"` came from a pasted manual xhost line."""
        instructions = re.findall(r'echo\s+"[^"]*xhost[^"]*"', script_text)
        assert not instructions, f"script tells the operator to run xhost: {instructions}"

    def test_does_not_hand_the_service_an_x_cookie(self, script_text):
        """Display access is granted per-login by repair_rpi_runtime.sh via
        `xhost +SI:localuser:hallptz`, which authorises by UID and needs no cookie.

        The old drop-in set XAUTHORITY from the desktop user's home, which
        forced ProtectHome down to read-only and exposed every home directory.
        """
        assert "XAUTHORITY=" not in script_text
        assert "setfacl" not in script_text

    def test_never_weakens_protecthome(self, script_text):
        """Matches the directive, not the word: the script documents in prose
        why the old ProtectHome=read-only override was removed."""
        directives = re.findall(r"^\s*ProtectHome\s*=", script_text, re.MULTILINE)
        assert not directives, f"script sets ProtectHome: {directives}"

    def test_does_not_bake_the_callers_display_into_a_unit(self, script_text):
        """Installing over SSH with X forwarding put a dead 'localhost:10.0'
        into the unit. The script no longer writes DISPLAY anywhere."""
        assert "Environment=DISPLAY" not in script_text

    def test_removes_the_superseded_dropin_so_rerunning_repairs_a_host(self, script_text):
        assert "10-display-session.conf" in script_text
        assert "rm -f" in script_text

    def test_reloads_systemd_after_changing_unit_configuration(self, script_text):
        assert "systemctl daemon-reload" in script_text


class TestDiagnosticsRunAsTheServiceIdentity:
    """`hallptz doctor` must not run as root from the installer.

    /var/log/hallptz is hallptz:hallptz 0750. A root-run doctor creates root:root
    app.log and blackbox files inside it, after which the service can never
    write its own logs — the same permission failure class as #884, caused by
    the installer itself.
    """

    def test_doctor_is_invoked_as_the_hallptz_user(self, script_text):
        assert "sudo -u hallptz hallptz doctor" in script_text

    def test_root_fallback_redirects_the_log_directory(self, script_text):
        """The non-product fallback must not write into service-owned paths."""
        assert "HALLPTZ_LOG_DIR=" in script_text

    def test_no_bare_root_doctor_invocation(self, script_text):
        """A plain `hallptz doctor` line would run as root and poison the paths."""
        bare = re.findall(r"^\s*hallptz doctor\b", script_text, re.MULTILINE)
        assert not bare, f"doctor invoked without dropping privileges: {bare}"


class TestReportingContract:
    def test_reports_the_installed_version_and_commit(self, script_text):
        assert "VERSION" in script_text
        assert "rev-parse --short HEAD" in script_text

    def test_distinguishes_success_config_required_and_fatal(self, script_text):
        assert "SUCCESS" in script_text
        assert "INSTALLED" in script_text
        assert "FAILED" in script_text

    def test_prints_a_single_next_action(self, script_text):
        assert "Next action:" in script_text

    def test_branches_on_every_doctor_outcome_exit_code(self, script_text):
        """Must stay aligned with domain/doctor_outcome.py exit codes."""
        from domain.doctor_outcome import DoctorOutcome, exit_code_for

        case_block = script_text.split("case \"${DOCTOR_RC}\"")[1]
        for outcome in (DoctorOutcome.PASS, DoctorOutcome.READY_WITH_ADVISORIES,
                        DoctorOutcome.CONFIG_REQUIRED):
            code = exit_code_for(outcome)
            assert re.search(rf"^\s*{code}\)", case_block, re.MULTILINE), \
                f"no branch for exit code {code} ({outcome.value})"
        # FAIL and anything unexpected share the catch-all branch.
        assert "*)" in case_block

    def test_config_required_exit_code_is_propagated(self, script_text):
        from domain.doctor_outcome import DoctorOutcome, exit_code_for

        assert f"RC={exit_code_for(DoctorOutcome.CONFIG_REQUIRED)}" in script_text


class TestIdempotenceAndSafety:
    def test_documents_that_it_is_safe_to_rerun(self, script_text):
        assert "Idempotent" in script_text

    def test_requires_root_before_changing_anything(self, script_text):
        root_check = script_text.index('EUID')
        installer_run = script_text.index('bash "${INSTALLER}"')
        assert root_check < installer_run

    def test_validates_readiness_before_installing(self, script_text):
        # The check is invoked through _CHECK_ARGS so that --dev reaches it too:
        # validating the product layout while installing the developer one let a
        # check pass that the install then failed.
        check_run = script_text.index('"${INSTALLER}" "${_CHECK_ARGS[@]}"')
        install_run = script_text.index('"${INSTALLER}" --wizard-user')
        assert check_run < install_run

    def test_readiness_check_uses_the_same_layout_as_the_install(self, script_text):
        """--dev selects /home/<user>/hallptz instead of /opt/hallptz and requires
        pip3, so the check must receive it as well."""
        assert "_CHECK_ARGS=(--check)" in script_text
        assert '_CHECK_ARGS+=(--dev)' in script_text

    def test_never_deletes_customer_paths(self, script_text):
        assert "rm -rf /etc/hallptz" not in script_text
        assert "rm -rf /var/lib/hallptz" not in script_text
