#!/usr/bin/env bash
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
#
# validate_rpi_acceptance.sh — hardware acceptance harness for #890 / #381
#
# Runs the automatable half of the #890 acceptance checklist on the real
# Raspberry Pi and writes a report that can be pasted straight into the issue.
#
# READ-ONLY by default. #890 states that any manual patch during the acceptance
# run is a failed result, so this script inspects and never repairs: no xhost,
# no systemd edits, no writes under /opt/khptz. `--with-backup` additionally
# exercises `khptz backup`, which #890 asks for and which only adds a new ZIP.
#
# Physical checks (camera movement, presets, operator login, the 10-minute GUI
# soak) cannot be automated; they are printed as MANUAL with the exact step so
# nothing is silently skipped.
#
# Usage:
#   bash scripts/validate_rpi_acceptance.sh [--with-backup] [--report FILE]
#                                         [--wizard-user USER]
#
# --wizard-user names the desktop user the GUI session belongs to. When it
# is not given, the user is resolved in this order (first candidate that is
# a real account wins):
#   1. KHPTZ_WIZARD_USER recorded by install.sh in install-state.env
#   2. SUDO_USER, when the validator runs under sudo
#   3. the invoking user, when it is not root
# Without a resolved user the desktop-session check SKIPs instead of
# guessing.
#
# Exit codes:
#   0  no automated check failed (manual items may remain)
#   1  at least one automated check FAILED

set -uo pipefail

ACCEPTANCE_SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT=""
WITH_BACKUP=false
WIZARD_USER_ARG=""

# A value-taking flag must consume a real value. `shift 2` with only one
# argument left fails silently (no set -e here), the loop never advances and
# the validator hangs forever; an option-looking value is just as wrong.
_need_value() {
    if [[ $# -lt 2 || -z "$2" || "$2" == -* ]]; then
        echo "$1 needs a value (try --help)" >&2
        exit 2
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-backup) WITH_BACKUP=true; shift ;;
        --report) _need_value "$1" "${2:-}"; REPORT="$2"; shift 2 ;;
        --report=*) REPORT="${1#*=}"; shift ;;
        --wizard-user) _need_value "$1" "${2:-}"; WIZARD_USER_ARG="$2"; shift 2 ;;
        --wizard-user=*) WIZARD_USER_ARG="${1#*=}"; shift ;;
        -h|--help)
            sed -n '5,37p' "$0"; exit 0 ;;
        *)
            echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
    esac
done

[[ -n "${REPORT}" ]] || REPORT="${HOME}/khptz-acceptance-$(date +%Y%m%d-%H%M%S).txt"

PASS_N=0; FAIL_N=0; MANUAL_N=0; SKIP_N=0

# Plain ASCII throughout: the Bullseye terminal locale is not guaranteed to be
# UTF-8, and a report generator must not be the thing that hits #884.
say()    { printf '%s\n' "$*" | tee -a "${REPORT}"; }
head2()  { say ""; say "== $* =="; }
pass()   { PASS_N=$((PASS_N+1));     say "[PASS]   $*"; }
fail()   { FAIL_N=$((FAIL_N+1));     say "[FAIL]   $*"; }
manual() { MANUAL_N=$((MANUAL_N+1)); say "[MANUAL] $*"; }
skip()   { SKIP_N=$((SKIP_N+1));     say "[SKIP]   $*"; }

: > "${REPORT}"

say "======================================================================"
say " KHPTZ Raspberry Pi acceptance report (#890)"
say "======================================================================"

# ── Desktop user resolution ──────────────────────────────────────────────────
#
# Most checks are user-agnostic; the session-type check below is not. The
# installer already records its wizard user in install-state.env, so a bare
# `bash scripts/validate_rpi_acceptance.sh` on the Pi works without flags
# and without relying on how the shell happened to be entered. Order:
# flag > install state > SUDO_USER > invoking (non-root) user.

STATE_FILE="${KHPTZ_STATE_FILE:-/etc/khptz/install-state.env}"

DESKTOP_USER=""
DESKTOP_USER_FROM=""

_accept_desktop_user() {
    local u="$1" via="$2"
    [[ -n "${u}" && -z "${DESKTOP_USER}" ]] || return 1
    id -u "${u}" >/dev/null 2>&1 || return 1
    DESKTOP_USER="${u}"
    DESKTOP_USER_FROM="${via}"
}

_accept_desktop_user "${WIZARD_USER_ARG}" "--wizard-user flag"
_state_wizard_user="$(sed -n 's/^KHPTZ_WIZARD_USER=//p' "${STATE_FILE}" 2>/dev/null | tr -d '"' | tail -n1 || true)"
_accept_desktop_user "${_state_wizard_user}" "install state (${STATE_FILE})"
_accept_desktop_user "${SUDO_USER:-}" "SUDO_USER"
if [[ "$(id -u)" != "0" ]]; then
    _accept_desktop_user "$(id -un)" "invoking user"
fi
unset _state_wizard_user

# ── Environment block #890 requires recorded before anything changes ─────────

head2 "Environment"
say "Date        : $(date -Iseconds 2>/dev/null || date)"
say "Tester      : $(id -un)"
say "Host        : $(uname -a)"
if [[ -r /etc/os-release ]]; then
    say "OS          : $(. /etc/os-release && printf '%s' "${PRETTY_NAME:-unknown}")"
fi
# Hardware status is ALWAYS recorded explicitly (#381): a report that says
# nothing about the machine can be misread as hardware-verified acceptance.
# A readable device-tree model is only a REPORTED STRING - present but empty,
# unreadable, or faked under emulation are all possible - so detection never
# claims physical hardware, and HW_PROOF_NOTE is printed with every result.
_detect_hardware_status() {
    DEVICE_TREE_MODEL="${KHPTZ_DEVICE_TREE_MODEL:-/proc/device-tree/model}"
    if [[ ! -e "${DEVICE_TREE_MODEL}" ]]; then
        PI_MODEL=""
        HARDWARE_STATUS="NOT DETECTED (no device-tree model file at ${DEVICE_TREE_MODEL})"
    elif ! _model_raw="$(tr -d '\0' < "${DEVICE_TREE_MODEL}" 2>/dev/null)"; then
        PI_MODEL=""
        HARDWARE_STATUS="NOT DETECTED (device-tree model unreadable)"
    elif [[ -z "${_model_raw}" ]]; then
        PI_MODEL=""
        HARDWARE_STATUS="NOT DETECTED (device-tree model is empty)"
    else
        PI_MODEL="${_model_raw}"
        HARDWARE_STATUS="MODEL REPORTED: ${PI_MODEL}"
    fi
    HW_PROOF_NOTE="HARDWARE: a reported model string is not proof of a physical Pi - #890 acceptance requires the manual checks below on the real machine"
}
_detect_hardware_status
say "Pi model    : ${PI_MODEL:-not detected}"
say "Hardware    : ${HARDWARE_STATUS}"
say "Python      : $(python3 -V 2>&1)"

INSTALL_DIR="/opt/khptz"
STATE="/etc/khptz/install-state.env"
state_value() { sed -n "s/^$1=//p" "${STATE}" 2>/dev/null | tr -d '"' | tail -n1; }

if [[ -r "${STATE}" ]]; then
    say "Version     : $(state_value KHPTZ_INSTALLED_VERSION)"
    say "Commit/ref  : $(state_value KHPTZ_INSTALLED_REF)"
    say "Wizard user : $(state_value KHPTZ_WIZARD_USER)"
    say "Source dir  : $(state_value KHPTZ_SOURCE_DIR)"
else
    say "Install state: NOT FOUND at ${STATE}"
fi

# Same reader every other component uses, so an acceptance report can never
# disagree with the installer about which launcher owns the GUI.
_state_lib="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/install_state.sh"
if [[ -r "${_state_lib}" ]]; then
    # shellcheck source=/dev/null
    KHPTZ_INSTALL_STATE="${STATE}" source "${_state_lib}"
    GUI_MODE="$(KHPTZ_INSTALL_STATE="${STATE}" khptz_gui_mode)"
else
    GUI_MODE="$(state_value KHPTZ_GUI_MODE)"
    [[ "${GUI_MODE}" == "user" || "${GUI_MODE}" == "system" ]] || GUI_MODE="system"
fi
say "GUI mode    : ${GUI_MODE}"

# ── Diagnostics ───────────────────────────────────────────────────────────────

# Diagnostics can create/rotate app.log and blackbox files. Never let a
# sudo-run validator leave root-owned files in the service's runtime paths.
cli_as_service() {
    if [[ "$(id -u)" -eq 0 ]]; then
        if ! id khptz >/dev/null 2>&1; then
            printf '%s\n' 'khptz service account missing; refusing root CLI execution' >&2
            return 127
        fi
        sudo -u khptz -- "$@"
    else
        "$@"
    fi
}

head2 "Diagnostics (khptz version / status / doctor)"

if ! command -v khptz >/dev/null 2>&1; then
    fail "khptz CLI not on PATH - the install did not complete"
else
    for _cmd in version status; do
        if out="$(cli_as_service khptz "${_cmd}" 2>&1)"; then
            pass "khptz ${_cmd} completed"
        else
            fail "khptz ${_cmd} exited non-zero"
        fi
        printf '%s\n' "${out}" | sed 's/^/         | /' >> "${REPORT}"
        case "${out}" in
            *UnicodeEncodeError*) fail "khptz ${_cmd}: UnicodeEncodeError (#884 regression)" ;;
            *"Permission denied"*) fail "khptz ${_cmd}: permission denied (#884 regression)" ;;
        esac
    done

    doctor_out="$(cli_as_service khptz doctor 2>&1)"; doctor_rc=$?
    printf '%s\n' "${doctor_out}" | sed 's/^/         | /' >> "${REPORT}"
    case "${doctor_out}" in
        *UnicodeEncodeError*) fail "khptz doctor: UnicodeEncodeError (#884 regression)" ;;
        *) pass "khptz doctor produced output without an encoding crash" ;;
    esac
    case "${doctor_out}" in
        *"Permission denied"*|*"Could not write crash report"*)
            fail "khptz doctor: permission problem on a service-owned path (#884)" ;;
        *)  pass "khptz doctor: no permission-denied warnings" ;;
    esac

    # Exit codes come from domain/doctor_outcome.py (#887).
    case "${doctor_rc}" in
        0)  pass "doctor outcome: PASS (rc=0)" ;;
        10) pass "doctor outcome: READY_WITH_ADVISORIES (rc=10)" ;;
        20) fail "doctor outcome: CONFIG_REQUIRED (rc=20) - configuration incomplete" ;;
        30) fail "doctor outcome: FAIL (rc=30) - appliance cannot operate" ;;
        *)  fail "doctor outcome: unexpected exit code ${doctor_rc}" ;;
    esac

    # #890: JSON must agree with the human output and the exit code.
    json_out="$(cli_as_service khptz doctor --json 2>/dev/null)"; json_rc=$?
    # Equal process codes alone do not prove valid JSON or honest summaries.
    # Require one explicit human outcome plus JSON checks that derive the same
    # domain outcome. These are sequential snapshots, so drift needs review.
    human_outcome="$(printf '%s\n' "${doctor_out}" | sed -n 's/^  Outcome: //p')"
    if printf '%s\n' "${json_out}" | python3 "${ACCEPTANCE_SCRIPT_DIR}/check_doctor_acceptance.py" \
        --human-rc "${doctor_rc}" --json-rc "${json_rc}" --human-outcome "${human_outcome}"; then
        pass "khptz doctor JSON structure and outcomes agree with human output (${json_rc})"
    else
        fail "doctor JSON is malformed or disagrees with human/process/check outcomes"
    fi
    printf '%s\n' "${json_out}" > "${REPORT%.txt}-doctor.json" 2>/dev/null \
        && say "         (JSON saved to ${REPORT%.txt}-doctor.json)"
fi

# ── Service / GUI wiring ──────────────────────────────────────────────────────

head2 "Service and GUI (mode: ${GUI_MODE})"

if ! command -v systemctl >/dev/null 2>&1; then
    skip "systemctl unavailable - cannot inspect the service"
elif [[ "${GUI_MODE}" == "user" ]]; then
    for _asset in /etc/systemd/user/khptz-gui.service /usr/local/libexec/khptz-gui-session; do
        [[ -e "${_asset}" ]] && pass "present: ${_asset}" || fail "missing: ${_asset}"
    done
    if systemctl is-enabled --quiet khptz-control 2>/dev/null; then
        fail "khptz-control is STILL enabled alongside the session GUI - two GUIs would compete (#885)"
    else
        pass "khptz-control is disabled - the desktop session owns the GUI"
    fi
    manual "As ${DESKTOP_USER:-khptz}, after login run: systemctl --user status khptz-gui"
else
    if systemctl is-enabled --quiet khptz-control 2>/dev/null; then
        pass "khptz-control is enabled"
    else
        fail "khptz-control is NOT enabled - it will not start on boot"
    fi

    active="$(systemctl is-active khptz-control 2>/dev/null)"
    say "         service state: ${active:-unknown}"

    restarts="$(systemctl show -p NRestarts --value khptz-control 2>/dev/null || echo 0)"
    if [[ "${restarts}" =~ ^[0-9]+$ ]] && [[ "${restarts}" -ge 3 ]]; then
        fail "khptz-control has restarted ${restarts} times - restart loop"
    else
        pass "khptz-control restart count is ${restarts:-0}"
    fi
fi

# ── Desktop session type ──────────────────────────────────────────────────────

head2 "Desktop session"

# The GUI units force QT_QPA_PLATFORM=xcb: only an X11 desktop can host the
# GUI, and Bookworm defaults to Wayland. Inspect the ACTIVE graphical session
# of the desktop user (a leftover session of the other type must not decide);
# anything uninspectable is a skip, never a guess.
if [[ -z "${DESKTOP_USER}" ]]; then
    skip "no desktop user resolved - rerun with --wizard-user, or check manually: loginctl list-sessions"
elif ! command -v loginctl >/dev/null 2>&1; then
    skip "loginctl not available - session type not inspectable"
else
    _sess_type=""
    for _sid in $(loginctl list-sessions --no-legend 2>/dev/null \
                  | awk -v u="${DESKTOP_USER}" '$3 == u { print $1 }' || true); do
        _t="$(loginctl show-session "${_sid}" --property=Type --value 2>/dev/null || true)"
        [[ "${_t}" == "x11" || "${_t}" == "wayland" ]] || continue
        [[ "$(loginctl show-session "${_sid}" --property=Active --value 2>/dev/null || true)" == "yes" ]] || continue
        _sess_type="${_t}"
        break
    done
    case "${_sess_type}" in
        x11)
            pass "active desktop session is X11 (user ${DESKTOP_USER} from ${DESKTOP_USER_FROM})" ;;
        wayland)
            fail "active desktop session for ${DESKTOP_USER} is Wayland (user from ${DESKTOP_USER_FROM}) - the GUI requires X11; switch with 'sudo raspi-config' -> Advanced Options -> Wayland -> X11 and reboot" ;;
        *)
            skip "no active graphical session to inspect - run acceptance from the Pi desktop" ;;
    esac
fi

# ── Runtime path permissions ─────────────────────────────────────────────────
#
# The mode of these directories is the difference between a GUI that can save
# presets and one that silently cannot, and it depends on who owns the GUI:
#
#   system — 0750 khptz:khptz. Only the service writes them.
#   user   — 2770 khptz:khptz. The desktop GUI writes them too, through the
#            'khptz' group; setgid keeps new files in that group so the service
#            identity can still read what the GUI wrote.
#
# Worth asserting on the device because three separate components write these
# modes in sequence (install.sh, runtime/provision.py, repair_rpi_runtime.sh)
# and the last one to run decides. When repair_rpi_runtime.sh asserted a flat
# 0750 it undid the other two on every session-owned install, and nothing in
# this harness noticed: the appliance passed acceptance and then could not
# persist a single preset.

head2 "Runtime path permissions (GUI mode: ${GUI_MODE})"

if [[ "${GUI_MODE}" == "user" ]]; then
    _expect_runtime_mode="2770"
else
    _expect_runtime_mode="0750"
fi

for _dir in /var/lib/khptz /var/log/khptz /var/backups/khptz; do
    if [[ ! -d "${_dir}" ]]; then
        fail "missing runtime directory: ${_dir}"
        continue
    fi
    _actual="$(stat -c '%04a %U:%G' "${_dir}" 2>/dev/null || true)"
    if [[ "${_actual}" == "${_expect_runtime_mode} khptz:khptz" ]]; then
        pass "${_dir} is ${_actual}"
    else
        fail "${_dir} is '${_actual}', expected '${_expect_runtime_mode} khptz:khptz'"
        [[ "${GUI_MODE}" == "user" ]] \
            && say "         the session GUI cannot write here - it will start with no presets or layout"
    fi
done

# Config stays admin-write / service-read in both modes. The setgid bit is what
# keeps files created there in the khptz group; others-traverse (the trailing 1)
# is what lets the unprivileged desktop session stat .provisioned to decide
# whether to open the setup wizard, without any read access to config.yaml or
# the secrets.
if [[ -d /etc/khptz ]]; then
    _cfg="$(stat -c '%04a %U:%G' /etc/khptz 2>/dev/null || true)"
    case "${_cfg}" in
        275[01]" root:khptz") pass "/etc/khptz is ${_cfg}" ;;
        *) fail "/etc/khptz is '${_cfg}', expected '2751 root:khptz' (2750 pre-provision)" ;;
    esac
else
    fail "missing config directory: /etc/khptz"
fi

# Application code must be readable and NEVER writable by the service.
if [[ -d "${INSTALL_DIR}" ]]; then
    _app="$(stat -c '%04a %U:%G' "${INSTALL_DIR}" 2>/dev/null || true)"
    if [[ "${_app}" == "0750 root:khptz" ]]; then
        pass "${INSTALL_DIR} is ${_app}"
    else
        fail "${INSTALL_DIR} is '${_app}', expected '0750 root:khptz'"
    fi
fi

# Secrets must stay owner-only. Group-readable here would hand the
# administrator password to every account in the khptz group, and the key is
# derived from the world-readable /etc/machine-id.
_secret_findings=0
for _secret in /var/lib/khptz/password.enc /etc/khptz/secrets/admin.enc; do
    [[ -e "${_secret}" ]] || continue
    _mode="$(stat -c '%a' "${_secret}" 2>/dev/null || true)"
    if [[ "${_mode}" == "600" ]]; then
        pass "$(basename "${_secret}") is 600"
    else
        fail "$(basename "${_secret}") is ${_mode}, expected 600"
        _secret_findings=$((_secret_findings + 1))
    fi
done
[[ ${_secret_findings} -eq 0 ]] || say "         inspect secret ownership and permissions; see docs/HARDENING2.md"

# ── Boot journal: the errors #890 says must not return ───────────────────────

head2 "Boot journal scan"

if ! command -v journalctl >/dev/null 2>&1; then
    skip "journalctl unavailable"
elif ! journal="$(journalctl -b --no-pager 2>/dev/null)" || [[ -z "${journal}" ]]; then
    skip "could not read the boot journal (run with sudo for this section)"
else
    # Each pattern maps to a specific regression #890 lists.
    scan() {
        local label="$1" pattern="$2" hits
        hits="$(printf '%s\n' "${journal}" | grep -c -- "${pattern}" 2>/dev/null || true)"
        if [[ "${hits}" -gt 0 ]]; then
            fail "${label} (${hits} occurrence(s) in this boot)"
            printf '%s\n' "${journal}" | grep -m3 -- "${pattern}" | sed 's/^/         > /' >> "${REPORT}"
        else
            pass "${label}: not present"
        fi
    }
    scan "XCB display connection failure"  "could not connect to display"
    scan "X11 authorisation refused"       "No protocol specified"
    scan "Qt platform plugin failure"      "Could not load the Qt platform plugin"
    scan "XDG_RUNTIME_DIR missing"         "XDG_RUNTIME_DIR not set"
    scan "Session D-Bus failure"           "Failed to start message bus"
    scan "GPIO aborted the process"        "Not running on a RPi"
    scan "Qt thread destroyed while running" "QThread: Destroyed while thread is still running"
    scan "Process aborted (SIGABRT)"       "status=6/ABRT"
    scan "Wizard stylesheet parse error"   "Could not parse stylesheet"
    scan "UnicodeEncodeError"              "UnicodeEncodeError"
fi

# ── Configuration sanity (#886) ───────────────────────────────────────────────

head2 "Configuration"

CONFIG="/etc/khptz/config.yaml"
if [[ ! -r "${CONFIG}" ]]; then
    skip "cannot read ${CONFIG} (run with sudo, or the install is incomplete)"
else
    cams="$(grep -cE '^[[:space:]]*-[[:space:]]*(name|ip):' "${CONFIG}" 2>/dev/null || echo 0)"
    profile="$(sed -n 's/^[[:space:]]*profile:[[:space:]]*//p' "${CONFIG}" | tr -d '"' | head -1)"
    say "         cameras: ${cams:-0}"
    say "         profile: ${profile:-<unset>}"
    if grep -qE '^[[:space:]]*enabled:[[:space:]]*true' "${CONFIG}" \
       && grep -qE '^[[:space:]]*ip:[[:space:]]*""' "${CONFIG}"; then
        fail "ATEM appears enabled with an empty IP (#886)"
    else
        pass "no ATEM-enabled-without-IP contradiction detected"
    fi
    say "         (camera/profile agreement is asserted by khptz doctor above)"
fi

# ── Persistence ───────────────────────────────────────────────────────────────

head2 "Persistence"

if [[ "${WITH_BACKUP}" == "true" ]] && command -v khptz >/dev/null 2>&1; then
    if cli_as_service khptz backup >/dev/null 2>&1; then
        pass "khptz backup created a backup"
    else
        fail "khptz backup failed"
    fi
else
    skip "khptz backup not exercised (pass --with-backup to include it)"
fi

manual "Re-run the bootstrap and confirm config, passwords, presets and layout survive"
manual "Reboot a second time and confirm the same installation starts"

# ── Physical checks that cannot be automated ─────────────────────────────────

head2 "Manual checks (physical room test)"
manual "GUI opens automatically after login, with no terminal command"
manual "Exactly one GUI instance is running (check with: pgrep -af ${INSTALL_DIR}/main.py)"
manual "GUI remains visible for at least 10 minutes"
manual "Operator login works"
manual "Administrator login works"
manual "Platform camera moves and stops"
manual "Audience camera moves and stops"
manual "Representative presets recall correctly"
manual "STOP remains available during movement"
manual "ATEM works if enabled, or stays cleanly disabled if not configured"
manual "Wizard shows no QSS parse warnings and two cameras yield standard_2_camera"

# ── Result record, ready to paste into #890 ──────────────────────────────────

head2 "Result record (paste into #890)"
say "Date:        $(date -Iseconds 2>/dev/null || date)"
say "Tester:      $(id -un)"
say "Pi model:    ${PI_MODEL:-unknown}"
say "Hardware:    ${HARDWARE_STATUS}"
say "OS:          $( [[ -r /etc/os-release ]] && (. /etc/os-release && printf '%s' "${PRETTY_NAME:-unknown}") || echo unknown)"
say "Python:      $(python3 -V 2>&1)"
say "KHPTZ version: $( [[ -r ${STATE} ]] && state_value KHPTZ_INSTALLED_VERSION || echo unknown)"
say "Commit:      $( [[ -r ${STATE} ]] && state_value KHPTZ_INSTALLED_REF || echo unknown)"
say "GUI mode:    ${GUI_MODE}"
say "Automated:   ${PASS_N} passed, ${FAIL_N} failed, ${SKIP_N} skipped"
say "Manual:      ${MANUAL_N} checks still to perform by hand"
say ""
say "Install:            PASS/FAIL   (fill in)"
say "Wizard:             PASS/FAIL   (fill in)"
say "Doctor outcome:     ${doctor_rc:-unknown}"
say "Reboot autostart:   PASS/FAIL   (fill in)"

say ""
say "======================================================================"
if [[ "${FAIL_N}" -gt 0 ]]; then
    say " RESULT: ${FAIL_N} automated check(s) FAILED - acceptance not met"
else
    say " RESULT: no automated check failed - complete the MANUAL items above"
fi
say " ${HW_PROOF_NOTE}"
say " Report saved to: ${REPORT}"
say "======================================================================"

[[ "${FAIL_N}" -eq 0 ]]
