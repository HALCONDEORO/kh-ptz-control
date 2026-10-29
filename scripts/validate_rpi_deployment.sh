#!/usr/bin/env bash
# Hall PTZ Control - Raspberry Pi deployment validation (read-only)
#
# Captures the evidence required to close #890 and #892 on the physical
# appliance. It NEVER changes the system: it only reads unit files, autostart
# entries and running processes, runs the diagnostics CLI, and runs the legacy
# cleanup in --dry-run so any remaining conflicting startup is reported without
# being altered.
#
# Run it twice, once per reboot, so the "after two reboots" criterion in #892
# can be checked from the saved reports:
#
#   sudo bash scripts/validate_rpi_deployment.sh --wizard-user isl
#
# Output goes to the terminal and to a timestamped report under
# /var/log/hallptz/validation/ (falls back to the invoking user's home when that
# directory is not writable, so read-only diagnostics never abort — see #884).

set -Eeuo pipefail
IFS=$'\n\t'

readonly SCRIPT_VERSION="1"
readonly SERVICE="hallptz-control.service"
readonly CLEANUP="scripts/cleanup_legacy_rpi_autostart.sh"

DESKTOP_USER="${SUDO_USER:-}"
TARGET_DISPLAY="${DISPLAY:-:0}"
EXTRA_PATTERN=""
FAILURES=0
WARNINGS=0

# Force UTF-8-safe output regardless of the desktop terminal locale (#884): a
# stray non-ASCII glyph must never abort validation.
export PYTHONIOENCODING="utf-8"
export PYTHONUTF8="1"

info() { printf '[INFO]  %s\n' "$*"; }
ok()   { printf '[ OK ]  %s\n' "$*"; }
warn() { printf '[WARN]  %s\n' "$*" >&2; ((WARNINGS += 1)); }
bad()  { printf '[FAIL]  %s\n' "$*" >&2; ((FAILURES += 1)); }
fail() { printf '[ERROR] %s\n' "$*" >&2; exit 2; }

usage() {
    cat <<'USAGE'
Usage: sudo bash scripts/validate_rpi_deployment.sh [options]

Read-only validation for #890/#892. Changes nothing on the appliance.

Options:
  --wizard-user USER      Human desktop user. Defaults to the user invoking sudo.
  --display DISPLAY       X11 display. Defaults to current DISPLAY or :0.
  --legacy-pattern REGEX  Extra regex forwarded to the cleanup dry-run.
  -h, --help              Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --wizard-user) [[ $# -ge 2 ]] || fail "--wizard-user requires a value"; DESKTOP_USER="$2"; shift 2 ;;
        --display) [[ $# -ge 2 ]] || fail "--display requires a value"; TARGET_DISPLAY="$2"; shift 2 ;;
        --legacy-pattern) [[ $# -ge 2 ]] || fail "--legacy-pattern requires a value"; EXTRA_PATTERN="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown option: $1" ;;
    esac
done

[[ "$(id -u)" -eq 0 ]] || fail "Run this script with sudo."
[[ -n "${DESKTOP_USER}" ]] || fail "Could not detect the desktop user. Use --wizard-user USER."
id "${DESKTOP_USER}" >/dev/null 2>&1 || fail "User does not exist: ${DESKTOP_USER}"

# Resolve the repository root from this script's location so it works from any
# working directory (#883).
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd)"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="/var/log/hallptz/validation"
if ! ( install -d -m 0755 "${LOG_DIR}" >/dev/null 2>&1 && [[ -w "${LOG_DIR}" ]] ); then
    HOME_DIR="$(getent passwd "${DESKTOP_USER}" | cut -d: -f6)"
    LOG_DIR="${HOME_DIR:-/tmp}/hallptz-validation"
    install -d -m 0755 "${LOG_DIR}" >/dev/null 2>&1 || LOG_DIR="/tmp"
fi
REPORT="${LOG_DIR}/validation-${TIMESTAMP}.txt"

# Mirror everything to the report file as well as the terminal.
exec > >(tee -a "${REPORT}") 2>&1

# ── Which hallptz entry point to use (installed wrapper, else module) ────────────
if command -v hallptz >/dev/null 2>&1; then
    HALLPTZ=(hallptz)
elif [[ -f "${REPO_ROOT}/runtime/cli.py" ]]; then
    HALLPTZ=(python3 -m runtime.cli)
else
    HALLPTZ=()
fi

run_hallptz() {
    # Run a hallptz subcommand read-only; never let its exit status abort us.
    if [[ ${#HALLPTZ[@]} -eq 0 ]]; then
        warn "hallptz CLI not found; skipped: $*"
        return 0
    fi
    ( cd "${REPO_ROOT}" && "${HALLPTZ[@]}" "$@" ) || warn "hallptz $* exited non-zero (see output above)"
}

capture_hallptz() {
    # Like run_hallptz but echoes the combined output so a caller can both display
    # and inspect it. Never aborts on a non-zero exit.
    if [[ ${#HALLPTZ[@]} -eq 0 ]]; then
        warn "hallptz CLI not found; skipped: $*" >&2
        return 0
    fi
    ( cd "${REPO_ROOT}" && "${HALLPTZ[@]}" "$@" 2>&1 ) || true
}

section() { printf '\n===== %s =====\n' "$*"; }

info "HALLPTZ deployment validation v${SCRIPT_VERSION} for ${DESKTOP_USER} on ${TARGET_DISPLAY}"
info "Report: ${REPORT}"
run_hallptz version

# ── 1. Startup mechanisms — the exact commands #892 asks to record ────────────
section "System service unit files (hallptz|dublin|isl|ptz)"
systemctl list-unit-files 2>/dev/null | grep -Ei 'hallptz|dublin|isl|ptz' || info "none"

section "User service unit files (hallptz|dublin|isl|ptz)"
runuser -u "${DESKTOP_USER}" -- systemctl --user list-unit-files 2>/dev/null \
    | grep -Ei 'hallptz|dublin|isl|ptz' || info "none"

section "Autostart .desktop entries"
find "$(getent passwd "${DESKTOP_USER}" | cut -d: -f6)/.config/autostart" /etc/xdg/autostart \
    -maxdepth 2 -type f -print 2>/dev/null || info "none"

section "Running controller processes"
pgrep -af 'python|HallPTZ|HALLPTZ|PTZ' 2>/dev/null || info "none"

# ── 2. Remaining legacy conflicts (dry-run: reports, changes nothing) ─────────
section "Legacy startup conflicts still present (cleanup --dry-run)"
CLEANUP_ARGS=(--wizard-user "${DESKTOP_USER}" --display "${TARGET_DISPLAY}" --dry-run)
[[ -n "${EXTRA_PATTERN}" ]] && CLEANUP_ARGS+=(--legacy-pattern "${EXTRA_PATTERN}")
CLEANUP_OUT=""
if [[ -f "${REPO_ROOT}/${CLEANUP}" ]]; then
    CLEANUP_OUT="$(cd "${REPO_ROOT}" && bash "${CLEANUP}" "${CLEANUP_ARGS[@]}" 2>&1)" || true
    printf '%s\n' "${CLEANUP_OUT}"
else
    warn "${CLEANUP} not found; cannot dry-run legacy detection."
fi

# ── 3. Diagnostics ────────────────────────────────────────────────────────────
section "hallptz verify-install"
run_hallptz verify-install
section "hallptz doctor"
DOCTOR_OUT="$(capture_hallptz doctor)"
printf '%s\n' "${DOCTOR_OUT}"

# ── 4. Automated pass/fail against #892's closure checks ──────────────────────
section "Acceptance checks (#890 / #892)"

# Exactly one HALLPTZ GUI Python process.
HALLPTZ_PROCS="$(pgrep -fa '/opt/hallptz/main.py' 2>/dev/null || true)"
HALLPTZ_COUNT="$(printf '%s' "${HALLPTZ_PROCS}" | grep -c . || true)"
if [[ "${HALLPTZ_COUNT}" -eq 1 ]]; then
    ok "Exactly one HALLPTZ GUI process is running."
elif [[ "${HALLPTZ_COUNT}" -eq 0 ]]; then
    bad "No HALLPTZ GUI process is running (expected exactly one)."
else
    bad "${HALLPTZ_COUNT} HALLPTZ GUI processes are running (expected exactly one)."
    printf '%s\n' "${HALLPTZ_PROCS}"
fi

# hallptz-control.service active.
if systemctl is-active --quiet "${SERVICE}"; then
    ok "${SERVICE} is active."
else
    bad "${SERVICE} is not active."
fi

# No second/legacy controller running.
LEGACY_PROCS="$(pgrep -fa 'HallPTZ|hallptz|PTZ.?[Cc]ontrol|camera.?controller' 2>/dev/null || true)"
if [[ -z "${LEGACY_PROCS}" ]]; then
    ok "No legacy HallPTZ/PTZ controller process is running."
else
    bad "A legacy controller process is still running:"
    printf '%s\n' "${LEGACY_PROCS}"
fi

# The cleanup dry-run must report zero remaining conflicts to change.
if [[ -n "${CLEANUP_OUT}" ]]; then
    if printf '%s' "${CLEANUP_OUT}" | grep -q 'Conflicting entries matched: 0'; then
        ok "No conflicting startup entries remain (cleanup dry-run matched 0)."
    elif printf '%s' "${CLEANUP_OUT}" | grep -Eq 'Would (quarantine|disable|stop)'; then
        bad "Cleanup dry-run still reports conflicting startup entries (see section above)."
    else
        warn "Could not determine remaining-conflict count from cleanup output."
    fi
fi

# ── 5. Wizard / Qt Bullseye checks (#886) ─────────────────────────────────────
section "Wizard / Qt Bullseye checks (#886)"

# The Qt 5.15 QSS parse failure only manifests at runtime on the real Bullseye
# image; the static CI tests cannot reproduce it. Scan the service journal for
# the exact Qt message. ui/styles.py already guards against it by falling back
# to native styling, so its absence confirms the guard held.
if command -v journalctl >/dev/null 2>&1; then
    QSS_HITS="$(journalctl -u "${SERVICE}" --no-pager 2>/dev/null \
        | grep -c 'Could not parse stylesheet' || true)"
    if [[ "${QSS_HITS}" -eq 0 ]]; then
        ok "No 'Could not parse stylesheet' in the ${SERVICE} journal."
    else
        bad "${QSS_HITS} 'Could not parse stylesheet' message(s) in the journal (#886)."
    fi
else
    warn "journalctl unavailable; cannot check for stylesheet parse errors."
fi

# A completed standard setup must not leave the config contradictions #886
# describes. These are the exact strings doctor emits.
if [[ -n "${DOCTOR_OUT}" ]]; then
    if printf '%s' "${DOCTOR_OUT}" | grep -q 'Profile mismatch'; then
        bad "doctor reports a profile/camera-count mismatch (#886)."
        printf '%s\n' "${DOCTOR_OUT}" | grep 'Profile mismatch' || true
    else
        ok "No profile/camera-count mismatch reported by doctor."
    fi
    if printf '%s' "${DOCTOR_OUT}" | grep -q 'ATEM enabled but IP not configured'; then
        bad "ATEM is enabled without an IP address (#886)."
    else
        ok "No 'ATEM enabled but IP not configured' condition."
    fi
fi

# ── 6. X11 / systemd session startup checks (#885) ────────────────────────────
section "X11 / systemd session startup checks (#885)"

# The display/D-Bus failures in #885 are Qt/X11 runtime messages that only occur
# on the appliance. Any of these in the journal means the session handoff broke
# and a manual xhost/systemd workaround would be needed.
if command -v journalctl >/dev/null 2>&1; then
    X11_PATTERN='No protocol specified|could not connect to display|Could not load the Qt platform plugin|could not connect to any X display|XDG_RUNTIME_DIR not set|Failed to start message bus|Read-only file system'
    X11_HITS="$(journalctl -u "${SERVICE}" --no-pager 2>/dev/null \
        | grep -Ec "${X11_PATTERN}" || true)"
    if [[ "${X11_HITS}" -eq 0 ]]; then
        ok "No X11/display/D-Bus session errors in the ${SERVICE} journal."
    else
        bad "${X11_HITS} X11/display/D-Bus session error line(s) in the journal (#885):"
        journalctl -u "${SERVICE}" --no-pager 2>/dev/null | grep -E "${X11_PATTERN}" | tail -10 || true
    fi
else
    warn "journalctl unavailable; cannot check for X11/display session errors."
fi

# The GUI must run under the service identity (hallptz), never as root (#885: "does
# not require broad root privileges").
GUI_USERS="$(pgrep -f '/opt/hallptz/main.py' 2>/dev/null \
    | xargs -r -I{} ps -o user= -p {} 2>/dev/null | sort -u || true)"
if [[ -z "${GUI_USERS}" ]]; then
    warn "No HALLPTZ GUI process found to check its runtime user."
elif [[ "${GUI_USERS}" == "root" ]]; then
    bad "HALLPTZ GUI is running as root (#885: must run as the service user)."
elif printf '%s\n' "${GUI_USERS}" | grep -qx 'root'; then
    bad "A HALLPTZ GUI process is running as root (#885)."
else
    ok "HALLPTZ GUI runs as non-root: $(printf '%s' "${GUI_USERS}" | tr '\n' ' ')"
fi

# Controlled restart, not an infinite rapid loop (#885). The unit caps restarts
# at StartLimitBurst within StartLimitIntervalSec; a hit means it gave up looping.
SVC_RESULT="$(systemctl show "${SERVICE}" -p Result --value 2>/dev/null || true)"
SVC_NRESTARTS="$(systemctl show "${SERVICE}" -p NRestarts --value 2>/dev/null || true)"
SVC_SUBSTATE="$(systemctl show "${SERVICE}" -p SubState --value 2>/dev/null || true)"
info "Service Result=${SVC_RESULT:-?} NRestarts=${SVC_NRESTARTS:-?} SubState=${SVC_SUBSTATE:-?}"
if [[ "${SVC_RESULT}" == "start-limit-hit" ]]; then
    bad "${SERVICE} hit its restart limit — it is failing in a loop (#885)."
elif [[ "${SVC_SUBSTATE}" == "auto-restart" ]]; then
    bad "${SERVICE} is in auto-restart (currently cycling) — re-check after it settles (#885)."
elif [[ -n "${SVC_NRESTARTS}" && "${SVC_NRESTARTS}" =~ ^[0-9]+$ && "${SVC_NRESTARTS}" -gt 3 ]]; then
    warn "${SERVICE} has restarted ${SVC_NRESTARTS} times this boot — investigate stability (#885)."
else
    ok "${SERVICE} restart state is controlled (no rapid loop)."
fi

# Display access must be scoped, never a global 'xhost +' (disabled ACL). Query
# as the desktop user against its X session; best-effort only.
XHOST_OUT="$(runuser -u "${DESKTOP_USER}" -- env DISPLAY="${TARGET_DISPLAY}" xhost 2>/dev/null || true)"
if [[ -z "${XHOST_OUT}" ]]; then
    info "Could not query xhost (no reachable X session from this context) — skipped."
elif printf '%s' "${XHOST_OUT}" | grep -q 'access control enabled'; then
    ok "X11 access control is enabled (scoped grants, no global 'xhost +')."
else
    warn "X11 access control appears disabled ('xhost +'?) — should be scoped (#885)."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
section "Summary"
info "Warnings: ${WARNINGS}"
info "Failures: ${FAILURES}"
info "Report saved to: ${REPORT}"
if [[ "${FAILURES}" -gt 0 ]]; then
    warn "Validation FAILED — do not close #890/#892. Re-check the failing items above."
    exit 1
fi
info "Validation checks passed. Reboot and run this script again to satisfy the two-reboot criterion."
exit 0
