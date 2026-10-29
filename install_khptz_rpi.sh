#!/usr/bin/env bash
# install_khptz_rpi.sh — single supported entry point for a Raspberry Pi install (#883)
#
# Usage:
#   sudo bash install_khptz_rpi.sh [--wizard-user USER] [--gui-mode system|user]
#                                 [--atem] [--check] [--allow-dirty] [--dev]
#
# Run with --help for the authoritative flag list.
#
# The first physical install required the operator to paste several commands in
# the right directory and shell context. Lines were split or concatenated,
# producing errors such as:
#
#   sudo: ./runtime/installer/install.sh: command not found
#   xhost: bad hostname "sudo"
#
# This wrapper is the one command an installer needs. It:
#   - finds the repository root regardless of the current directory;
#   - validates root, the desktop user and the display session;
#   - runs the readiness check, then the installer;
#   - removes the superseded display drop-in (see below);
#   - runs diagnostics and prints ONE next action.
#
# It deliberately does NOT grant display access. That is owned by the wizard
# integration step (scripts/repair_rpi_runtime.sh), which installs a per-login
# helper running `xhost +SI:localuser:khptz` — scoped to the service user and
# re-applied on every login. The operator still never runs xhost by hand.
#
# Idempotent: safe to re-run on an already-installed system.
#
# Exit codes:
#   0  installed and healthy (or healthy with advisories)
#   20 installed, but configuration is still required
#   30 fatal: not installed, or the appliance cannot run

set -euo pipefail

# ── Locate the repository root (works from any directory) ─────────────────────
# BASH_SOURCE is resolved rather than trusting $PWD, so `sudo bash
# /path/to/install_khptz_rpi.sh` from $HOME behaves the same as running it from
# the checkout.

_source="${BASH_SOURCE[0]}"
while [[ -L "${_source}" ]]; do
    _dir="$(cd -P "$(dirname "${_source}")" && pwd)"
    _source="$(readlink "${_source}")"
    [[ "${_source}" != /* ]] && _source="${_dir}/${_source}"
done
REPO_ROOT="$(cd -P "$(dirname "${_source}")" && pwd)"

# Absolute path to this script. Every command we print back to the operator uses
# it, so a copy/pasted re-run works from any directory — running from the wrong
# one is precisely what broke the first install (#883).
SELF="${REPO_ROOT}/$(basename "${_source}")"

INSTALLER="${REPO_ROOT}/runtime/installer/install.sh"
SERVICE_NAME="khptz-control"
DROPIN_DIR="/etc/systemd/system/${SERVICE_NAME}.service.d"
DROPIN_FILE="${DROPIN_DIR}/10-display-session.conf"

# ── Output helpers ────────────────────────────────────────────────────────────
# Deliberately plain ASCII: the Bullseye terminal locale is not guaranteed to
# be UTF-8 (#884).

info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*" >&2; }
step()  { echo; echo "==> $*"; }

fatal() {
    echo >&2
    echo "[FATAL] $*" >&2
    echo >&2
    echo "Installation stopped. Nothing further was changed." >&2
    exit 30
}

# ── Arguments ─────────────────────────────────────────────────────────────────

WIZARD_USER=""
CHECK_ONLY=false
ALLOW_DIRTY=false
# Which launcher owns the GUI (#885). Mirrors install.sh's default so the
# post-install verification below knows which unit to check.
GUI_MODE="system"
DEV_MODE=false
PASSTHROUGH=()

# Reject an unknown mode here rather than letting it travel to install.sh and
# fail after the readiness check has already run (#883: stop with a clear,
# actionable message instead of a late, confusing one).
_validate_gui_mode() {
    case "${GUI_MODE}" in
        system|user) : ;;
        *) fatal "Invalid --gui-mode '${GUI_MODE}'. Expected:
    system  GUI runs as the 'khptz' service user (default, validated)
    user    GUI runs inside the desktop session (#885)" ;;
    esac
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --wizard-user)
            [[ $# -ge 2 ]] || fatal "--wizard-user needs a username, e.g. --wizard-user khptz"
            WIZARD_USER="$2"; shift 2 ;;
        --wizard-user=*)
            WIZARD_USER="${1#*=}"; shift ;;
        --check)
            CHECK_ONLY=true; shift ;;
        --allow-dirty)
            ALLOW_DIRTY=true; shift ;;
        --gui-mode)
            [[ $# -ge 2 ]] || fatal "--gui-mode needs a value: system | user"
            GUI_MODE="$2"; shift 2
            _validate_gui_mode
            PASSTHROUGH+=("--gui-mode" "${GUI_MODE}") ;;
        --gui-mode=*)
            GUI_MODE="${1#*=}"; shift
            _validate_gui_mode
            PASSTHROUGH+=("--gui-mode" "${GUI_MODE}") ;;
        --dev)
            # Tracked, not just forwarded: a developer install uses a different
            # layout and deliberately installs no session-GUI assets, so the
            # readiness check and the post-install verification below must both
            # know about it.
            DEV_MODE=true; PASSTHROUGH+=("$1"); shift ;;
        --atem)
            PASSTHROUGH+=("$1"); shift ;;
        --help|-h)
            # A heredoc rather than sed'ing this file's own header: the header
            # line numbers drift every time the comment block is edited.
            cat <<HELP
install_khptz_rpi.sh — single supported entry point for a Raspberry Pi install

Usage:
  sudo bash install_khptz_rpi.sh [--wizard-user USER] [--atem] [--check] [--dev]

Options:
  --wizard-user USER  Desktop user that owns the GUI and the setup wizard.
                      Defaults to \$SUDO_USER, then the active graphical seat.
  --atem              Install the optional ATEM dependencies.
  --check             Validate readiness only; write nothing.
  --allow-dirty       Permit installing from a checkout with uncommitted
                      changes (blocked by default for customer installs).
  --gui-mode MODE     Which process owns the GUI:
                        system (default) — khptz-control.service runs it as the
                          'khptz' user, bridged to the display by the scoped
                          xhost helper. The currently validated path.
                        user — khptz-gui.service runs it inside the desktop
                          session, inheriting DISPLAY/XAUTHORITY/D-Bus with no
                          display grant and no root (#885).
                      Switching either way is safe and reversible: installing
                      one mode removes the other's launcher.
  --dev               Developer layout install.
  --help, -h          Show this help.

Idempotent: safe to re-run on an already-installed system.

Exit codes:
  0   installed and healthy (or healthy with advisories)
  20  installed, but configuration is still required
  30  fatal: not installed, or the appliance cannot run
HELP
            exit 0 ;;
        *)
            fatal "Unknown option: $1 (run with --help to see the supported flags)" ;;
    esac
done

# ── Preflight ─────────────────────────────────────────────────────────────────

step "Checking how this script was started"

if [[ "${EUID}" -ne 0 ]]; then
    fatal "This installer must run as root. Use:
    sudo bash ${SELF} --wizard-user ${SUDO_USER:-${USER:-pi}}"
fi

[[ -f "${INSTALLER}" ]] || fatal "Could not find the installer at:
    ${INSTALLER}
  This script must stay inside the KHPTZ repository checkout."

info "Repository root: ${REPO_ROOT}"

# Version/commit identity, so a support bundle can be tied to what was installed.
VERSION="unknown"
[[ -f "${REPO_ROOT}/VERSION" ]] && VERSION="$(tr -d '[:space:]' < "${REPO_ROOT}/VERSION")"
COMMIT="unknown"
# `safe.directory` is required: this runs under sudo while the checkout belongs
# to the desktop user, and git refuses to read a repo owned by someone else
# ("detected dubious ownership"). Without it every git call here fails, COMMIT
# stays "unknown" — losing the version/commit identity #883 requires — and the
# dirty-checkout guard below silently never fires. install.sh and rollback.sh
# already do this; this entry point was the one that did not.
_git() { git -c safe.directory='*' -C "${REPO_ROOT}" "$@"; }

if command -v git >/dev/null 2>&1 && _git rev-parse --short HEAD >/dev/null 2>&1; then
    COMMIT="$(_git rev-parse --short HEAD)"
    if [[ -n "$(_git status --porcelain 2>/dev/null)" ]]; then
        COMMIT="${COMMIT}-dirty"
    fi
fi
info "Installing version ${VERSION} (commit ${COMMIT})"

# Refuse to deploy an unidentified or modified checkout onto a customer
# appliance unless the operator explicitly opts in. CLAUDE.md forbids
# installing customer systems from arbitrary/uncommitted state; a -dirty commit
# means the installed bytes match no reviewed revision, so a later support
# bundle cannot be tied back to anything.
if [[ "${COMMIT}" == *-dirty ]] && [[ "${ALLOW_DIRTY}" != "true" ]]; then
    fatal "This checkout has uncommitted changes (commit ${COMMIT}).
  A customer install must come from a clean, identifiable revision.
  Commit or stash the changes, or re-run with --allow-dirty for a dev install."
fi

# ── Desktop user ──────────────────────────────────────────────────────────────
# The GUI, its X session and the setup wizard all belong to the logged-in
# desktop user, not to root and not to the khptz service user.

step "Identifying the desktop user"

if [[ -z "${WIZARD_USER}" ]]; then
    WIZARD_USER="${SUDO_USER:-}"
fi

if [[ -z "${WIZARD_USER}" || "${WIZARD_USER}" == "root" ]]; then
    # Fall back to whoever owns the active graphical seat.
    if command -v loginctl >/dev/null 2>&1; then
        WIZARD_USER="$(loginctl list-sessions --no-legend 2>/dev/null \
            | awk '$3 != "root" && $3 != "" { print $3; exit }' || true)"
    fi
fi

if [[ -z "${WIZARD_USER}" ]]; then
    fatal "Could not determine the desktop user.
  Re-run naming it explicitly, for example:
    sudo bash ${SELF} --wizard-user khptz"
fi

if ! id "${WIZARD_USER}" >/dev/null 2>&1; then
    fatal "Desktop user '${WIZARD_USER}' does not exist on this system.
  List the available users with:  ls /home"
fi

WIZARD_HOME="$(getent passwd "${WIZARD_USER}" | cut -d: -f6)"
WIZARD_UID="$(id -u "${WIZARD_USER}")"
[[ -n "${WIZARD_HOME}" ]] || fatal "User '${WIZARD_USER}' has no home directory."

info "Desktop user: ${WIZARD_USER} (uid ${WIZARD_UID}, home ${WIZARD_HOME})"

# ── Display session ───────────────────────────────────────────────────────────
# Informational only. Display access itself is granted by the wizard's
# integration step (scripts/repair_rpi_runtime.sh), which installs a per-login
# helper running `xhost +SI:localuser:khptz`. See the cleanup step below.

step "Checking the display session"

if command -v loginctl >/dev/null 2>&1 \
   && loginctl show-user "${WIZARD_USER}" --property=State 2>/dev/null | grep -q "active"; then
    info "${WIZARD_USER} has an active session"
else
    warn "${WIZARD_USER} has no active desktop session yet."
    warn "The GUI starts once ${WIZARD_USER} logs into the desktop."
fi

# ── Readiness check ───────────────────────────────────────────────────────────

step "Validating Raspberry Pi readiness"

# --dev must reach the check too: it selects a different path layout
# (/home/<user>/khptz instead of /opt/khptz) and requires pip3. Checking the
# product layout and then installing the developer one validates the wrong
# thing, and lets a check pass that the install then fails.
_CHECK_ARGS=(--check)
[[ "${DEV_MODE}" == "true" ]] && _CHECK_ARGS+=(--dev)

if ! bash "${INSTALLER}" "${_CHECK_ARGS[@]}"; then
    fatal "This Pi is not ready to install KHPTZ. Fix the FAIL items listed above and re-run."
fi

if [[ "${CHECK_ONLY}" == "true" ]]; then
    echo
    info "Check-only run complete. Nothing was installed."
    exit 0
fi

# ── Install / repair ──────────────────────────────────────────────────────────

step "Installing KHPTZ (safe to re-run)"

if ! bash "${INSTALLER}" --wizard-user "${WIZARD_USER}" ${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}; then
    fatal "The installer did not complete. See the output above."
fi

# ── Remove the superseded display drop-in ─────────────────────────────────────
# Earlier revisions of this script wrote 10-display-session.conf, handing the
# service the desktop user's X cookie. That approach is obsolete and actively
# harmful now that the wizard integration installs the scoped
# `xhost +SI:localuser:khptz` helper (scripts/repair_rpi_runtime.sh), because:
#
#   - it set ProtectHome=read-only, overriding the unit's ProtectHome=true and
#     exposing every home directory to the service, for a cookie the scoped
#     helper does not need;
#   - the ACL granting 'khptz' read access to ~/.Xauthority did not survive a
#     re-login, since the display manager recreates that file;
#   - it baked $DISPLAY from the *caller's* environment into the unit, so
#     installing over SSH with X forwarding wrote a dead 'localhost:10.0'.
#
# Removing it here means re-running this script repairs an already-affected
# machine rather than only avoiding the problem on fresh installs (#883).

step "Removing the superseded display drop-in"

if [[ -e "${DROPIN_FILE}" ]]; then
    rm -f -- "${DROPIN_FILE}"
    rmdir --ignore-fail-on-non-empty "${DROPIN_DIR}" 2>/dev/null || true
    systemctl daemon-reload
    info "Removed ${DROPIN_FILE} and reloaded systemd"
else
    info "Not present — nothing to remove"
fi

info "Display access is granted per-login by the wizard integration step."

# ── Diagnostics ───────────────────────────────────────────────────────────────

# Run diagnostics as the SERVICE identity, never as root.
#
# `khptz doctor` opens /var/log/khptz/app.log and the blackbox event log. Those
# directories are khptz:khptz 0750, so a root-run doctor creates root:root files
# inside them and the service can then never write its own logs — the same
# class of permission failure #884 was raised for, only caused by the
# installer. Running as khptz also makes the check reflect what the service
# actually sees.

step "Running diagnostics"

DOCTOR_RC=0
if id khptz >/dev/null 2>&1 && command -v khptz >/dev/null 2>&1; then
    info "Running as the 'khptz' service user"
    sudo -u khptz khptz doctor || DOCTOR_RC=$?
else
    # Not installed as a product (e.g. --dev): keep root's log writes out of
    # the service-owned paths entirely.
    _tmp_log="$(mktemp -d)"
    (
        cd "${REPO_ROOT}" \
        && KHPTZ_LOG_DIR="${_tmp_log}" python3 -m runtime.cli doctor
    ) || DOCTOR_RC=$?
    rm -rf "${_tmp_log}"
fi

# ── Service will actually start ───────────────────────────────────────────────
# doctor reports configuration health, but not whether systemd will bring the
# GUI up on the next boot. The unit only runs after graphical.target once the
# desktop user has logged in, so it is normally INACTIVE at install time —
# checking is-active here would be a false failure. What we can and must verify:
#   - the unit is ENABLED, so it is wired to start on boot at all;
#   - if it is already running, it is not stuck in a restart loop (the exact
#     failure mode the first install hit before the display fix).

step "Verifying the GUI is wired to start"

if ! command -v systemctl >/dev/null 2>&1; then
    warn "systemctl not found — cannot confirm the GUI will start"
elif [[ "${DEV_MODE}" == "true" ]]; then
    # A developer install deliberately ships no session-GUI assets and no
    # provisioning channel (install.sh gates both on product mode). Asserting
    # the product wiring here would report a fatal failure for an install that
    # did exactly what was asked.
    info "Developer install — skipping the product GUI wiring checks."
    info "Run the app directly from the checkout: python3 main.py"
elif [[ "${GUI_MODE}" == "user" ]]; then
    # Session-owned GUI (#885). The unit lives in the desktop user's manager,
    # which does not exist until they log in, so `systemctl --user` from here
    # would be meaningless. What must be true right now is that the launcher
    # assets are installed and the system service is NOT also going to start.
    _gui_unit="/etc/systemd/user/khptz-gui.service"
    _gui_helper="/usr/local/libexec/khptz-gui-session"
    _gui_autostart="${WIZARD_HOME}/.config/autostart/khptz-gui.desktop"

    for _asset in "${_gui_unit}" "${_gui_helper}" "${_gui_autostart}"; do
        if [[ -e "${_asset}" ]]; then
            info "present: ${_asset}"
        else
            warn "missing: ${_asset} — the session GUI will not start automatically."
            [[ "${DOCTOR_RC}" -lt 20 ]] && DOCTOR_RC=20
        fi
    done

    if systemctl is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
        warn "${SERVICE_NAME} is STILL enabled while the GUI runs in the session."
        warn "Two launchers would open two GUIs. Disable it with:"
        warn "  sudo systemctl disable --now ${SERVICE_NAME}"
        DOCTOR_RC=30
    else
        info "${SERVICE_NAME} is disabled — the desktop session owns the GUI"
    fi
else
    if systemctl is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
        info "${SERVICE_NAME} is enabled and will start on boot"
    else
        warn "${SERVICE_NAME} is not enabled — it will NOT start automatically."
        warn "Enable it with:  sudo systemctl enable ${SERVICE_NAME}"
        [[ "${DOCTOR_RC}" -lt 20 ]] && DOCTOR_RC=20
    fi

    _active="$(systemctl is-active "${SERVICE_NAME}" 2>/dev/null || true)"
    _nrestarts="$(systemctl show -p NRestarts --value "${SERVICE_NAME}" 2>/dev/null || echo 0)"
    if [[ "${_active}" == "failed" ]] || { [[ "${_nrestarts}" =~ ^[0-9]+$ ]] && [[ "${_nrestarts}" -ge 3 ]]; }; then
        warn "${SERVICE_NAME} is restarting repeatedly (state=${_active}, restarts=${_nrestarts})."
        warn "Inspect it with:  journalctl -u ${SERVICE_NAME} -b --no-pager"
        DOCTOR_RC=30
    else
        info "Service state: ${_active:-unknown} (starts after desktop login)"
    fi
fi

# ── One clear next action ─────────────────────────────────────────────────────
# Exit codes come from domain/doctor_outcome.py (#887):
#   0 PASS · 10 READY_WITH_ADVISORIES · 20 CONFIG_REQUIRED · 30 FAIL

echo
echo "======================================================================"
case "${DOCTOR_RC}" in
    0)
        echo " SUCCESS — KHPTZ ${VERSION} is installed and healthy."
        echo
        echo " Next action:  reboot, then log in as ${WIZARD_USER}."
        echo "               The touchscreen application starts automatically."
        RC=0
        ;;
    10)
        echo " SUCCESS — KHPTZ ${VERSION} is installed and operational."
        echo " Deployment recommendations remain (listed above); none of them block use."
        echo
        echo " Next action:  reboot, then log in as ${WIZARD_USER}."
        RC=0
        ;;
    20)
        echo " INSTALLED — configuration is still required."
        echo
        echo " Next action:  run the setup wizard as the desktop user:"
        echo "                 sudo -u ${WIZARD_USER} khptz setup --force"
        echo "               Then re-run this script to confirm."
        RC=20
        ;;
    *)
        echo " FAILED — KHPTZ cannot run on this system yet."
        echo
        echo " Next action:  fix the items marked FAIL above, then re-run:"
        echo "                 sudo bash ${SELF} --wizard-user ${WIZARD_USER}"
        echo
        echo " If you need help, collect diagnostics with:"
        echo "                 khptz support-bundle"
        RC=30
        ;;
esac
echo " Version ${VERSION} (commit ${COMMIT})"
echo "======================================================================"

exit "${RC}"
