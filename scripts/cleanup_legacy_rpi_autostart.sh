#!/usr/bin/env bash
# KH PTZ Control - Raspberry Pi autostart migration
#
# Removes obsolete pre-KHPTZ controller autostarts and installs the canonical KHPTZ
# desktop-to-systemd startup chain. The setup installer can call this script later.
# Legacy program files are never deleted; changed startup files are backed up.

set -Eeuo pipefail
IFS=$'\n\t'

readonly SCRIPT_VERSION="3"
readonly SERVICE="khptz-control.service"
readonly DISPLAY_HELPER="/usr/local/libexec/khptz-display-session"
readonly DISPLAY_PATH="khptz-display-ready.path"
readonly DISPLAY_SERVICE="khptz-display-ready.service"
readonly AUTOSTART_NAME="khptz-display-session.desktop"

DESKTOP_USER="${SUDO_USER:-}"
TARGET_DISPLAY="${DISPLAY:-:0}"
EXTRA_PATTERN=""
DRY_RUN=false
MATCHES=0
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/var/backups/khptz/autostart-migration-${TIMESTAMP}"
REPORT="${BACKUP_DIR}/report.txt"

info() { printf '[INFO]  %s\n' "$*"; }
warn() { printf '[WARN]  %s\n' "$*" >&2; }
fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'USAGE'
Usage: sudo bash scripts/cleanup_legacy_rpi_autostart.sh [options]

Options:
  --wizard-user USER      Human desktop user. Defaults to the user invoking sudo.
  --display DISPLAY       X11 display. Defaults to current DISPLAY or :0.
  --legacy-pattern REGEX  Extra case-insensitive regex identifying the old program.
  --dry-run               Report changes without applying them.
  -h, --help              Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --wizard-user) [[ $# -ge 2 ]] || fail "--wizard-user requires a value"; DESKTOP_USER="$2"; shift 2 ;;
        --display) [[ $# -ge 2 ]] || fail "--display requires a value"; TARGET_DISPLAY="$2"; shift 2 ;;
        --legacy-pattern) [[ $# -ge 2 ]] || fail "--legacy-pattern requires a value"; EXTRA_PATTERN="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "Unknown option: $1" ;;
    esac
done

[[ "$(id -u)" -eq 0 ]] || fail "Run this script with sudo."
[[ -n "${DESKTOP_USER}" ]] || fail "Could not detect the desktop user. Use --wizard-user USER."
[[ "${DESKTOP_USER}" != "root" && "${DESKTOP_USER}" != "khptz" ]] || fail "Use the human desktop user."
[[ "${TARGET_DISPLAY}" =~ ^:[0-9]+(\.[0-9]+)?$ ]] || fail "Invalid display: ${TARGET_DISPLAY}"
id "${DESKTOP_USER}" >/dev/null 2>&1 || fail "User does not exist: ${DESKTOP_USER}"
id khptz >/dev/null 2>&1 || fail "The khptz user does not exist. Run the installer first."

for command in cp find getent grep install mktemp pgrep runuser stat systemctl systemd-tmpfiles tee; do
    command -v "${command}" >/dev/null 2>&1 || fail "Required command missing: ${command}"
done

HOME_DIR="$(getent passwd "${DESKTOP_USER}" | cut -d: -f6)"
USER_GROUP="$(id -gn "${DESKTOP_USER}")"
USER_UID="$(id -u "${DESKTOP_USER}")"
AUTOSTART_DIR="${HOME_DIR}/.config/autostart"
AUTOSTART_FILE="${AUTOSTART_DIR}/${AUTOSTART_NAME}"
[[ -d "${HOME_DIR}" ]] || fail "Home directory not found for ${DESKTOP_USER}."

# Which launcher owns the GUI on this install (#885). Recorded by install.sh;
# installs predating the flag were all system mode, so that is the fallback.
# This decides which replacement must be in place before the old startup is
# removed — requiring the display-ready chain under --gui-mode user would abort
# a perfectly healthy appliance.
_state_lib="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/install_state.sh"
if [[ -r "${_state_lib}" ]]; then
    # shellcheck source=/dev/null
    source "${_state_lib}"
else
    khptz_gui_mode() { printf 'system\n'; }
fi
GUI_MODE="$(khptz_gui_mode)"
readonly GUI_MODE

# Never remove the old startup unless the replacement is ready to be activated.
[[ -f /opt/khptz/main.py ]] || fail "KHPTZ is not installed at /opt/khptz/main.py."

if [[ "${GUI_MODE}" == "user" ]]; then
    # Session-owned GUI: the launcher is the user unit plus its autostart shim.
    # khptz-control.service is deliberately disabled here, so do not require it.
    [[ -f /etc/systemd/user/khptz-gui.service ]] \
        || fail "GUI mode is 'user' but /etc/systemd/user/khptz-gui.service is missing.
  Re-run: sudo bash install_khptz_rpi.sh --wizard-user ${DESKTOP_USER} --gui-mode user"
    [[ -x /usr/local/libexec/khptz-gui-session ]] \
        || fail "GUI mode is 'user' but the session launcher is missing.
  Re-run: sudo bash install_khptz_rpi.sh --wizard-user ${DESKTOP_USER} --gui-mode user"
    grep -Fq '/opt/khptz/main.py' /etc/systemd/user/khptz-gui.service \
        || fail "khptz-gui.service does not launch /opt/khptz/main.py."
else
    [[ -f /etc/systemd/system/khptz-control.service ]] || fail "${SERVICE} is not installed. Run repair v3 first."
    [[ -x "${DISPLAY_HELPER}" ]] || fail "${DISPLAY_HELPER} is missing. Run repair v3 first."
    [[ -f "/etc/systemd/system/${DISPLAY_PATH}" ]] || fail "${DISPLAY_PATH} is missing. Run repair v3 first."
    [[ -f "/etc/systemd/system/${DISPLAY_SERVICE}" ]] || fail "${DISPLAY_SERVICE} is missing. Run repair v3 first."
    grep -Fq '/opt/khptz/main.py' /etc/systemd/system/khptz-control.service \
        || fail "${SERVICE} does not launch /opt/khptz/main.py."
fi

if [[ "${DRY_RUN}" == "true" ]]; then
    REPORT="/tmp/khptz-autostart-migration-${TIMESTAMP}.txt"
    : > "${REPORT}"
else
    install -d -m 0750 -o khptz -g khptz "${BACKUP_DIR}"
    : > "${REPORT}"
fi

backup() {
    [[ "${DRY_RUN}" == "true" ]] && return 0
    if [[ -e "$1" || -L "$1" ]]; then
        cp -a --parents -- "$1" "${BACKUP_DIR}/"
    fi
    return 0
}

record() { printf '%s\n' "$*" | tee -a "${REPORT}" >/dev/null; info "$*"; }

is_canonical() {
    local text="${1,,}"
    [[ "${text}" == *"${DISPLAY_HELPER,,}"* \
        || "${text}" == *"${AUTOSTART_NAME,,}"* \
        || "${text}" == *"khptz-display-ready"* \
        || "${text}" == *"khptz-control.service"* \
        || "${text}" == *"khptz-provision"* \
        || "${text}" == *"/usr/local/bin/khptz"* \
        || "${text}" == *"khptz-adaptive"* \
        || "${text}" == *"repair_rpi_runtime"* \
        || "${text}" == *"cleanup_legacy_rpi_autostart"* \
        || "${text}" == *"/run/khptz"* \
        || "${text}" == *"khptz-gui.service"* \
        || "${text}" == *"khptz-gui.desktop"* \
        || "${text}" == *"khptz-gui-session"* ]]
}

is_conflict() {
    local text="$1"
    local lower="${text,,}"
    is_canonical "${text}" && return 1

    # A direct desktop launch of the installed GUI would create a second instance.
    [[ "${lower}" == *"/opt/khptz/main.py"* ]] && return 0

    # Known names used by previous PTZ controller generations. The current
    # install user's home prefix is stripped first so /home/khptz itself never
    # counts as a product-name match.
    local stripped="${lower//${HOME_DIR,,}/}"
    [[ "${stripped}" =~ khptz|khptz_controls|hallptz|hallptz_controls|ptz[_[:space:]-]?(control|controller)|camera[_[:space:]-]?controller ]] && return 0

    [[ -n "${EXTRA_PATTERN}" ]] \
        && printf '%s\n' "${text}" | grep -Eiq -- "${EXTRA_PATTERN}" \
        && return 0

    # Conservative fallback: require a home-directory script plus a camera term.
    [[ "${lower}" == *"${HOME_DIR,,}/"* \
        && "${lower}" =~ /(main|app|run)\.py|/(start|launch|run)\.sh \
        && "${stripped}" =~ ptz|visca|atem|camera|joystick|hallptz|khptz ]]
}

quarantine_desktop_dir() {
    local directory="$1" file content destination
    [[ -d "${directory}" ]] || return 0
    while IFS= read -r -d '' file; do
        [[ "${file}" == "${AUTOSTART_FILE}" ]] && continue
        content="$(cat "${file}" 2>/dev/null || true)"
        is_conflict "${file}"$'\n'"${content}" || continue
        ((MATCHES += 1))
        if [[ "${DRY_RUN}" == "true" ]]; then
            record "Would quarantine desktop autostart: ${file}"
        else
            backup "${file}"
            destination="${file}.disabled-by-khptz-${TIMESTAMP}"
            mv -- "${file}" "${destination}"
            record "Quarantined desktop autostart: ${file} -> ${destination}"
        fi
    done < <(find "${directory}" -maxdepth 1 \( -type f -o -type l \) -name '*.desktop' -print0 2>/dev/null)
}

rewrite_lines() {
    local file="$1" tmp line changed=false mode owner group
    [[ -f "${file}" ]] || return 0
    tmp="$(mktemp)"
    mode="$(stat -c '%a' "${file}")"; owner="$(stat -c '%u' "${file}")"; group="$(stat -c '%g' "${file}")"
    while IFS= read -r line || [[ -n "${line}" ]]; do
        if [[ ! "${line}" =~ ^[[:space:]]*# && ! "${line}" =~ ^[[:space:]]*\; ]] && is_conflict "${line}"; then
            ((MATCHES += 1)); changed=true
            if [[ "${DRY_RUN}" == "true" ]]; then
                printf '%s\n' "${line}" >> "${tmp}"
                record "Would disable startup line in ${file}: ${line}"
            else
                printf '# disabled by KHPTZ autostart migration %s: %s\n' "${TIMESTAMP}" "${line}" >> "${tmp}"
                record "Disabled startup line in ${file}: ${line}"
            fi
        else
            printf '%s\n' "${line}" >> "${tmp}"
        fi
    done < "${file}"
    if [[ "${changed}" == "true" && "${DRY_RUN}" != "true" ]]; then
        backup "${file}"; cat "${tmp}" > "${file}"; chown "${owner}:${group}" "${file}"; chmod "${mode}" "${file}"
    fi
    rm -f "${tmp}"
}

scan_cron() {
    # #892 lists cron @reboot jobs as a startup mechanism. Only the desktop
    # user's crontab is touched: root's may legitimately carry site automation,
    # so it is reported but never rewritten.
    local current filtered changed=false line
    command -v crontab >/dev/null 2>&1 || return 0

    current="$(crontab -u "${DESKTOP_USER}" -l 2>/dev/null || true)"
    [[ -n "${current}" ]] || return 0

    filtered="$(mktemp)"
    while IFS= read -r line || [[ -n "${line}" ]]; do
        if [[ ! "${line}" =~ ^[[:space:]]*# ]] && is_conflict "${line}"; then
            ((MATCHES += 1)); changed=true
            if [[ "${DRY_RUN}" == "true" ]]; then
                printf '%s\n' "${line}" >> "${filtered}"
                record "Would disable cron entry for ${DESKTOP_USER}: ${line}"
            else
                printf '# disabled by KHPTZ autostart migration %s: %s\n' "${TIMESTAMP}" "${line}" >> "${filtered}"
                record "Disabled cron entry for ${DESKTOP_USER}: ${line}"
            fi
        else
            printf '%s\n' "${line}" >> "${filtered}"
        fi
    done <<< "${current}"

    if [[ "${changed}" == "true" && "${DRY_RUN}" != "true" ]]; then
        # Back up the original crontab as a file so it can be restored verbatim.
        printf '%s\n' "${current}" > "${BACKUP_DIR}/crontab-${DESKTOP_USER}.txt"
        crontab -u "${DESKTOP_USER}" "${filtered}" \
            || warn "Could not rewrite the crontab for ${DESKTOP_USER}."
    fi
    rm -f "${filtered}"

    # Root and system crontabs: report only.
    local root_cron
    root_cron="$(crontab -u root -l 2>/dev/null || true)"
    while IFS= read -r line; do
        [[ -n "${line}" ]] || continue
        [[ "${line}" =~ ^[[:space:]]*# ]] && continue
        is_conflict "${line}" || continue
        ((MATCHES += 1))
        record "REVIEW MANUALLY - legacy-looking entry in root's crontab: ${line}"
    done <<< "${root_cron}"
}

scan_shell_profiles() {
    # #892 lists shell profile startup commands. These files also hold ordinary
    # user configuration, so conflicting lines are commented out in place by
    # rewrite_lines (which backs the file up first) rather than removed.
    local file
    for file in \
        "${HOME_DIR}/.bashrc" "${HOME_DIR}/.bash_profile" "${HOME_DIR}/.profile" \
        "${HOME_DIR}/.xsessionrc" "${HOME_DIR}/.xinitrc" "${HOME_DIR}/.xsession"; do
        rewrite_lines "${file}"
    done
}

quarantine_user_services() {
    local directory="${HOME_DIR}/.config/systemd/user" file unit content destination
    [[ -d "${directory}" ]] || return 0
    while IFS= read -r -d '' file; do
        content="$(cat "${file}" 2>/dev/null || true)"
        is_conflict "${file}"$'\n'"${content}" || continue
        unit="$(basename "${file}")"; ((MATCHES += 1))
        if [[ "${DRY_RUN}" == "true" ]]; then
            record "Would disable user service: ${unit}"
        else
            backup "${file}"
            runuser -u "${DESKTOP_USER}" -- env XDG_RUNTIME_DIR="/run/user/${USER_UID}" \
                systemctl --user disable --now "${unit}" >/dev/null 2>&1 || true
            destination="${file}.disabled-by-khptz-${TIMESTAMP}"; mv -- "${file}" "${destination}"
            record "Disabled user service: ${unit}"
        fi
    done < <(find "${directory}" -maxdepth 1 -type f -name '*.service' -print0 2>/dev/null)
}

disable_system_services() {
    local unit details fragment destination
    while read -r unit _; do
        [[ -n "${unit}" ]] || continue
        case "${unit}" in khptz-control.service|khptz-display-ready.service|khptz-provision.service) continue ;; esac
        details="$(systemctl show "${unit}" -p Description -p ExecStart --no-pager 2>/dev/null || true)"
        details+=$'\n'"$(systemctl cat "${unit}" --no-pager 2>/dev/null || true)"
        is_conflict "${unit}"$'\n'"${details}" || continue
        ((MATCHES += 1))
        if [[ "${DRY_RUN}" == "true" ]]; then
            record "Would disable system service: ${unit}"
        else
            fragment="$(systemctl show "${unit}" -p FragmentPath --value 2>/dev/null || true)"
            [[ -n "${fragment}" ]] && backup "${fragment}"
            systemctl disable --now "${unit}" >/dev/null 2>&1 || warn "Could not stop ${unit}."
            if [[ "${fragment}" == /etc/systemd/system/* && -f "${fragment}" ]]; then
                destination="${fragment}.disabled-by-khptz-${TIMESTAMP}"; mv -- "${fragment}" "${destination}"
            else
                systemctl mask "${unit}" >/dev/null 2>&1 || warn "Could not mask ${unit}."
            fi
            record "Disabled system service: ${unit}"
        fi
    done < <(systemctl list-unit-files --type=service --no-legend --no-pager 2>/dev/null || true)
}

# True when PID belongs to a unit KHPTZ itself manages.
#
# Under --gui-mode user the supported GUI runs as the DESKTOP user with the
# command line "/usr/bin/python3 /opt/khptz/main.py" — which is_conflict matches
# on purpose, because a hand-rolled desktop launcher of that same command is a
# second instance. The cgroup is what tells the two apart: one is inside
# khptz-gui.service, the other is not. Without this check, reopening the wizard
# on a session-owned appliance killed the very GUI this script exists to
# guarantee (systemd restarted it, but the operator saw the screen die
# mid-setup).
_pid_is_khptz_managed() {
    local pid="$1" cgroup=""
    [[ "${pid}" =~ ^[0-9]+$ ]] || return 1
    [[ -r "/proc/${pid}/cgroup" ]] || return 1
    cgroup="$(tr -d ' ' < "/proc/${pid}/cgroup" 2>/dev/null || true)"
    [[ "${cgroup}" == *"khptz-gui.service"* || "${cgroup}" == *"khptz-control.service"* ]]
}

stop_conflicts() {
    local row pid command_line
    local -a pids=()
    while IFS= read -r row; do
        [[ -n "${row}" ]] || continue
        pid="${row%% *}"; command_line="${row#* }"; [[ "${pid}" =~ ^[0-9]+$ ]] || continue
        is_conflict "${command_line}" || continue
        if _pid_is_khptz_managed "${pid}"; then
            record "Kept KHPTZ-managed process ${pid}: ${command_line}"
            continue
        fi
        ((MATCHES += 1))
        if [[ "${DRY_RUN}" == "true" ]]; then record "Would stop process ${pid}: ${command_line}"
        else pids+=("${pid}"); record "Stopping process ${pid}: ${command_line}"; fi
    done < <(pgrep -u "${DESKTOP_USER}" -af '.' 2>/dev/null || true)
    [[ "${DRY_RUN}" == "true" || ${#pids[@]} -eq 0 ]] && return 0
    kill "${pids[@]}" 2>/dev/null || true; sleep 2
    for pid in "${pids[@]}"; do kill -0 "${pid}" 2>/dev/null && kill -KILL "${pid}" 2>/dev/null || true; done
}

install_khptz_startup() {
    if [[ "${GUI_MODE}" == "user" ]]; then
        # The session-owned GUI is activated by install.sh (user unit + XDG
        # autostart). There is no display-ready chain to enable here, and
        # installing the xhost bridge would add a second, pointless launcher.
        local session_autostart="${AUTOSTART_DIR}/khptz-gui.desktop"
        if [[ -f "${session_autostart}" ]]; then
            record "Session-owned GUI autostart present: ${session_autostart}"
        else
            warn "GUI mode is 'user' but ${session_autostart} is missing."
            warn "The GUI will not start at login. Re-run:"
            warn "  sudo bash install_khptz_rpi.sh --wizard-user ${DESKTOP_USER} --gui-mode user"
        fi
        return 0
    fi

    if [[ "${DRY_RUN}" == "true" ]]; then
        record "Would install ${AUTOSTART_FILE} and enable ${SERVICE} + ${DISPLAY_PATH}."
        return 0
    fi
    install -d -m 0755 -o "${DESKTOP_USER}" -g "${USER_GROUP}" "${AUTOSTART_DIR}"
    backup "${AUTOSTART_FILE}"
    cat > "${AUTOSTART_FILE}" <<EOF_DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=KHPTZ display session
Comment=Start KHPTZ after the Raspberry Pi desktop display is ready
TryExec=${DISPLAY_HELPER}
Exec=${DISPLAY_HELPER}
Terminal=false
NoDisplay=true
Hidden=false
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF_DESKTOP
    chown "${DESKTOP_USER}:${USER_GROUP}" "${AUTOSTART_FILE}"; chmod 0644 "${AUTOSTART_FILE}"
    backup "${AUTOSTART_DIR}/khptz-display-permission.desktop"
    rm -f -- "${AUTOSTART_DIR}/khptz-display-permission.desktop"
    systemd-tmpfiles --create /etc/tmpfiles.d/khptz.conf
    systemctl daemon-reload
    systemctl enable "${SERVICE}" >/dev/null
    systemctl enable --now "${DISPLAY_PATH}" >/dev/null
    record "Installed canonical KHPTZ desktop autostart and enabled its systemd chain."
}

find_xauthority() {
    local candidate
    for candidate in "${XAUTHORITY:-}" "${HOME_DIR}/.Xauthority" "/run/user/${USER_UID}/gdm/Xauthority"; do
        [[ -n "${candidate}" && -r "${candidate}" ]] && { printf '%s\n' "${candidate}"; return 0; }
    done
    find "/run/user/${USER_UID}" -maxdepth 2 -type f \
        \( -name '*Xauthority*' -o -name '.mutter-Xwaylandauth.*' \) -print -quit 2>/dev/null || true
}

start_khptz_now() {
    local xauth="" active=false
    local -a environment=("HOME=${HOME_DIR}" "USER=${DESKTOP_USER}" "LOGNAME=${DESKTOP_USER}" "DISPLAY=${TARGET_DISPLAY}")
    [[ "${DRY_RUN}" == "true" ]] && return 0
    if [[ "${GUI_MODE}" == "user" ]]; then
        # The GUI belongs to the desktop session's own systemd manager, which
        # this root context cannot meaningfully drive. It starts at the next
        # login via the autostart entry.
        record "GUI mode 'user': KHPTZ starts at the next desktop login."
        return 0
    fi
    xauth="$(find_xauthority)"; [[ -n "${xauth}" ]] && environment+=("XAUTHORITY=${xauth}")
    if runuser -u "${DESKTOP_USER}" -- env "${environment[@]}" "${DISPLAY_HELPER}"; then
        systemctl start "${DISPLAY_SERVICE}"
        for ((attempt=1; attempt<=20; attempt++)); do
            systemctl is-active --quiet "${SERVICE}" && { active=true; break; }; sleep 1
        done
        [[ "${active}" == "true" ]] || { journalctl -u "${SERVICE}" -n 60 --no-pager || true; fail "${SERVICE} did not start."; }
        record "KHPTZ is active through the canonical display-ready chain."
    else
        warn "Current display could not be authorised; reboot will test the installed autostart."
    fi
}

verify() {
    [[ "${DRY_RUN}" == "true" ]] && return 0
    if [[ "${GUI_MODE}" == "user" ]]; then
        # Exactly one launcher must remain. The system service staying enabled
        # alongside the session GUI is the two-competing-GUIs failure (#885).
        [[ -f /etc/systemd/user/khptz-gui.service ]] || fail "khptz-gui.service is missing."
        [[ -x /usr/local/libexec/khptz-gui-session ]] || fail "The session launcher is missing."
        if systemctl is-enabled --quiet "${SERVICE}" 2>/dev/null; then
            fail "${SERVICE} is still enabled while the GUI is session-owned.
  Two GUIs would compete for the cameras. Disable it with:
    sudo systemctl disable --now ${SERVICE}"
        fi
        return 0
    fi
    grep -Fqx "Exec=${DISPLAY_HELPER}" "${AUTOSTART_FILE}" || fail "Canonical desktop autostart is incorrect."
    systemctl is-enabled --quiet "${SERVICE}" || fail "${SERVICE} is not enabled."
    systemctl is-enabled --quiet "${DISPLAY_PATH}" || fail "${DISPLAY_PATH} is not enabled."
}

info "KHPTZ autostart migration v${SCRIPT_VERSION} for ${DESKTOP_USER} on ${TARGET_DISPLAY}"
quarantine_desktop_dir "${HOME_DIR}/.config/autostart"
quarantine_desktop_dir "/etc/xdg/autostart"
for directory in "${HOME_DIR}/.config/lxsession" "/etc/xdg/lxsession"; do
    while IFS= read -r -d '' file; do rewrite_lines "${file}"; done \
        < <(find "${directory}" -type f -name autostart -print0 2>/dev/null || true)
done
for file in \
    "${HOME_DIR}/.config/openbox/autostart" "/etc/xdg/openbox/autostart" \
    "${HOME_DIR}/.config/labwc/autostart" "/etc/xdg/labwc/autostart" \
    "${HOME_DIR}/.config/wayfire.ini" "/etc/wayfire.ini" "/etc/rc.local"; do
    rewrite_lines "${file}"
done
scan_shell_profiles
scan_cron
quarantine_user_services
disable_system_services
stop_conflicts
install_khptz_startup
[[ "${DRY_RUN}" == "true" ]] || { systemctl daemon-reload; runuser -u "${DESKTOP_USER}" -- env XDG_RUNTIME_DIR="/run/user/${USER_UID}" systemctl --user daemon-reload >/dev/null 2>&1 || true; }
start_khptz_now
verify

[[ "${MATCHES}" -gt 0 ]] || warn "No recognised old startup was found; use --legacy-pattern when its name is unusual."
info "Conflicting entries matched: ${MATCHES}"
info "Mode       : $([[ "${DRY_RUN}" == "true" ]] && printf 'dry-run' || printf 'applied')"
info "Report     : ${REPORT}"
if [[ "${DRY_RUN}" != "true" ]]; then
    info "Backup     : ${BACKUP_DIR}"
    info "Next action: reboot and confirm that only KHPTZ opens."
fi
