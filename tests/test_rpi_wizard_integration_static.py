#!/usr/bin/env python3
"""Static contract for the integrated Raspberry Pi wizard provisioning flow."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_provision_service_uses_integration_wrapper():
    text = (ROOT / "runtime/systemd/hallptz-provision.service").read_text(encoding="utf-8")
    assert "provision_with_rpi_integration.sh" in text
    assert "runtime.provision" in text
    assert "EnvironmentFile=-/etc/hallptz/install-state.env" in text
    assert "LANG=C.UTF-8" in text


def test_product_display_gate_is_installed_without_breaking_dev_mode():
    service = (ROOT / "runtime/systemd/hallptz-control.service").read_text(encoding="utf-8")
    repair = (ROOT / "scripts/repair_rpi_runtime.sh").read_text(encoding="utf-8")
    assert "ConditionPathExists=/run/hallptz/display-ready" not in service
    assert "ConditionPathExists=/run/hallptz/display-ready" in repair
    assert "PrivateTmp=false" in service
    assert "PYTHONIOENCODING=utf-8" in service


def test_wrapper_always_removes_the_request_on_exit():
    """hallptz-provision.path triggers on PathExists=/run/hallptz/request.json and
    re-arms the moment the oneshot deactivates. A request that survives a
    failure therefore restarts the whole provisioning chain immediately and
    forever — and parks both plaintext passwords on tmpfs while it does.

    Two failure paths used to leave it behind: an undetectable wizard user, and
    a provisioner that died before reaching its own shred (an import error, a
    missing interpreter). The EXIT trap has to cover them.
    """
    text = (ROOT / "scripts/provision_with_rpi_integration.sh").read_text(encoding="utf-8")
    trap_at = text.index("trap finish EXIT")
    finish = text[text.index("finish() {"):trap_at]
    assert "secure_remove_request" in finish
    assert "publish_pending" in finish
    # The request must go first: publishing a failure result lets the wizard
    # retry, and a retry must not race a request the previous run left behind.
    assert finish.index("secure_remove_request") < finish.index("publish_pending")


def test_wrapper_exit_trap_cannot_mask_the_real_exit_status():
    """The trap runs under `set -e`; a failing cleanup must not become the
    reported outcome of provisioning."""
    text = (ROOT / "scripts/provision_with_rpi_integration.sh").read_text(encoding="utf-8")
    finish = text[text.index("finish() {"):text.index("trap finish EXIT")]
    assert finish.count("|| true") >= 2


def test_repair_keeps_runtime_dirs_writable_for_a_session_owned_gui():
    """repair_rpi_runtime.sh is the LAST writer of these modes in the wizard
    chain, after install.sh and runtime/provision.py have both set 2770 for a
    --gui-mode user install. A flat `install -d -m 0750` here silently undid
    both (install(1) applies the numeric mode with chmod(), which clears the
    setgid bit), leaving the session GUI unable to save presets, layout or logs
    on an install that reported success.
    """
    text = (ROOT / "scripts/repair_rpi_runtime.sh").read_text(encoding="utf-8")
    assert 'RUNTIME_DIR_MODE="2770"' in text
    assert 'RUNTIME_DIR_MODE="0750"' in text
    for path in ("/var/lib/hallptz", "/var/log/hallptz", "/var/backups/hallptz"):
        assert f'install -d -m "${{RUNTIME_DIR_MODE}}" -o hallptz -g hallptz {path}\n' in text, path
    # No hard-coded 0750 may remain on a shared runtime directory.
    for path in ("/var/lib/hallptz", "/var/log/hallptz"):
        assert f"install -d -m 0750 -o hallptz -g hallptz {path}" not in text, path


def test_repair_only_reaches_for_apt_when_xhost_is_actually_used():
    """Under --gui-mode user the session owns its own display and xhost is
    never called. Installing it anyway means an apt-get on an appliance that
    may have no network — and a failure there aborts the wizard and rolls the
    customer's configuration back."""
    text = (ROOT / "scripts/repair_rpi_runtime.sh").read_text(encoding="utf-8")
    guard = text.index("command -v xhost")
    assert 'GUI_MODE' in text[guard - 200:guard + 80]


def test_wrapper_calls_both_standalone_migrations_before_publishing_result():
    text = (ROOT / "scripts/provision_with_rpi_integration.sh").read_text(encoding="utf-8")
    repair_at = text.index("repair_rpi_runtime.sh")
    cleanup_at = text.index("cleanup_legacy_rpi_autostart.sh")
    publish_at = text.rindex("publish_pending")
    assert repair_at < cleanup_at < publish_at
    assert "runtime.rpi_post_provision" in text
    assert ".rpi-integrated" in text
    assert "ROLLBACK_TARGETS" in text
    assert "restore_snapshot" in text


def _shell_block(text: str, opener: str) -> str:
    """Return the body of the shell function starting at *opener*.

    A helper rather than an inline slice because every test below needs the
    same "from this line to the closing brace at column 0" cut.
    """
    start = text.index(opener)
    return text[start:text.index("\n}\n", start)]


def test_a_fatal_diagnosis_keeps_the_customer_configuration():
    """A `hallptz doctor` FAIL at the end of provisioning must not discard the
    wizard answers.

    The chain treats any non-zero exit from repair_rpi_runtime.sh as
    "integration failed" and calls restore_snapshot, which deletes config.yaml,
    both password secrets and both markers. That is right for a half-applied
    integration. It is wrong for this: every OS step succeeded, the written
    configuration is exactly what was asked for, and what failed is a health
    verdict about the ENVIRONMENT - an unreachable camera, a missing
    permission. Rolling back made the operator retype two passwords and every
    camera address to reach the identical verdict, at the end of a wizard that
    had looked successful.
    """
    repair = (ROOT / "scripts/repair_rpi_runtime.sh").read_text(encoding="utf-8")
    chain = (ROOT / "scripts/provision_with_rpi_integration.sh").read_text(encoding="utf-8")

    # Both sides must agree on the code, and it must not be the generic 1.
    assert "readonly RC_DIAGNOSTICS_FATAL=40" in repair
    assert "readonly RC_DIAGNOSTICS_FATAL=40" in chain
    assert 'exit "${RC_DIAGNOSTICS_FATAL}"' in repair

    # The branch that handles it must not roll back.
    start = chain.index("if [[ ${repair_rc} -eq ${RC_DIAGNOSTICS_FATAL} ]]")
    # Cut at the elif: this is the diagnostics-fatal branch only, not the
    # generic failure branch after it, which SHOULD still roll back.
    branch = chain[start:chain.index("\nelif ", start)]
    assert "write_unhealthy_result" in branch
    assert "restore_snapshot" not in branch
    assert "write_integration_failure" not in branch


def test_the_unhealthy_result_tells_the_operator_their_settings_survived():
    """"Setup failed" plus a silently preserved config is the worst of both
    worlds: the operator cannot tell whether to start over."""
    chain = (ROOT / "scripts/provision_with_rpi_integration.sh").read_text(encoding="utf-8")
    helper = _shell_block(chain, "write_unhealthy_result() {")
    assert '"rolled_back": False' in helper
    assert '"configuration_kept": True' in helper
    assert "hallptz doctor" in helper


def test_a_genuine_integration_failure_still_rolls_back():
    """The safety this narrows must still exist for the case it was built for."""
    chain = (ROOT / "scripts/provision_with_rpi_integration.sh").read_text(encoding="utf-8")
    assert 'write_integration_failure "runtime finalization failed"' in chain
    assert 'write_integration_failure "legacy autostart migration failed"' in chain
    assert "restore_snapshot" in _shell_block(chain, "write_integration_failure() {")


def test_a_killed_provisioner_still_answers_the_wizard():
    """hallptz-provision.service sets TimeoutStartSec=600 and the wizard polls to
    660. Bash does not run an EXIT trap for an unhandled SIGTERM, so a timeout
    killed the script leaving request.json - with both plaintext passwords - on
    tmpfs and no result at all. The wizard then span until its own deadline and
    reported a meaningless "did not finish in time"."""
    chain = (ROOT / "scripts/provision_with_rpi_integration.sh").read_text(encoding="utf-8")
    for signal in ("TERM", "INT", "HUP"):
        assert "trap 'on_signal %s' %s" % (signal, signal) in chain
    handler = _shell_block(chain, "on_signal() {")
    assert "PENDING" in handler
    assert "interrupted" in handler.lower()


def test_the_shredder_is_defined_before_the_trap_that_calls_it():
    """A function the trap cannot resolve fails silently through its `|| true`,
    leaving the plaintext-password request on tmpfs exactly when a crash or a
    systemd timeout makes removing it matter most."""
    chain = (ROOT / "scripts/provision_with_rpi_integration.sh").read_text(encoding="utf-8")
    assert chain.index("secure_remove_request() {") < chain.index("finish() {")
    assert chain.index("publish_pending() {") < chain.index("finish() {")


def test_the_migration_never_kills_the_gui_it_installed():
    """Under --gui-mode user the supported GUI runs as the DESKTOP user with
    the command line "/usr/bin/python3 /opt/hallptz/main.py" - which the conflict
    scan matches on purpose, because a hand-rolled desktop launcher of that
    same command IS a second instance. The cgroup is what tells them apart."""
    cleanup = (ROOT / "scripts/cleanup_legacy_rpi_autostart.sh").read_text(encoding="utf-8")
    assert "_pid_is_hallptz_managed" in cleanup
    assert "hallptz-gui.service" in cleanup
    assert "/proc/${pid}/cgroup" in cleanup
    stop = _shell_block(cleanup, "stop_conflicts() {")
    # The guard has to run before the PID is queued for killing.
    assert stop.index("_pid_is_hallptz_managed") < stop.index("pids+=(")


def test_an_interrupted_provisioning_rolls_back():
    """A signal can land anywhere: mid-write in runtime.provision, between
    config.yaml and the two secrets, or half-way through OS integration.
    systemd kills the whole cgroup, so the Python provisioner dies without
    running its own rollback and an install can be left with the NEW
    config.yaml and the OLD (or no) password secrets - locking the operator out
    of an appliance that reports nothing wrong.

    Every other failure path here restores the snapshot. An interruption is the
    case where the on-disk state is least knowable, so it is the last place to
    skip it."""
    chain = (ROOT / "scripts/provision_with_rpi_integration.sh").read_text(encoding="utf-8")
    handler = _shell_block(chain, "on_signal() {")
    assert "restore_snapshot" in handler
    # Guarded on the variable, not on the function: a signal arriving before
    # snapshot_state ran has nothing to restore.
    assert "snapshot_taken" in handler
    assert handler.index("snapshot_taken") < handler.index("restore_snapshot")
    # And the result must say which way it went, or the operator cannot tell
    # whether their answers survived.
    assert "rolled_back" in handler


def test_the_display_chain_is_only_installed_where_it_is_used():
    """It bridges the 'hallptz' service user to the desktop display, which only
    exists in system GUI mode."""
    repair = (ROOT / "scripts/repair_rpi_runtime.sh").read_text(encoding="utf-8")
    guard = repair.index('if [[ "${GUI_MODE}" != "user" ]]; then\ninstall -d -m 0755 /usr/local/libexec')
    installs = repair.index('cat > "${DISPLAY_HELPER}"')
    assert guard < installs
    assert repair.index("hallptz-display-session.desktop", guard) > guard


def test_user_mode_tears_the_display_chain_down():
    """`systemctl disable` is not `mask`: the helper writing
    /run/hallptz/display-ready triggers hallptz-display-ready.service, whose ExecStart
    is `systemctl restart hallptz-control.service` - and restart STARTS a
    merely-disabled unit. On a machine switched from system to user mode those
    leftovers put hallptz-control back on screen next to hallptz-gui.service: two
    full-screen GUIs driving the same cameras, re-armed by the very step meant
    to prevent it (#885)."""
    repair = (ROOT / "scripts/repair_rpi_runtime.sh").read_text(encoding="utf-8")
    teardown = repair[repair.index("GUI mode 'user': removing the display-ready chain"):]
    teardown = teardown[:teardown.index("\nfi\n")]

    # The path unit must be actively disabled, not just left unenabled.
    assert "systemctl disable --now" in teardown
    assert "hallptz-display-ready.path" in teardown
    assert "hallptz-display-ready.service" in teardown

    # And every artifact that could re-arm it has to go.
    for artifact in (
        "${DISPLAY_HELPER}",
        "${DISPLAY_PATH_UNIT}",
        "${DISPLAY_SERVICE_UNIT}",
        "${SERVICE_DROPIN}",
        "hallptz-display-session.desktop",
    ):
        assert artifact in teardown, artifact
    assert "rm -f --" in teardown


def test_the_teardown_is_reversible():
    """Switching back to system mode must re-create everything, so the removal
    is a mode switch rather than a one-way door. Every removed path is also
    backed up by backup_path before anything is touched."""
    repair = (ROOT / "scripts/repair_rpi_runtime.sh").read_text(encoding="utf-8")
    backup_section = repair[repair.index("Backing up replaced OS files"):]
    backup_section = backup_section[:backup_section.index("backup_path \"${path}\"")]
    for artifact in ("${DISPLAY_HELPER}", "${DISPLAY_PATH_UNIT}",
                     "${DISPLAY_SERVICE_UNIT}", "${SERVICE_DROPIN}"):
        assert artifact in backup_section, artifact
    assert "hallptz-display-session.desktop" in backup_section

