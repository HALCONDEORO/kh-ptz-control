"""Run real copy/trap shell branches with scratch data and inert host commands.

This is not a full installation rehearsal, real rsync, filesystem ENOSPC, or
systemd validation. It documents the best-effort availability boundary, not an
atomic rollback guarantee. No root, packages, network or appliance paths.
"""
from pathlib import Path
import os
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "runtime/installer/install.sh").read_text()
TRAP = SOURCE[SOURCE.index("_restart_stopped_service_on_abort() {"):
              SOURCE.index("warn()", SOURCE.index("_restart_stopped_service_on_abort() {"))]
COPY = SOURCE[SOURCE.index("RSYNC_EXCLUDES=("):
              SOURCE.index('if [[ "${DEV_MODE}" == "false" ]]; then\n    # App code:')]


def run_copy(tmp_path, *, active=True, gui="system", stop_rc=0, copy_rc=0, restart_rc=0,
             dev=False, same_tree=False):
    source = tmp_path / "release"
    target = source if same_tree else tmp_path / "installed"
    source.mkdir()
    target.mkdir(exist_ok=True)
    (source / "module.py").write_text("new-release\n")
    (target / "module.py").write_text("old-release\n")
    config = tmp_path / "customer-config"
    config.write_text("synthetic-config-unchanged\n")
    events = tmp_path / "events"
    events.write_text("")
    script = r'''
set -euo pipefail
info() { echo "$*"; }
for forbidden in sudo useradd chown chmod find cp rm curl wget ssh; do
    eval "$forbidden() { echo FORBIDDEN_HOST_COMMAND >&2; return 98; }"
done
install() {
    # Runtime mkdir now follows the quiesce guard. Only these inert scratch
    # targets are allowed here; directory-mode behavior has its own real test.
    [[ "$*" == "-d -m 750 -o synthetic -g synthetic $DATA_DIR" ||
       "$*" == "-d -m 750 -o synthetic -g synthetic $LOG_DIR" ||
       "$*" == "-d -m 750 -o synthetic -g synthetic $BACKUP_DIR" ]] || return 98
}
systemctl() {
    # This harness covers system-service recovery, not live user managers.
    # The dedicated quiesce tests exercise enumeration and user stop failures.
    [[ "$1" != "list-units" ]] || return 0
    printf 'systemctl:%s\n' "$*" >> "$EVENTS"
    case "$1" in
        is-active) [[ "$ACTIVE" == 1 ]] ;;
        stop) return "$STOP_RC" ;;
        start) return "$RESTART_RC" ;;
        *) echo UNEXPECTED_SYSTEMCTL >&2; return 99 ;;
    esac
}
rsync() {
    printf 'rsync:%s\n' "$*" >> "$EVENTS"
    # Model a copy that changed some bytes before returning an rsync error.
    # This is deliberately not a real ENOSPC or an actual interrupted process.
    printf 'partial-new-release\n' > "$INSTALL_DIR/module.py"
    if [[ "$COPY_RC" != 0 ]]; then
        echo "SYNTHETIC rsync error $COPY_RC" >&2
        return "$COPY_RC"
    fi
}
''' + TRAP + '\n' + COPY.replace('_stop_session_guis /run/user',
        '_stop_session_guis "$REPO_ROOT/no-user-managers"') + r'''
printf 'AFTER_COPY\n' >> "$EVENTS"
# The full installer disarms the abort trap after its planned service restart.
# This copy-only harness ends here; do not pretend that later installation ran.
trap - EXIT
'''
    # The pre-update backup block lives in the extracted window; the real
    # installer always defines CONFIG_DIR. Point it at a path without an
    # install-state.env so the block evaluates its gate and skips, as on a
    # first install.
    env = dict(os.environ, REPO_ROOT=str(source), INSTALL_DIR=str(target),
               CONFIG_DIR=str(tmp_path / "config-dir"),
               DEV_MODE="true" if dev else "false", GUI_MODE=gui,
               SERVICE_NAME="synthetic-khptz-service", EVENTS=str(events),
               APP_USER="synthetic", DATA_DIR=str(tmp_path / "data"),
               LOG_DIR=str(tmp_path / "log"), BACKUP_DIR=str(tmp_path / "backup"),
               ACTIVE="1" if active else "0", STOP_RC=str(stop_rc),
               COPY_RC=str(copy_rc), RESTART_RC=str(restart_rc))
    result = subprocess.run(["bash", "-c", script], env=env,
                            capture_output=True, text=True, timeout=10)
    assert "FORBIDDEN_HOST_COMMAND" not in result.stderr
    assert config.read_text() == "synthetic-config-unchanged\n"
    return result, events.read_text().splitlines(), target


@pytest.mark.parametrize("copy_rc", [11, 20, 23])
def test_failed_copy_preserves_primary_status_and_attempts_restart(tmp_path, copy_rc):
    result, events, target = run_copy(tmp_path, copy_rc=copy_rc)
    assert result.returncode == copy_rc
    assert events[0] == "systemctl:is-active --quiet synthetic-khptz-service"
    assert events[1] == "systemctl:stop synthetic-khptz-service"
    assert events[2].startswith("rsync:-a --delete ")
    assert events[3:] == ["systemctl:start synthetic-khptz-service"]
    assert f"SYNTHETIC rsync error {copy_rc}" in result.stderr
    assert f"install failed (exit {copy_rc})" in result.stderr
    # Restart is only an availability attempt. It cannot undo the partial copy.
    assert target.joinpath("module.py").read_text() == "partial-new-release\n"
    assert "AFTER_COPY" not in events


def test_failed_restart_is_visible_but_does_not_replace_copy_error(tmp_path):
    result, events, _ = run_copy(tmp_path, copy_rc=23, restart_rc=5)
    assert result.returncode == 23
    assert "SYNTHETIC rsync error 23" in result.stderr
    assert "restart FAILED" in result.stderr
    assert events.count("systemctl:start synthetic-khptz-service") == 1
    assert "AFTER_COPY" not in events


def test_failed_stop_aborts_before_copy_without_false_restart(tmp_path):
    result, events, target = run_copy(tmp_path, stop_rc=5)
    assert result.returncode == 5
    assert events == ["systemctl:is-active --quiet synthetic-khptz-service",
                      "systemctl:stop synthetic-khptz-service"]
    assert target.joinpath("module.py").read_text() == "old-release\n"


def test_previously_inactive_service_is_not_started_on_copy_failure(tmp_path):
    result, events, _ = run_copy(tmp_path, active=False, copy_rc=11)
    assert result.returncode == 11
    assert not any(e.startswith("systemctl:start") or e.startswith("systemctl:stop") for e in events)
    assert "AFTER_COPY" not in events


def test_user_gui_never_starts_system_gui_on_abort(tmp_path):
    result, events, _ = run_copy(tmp_path, gui="user", copy_rc=23)
    assert result.returncode == 23
    assert "systemctl:start synthetic-khptz-service" not in events
    assert "AFTER_COPY" not in events


def test_developer_copy_never_deletes_or_operates_system_service(tmp_path):
    result, events, _ = run_copy(tmp_path, dev=True, copy_rc=23)
    assert result.returncode == 23
    assert len(events) == 1 and events[0].startswith("rsync:-a ")
    assert "--delete" not in events[0]


def test_same_source_destination_does_not_copy_or_stop(tmp_path):
    result, events, _ = run_copy(tmp_path, same_tree=True)
    assert result.returncode == 0
    assert events == ["AFTER_COPY"]


def test_successful_copy_does_not_take_abort_recovery_path(tmp_path):
    result, events, _ = run_copy(tmp_path)
    assert result.returncode == 0
    assert events[-1] == "AFTER_COPY"
    assert "systemctl:start synthetic-khptz-service" not in events
    assert "install failed" not in result.stderr
