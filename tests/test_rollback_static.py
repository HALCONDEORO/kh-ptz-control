#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Static regression tests for runtime/installer/rollback.sh.

These tests parse the rollback script as text without executing it (it needs
root, systemd and a real Pi). They lock in the contract between install.sh and
rollback.sh that a live install depends on:

  install.sh rsyncs /opt/khptz with --exclude='.git' and makes it root:khptz 0750,
  so /opt/khptz is a *deployed artifact*, never a checkout. A product rollback
  must therefore re-deploy an older ref from the source checkout recorded in
  /etc/khptz/install-state.env — it cannot `git checkout` inside the install dir.

The previous version of this script asserted `-d $INSTALL_DIR/.git` in its
preflight, which made every product rollback abort before doing anything.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT   = Path(__file__).parent.parent
ROLLBACK_SH = REPO_ROOT / "runtime" / "installer" / "rollback.sh"
INSTALL_SH  = REPO_ROOT / "runtime" / "installer" / "install.sh"

STATE_FILENAME = "install-state.env"


def _sh() -> str:
    return ROLLBACK_SH.read_text(encoding="utf-8")


def _install_sh() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


def _product_branch(text: str, marker: str, end_marker: str) -> str:
    start = text.find(marker)
    assert start != -1, f"marker not found: {marker}"
    end = text.find(end_marker, start)
    assert end != -1, f"end marker not found: {end_marker}"
    return text[start:end]


# ── install.sh writes the state rollback.sh reads ────────────────────────────

class TestInstallStateContract:
    """install.sh must record where it was installed from and which ref is
    live, or rollback.sh has nothing to re-deploy."""

    def test_installer_writes_state_file_to_config_dir(self):
        sh = _install_sh()
        assert f'STATE_FILE="${{CONFIG_DIR}}/{STATE_FILENAME}"' in sh, (
            "install-state.env must live in CONFIG_DIR — the install dir is "
            "replaced wholesale by rsync on every deploy"
        )

    def test_installer_records_all_fields_rollback_reads(self):
        sh = _install_sh()
        for key in (
            "KHPTZ_INSTALLED_REF",
            "KHPTZ_PREVIOUS_REF",
            "KHPTZ_SOURCE_DIR",
            "KHPTZ_WIZARD_USER",
        ):
            assert f"{key}=" in sh, f"install.sh does not record {key}"

    def test_rollback_reads_every_field_installer_writes(self):
        sh = _sh()
        for key in ("KHPTZ_PREVIOUS_REF", "KHPTZ_SOURCE_DIR", "KHPTZ_WIZARD_USER"):
            assert key in sh, f"rollback.sh never reads {key}"

    def test_installer_uses_safe_directory_for_git(self):
        """git refuses to read a repo owned by another user under sudo."""
        assert "safe.directory" in _install_sh()

    def test_state_file_not_world_readable_in_product_mode(self):
        sh = _install_sh()
        block = _product_branch(sh, 'STATE_FILE="${CONFIG_DIR}', "# ── Done")
        assert 'chmod 640 "${STATE_FILE}"' in block
        assert 'chown root:"${APP_USER}" "${STATE_FILE}"' in block


# ── product rollback must not assume a checkout in the install dir ───────────

class TestProductRollbackDoesNotRequireGitInInstallDir:

    def test_no_unconditional_git_check_on_install_dir(self):
        """`-d "$INSTALL_DIR/.git"` must never be asserted for a product
        install — install.sh rsyncs with --exclude='.git', so it can never
        be true and the old check aborted every product rollback."""
        sh = _sh()
        assert '[[ -d "$INSTALL_DIR/.git" ]] || fail' not in sh

    def test_git_check_on_install_dir_is_dev_mode_only(self):
        sh = _sh()
        idx = sh.find('[[ -d "$SOURCE_DIR/.git" ]] || fail "Not a git repository')
        assert idx != -1, "dev-mode checkout guard not found"
        guard = sh.rfind('if [[ "${DEV_MODE}" == "true" ]]', 0, idx)
        product = sh.rfind("else", 0, idx)
        assert guard != -1 and guard > product, (
            "the in-place git guard must sit in the dev-mode branch"
        )

    def test_installer_still_excludes_git_from_deploy(self):
        """Guards the assumption above: if the deploy ever stops excluding
        .git this test should be revisited together with rollback.sh."""
        assert "--exclude='.git'" in _install_sh()

    def test_product_rollback_redeploys_via_install_sh(self):
        sh = _sh()
        assert "runtime/installer/install.sh" in sh, (
            "product rollback must re-deploy through install.sh"
        )

    def test_redeploy_preserves_wizard_user(self):
        """Re-running install.sh without --wizard-user would drop the
        provisioning channel and the first-boot autostart."""
        assert '--wizard-user "$WIZARD_USER"' in _sh()

    def test_source_dir_can_be_overridden(self):
        sh = _sh()
        assert "--source" in sh
        assert "SOURCE_DIR_OVERRIDE" in sh


# ── deploy must be an exact mirror so a downgrade is clean ───────────────────

class TestDeployIsExactMirror:
    """Without --delete, rolling back leaves files from the newer release in
    /opt/khptz and the running install is a mix of two versions."""

    def test_product_deploy_uses_rsync_delete(self):
        assert "rsync -a --delete" in _install_sh()

    def test_dev_deploy_does_not_use_delete(self):
        """Dev layout keeps config/data in or beside the install dir."""
        sh = _install_sh()
        idx = sh.find("# Dev layout keeps config/data inside or beside")
        assert idx != -1, "dev-mode rsync branch comment not found"
        dev_block = sh[idx:sh.find("\nfi\n", idx)]
        code = [
            line for line in dev_block.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert "--delete" not in "\n".join(code)

    def test_same_source_and_install_dir_skips_copy(self):
        """`git clone … khptz` into the dev install dir makes src == dst."""
        assert '[[ "${REPO_ROOT}" == "${INSTALL_DIR}" ]]' in _install_sh()


# ── shell footguns found in review ───────────────────────────────────────────

class TestShellRobustness:
    """Three defects caught reviewing the first cut of these scripts. Each one
    fails silently or at the worst moment, so they get their own tests."""

    def test_state_value_survives_a_missing_state_file(self):
        """`set -o pipefail` makes the pipeline inherit sed's exit 2 when the
        file is absent, aborting the script from inside a "$(...)" assignment
        with no message at all."""
        for text in (_sh(), _install_sh()):
            assert "sed -n" in text
            helper_lines = [
                line for line in text.splitlines()
                if "sed -n" in line and "install-state" not in line
            ]
            assert helper_lines, "state_value helper not found"
            for line in helper_lines:
                assert line.rstrip().endswith("|| true"), (
                    f"state_value pipeline must not abort under pipefail: {line}"
                )

    def test_backup_filename_sanitizes_the_ref(self):
        """A ref may contain '/' (`--to release/v3.2.0`). Interpolated raw it
        becomes a path separator, so `khptz backup --dest` writes into a
        directory that does not exist and step 1 aborts the rollback."""
        sh = _sh()
        assert "sanitize_ref()" in sh
        backup_line = next(
            line for line in sh.splitlines() if line.startswith("BACKUP_NAME=")
        )
        assert "sanitize_ref" in backup_line, (
            f"BACKUP_NAME interpolates the ref unsanitised: {backup_line}"
        )

    def test_reinstalling_the_same_ref_keeps_the_rollback_target(self):
        """Re-running install.sh on the deployed ref (permission repair,
        re-registering units) must not blank KHPTZ_PREVIOUS_REF — that silently
        disables rollback and loses the only pointer to the previous release."""
        sh = _install_sh()
        assert "PREV_ROLLBACK_REF" in sh, (
            "installer does not read the existing rollback target, so a same-ref "
            "re-run cannot preserve it"
        )
        idx = sh.find('if [[ "${PREV_INSTALLED_REF}" == "${SOURCE_REF}" ]]')
        assert idx != -1, "same-ref branch not found"
        branch = sh[idx:sh.find("\nfi\n", idx)]
        assert 'PREVIOUS_REF="${PREV_ROLLBACK_REF}"' in branch


# ── customer data / provisioning safety ──────────────────────────────────────

class TestRollbackSafety:

    def test_backup_taken_before_any_change(self):
        sh = _sh()
        backup = sh.find("Step 1: Creating pre-rollback backup")
        revert = sh.find("Step 3: Checking out")
        assert backup != -1 and revert != -1 and backup < revert

    def test_service_stopped_before_revert(self):
        sh = _sh()
        stop = sh.find("Step 2: Stopping")
        revert = sh.find("Step 3: Checking out")
        assert stop != -1 and revert != -1 and stop < revert

    def test_rollback_never_removes_provisioned_marker(self):
        """A rollback is a code-level operation: the wizard's provisioning
        (marker + both password secrets + config.yaml) must survive it, or the
        setup wizard would re-run and khptz-control would refuse to start."""
        sh = _sh()
        assert ".provisioned" in sh, "rollback.sh should reason about the marker"
        for destructive in ("rm -rf", "rm -f /etc/khptz", "shred"):
            assert destructive not in sh

    def test_dry_run_supported(self):
        sh = _sh()
        assert "--dry-run" in sh
        assert 'DRY_RUN="${DRY_RUN:-0}"' in sh

    def test_refuses_rollback_to_current_version(self):
        assert '[[ "$CURRENT_REF" != "$TARGET_REF" ]] || fail' in _sh()

    def test_strict_mode_enabled(self):
        assert "set -euo pipefail" in _sh()

    def test_requires_root(self):
        assert '[[ "$(id -u)" -eq 0 ]] || fail' in _sh()


# ── pip3 must not be a hidden product-mode prerequisite ──────────────────────

class TestProductModePipGuard:
    """requirements-rpi.txt carries only comments. `-s` (size > 0) was true for
    it, so every product install ran pip3 — which is not a product-mode
    prerequisite. Under `set -e` that aborted the install after the service
    user and directories existed but before the app was copied."""

    def test_installer_does_not_use_size_test_on_requirements_rpi(self):
        assert '[[ -s "${REPO_ROOT}/requirements-rpi.txt" ]]' not in _install_sh()

    def test_installer_tests_for_a_real_requirement_line(self):
        sh = _install_sh()
        assert "grep -qE '^[[:space:]]*[^#[:space:]]'" in sh

    def test_pip3_required_before_use_in_product_branch(self):
        sh = _install_sh()
        idx = sh.find("Installing additional pip dependencies from requirements-rpi.txt")
        assert idx != -1
        block = sh[idx:idx + 400]
        require = block.find("require_command pip3 python3-pip")
        use = block.find("pip3 install")
        assert require != -1 and require < use, (
            "pip3 must be checked before it is used in the product-mode branch"
        )

    def test_current_requirements_rpi_has_no_pip_requirements(self):
        """If this ever fails, product installs now genuinely need pip3 and
        docs/INSTALL_RPI.md must add python3-pip to the apt line."""
        text = (REPO_ROOT / "requirements-rpi.txt").read_text(encoding="utf-8")
        real = [
            line for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert real == [], f"requirements-rpi.txt now lists packages: {real}"
