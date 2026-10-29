#!/usr/bin/env bash
# Complete wizard provisioning, then apply Raspberry Pi runtime integration before
# publishing result.json back to the unprivileged setup wizard.
set -Eeuo pipefail
IFS=$'\n\t'

readonly REQUEST="/run/khptz/request.json"
readonly RESULT="/run/khptz/result.json"
readonly PENDING="/run/khptz/result.pending.json"
readonly ADVISORIES="/run/khptz/rpi-advisories.json"
readonly PROVISIONED_MARKER="/etc/khptz/.provisioned"
readonly INTEGRATION_MARKER="/etc/khptz/.rpi-integrated"
readonly APP_ROOT="/opt/khptz"
readonly DISPLAY_VALUE="${KHPTZ_DISPLAY:-:0}"
# Assigned separately from `readonly` so a failing date is not masked (SC2155).
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
readonly TIMESTAMP
readonly ROLLBACK_DIR="/var/backups/khptz/wizard-integration-${TIMESTAMP}"

# Exit code scripts/repair_rpi_runtime.sh uses for "every OS step succeeded
# and the configuration is applied, but `khptz doctor` says the appliance is
# not healthy". Distinct from a generic failure so this script can keep the
# customer's configuration instead of rolling it back. Kept in sync there.
readonly RC_DIAGNOSTICS_FATAL=40

ROLLBACK_TARGETS=(
    "/etc/khptz/config.yaml"
    "/var/lib/khptz/password.enc"
    "/var/lib/khptz/admin.enc"
    "${PROVISIONED_MARKER}"
    "${INTEGRATION_MARKER}"
)
published=false
snapshot_taken=false

log() { printf '[khptz-provision] %s\n' "$*"; }

publish_pending() {
    if [[ "${published}" != "true" && -f "${PENDING}" ]]; then
        mv -f -- "${PENDING}" "${RESULT}"
        chmod 0644 "${RESULT}" 2>/dev/null || true
        published=true
    fi
}

# Defined ABOVE the EXIT/signal traps on purpose: `finish` calls it, and a
# function the trap cannot resolve fails silently through its `|| true`,
# leaving the plaintext-password request on tmpfs exactly when a crash or a
# systemd timeout makes removing it matter most.
secure_remove_request() {
    python3 - "${REQUEST}" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    size = path.stat().st_size
    with path.open("r+b", buffering=0) as handle:
        handle.write(b"\0" * max(size, 1))
        handle.flush()
        os.fsync(handle.fileno())
except OSError:
    pass
try:
    path.unlink()
except OSError:
    pass
PY
}

# Two things must be true however this script exits, or the appliance is left in
# a state the operator cannot recover from:
#
#   1. request.json must be gone. khptz-provision.path triggers on
#      PathExists=/run/khptz/request.json and re-arms as soon as the oneshot
#      deactivates, so a request that survives a failure restarts this script
#      immediately, forever. Two paths used to leave it behind — an
#      undetectable wizard user, and a provisioner that died before its own
#      shred (an import error, a missing interpreter) — and both also parked
#      BOTH plaintext passwords on tmpfs indefinitely, which is exactly what
#      the shred exists to prevent.
#   2. the pending result must be published, so the wizard sees an answer
#      instead of polling until its own timeout.
#
# Order matters: remove the request first, so the wizard cannot read a failure
# result and immediately retry into a run that is still racing the old request.
#
# Both steps are best-effort: this runs under `set -e` from an EXIT trap, so a
# failure here (no python3, a read-only /run) must not replace the real exit
# status with a confusing one.
finish() {
    secure_remove_request || true
    publish_pending || true
}
trap finish EXIT

# EXIT alone is not enough. khptz-provision.service sets
# TimeoutStartSec=600; when systemd hits it, it sends SIGTERM - and bash
# does NOT run an EXIT trap for a signal it has no handler for. The script
# would die leaving request.json (with both plaintext passwords) on tmpfs
# and no result for the wizard, which then polls uselessly to its own
# 660-second timeout and reports a meaningless "did not finish in time".
# Handling the signals turns that into a real, immediate answer.
on_signal() {
    local signal="$1"
    local rolled_back="false"
    log "Received SIG${signal} - provisioning was cut short."

    # A signal can land anywhere: mid-write in runtime.provision, between
    # config.yaml and the two secrets, or half-way through the OS
    # integration. systemd kills the whole cgroup, so the Python
    # provisioner dies without running its own rollback - an install can be
    # left with the NEW config.yaml and the OLD (or no) password secrets,
    # which locks the operator out of an appliance that reports nothing
    # wrong. Every other failure path in this script restores the snapshot;
    # an interruption is the one case where the state is least knowable, so
    # it is the last place to skip it. Nothing to restore on a fresh
    # install: the snapshot recorded absence, so this just clears the
    # partial writes and the wizard reopens at the next login.
    if [[ "${snapshot_taken}" == "true" ]]; then
        log "Restoring the previous configuration before exiting."
        restore_snapshot || log "Snapshot restore did not complete cleanly."
        rolled_back="true"
    fi

    # rolled_back is what tells the operator whether to expect their answers
    # to still be there. Saying nothing is worse than either answer.
    printf '{"ok":false,"rolled_back":%s,"error":"Setup was interrupted (SIG%s) before it finished. Nothing was applied - open KHPTZ Setup again to retry."}' "${rolled_back}" "${signal}" > "${PENDING}"
    exit 143
}
trap 'on_signal TERM' TERM
trap 'on_signal INT' INT
trap 'on_signal HUP' HUP

wizard_user_from_state() {
    local state="/etc/khptz/install-state.env"
    [[ -r "${state}" ]] || return 1
    sed -n 's/^KHPTZ_WIZARD_USER="\{0,1\}\([^"[:space:]]*\)"\{0,1\}$/\1/p' \
        "${state}" | tail -n1
}

detect_wizard_user() {
    local candidate="${KHPTZ_WIZARD_USER:-}"
    [[ -n "${candidate}" ]] || candidate="$(wizard_user_from_state || true)"
    if [[ -z "${candidate}" && -d /run/khptz ]]; then
        candidate="$(stat -c '%U' /run/khptz 2>/dev/null || true)"
    fi
    [[ -n "${candidate}" && "${candidate}" != "root" && "${candidate}" != "khptz" ]] \
        || return 1
    id "${candidate}" >/dev/null 2>&1 || return 1
    printf '%s\n' "${candidate}"
}

validate_request_for_rpi() {
    python3 - "${REQUEST}" "${PENDING}" <<'PY'
import json
import sys
from pathlib import Path

request = Path(sys.argv[1])
result = Path(sys.argv[2])
try:
    data = json.loads(request.read_text(encoding="utf-8"))
except Exception as exc:
    result.write_text(json.dumps({
        "ok": False,
        "error": f"Invalid setup request: {exc}",
    }), encoding="utf-8")
    raise SystemExit(1)

if bool(data.get("atem_enabled")) and not str(data.get("atem_ip") or "").strip():
    result.write_text(json.dumps({
        "ok": False,
        "issues": [{
            "field": "atem_ip",
            "message": "ATEM is enabled but its IP address is empty.",
        }],
    }), encoding="utf-8")
    raise SystemExit(1)
raise SystemExit(0)
PY
}

snapshot_state() {
    install -d -m 0700 -o root -g root "${ROLLBACK_DIR}"
    local target
    for target in "${ROLLBACK_TARGETS[@]}"; do
        if [[ -e "${target}" || -L "${target}" ]]; then
            cp -a --parents -- "${target}" "${ROLLBACK_DIR}/"
        fi
    done
    snapshot_taken=true
}

restore_snapshot() {
    [[ "${snapshot_taken}" == "true" ]] || return 0
    local target backup
    for target in "${ROLLBACK_TARGETS[@]}"; do
        backup="${ROLLBACK_DIR}${target}"
        rm -f -- "${target}"
        if [[ -e "${backup}" || -L "${backup}" ]]; then
            mkdir -p -- "$(dirname "${target}")"
            cp -a -- "${backup}" "${target}"
        fi
    done
    systemctl daemon-reload >/dev/null 2>&1 || true
}

# Report an applied-but-unhealthy install. Deliberately does NOT roll back.
#
# The mirror image of write_integration_failure: there, provisioning itself
# broke and the previous working state is the safest place to land. Here the
# configuration is exactly what the operator asked for and is already on disk -
# only the health verdict failed. Deleting a correct config.yaml and both
# password secrets over an unreachable camera would force a full re-run of the
# wizard to reach the identical verdict.
#
# rolled_back:false is explicit so the wizard can say "your settings were kept"
# rather than leaving the operator guessing what survived.
write_unhealthy_result() {
    python3 - "${PENDING}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
except Exception:
    data = {}
data.update({
    "ok": False,
    "error": (
        "Your settings were saved, but this device is not healthy yet. "
        "Run 'khptz doctor' to see what is wrong, fix it, then open KHPTZ Setup "
        "again - you will not have to re-enter anything."
    ),
    "rpi_integration": False,
    "rolled_back": False,
    "configuration_kept": True,
})
path.write_text(json.dumps(data), encoding="utf-8")
PY
    chmod 0644 "${PENDING}" 2>/dev/null || true
}

write_integration_failure() {
    local message="$1"
    restore_snapshot
    python3 - "${PENDING}" "${message}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
message = sys.argv[2]
try:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
except Exception:
    data = {}
data.update({
    "ok": False,
    "error": f"Raspberry Pi integration failed: {message}",
    "rpi_integration": False,
    "rolled_back": True,
})
path.write_text(json.dumps(data), encoding="utf-8")
PY
    chmod 0644 "${PENDING}" 2>/dev/null || true
    systemctl stop khptz-control.service >/dev/null 2>&1 || true
}

result_is_ok() {
    python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path
try:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if data.get("ok") is True else 1)
PY
}

augment_success_result() {
    python3 - "${PENDING}" "${ADVISORIES}" <<'PY'
import json
import sys
from pathlib import Path

result_path = Path(sys.argv[1])
advisory_path = Path(sys.argv[2])
data = json.loads(result_path.read_text(encoding="utf-8"))
advisories = []
if advisory_path.exists():
    try:
        advisories = json.loads(
            advisory_path.read_text(encoding="utf-8")
        ).get("advisories", [])
    except Exception:
        advisories = []
data["rpi_integration"] = True
data["advisories"] = advisories
result_path.write_text(json.dumps(data), encoding="utf-8")
PY
}

rm -f -- "${PENDING}" "${RESULT}" "${ADVISORIES}"

WIZARD_USER="$(detect_wizard_user)" || {
    printf '{"ok":false,"error":"Could not determine the desktop wizard user."}' \
        > "${PENDING}"
    exit 1
}
log "Desktop user: ${WIZARD_USER}; display: ${DISPLAY_VALUE}"

if ! validate_request_for_rpi; then
    secure_remove_request
    chmod 0644 "${PENDING}" 2>/dev/null || true
    exit 1
fi

snapshot_state

set +e
/usr/bin/python3 -m runtime.provision \
    --request "${REQUEST}" \
    --result "${PENDING}"
provision_rc=$?
set -e

if [[ ! -f "${PENDING}" ]]; then
    printf '{"ok":false,"error":"Provisioner did not produce a result."}' \
        > "${PENDING}"
    restore_snapshot
    exit 1
fi
if [[ ${provision_rc} -ne 0 ]] || ! result_is_ok "${PENDING}"; then
    log "Core provisioning failed; Raspberry Pi integration was not applied."
    exit "${provision_rc:-1}"
fi

if ! /usr/bin/python3 -m runtime.rpi_post_provision \
    --config /etc/khptz/config.yaml \
    --advisories "${ADVISORIES}"; then
    write_integration_failure "configuration normalization or ATEM validation failed"
    exit 1
fi

set +e
/bin/bash "${APP_ROOT}/scripts/repair_rpi_runtime.sh" \
    --wizard-user "${WIZARD_USER}" \
    --display "${DISPLAY_VALUE}"
repair_rc=$?
set -e

if [[ ${repair_rc} -eq ${RC_DIAGNOSTICS_FATAL} ]]; then
    # Runtime finalisation applied every OS step successfully; `khptz doctor`
    # then reported the appliance as unhealthy. That is a verdict about the
    # ENVIRONMENT, not about the answers the operator typed, so rolling back
    # here would delete a correct config.yaml and both password secrets and
    # make them redo the entire wizard to reach the same verdict. Keep the
    # configuration, report the failure, and let them retry after fixing the
    # environment - the .rpi-integrated marker is not written, so the wizard
    # reopens at the next desktop login.
    write_unhealthy_result
    exit "${repair_rc}"
elif [[ ${repair_rc} -ne 0 ]]; then
    write_integration_failure "runtime finalization failed"
    exit 1
fi

if ! /bin/bash "${APP_ROOT}/scripts/cleanup_legacy_rpi_autostart.sh" \
    --wizard-user "${WIZARD_USER}" \
    --display "${DISPLAY_VALUE}"; then
    write_integration_failure "legacy autostart migration failed"
    exit 1
fi

install -m 0644 /dev/null "${INTEGRATION_MARKER}"
printf 'ok\n' > "${INTEGRATION_MARKER}"
augment_success_result
publish_pending
# Disarm every trap together. Leaving the signal handlers armed past this
# point would let a stray SIGTERM during teardown overwrite a published
# success with an "interrupted" result the operator cannot explain.
trap - EXIT TERM INT HUP
log "Core provisioning and Raspberry Pi integration completed."
