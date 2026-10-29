#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Static regression tests for runtime/installer/install.sh.

These tests parse the installer shell script and systemd service template as
text without executing them.  They catch regressions that would otherwise only
surface during a real Raspberry Pi install.

Issue: #671
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT      = Path(__file__).parent.parent
INSTALL_SH     = REPO_ROOT / "runtime" / "installer" / "install.sh"
SERVICE_FILE   = REPO_ROOT / "runtime" / "systemd" / "khptz-control.service"
PROVISION_SERVICE = REPO_ROOT / "runtime" / "systemd" / "khptz-provision.service"
PROVISION_PATH    = REPO_ROOT / "runtime" / "systemd" / "khptz-provision.path"
SETUP_DESKTOP      = REPO_ROOT / "runtime" / "khptz-setup.desktop"
SETUP_MENU_DESKTOP = REPO_ROOT / "runtime" / "khptz-setup-menu.desktop"
REQUIREMENTS   = {
    "rpi":  REPO_ROOT / "requirements-rpi.txt",
    "atem": REPO_ROOT / "requirements-atem.txt",
    "main": REPO_ROOT / "requirements.txt",
    "dev":  REPO_ROOT / "requirements-dev.txt",
}

# ── helpers ───────────────────────────────────────────────────────────────────

def _sh() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


def _svc() -> str:
    return SERVICE_FILE.read_text(encoding="utf-8")


def _product_paths_from_sh() -> dict[str, str]:
    """Extract product-mode path defaults from install.sh (else/default branch)."""
    sh = _sh()
    paths = {}
    for var, pattern in [
        ("APP_USER",    r'APP_USER="([^"]+)"'),
        ("INSTALL_DIR", r'INSTALL_DIR="([^"]+)"'),
        ("CONFIG_DIR",  r'CONFIG_DIR="([^"]+)"'),
        ("DATA_DIR",    r'DATA_DIR="([^"]+)"'),
        ("LOG_DIR",     r'LOG_DIR="([^"]+)"'),
        ("BACKUP_DIR",  r'BACKUP_DIR="([^"]+)"'),
    ]:
        # Only the product-mode (else) block; take the second match because
        # the dev block comes first and sets different values.
        matches = re.findall(pattern, sh)
        if len(matches) >= 2:
            paths[var] = matches[1]   # second = product-mode else block
        elif matches:
            paths[var] = matches[0]
    return paths


# ── require_command coverage ──────────────────────────────────────────────────

class TestRequireCommandCoverage:

    def test_python3_is_checked(self):
        assert "require_command python3" in _sh()

    def test_git_is_checked(self):
        assert "require_command git" in _sh()

    def test_rsync_is_checked(self):
        assert "require_command rsync" in _sh()

    def test_systemctl_is_checked(self):
        assert "require_command systemctl" in _sh()

    def test_pip3_only_checked_in_guarded_context(self):
        """pip3 must not be checked unconditionally at the top level."""
        sh = _sh()
        # It should appear but only inside a conditional block (dev mode or ATEM)
        unconditional = re.search(
            r'^require_command pip3',
            sh,
            flags=re.MULTILINE,
        )
        assert unconditional is None, (
            "require_command pip3 found at the top level — "
            "it must only be inside a conditional (dev mode or --atem) block"
        )

    def test_require_command_shows_apt_hint(self):
        """require_command must accept an apt hint argument."""
        sh = _sh()
        # The function definition should have a local apt_hint variable
        assert "apt_hint" in sh

    def test_require_command_uses_apt_hint_in_error(self):
        sh = _sh()
        assert "sudo apt install" in sh


class TestPythonRuntimeImports:
    """Hard Python imports product mode never installs must be pre-flighted.

    Product mode installs no pip packages (requirements-rpi.txt is comments
    only), so every third-party import the appliance makes has to come from
    apt. PyQt5 was checked; PyYAML was not — yet config/loader.py imports it at
    module scope, so main.py, `khptz doctor` and runtime/rpi_post_provision.py
    all raise ModuleNotFoundError. Without this gate the installer reports a
    successful install of an appliance that cannot start.
    """

    def test_pyqt5_is_checked(self):
        assert "require_pyqt5" in _sh()

    def test_yaml_is_checked(self):
        assert re.search(r"^require_python_module yaml\b", _sh(), flags=re.MULTILINE)

    def test_yaml_check_names_the_apt_package(self):
        assert "python3-yaml" in _sh()

    def test_yaml_is_checked_before_any_file_is_written(self):
        """A missing module must abort before the service user or directories
        exist, not halfway through an install that then needs unpicking."""
        sh = _sh()
        check_at = sh.index("require_python_module yaml")
        assert check_at < sh.index("useradd")
        assert check_at < sh.index("install -d")

    def test_yaml_is_a_real_runtime_import(self):
        """Guard against the check outliving the dependency it protects."""
        loader = (REPO_ROOT / "config" / "loader.py").read_text(encoding="utf-8")
        assert re.search(r"^import yaml$", loader, flags=re.MULTILINE)


# ── product mode dependency policy ───────────────────────────────────────────

class TestProductModeDependencyPolicy:

    def test_requirements_txt_not_installed_unconditionally(self):
        """requirements.txt must only be installed when DEV_MODE is true.

        For each non-comment line that references requirements.txt, there must
        be a DEV_MODE guard within the preceding 25 lines.
        """
        sh_lines = _sh().splitlines()
        req_lines = [
            (i, l) for i, l in enumerate(sh_lines)
            if "requirements.txt" in l and not l.strip().startswith("#")
        ]
        for lineno, line in req_lines:
            context_above = "\n".join(sh_lines[max(0, lineno - 25) : lineno])
            assert "DEV_MODE" in context_above, (
                f"requirements.txt used at line {lineno + 1} without a nearby "
                f"DEV_MODE guard:\n  {line}"
            )

    def test_requirements_rpi_txt_respected(self):
        """requirements-rpi.txt must be referenced (even if empty)."""
        assert "requirements-rpi.txt" in _sh()

    def test_atem_install_is_conditional(self):
        """ATEM dependency install must be gated on INSTALL_ATEM."""
        sh = _sh()
        assert "INSTALL_ATEM" in sh
        atem_block = re.search(
            r'if \[\[ "\$\{INSTALL_ATEM[^}]*\}" == "true" \]\].*?fi',
            sh,
            flags=re.DOTALL,
        )
        assert atem_block is not None, "No INSTALL_ATEM guard found"
        assert "requirements-atem.txt" in atem_block.group(0)

    def test_atem_flag_documented_in_help(self):
        sh = _sh()
        assert "--atem" in sh


# ── product paths consistency ─────────────────────────────────────────────────

class TestProductPathsConsistency:

    def test_install_dir_is_opt_khptz(self):
        paths = _product_paths_from_sh()
        assert paths.get("INSTALL_DIR") == "/opt/khptz"

    def test_config_dir_is_etc_khptz(self):
        paths = _product_paths_from_sh()
        assert paths.get("CONFIG_DIR") == "/etc/khptz"

    def test_data_dir_is_var_lib_khptz(self):
        paths = _product_paths_from_sh()
        assert paths.get("DATA_DIR") == "/var/lib/khptz"

    def test_log_dir_is_var_log_khptz(self):
        paths = _product_paths_from_sh()
        assert paths.get("LOG_DIR") == "/var/log/khptz"

    def test_backup_dir_is_var_backups_khptz(self):
        paths = _product_paths_from_sh()
        assert paths.get("BACKUP_DIR") == "/var/backups/khptz"

    def test_app_user_is_khptz(self):
        paths = _product_paths_from_sh()
        assert paths.get("APP_USER") == "khptz"


# ── service file consistency ──────────────────────────────────────────────────

class TestServiceFileConsistency:

    def test_service_user_is_khptz(self):
        assert "User=khptz" in _svc()

    def test_service_group_is_khptz(self):
        assert "Group=khptz" in _svc()

    def test_service_working_directory(self):
        assert "WorkingDirectory=/opt/khptz" in _svc()

    def test_service_exec_start(self):
        assert "ExecStart=/usr/bin/python3 /opt/khptz/main.py" in _svc()

    def test_service_read_write_paths_include_etc_khptz(self):
        assert "/etc/khptz" in _svc()

    def test_service_read_write_paths_include_var_lib_khptz(self):
        assert "/var/lib/khptz" in _svc()

    def test_service_read_write_paths_include_var_log_khptz(self):
        assert "/var/log/khptz" in _svc()

    def test_service_read_write_paths_include_var_backups_khptz(self):
        assert "/var/backups/khptz" in _svc()

    def test_service_no_write_to_opt_khptz(self):
        """App code in /opt/khptz must not appear in ReadWritePaths."""
        svc = _svc()
        rw_line = next(
            (l for l in svc.splitlines() if l.strip().startswith("ReadWritePaths")),
            None,
        )
        assert rw_line is not None, "ReadWritePaths not found in service file"
        assert "/opt/khptz" not in rw_line, (
            "/opt/khptz must not be in ReadWritePaths — app code should be read-only"
        )

    def test_service_gates_on_provisioned_marker(self):
        """khptz-control.service must not start with starter/unconfigured
        credentials before the setup wizard provisions the install."""
        assert "ConditionPathExists=/etc/khptz/.provisioned" in _svc()

    def test_dev_mode_strips_provisioned_condition(self):
        """Dev installs never run the wizard/provisioning channel (both gated
        to product mode), so the marker never exists — the dev-mode sed must
        remove the gate, or a dev install's service could never start."""
        sh = _sh()
        assert r"/^ConditionPathExists=\/etc\/khptz\/\.provisioned$/d" in sh


# ── backfill .provisioned for pre-wizard legacy installs ──────────────────────

class TestLegacyProvisionedBackfill:
    """Reinstalling/updating a working install that predates the setup wizard
    must not leave khptz-control.service permanently unable to start just
    because .provisioned was never created by the old manual flow. See PR
    #867 review."""

    def _existing_config_block(self) -> str:
        sh = _sh()
        start = sh.find('info "Existing config.yaml found at')
        assert start != -1
        end = sh.find("# ── khptz CLI symlink", start)
        assert end != -1
        return sh[start:end]

    def test_backfill_only_when_marker_absent_and_secret_present(self):
        block = self._existing_config_block()
        assert '! -f "${PROVISIONED_MARKER}"' in block
        assert '-f "${ENTRY_SECRET}"' in block

    def test_backfill_checks_the_real_entry_secret_path(self):
        block = self._existing_config_block()
        assert 'ENTRY_SECRET="${DATA_DIR}/password.enc"' in block

    def test_backfill_gated_on_product_mode(self):
        block = self._existing_config_block()
        idx = block.find("PROVISIONED_MARKER=")
        assert idx != -1
        guard = block.rfind('if [[ "${DEV_MODE}" == "false" ]]', 0, idx)
        assert guard != -1, "backfill is not gated on product mode"

    def test_backfill_writes_marker_content(self):
        block = self._existing_config_block()
        assert "printf 'ok\\n' > \"${PROVISIONED_MARKER}\"" in block
        assert 'chmod 644 "${PROVISIONED_MARKER}"' in block


# ── post-install "Next steps" message ─────────────────────────────────────────

class TestNextStepsMessage:
    """The final instructions must describe a path that actually works —
    `khptz set-password` was never a real subcommand, and product-mode
    khptz-control.service now gates on .provisioned so `systemctl start`
    right after install would just be skipped. See PR #867 review."""

    def test_no_reference_to_nonexistent_set_password_command(self):
        assert "khptz set-password" not in _sh()

    def test_product_mode_points_at_the_wizard(self):
        sh = _sh()
        marker = 'info "Next steps:"'
        idx = sh.find(marker)
        assert idx != -1
        # Product branch is the `if` arm immediately following the marker.
        product_block_end = sh.find("\nelse\n", idx)
        assert product_block_end != -1
        product_block = sh[idx:product_block_end]
        assert "setup wizard" in product_block
        assert "khptz doctor" in product_block
        assert "systemctl start" not in product_block

    def test_dev_mode_still_documents_manual_password_setup(self):
        sh = _sh()
        marker = 'info "Next steps:"'
        idx = sh.find(marker)
        else_idx = sh.find("\nelse\n", idx)
        assert else_idx != -1
        fi_idx = sh.find("\nfi\n", else_idx)
        assert fi_idx != -1
        dev_block = sh[else_idx:fi_idx]
        assert "runtime.setup_password" in dev_block
        assert "systemctl start" in dev_block


# ── shared secrets dir between control and provision services ────────────────

class TestSecretsDirConsistency:
    """khptz-control.service and khptz-provision.service must resolve secrets to
    the same directory. Without KHPTZ_DATA_DIR pinned in both, secret_manager
    falls back to Path.home() — /root for the provisioning oneshot (runs as
    root) vs wherever Path.home() resolves for the khptz user in the control
    service. Those never agree, so a wizard-provisioned password could never
    decrypt at login. See PR #867 review."""

    def test_control_service_pins_khptz_data_dir(self):
        assert "Environment=KHPTZ_DATA_DIR=/var/lib/khptz" in _svc()

    def test_provision_service_pins_khptz_data_dir(self):
        text = PROVISION_SERVICE.read_text(encoding="utf-8")
        assert "Environment=KHPTZ_DATA_DIR=/var/lib/khptz" in text

    def test_dev_mode_patches_control_service_data_dir(self):
        """Dev-mode sed must repoint KHPTZ_DATA_DIR too, or a dev install's
        control service would still point secrets at /var/lib/khptz."""
        sh = _sh()
        assert "Environment=KHPTZ_DATA_DIR=/var/lib/khptz|Environment=KHPTZ_DATA_DIR=${DATA_DIR}" in sh


# ── installer/service path cross-check ───────────────────────────────────────

class TestInstallerServiceCrossCheck:
    """The installer and service template must agree on canonical paths."""

    def test_install_dir_matches_service_working_directory(self):
        paths = _product_paths_from_sh()
        assert f"WorkingDirectory={paths['INSTALL_DIR']}" in _svc()

    def test_install_dir_matches_service_exec_start(self):
        paths = _product_paths_from_sh()
        install_dir = paths["INSTALL_DIR"]
        assert f"ExecStart=/usr/bin/python3 {install_dir}/main.py" in _svc()

    def test_config_dir_in_service_read_write_paths(self):
        paths = _product_paths_from_sh()
        assert paths["CONFIG_DIR"] in _svc()

    def test_data_dir_in_service_read_write_paths(self):
        paths = _product_paths_from_sh()
        assert paths["DATA_DIR"] in _svc()

    def test_log_dir_in_service_read_write_paths(self):
        paths = _product_paths_from_sh()
        assert paths["LOG_DIR"] in _svc()

    def test_backup_dir_in_service_read_write_paths(self):
        paths = _product_paths_from_sh()
        assert paths["BACKUP_DIR"] in _svc()


# ── ownership / permissions ───────────────────────────────────────────────────

class TestOwnershipAndPermissions:

    def test_opt_khptz_owned_root_khptz(self):
        sh = _sh()
        assert 'chown -R root:"${APP_USER}" "${INSTALL_DIR}"' in sh

    def test_opt_khptz_dirs_mode_750(self):
        assert "chmod 750" in _sh()

    def test_opt_khptz_files_mode_640(self):
        assert "chmod 640" in _sh()

    def test_no_world_readable_chown(self):
        """chown -R root:root must not appear — that was the old (wrong) pattern."""
        assert "chown -R root:root" not in _sh()

    def test_etc_khptz_owned_root_khptz(self):
        sh = _sh()
        assert 'chown root:"${APP_USER}" "${CONFIG_DIR}"' in sh

    def test_etc_khptz_mode_2750_setgid(self):
        assert "2750" in _sh()


# ── launcher ──────────────────────────────────────────────────────────────────

class TestLauncherScript:

    def test_launcher_runs_from_install_dir_as_module(self):
        """Wrapper must cd into INSTALL_DIR and use -m so imports resolve from any cwd."""
        sh = _sh()
        assert 'cd "${INSTALL_DIR}" && exec python3 -m runtime.cli' in sh

    def test_launcher_installed_to_usr_local_bin(self):
        assert "/usr/local/bin/khptz" in _sh()

    def test_launcher_is_executable(self):
        sh = _sh()
        assert 'chmod +x "${KHPTZ_LAUNCHER}"' in sh


# ── installation_id generation ───────────────────────────────────────────────

class TestInstallationIdGeneration:

    def test_installer_generates_installation_id(self):
        """Installer must generate site.installation_id on first config creation."""
        sh = _sh()
        assert "generate_installation_id" in sh

    def test_installer_id_generation_guarded_by_new_config_only(self):
        """ID generation must be inside the 'config not found' block."""
        sh = _sh()
        # The generation should appear after the config copy, inside the
        # 'if [[ ! -f "${CONFIG_TARGET}" ]]' block
        not_found_block_start = sh.find('if [[ ! -f "${CONFIG_TARGET}" ]]')
        gen_pos = sh.find("generate_installation_id", not_found_block_start)
        assert gen_pos != -1 and gen_pos > not_found_block_start, (
            "generate_installation_id must be inside the 'config not found' block"
        )

    def test_installer_never_overwrites_existing_id(self):
        """sed substitution must target the empty placeholder, not any existing value."""
        sh = _sh()
        # In the shell script the sed pattern is: installation_id: \"\"
        # which matches only the empty placeholder from starter.yaml
        assert 'installation_id: \\"\\"\\"' in sh or 'installation_id: \\"\\"\\"' in sh or (
            "installation_id" in sh and '\\"\\"' in sh
        )


# ── check mode (dry-run) ─────────────────────────────────────────────────────

class TestCheckMode:

    def test_check_flag_defined(self):
        assert "--check" in _sh()

    def test_check_mode_variable(self):
        assert "CHECK_MODE" in _sh()

    def test_check_mode_exits_before_creating_files(self):
        """CHECK_MODE block must appear before the first directory creation."""
        sh = _sh()
        sh.find("CHECK_MODE") == "true"
        # CHECK_MODE guard should come before 'install -d' (directory creation)
        check_start = sh.find('if [[ "${CHECK_MODE}" == "true" ]]')
        dir_create   = sh.find("install -d")
        assert check_start < dir_create, (
            "CHECK_MODE guard must appear before first directory creation"
        )

    def test_check_mode_exits_non_zero_on_failure(self):
        sh = _sh()
        assert "_check_fails" in sh
        assert "exit" in sh

    def test_check_mode_outputs_pass_warn_fail_labels(self):
        sh = _sh()
        assert "[PASS]" in sh
        assert "[WARN]" in sh
        assert "[FAIL]" in sh

    def _check_block(self) -> str:
        """Extract the text of the CHECK_MODE=true block from install.sh."""
        sh = _sh()
        start = sh.find('if [[ "${CHECK_MODE}" == "true" ]]')
        assert start != -1, "CHECK_MODE block not found"
        # Block ends at the fi that closes it; find the sentinel comment after it
        sentinel = "# ── Create dedicated service user"
        end = sh.find(sentinel, start)
        assert end != -1
        return sh[start:end]

    def test_check_mode_checks_python_version(self):
        block = self._check_block()
        assert "PYTHON_VERSION" in block or "python3" in block

    def test_check_mode_checks_service_template(self):
        block = self._check_block()
        assert "SERVICE_TEMPLATE" in block

    def test_check_mode_reports_on_xhost(self):
        """xhost is what lets the 'khptz' service user reach the display.

        It is installed by scripts/repair_rpi_runtime.sh — from inside the
        wizard's provisioning chain, via apt. On an offline appliance that apt
        call fails, the chain reports "runtime finalization failed" and rolls
        back the config and both passwords the operator just typed. Readiness
        is the place to find out, before anything is written.
        """
        assert "xhost" in self._check_block()

    def test_xhost_finding_is_gui_mode_aware(self):
        """--gui-mode user never touches xhost; demanding it there would be a
        readiness failure for a capability that install does not use."""
        block = self._check_block()
        xhost_at = block.index("xhost")
        context = block[max(0, xhost_at - 900):xhost_at + 900]
        assert "GUI_MODE" in context

    def test_missing_xhost_without_apt_is_blocking(self):
        """No xhost and no way to get it means the GUI can never be displayed."""
        block = self._check_block()
        xhost_section = block[block.index("xhost"):]
        assert "_chk_fail" in xhost_section


# ── setup-wizard provisioning channel ─────────────────────────────────────────

class TestProvisioningChannel:
    """The installer must wire the password-free /run/khptz provisioning channel."""

    def test_provision_unit_templates_exist(self):
        assert PROVISION_SERVICE.exists()
        assert PROVISION_PATH.exists()

    def test_path_unit_watches_request_file(self):
        text = PROVISION_PATH.read_text(encoding="utf-8")
        assert "/run/khptz/request.json" in text
        assert "Unit=khptz-provision.service" in text

    def test_service_unit_runs_provision_entrypoint(self):
        text = PROVISION_SERVICE.read_text(encoding="utf-8")
        assert "runtime.provision" in text
        assert "Type=oneshot" in text

    def test_installer_copies_both_provision_units(self):
        sh = _sh()
        assert "/etc/systemd/system/khptz-provision.service" in sh
        assert "/etc/systemd/system/khptz-provision.path" in sh

    def test_installer_creates_run_khptz_tmpfiles(self):
        sh = _sh()
        assert "/etc/tmpfiles.d/khptz.conf" in sh
        # /run/khptz must be owned by the wizard user (write access to create
        # request.json), group root, 0750 — root:<user> would only give the
        # wizard r-x via the group and it could never write its own request.
        assert 'd /run/khptz 0750 %s root' in sh
        assert "systemd-tmpfiles --create" in sh

    def test_installer_enables_path_unit(self):
        assert "systemctl enable khptz-provision.path" in _sh()

    def test_wizard_user_defaults_to_sudo_user(self):
        sh = _sh()
        assert "--wizard-user" in sh
        assert 'WIZARD_USER="${WIZARD_USER:-${SUDO_USER:-}}"' in sh

    def test_channel_install_gated_on_product_mode(self):
        """The channel block must live inside a DEV_MODE==false guard."""
        sh = _sh()
        marker = "Installing setup-wizard provisioning channel"
        idx = sh.find(marker)
        assert idx != -1, "provisioning channel block not found"
        guard = sh.rfind('if [[ "${DEV_MODE}" == "false" ]]', 0, idx)
        assert guard != -1, "channel block is not gated on product mode"


# ── setup-wizard launcher + first-boot autostart ──────────────────────────────

class TestSetupWizardAutostart:
    """The installer must install the menu launcher and the first-boot autostart.

    They are deliberately two different .desktop files: the autostart entry
    must NOT pass --force (so it self-suppresses once provisioned), while the
    menu entry must always pass --force (so it can still reopen Repair after
    first-run setup completes) — see PR #867 review.
    """

    def test_setup_desktop_template_exists(self):
        assert SETUP_DESKTOP.exists()
        assert SETUP_MENU_DESKTOP.exists()

    def test_autostart_desktop_has_no_force(self):
        """Autostart entry must self-suppress once provisioned — no --force."""
        text = SETUP_DESKTOP.read_text(encoding="utf-8")
        exec_line = next(l for l in text.splitlines() if l.startswith("Exec="))
        assert exec_line == "Exec=khptz setup"
        assert "Type=Application" in text

    def test_menu_desktop_uses_force(self):
        """Menu entry must reopen Repair even when already provisioned."""
        text = SETUP_MENU_DESKTOP.read_text(encoding="utf-8")
        assert "Exec=khptz setup --force" in text
        assert "Type=Application" in text

    def test_installer_installs_menu_launcher_from_menu_template(self):
        sh = _sh()
        assert "/usr/share/applications/khptz-setup.desktop" in sh
        assert 'install -m 644 "${MENU_DESKTOP_TEMPLATE}"' in sh

    def test_installer_drops_autostart_from_plain_template(self):
        sh = _sh()
        assert ".config/autostart" in sh
        assert 'install -m 644 -o "${WIZARD_USER}" "${DESKTOP_TEMPLATE}"' in sh

    def test_autostart_owned_by_wizard_user(self):
        """The autostart drop must be chowned to the desktop (wizard) user."""
        sh = _sh()
        assert '-o "${WIZARD_USER}"' in sh

    def test_autostart_gated_on_product_mode(self):
        sh = _sh()
        marker = "Installing setup-wizard launcher"
        idx = sh.find(marker)
        assert idx != -1, "setup-wizard launcher block not found"
        guard = sh.rfind('if [[ "${DEV_MODE}" == "false" ]]', 0, idx)
        assert guard != -1, "launcher block is not gated on product mode"

    def test_wizard_user_added_to_app_group(self):
        """Desktop user must be added to the khptz group to read /opt/khptz code."""
        sh = _sh()
        assert 'usermod -aG "${APP_USER}" "${WIZARD_USER}"' in sh


# ── syntax ────────────────────────────────────────────────────────────────────

class TestShellSyntax:

    def test_bash_strict_mode_enabled(self):
        assert "set -euo pipefail" in _sh()

    def test_install_sh_exists(self):
        assert INSTALL_SH.exists()

    def test_service_file_exists(self):
        assert SERVICE_FILE.exists()

