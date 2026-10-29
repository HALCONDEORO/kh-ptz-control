#!/usr/bin/env bash
# KH PTZ Control - Raspberry Pi runtime finalisation
#
# Installs the canonical display/UTF-8/runtime contract used by the real setup
# wizard. This script performs OS integration only; application compatibility is
# fixed in the source tree and is no longer patched in-place under /opt/khptz.
#
# Safe to run repeatedly. Customer configuration, passwords, presets and layouts
# are never replaced. Every OS file replaced by this script is backed up first.

set -Eeuo pipefail
IFS=$'\n\t'

readonly SCRIPT_VERSION="5"
readonly SERVICE_NAME="khptz-control.service"
readonly DISPLAY_HELPER="/usr/local/libexec/khptz-display-session"
readonly DISPLAY_PATH_UNIT="/etc/systemd/system/khptz-display-ready.path"
readonly DISPLAY_SERVICE_UNIT="/etc/systemd/system/khptz-display-ready.service"
readonly SERVICE_DROPIN_DIR="/etc/systemd/system/khptz-control.service.d"
readonly SERVICE_DROPIN="${SERVICE_DROPIN_DIR}/20-rpi-display.conf"
readonly KHPTZ_LAUNCHER="/usr/local/bin/khptz"

# Exit code meaning "every OS step succeeded and the configuration is applied,
# but `khptz doctor` reports the appliance is not healthy". Distinct from 1 so
# the caller can keep the customer's configuration instead of rolling it back.
# Kept in sync with scripts/provision_with_rpi_integration.sh.
readonly RC_DIAGNOSTICS_FATAL=40

WIZARD_USER="${SUDO_USER:-}"
TARGET_DISPLAY="${DISPLAY:-:0}"
BACKUP_DIR=""

info() { printf '[INFO]  %s\n' "$*"; }
warn() { printf '[WARN]  %s\n' "$*" >&2; }
fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

# Which process owns the GUI (#885). This script is reached from the wizard's
# provisioning chain (khptz-provision.service ->
# provision_with_rpi_integration.sh -> here), which runs on EVERY install
# including session-owned ones. Re-enabling khptz-control there would put two
# full-screen GUIs on the same cameras, so the mode has to be read before any
# systemd activation happens.
_state_lib="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/install_state.sh"
if [[ -r "${_state_lib}" ]]; then
    # shellcheck source=/dev/null
    source "${_state_lib}"
else
    # Partially deployed tree: assume the historical layout rather than guessing
    # "user" and leaving the machine with no launcher at all.
    khptz_gui_mode() { printf 'system\n'; }
fi
GUI_MODE="$(khptz_gui_mode)"
readonly GUI_MODE

# Mode for the runtime-writable directories (/var/lib, /var/log, /var/backups).
#
# This script runs from the wizard's provisioning chain AFTER install.sh and
# after runtime/provision.py's plan_system_commands(), both of which already
# make these directories 2770 on a session-owned install so the desktop GUI can
# write its own presets, layout and logs through the 'khptz' group. Re-asserting
# a flat 0750 here — as this script did — was the last write in the chain, so
# it silently undid that and left the session GUI with a read-only data
# directory on an install that reported success. Keep the single rule in one
# place: 2770 when the GUI shares these directories, 0750 when only the service
# writes them (matching runtime/provision.py's runtime_mode).
if [[ "${GUI_MODE}" == "user" ]]; then
    RUNTIME_DIR_MODE="2770"
else
    RUNTIME_DIR_MODE="0750"
fi
readonly RUNTIME_DIR_MODE

on_error() {
    local line="$1" code="$2"
    printf '[ERROR] Runtime finalisation stopped at line %s (exit %s).\n' \
        "${line}" "${code}" >&2
    [[ -n "${BACKUP_DIR}" ]] \
        && printf '[ERROR] Backups are under %s.\n' "${BACKUP_DIR}" >&2
    exit "${code}"
}
trap 'on_error "$LINENO" "$?"' ERR

usage() {
    cat <<'USAGE'
Usage: sudo bash scripts/repair_rpi_runtime.sh [options]

Options:
  --wizard-user USER  Human desktop user that runs KHPTZ Setup.
  --display DISPLAY   X11 display. Defaults to current DISPLAY or :0.
  -h, --help          Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --wizard-user)
            [[ $# -ge 2 ]] || fail "--wizard-user requires a value"
            WIZARD_USER="$2"; shift 2 ;;
        --display)
            [[ $# -ge 2 ]] || fail "--display requires a value"
            TARGET_DISPLAY="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown option: $1" ;;
    esac
done

[[ "$(id -u)" -eq 0 ]] || fail "Run this script with sudo."
[[ -n "${WIZARD_USER}" ]] || fail "Could not detect the desktop user. Use --wizard-user USER."
[[ "${WIZARD_USER}" != "root" && "${WIZARD_USER}" != "khptz" ]] \
    || fail "The wizard user must be the human desktop user."
[[ "${TARGET_DISPLAY}" =~ ^:[0-9]+(\.[0-9]+)?$ ]] \
    || fail "Invalid X11 display: ${TARGET_DISPLAY}"
id "${WIZARD_USER}" >/dev/null 2>&1 || fail "User does not exist: ${WIZARD_USER}"
id khptz >/dev/null 2>&1 || fail "The khptz service user does not exist. Run the product installer first."
[[ -f /opt/khptz/main.py ]] || fail "Installed application not found at /opt/khptz/main.py."
[[ -f /etc/systemd/system/khptz-control.service ]] \
    || fail "khptz-control.service is not installed."

for command in cp find getent install journalctl locale runuser stat sudo systemctl systemd-tmpfiles; do
    command -v "${command}" >/dev/null 2>&1 \
        || fail "Required command not found: ${command}"
done

# xhost is only ever used to grant the 'khptz' service user access to the
# desktop user's X display, which exists solely in system GUI mode. Under
# --gui-mode user the GUI already runs inside the session and never touches
# xhost, so requiring it there would abort the wizard — and reaching for
# apt-get would do it on an appliance that may have no network at all.
if [[ "${GUI_MODE}" != "user" ]] && ! command -v xhost >/dev/null 2>&1; then
    command -v apt-get >/dev/null 2>&1 \
        || fail "xhost is missing. Install x11-xserver-utils and re-run."
    info "Installing scoped X11 authorization support..."
    DEBIAN_FRONTEND=noninteractive apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y x11-xserver-utils
fi

WIZARD_HOME="$(getent passwd "${WIZARD_USER}" | cut -d: -f6)"
WIZARD_GROUP="$(id -gn "${WIZARD_USER}")"
WIZARD_UID="$(id -u "${WIZARD_USER}")"
[[ -n "${WIZARD_HOME}" && -d "${WIZARD_HOME}" ]] \
    || fail "Could not resolve the home directory for ${WIZARD_USER}."

UTF8_LOCALE="C.UTF-8"
if ! LC_ALL="${UTF8_LOCALE}" locale charmap 2>/dev/null | grep -qi 'UTF-8'; then
    if locale -a 2>/dev/null | grep -qx 'C.utf8'; then
        UTF8_LOCALE="C.utf8"
    elif locale -a 2>/dev/null | grep -qx 'en_GB.utf8'; then
        UTF8_LOCALE="en_GB.utf8"
    elif locale -a 2>/dev/null | grep -qx 'en_US.utf8'; then
        UTF8_LOCALE="en_US.utf8"
    else
        fail "No UTF-8 locale is available. Enable C.UTF-8 or en_GB.UTF-8."
    fi
fi

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/var/backups/khptz/rpi-runtime-finalisation-${TIMESTAMP}"
install -d -m "${RUNTIME_DIR_MODE}" -o khptz -g khptz /var/backups/khptz
install -d -m 0750 -o khptz -g khptz "${BACKUP_DIR}"

backup_path() {
    local path="$1"
    if [[ -e "${path}" || -L "${path}" ]]; then
        cp -a --parents -- "${path}" "${BACKUP_DIR}/"
    fi
    return 0
}

info "KHPTZ Raspberry Pi runtime finalisation v${SCRIPT_VERSION}"
info "Backing up replaced OS files to ${BACKUP_DIR}"
for path in \
    "${KHPTZ_LAUNCHER}" \
    "${SERVICE_DROPIN}" \
    "${DISPLAY_HELPER}" \
    "${DISPLAY_PATH_UNIT}" \
    "${DISPLAY_SERVICE_UNIT}" \
    "/etc/tmpfiles.d/khptz.conf" \
    "${WIZARD_HOME}/.config/autostart/khptz-display-session.desktop" \
    "${WIZARD_HOME}/.config/autostart/khptz-display-permission.desktop"; do
    backup_path "${path}"
done

info "Repairing canonical runtime directories (mode ${RUNTIME_DIR_MODE}, GUI mode ${GUI_MODE})..."
install -d -m "${RUNTIME_DIR_MODE}" -o khptz -g khptz /var/lib/khptz
install -d -m "${RUNTIME_DIR_MODE}" -o khptz -g khptz /var/log/khptz
install -d -m "${RUNTIME_DIR_MODE}" -o khptz -g khptz /var/log/khptz/blackbox
install -d -m "${RUNTIME_DIR_MODE}" -o khptz -g khptz /var/log/khptz/incidents
install -d -m "${RUNTIME_DIR_MODE}" -o khptz -g khptz /var/backups/khptz

if ! id -nG "${WIZARD_USER}" | tr ' ' '\n' | grep -qx khptz; then
    info "Adding ${WIZARD_USER} to the khptz group..."
    usermod -aG khptz "${WIZARD_USER}"
    warn "The new group membership becomes active after logout/login or reboot."
fi

info "Configuring the volatile desktop-ready channel..."
printf 'd /run/khptz 0750 %s root -\n' "${WIZARD_USER}" > /etc/tmpfiles.d/khptz.conf
systemd-tmpfiles --create /etc/tmpfiles.d/khptz.conf

# The display-ready chain exists for ONE reason: to bridge the 'khptz'
# service user to the desktop user's X display in system GUI mode. A
# session-owned GUI already owns its session's display, so none of it
# applies there - and installing it anyway is not merely redundant.
#
# The autostart entry runs the helper at every login, where it loops up to
# 60 times at two-second intervals trying to reach xhost. On an appliance
# without x11-xserver-utils (which this mode no longer installs) that is two
# minutes of a pointless background process per login, and where xhost IS
# present it grants the service user display access this mode never needs.
#
# The path unit is worse. `systemctl disable` is not `mask`: the helper
# writing /run/khptz/display-ready triggers khptz-display-ready.service, whose
# ExecStart is `systemctl restart khptz-control.service` - and restart STARTS
# a merely-disabled unit. On a machine switched from system to user mode
# these leftovers therefore put khptz-control back on screen alongside
# khptz-gui.service: two full-screen GUIs driving the same cameras, the exact
# failure #885 exists to prevent, re-armed by the integration step meant to
# prevent it.
#
# So: install the chain in system mode, actively tear it down in user mode.
# Every file removed below was captured by backup_path above, and switching
# back re-creates all of it, so the mode switch stays reversible.
#
# The body is left unindented: it contains heredocs whose terminators must
# stay at column 0.
if [[ "${GUI_MODE}" != "user" ]]; then
install -d -m 0755 /usr/local/libexec
cat > "${DISPLAY_HELPER}" <<'HELPER'
#!/usr/bin/env bash
set -Eeuo pipefail

export DISPLAY="${DISPLAY:-:0}"
readonly marker="/run/khptz/display-ready"
readonly temporary="${marker}.$$"
trap 'rm -f "${temporary}"' EXIT

rm -f "${marker}"
for ((attempt = 1; attempt <= 60; attempt++)); do
    if [[ -d /run/khptz ]] && /usr/bin/xhost +SI:localuser:khptz >/dev/null 2>&1; then
        umask 022
        printf 'display=%s\nuser=%s\ntime=%s\n' \
            "${DISPLAY}" "$(id -un)" "$(date -Iseconds)" > "${temporary}"
        mv -f "${temporary}" "${marker}"
        command -v logger >/dev/null 2>&1 \
            && logger -t khptz-display-session \
                "Display access granted to local user khptz on ${DISPLAY}"
        exit 0
    fi
    sleep 2
done

command -v logger >/dev/null 2>&1 \
    && logger -t khptz-display-session \
        "Could not grant display access to khptz on ${DISPLAY}"
exit 1
HELPER
chmod 0755 "${DISPLAY_HELPER}"

info "Installing the desktop-session handoff..."
AUTOSTART_DIR="${WIZARD_HOME}/.config/autostart"
AUTOSTART_FILE="${AUTOSTART_DIR}/khptz-display-session.desktop"
install -d -m 0755 -o "${WIZARD_USER}" -g "${WIZARD_GROUP}" "${AUTOSTART_DIR}"
cat > "${AUTOSTART_FILE}" <<EOF_DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=KHPTZ display session
Comment=Grant KHPTZ scoped access to the local touchscreen display
TryExec=${DISPLAY_HELPER}
Exec=${DISPLAY_HELPER}
Terminal=false
NoDisplay=true
Hidden=false
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF_DESKTOP
chown "${WIZARD_USER}:${WIZARD_GROUP}" "${AUTOSTART_FILE}"
chmod 0644 "${AUTOSTART_FILE}"
rm -f -- "${AUTOSTART_DIR}/khptz-display-permission.desktop"

info "Installing display-ready systemd units..."
cat > "${DISPLAY_PATH_UNIT}" <<'EOF_PATH'
[Unit]
Description=Watch for the KHPTZ desktop display-ready marker
After=local-fs.target

[Path]
PathChanged=/run/khptz/display-ready
Unit=khptz-display-ready.service

[Install]
WantedBy=multi-user.target
EOF_PATH

cat > "${DISPLAY_SERVICE_UNIT}" <<'EOF_SERVICE'
[Unit]
Description=Start KHPTZ Control after desktop display access is ready

[Service]
Type=oneshot
ExecStart=-/bin/systemctl reset-failed khptz-control.service
ExecStart=/bin/systemctl restart khptz-control.service
TimeoutStartSec=30
EOF_SERVICE

# Keep this drop-in for upgraded installations whose base unit predates the
# integrated template. New installs already carry the same settings directly.
info "Installing the compatibility service override..."
install -d -m 0755 "${SERVICE_DROPIN_DIR}"
cat > "${SERVICE_DROPIN}" <<EOF_DROPIN
[Unit]
After=graphical.target
ConditionPathExists=/run/khptz/display-ready

[Service]
PrivateTmp=false
Environment=LANG=${UTF8_LOCALE}
Environment=LC_ALL=${UTF8_LOCALE}
Environment=PYTHONUTF8=1
Environment=PYTHONIOENCODING=utf-8
EOF_DROPIN

else
info "GUI mode 'user': removing the display-ready chain..."

# Disable before deleting: removing a unit file that is still enabled leaves
# a dangling symlink systemd warns about on every later daemon-reload.
for _unit in khptz-display-ready.path khptz-display-ready.service; do
    systemctl disable --now "${_unit}" >/dev/null 2>&1 || true
done

# An array keeps the list readable without line continuations.
_display_chain_artifacts=(
    "${DISPLAY_HELPER}"
    "${DISPLAY_PATH_UNIT}"
    "${DISPLAY_SERVICE_UNIT}"
    "${SERVICE_DROPIN}"
    "${WIZARD_HOME}/.config/autostart/khptz-display-session.desktop"
    "${WIZARD_HOME}/.config/autostart/khptz-display-permission.desktop"
)
for _artifact in "${_display_chain_artifacts[@]}"; do
    if [[ -e "${_artifact}" ]]; then
        rm -f -- "${_artifact}"
        info "Removed display-chain leftover: ${_artifact}"
    fi
done
rmdir --ignore-fail-on-non-empty "${SERVICE_DROPIN_DIR}" 2>/dev/null || true

info "The session GUI reaches the display through its own session - no grant needed."
fi

info "Installing the UTF-8-safe KHPTZ launcher..."
cat > "${KHPTZ_LAUNCHER}" <<EOF_LAUNCHER
#!/usr/bin/env bash
set -Eeuo pipefail
export LANG=${UTF8_LOCALE}
export LC_ALL=${UTF8_LOCALE}
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

subcommand="\${1:-}"
if [[ "\$(id -u)" -ne 0 && "\$(id -un)" != "khptz" ]]; then
    case "\${subcommand}" in
        status|uptime|cameras|doctor|fingerprint|known-good|maintenance|installability|supportability|support-bundle|backup|network-report|verify-install)
            exec /usr/bin/sudo -u khptz -H env \
                LANG=${UTF8_LOCALE} LC_ALL=${UTF8_LOCALE} \
                PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
                /bin/bash -c 'cd /opt/khptz && exec /usr/bin/python3 -m runtime.cli "\$@"' \
                khptz-cli "\$@"
            ;;
        restore)
            exec /usr/bin/sudo env \
                LANG=${UTF8_LOCALE} LC_ALL=${UTF8_LOCALE} \
                PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
                /bin/bash -c 'cd /opt/khptz && exec /usr/bin/python3 -m runtime.cli "\$@"' \
                khptz-cli "\$@"
            ;;
        setup|demo)
            state_root="\${XDG_STATE_HOME:-\${HOME}/.local/state}"
            export KHPTZ_LOG_DIR="\${KHPTZ_LOG_DIR:-\${state_root}/khptz/log}"
            mkdir -p "\${KHPTZ_LOG_DIR}"
            ;;
    esac
fi

cd /opt/khptz
exec /usr/bin/python3 -m runtime.cli "\$@"
EOF_LAUNCHER
chmod 0755 "${KHPTZ_LAUNCHER}"

systemctl daemon-reload

# Activation depends on who owns the GUI. On a session-owned install the system
# service is deliberately disabled by install.sh --gui-mode user; enabling it
# here (as this script did unconditionally) would mean the operator finishing
# the wizard silently re-armed a SECOND launcher, and the next boot would open
# two full-screen GUIs driving the same cameras — the exact failure #885 exists
# to prevent, triggered by the provisioning chain itself.
if [[ "${GUI_MODE}" == "user" ]]; then
    info "GUI mode 'user': leaving ${SERVICE_NAME} disabled (the desktop session owns the GUI)."
    if systemctl is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
        warn "${SERVICE_NAME} was enabled on a session-owned install - disabling it."
        systemctl disable --now "${SERVICE_NAME}" >/dev/null 2>&1 || true
    fi
    # The display-ready chain bridges the system service to the X display. A
    # session-owned GUI already has the session's display, so it is not needed.
    info "Display-ready chain not required in this mode."
else
    systemctl enable --now khptz-display-ready.path
    systemctl enable "${SERVICE_NAME}" >/dev/null
fi

find_xauthority() {
    local candidate=""
    for candidate in \
        "${XAUTHORITY:-}" \
        "${WIZARD_HOME}/.Xauthority" \
        "/run/user/${WIZARD_UID}/gdm/Xauthority"; do
        if [[ -n "${candidate}" && -r "${candidate}" ]]; then
            printf '%s\n' "${candidate}"
            return 0
        fi
    done
    if [[ -d "/run/user/${WIZARD_UID}" ]]; then
        find "/run/user/${WIZARD_UID}" -maxdepth 2 -type f \
            \( -name '*Xauthority*' -o -name '.mutter-Xwaylandauth.*' \) \
            -print -quit 2>/dev/null || true
    fi
}

# Display authorisation and the wait for khptz-control only apply when the
# system service owns the GUI. On a session-owned install the service is
# deliberately down, so waiting for it would abort the wizard's provisioning
# with "khptz-control did not become active" on a perfectly healthy machine.
if [[ "${GUI_MODE}" == "user" ]]; then
    info "GUI mode 'user': no display grant needed - the session owns its own display."
    info "The GUI starts from khptz-gui.service at the next desktop login."
else
    info "Authorising the current desktop display..."
    XAUTH_FILE="$(find_xauthority || true)"
    ENV_ARGS=(
        "HOME=${WIZARD_HOME}"
        "USER=${WIZARD_USER}"
        "LOGNAME=${WIZARD_USER}"
        "DISPLAY=${TARGET_DISPLAY}"
        "LANG=${UTF8_LOCALE}"
        "LC_ALL=${UTF8_LOCALE}"
    )
    [[ -n "${XAUTH_FILE}" ]] && ENV_ARGS+=("XAUTHORITY=${XAUTH_FILE}")

    if ! runuser -u "${WIZARD_USER}" -- env "${ENV_ARGS[@]}" "${DISPLAY_HELPER}"; then
        fail "The current desktop display could not be authorised. Keep the Pi desktop session open and retry setup."
    fi

    systemctl start khptz-display-ready.service

    info "Waiting for khptz-control to become active..."
    SERVICE_ACTIVE=false
    for ((attempt = 1; attempt <= 20; attempt++)); do
        if systemctl is-active --quiet "${SERVICE_NAME}"; then
            SERVICE_ACTIVE=true
            break
        fi
        sleep 1
    done
    if [[ "${SERVICE_ACTIVE}" != "true" ]]; then
        journalctl -u "${SERVICE_NAME}" -n 80 --no-pager || true
        fail "khptz-control did not become active after display authorisation."
    fi
fi

info "Running production diagnostics as khptz..."
DOCTOR_RESULT=0
runuser -u khptz -- env \
    LANG="${UTF8_LOCALE}" LC_ALL="${UTF8_LOCALE}" \
    PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
    "${KHPTZ_LAUNCHER}" doctor || DOCTOR_RESULT=$?

# Exit codes come from domain/doctor_outcome.py:
#   0  PASS                   · operational and correctly configured
#   10 READY_WITH_ADVISORIES  · operational; only non-blocking advice remains
#   20 CONFIG_REQUIRED        · runtime works, required configuration missing
#   30 FAIL                   · appliance cannot operate safely
#
# A blanket "reported advisories" for every non-zero code hid the FAIL case: a
# rc=30 (appliance unusable) was announced as a minor advisory. Classify it.
case "${DOCTOR_RESULT}" in
    0|10)
        info "Diagnostics: operational (rc=${DOCTOR_RESULT})." ;;
    20)
        warn "Diagnostics: configuration still required (rc=20)." \
             "Complete the setup wizard as ${WIZARD_USER}." ;;
    *)
        # Exit with a DISTINCT code, not the generic failure `fail` produces.
        #
        # The caller (scripts/provision_with_rpi_integration.sh) treats any
        # non-zero exit from this script as "integration failed" and rolls the
        # snapshot back - deleting config.yaml and BOTH password secrets the
        # operator just entered in the wizard. That is the right response to a
        # half-applied integration. It is the wrong response to this one: every
        # OS step above already succeeded, the configuration written is exactly
        # what was asked for, and what failed is a health verdict about the
        # ENVIRONMENT - an unreachable camera, a permission the appliance does
        # not have yet. Discarding the customer's answers for that makes them
        # retype two passwords and every camera address to reach the same
        # verdict, and it does it at the end of a wizard that looked successful.
        #
        # RC_DIAGNOSTICS_FATAL tells the caller: keep the configuration, report
        # the appliance as unhealthy, do not roll back. The .rpi-integrated
        # marker is deliberately NOT written, so the wizard reopens at the next
        # login and the operator can retry once the environment is fixed.
        warn "Diagnostics reported a fatal condition (rc=${DOCTOR_RESULT})."
        warn "The configuration was applied and has been KEPT."
        warn "The appliance cannot run yet - inspect the doctor output above."
        exit "${RC_DIAGNOSTICS_FATAL}" ;;
esac

info "Runtime finalisation complete."
info "Desktop user : ${WIZARD_USER}"
info "Display      : ${TARGET_DISPLAY}"
info "Backup       : ${BACKUP_DIR}"
info "GUI mode     : ${GUI_MODE}"
if [[ "${GUI_MODE}" == "user" ]]; then
    info "Launcher     : khptz-gui.service (starts at the next desktop login)"
else
    info "Service      : active"
fi
