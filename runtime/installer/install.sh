#!/usr/bin/env bash
# install.sh — KH PTZ Control installer for Raspberry Pi
#
# Usage:
#   sudo bash install.sh [--dev] [--atem] [--check]
#
# Modes:
#   (default)  Product install: dedicated 'khptz' OS user, /opt/khptz layout.
#   --dev      Developer install: uses current $USER, /home/$USER/khptz layout.
#              Safe for git-checkout development environments.
#   --atem     Install ATEM optional dependencies (requirements-atem.txt).
#   --check    Dry-run: validate Pi readiness without writing any files.
#              Outputs a PASS/WARN/FAIL report. Exits non-zero on blocking failures.
#   --skip-pre-update-backup
#              Skip the automatic pre-update backup taken before replacing an
#              existing product install. The backup failing aborts the update;
#              this flag is the only way past that guard.
#
# Product layout (default):
#   /opt/khptz/          app code     (root:khptz, mode 0750 — service user reads, cannot write)
#   /etc/khptz/          config       (root:khptz, setgid, admin-write only)
#   /var/lib/khptz/      runtime data (khptz:khptz)
#   /var/log/khptz/      logs         (khptz:khptz)
#   /var/backups/khptz/  backups      (khptz:khptz)
#
# See docs/RUNTIME_PATH_CONTRACT.md for full path ownership contract.
#
# Safety rules:
#   - Idempotent: safe to run more than once.
#   - Never deletes existing config or customer data.
#   - Creates khptz OS user if it does not already exist.
#   - Fails fast if required tools are missing.

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────

DEV_MODE=false
INSTALL_ATEM=false
CHECK_MODE=false
SHOW_CHECK_NEXT_ACTION=true
SKIP_PRE_UPDATE_BACKUP=false
WIZARD_USER=""
# Which process owns the GUI (#885).
#   system — khptz-control.service runs it as the 'khptz' system user, bridged to
#            the display by the scoped xhost helper. The validated default.
#   user   — khptz-gui.service runs it inside the desktop session, inheriting
#            DISPLAY/XAUTHORITY/XDG_RUNTIME_DIR/D-Bus with no display grant.
# Exactly one is ever active: installing either removes the other.
GUI_MODE="system"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev)   DEV_MODE=true; shift ;;
        --atem)  INSTALL_ATEM=true; shift ;;
        --check) CHECK_MODE=true; shift ;;
        --skip-pre-update-backup) SKIP_PRE_UPDATE_BACKUP=true; shift ;;
        --no-check-next-action) SHOW_CHECK_NEXT_ACTION=false; shift ;;
        --wizard-user)
            [[ $# -ge 2 && -n "$2" && "$2" != -* ]] \
                || { echo "--wizard-user requires a username (e.g. --wizard-user pi)" >&2; exit 1; }
            WIZARD_USER="$2"; shift 2 ;;
        --gui-mode)
            [[ $# -ge 2 ]] || { echo "--gui-mode requires a value" >&2; exit 1; }
            GUI_MODE="$2"; shift 2
            [[ "${GUI_MODE}" == "system" || "${GUI_MODE}" == "user" ]] \
                || { echo "Invalid --gui-mode '${GUI_MODE}' (expected: system | user)" >&2; exit 1; }
            ;;
        --gui-mode=*)
            GUI_MODE="${1#*=}"; shift
            [[ "${GUI_MODE}" == "system" || "${GUI_MODE}" == "user" ]] \
                || { echo "Invalid --gui-mode '${GUI_MODE}' (expected: system | user)" >&2; exit 1; }
            ;;
        --help)
            echo "Usage: sudo bash install.sh [--dev] [--atem] [--check] [--wizard-user USER] [--gui-mode MODE]"
            echo "  (no flags)       Product install — dedicated khptz user, /opt/khptz layout"
            echo "  --dev            Developer install — current user, /home/USER/khptz layout"
            echo "  --atem           Install ATEM optional dependencies (requires pip3)"
            echo "  --check          Dry-run: validate Pi readiness without writing any files"
            echo "  --no-check-next-action  With --check: caller supplies the next action"
            echo "  --wizard-user U  Desktop user that owns the setup-wizard provisioning"
            echo "                   channel (/run/khptz). Defaults to \$SUDO_USER."
            echo "  --gui-mode M     system (default) = GUI runs as the khptz service user;"
            echo "                   user = GUI runs inside the desktop session (#885)."
            echo "  --skip-pre-update-backup"
            echo "                   Skip the automatic backup taken before replacing an"
            echo "                   existing product install (not recommended)."
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ "${SHOW_CHECK_NEXT_ACTION}" == "false" && "${CHECK_MODE}" != "true" ]]; then
    echo "--no-check-next-action requires --check" >&2
    exit 1
fi

# The setup wizard runs in the desktop session as this user; it owns the
# /run/khptz provisioning channel. Default to the human who invoked sudo.
WIZARD_USER="${WIZARD_USER:-${SUDO_USER:-}}"

if [[ "${DEV_MODE}" == "true" ]]; then
    APP_USER="${SUDO_USER:-${USER}}"
    INSTALL_DIR="/home/${APP_USER}/khptz"
    CONFIG_DIR="/home/${APP_USER}/khptz"
    DATA_DIR="/home/${APP_USER}/.config/khptz"
    LOG_DIR="/var/log/khptz"
    BACKUP_DIR="/var/backups/khptz"
else
    APP_USER="khptz"
    INSTALL_DIR="/opt/khptz"
    CONFIG_DIR="/etc/khptz"
    DATA_DIR="/var/lib/khptz"
    LOG_DIR="/var/log/khptz"
    BACKUP_DIR="/var/backups/khptz"
fi

# Administrator credentials never share the GUI-writable runtime directory.
ADMIN_SECRET_DIR="${CONFIG_DIR}/secrets"
# Product launchers use this exact interpreter, regardless of sudo's PATH.
# Dev remains explicitly PATH-based, matching its existing launcher contract.
if [[ "${DEV_MODE}" == "true" ]]; then
    PYTHON_BIN="python3"
else
    PYTHON_BIN="/usr/bin/python3"
fi

SERVICE_NAME="khptz-control"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Helpers ───────────────────────────────────────────────────────────────────

info()  { echo "[INFO]  $*"; }

# Same sanitizer as runtime/installer/rollback.sh: make an installed ref safe
# for use in a backup filename.
sanitize_ref() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }

# Installed as an EXIT trap while a previously-running service is stopped for
# the update. On any failure it ATTEMPTS to restart the service — the copy may
# be half-done (rsync --delete is not atomic), so this restores availability,
# not a guaranteed clean rollback; the operator should re-run the install.
_restart_stopped_service_on_abort() {
    local rc=$?
    trap - EXIT
    if [[ "${SERVICE_WAS_ACTIVE:-0}" == "1" && "${GUI_MODE}" != "user" ]]; then
        echo "[ERROR] install failed (exit ${rc}) — attempting to restart ${SERVICE_NAME} (was running before the install)" >&2
        systemctl start "${SERVICE_NAME}" 2>/dev/null \
            || echo "[ERROR] restart FAILED — ${SERVICE_NAME} is DOWN; start it by hand: systemctl start ${SERVICE_NAME}" >&2
    fi
}
warn()  { echo "[WARN]  $*" >&2; }
error() { echo "[ERROR] $*" >&2; exit 1; }

# Remedy for any missing repo file: the checkout on the install media is
# incomplete (partial copy to the pendrive/SD clone). Named once so every
# template-missing message gives the same concrete next step on site.
INCOMPLETE_CHECKOUT_REMEDY="the repository checkout is incomplete — re-clone it (or restore the missing file from a clean clone) and re-run"

require_command() {
    local cmd="$1"
    local apt_hint="${2:-}"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        if [[ -n "$apt_hint" ]]; then
            error "Required command not found: $cmd — install with: sudo apt install -y $apt_hint"
        else
            error "Required command not found: $cmd"
        fi
    fi
}

require_pyqt5() {
    if ! "${PYTHON_BIN}" -c "import PyQt5" 2>/dev/null; then
        error "PyQt5 not available — install with: sudo apt install -y python3-pyqt5 python3-pyqt5.qtsvg"
    fi
    if ! "${PYTHON_BIN}" -c "from PyQt5 import QtSvg" 2>/dev/null; then
        error "PyQt5.QtSvg not available — required by the GUI. Install with: sudo apt install -y python3-pyqt5.qtsvg"
    fi
}

# A hard runtime import that product mode never installs (requirements-rpi.txt
# lists no pip packages), so it can only come from apt. Checking it here is the
# difference between failing on this line with an apt hint and reporting a
# successful install that cannot start: config/loader.py imports the module at
# module scope, so main.py, `khptz doctor` and runtime/rpi_post_provision.py all
# raise ModuleNotFoundError the first time the appliance is actually used.
require_python_module() {
    local module="$1"
    local apt_hint="$2"
    if ! "${PYTHON_BIN}" -c "import ${module}" 2>/dev/null; then
        error "Required Python module not available: ${module} — install with: sudo apt install -y ${apt_hint}"
    fi
}

# ── Pre-flight checks ─────────────────────────────────────────────────────────

info "Checking prerequisites..."
[[ "$(id -u)" -eq 0 ]] || error "This script must be run as root (use sudo)"

require_command "${PYTHON_BIN}" python3
require_command git      git
require_command rsync    rsync
require_command systemctl

# Optional ATEM installs use pip even in product mode. Check it before the
# read-only readiness exit and before creating users or directories.
if [[ "${DEV_MODE}" == "true" ]]; then
    require_command pip3 python3-pip
elif [[ "${INSTALL_ATEM}" == "true" ]]; then
    require_python_module pip python3-pip
fi

if [[ "${DEV_MODE}" == "false" && "${CHECK_MODE}" == "false" ]] \
    && [[ -e "${DATA_DIR}/admin.enc" || -L "${DATA_DIR}/admin.enc" ]]; then
    error "Legacy admin secret requires an offline privileged reset; see docs/HARDENING2.md. Installation aborted before changes."
fi

require_pyqt5
require_python_module yaml python3-yaml

PYTHON_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
info "Python version: ${PYTHON_VERSION}"
info "Install mode  : $([[ ${DEV_MODE} == true ]] && echo 'developer' || echo 'product')"
info "App user      : ${APP_USER}"
info "Install dir   : ${INSTALL_DIR}"

# ── Check mode (--check / dry-run) ────────────────────────────────────────────

if [[ "${CHECK_MODE}" == "true" ]]; then
    info ""
    info "=== KHPTZ Installer Readiness Check ==="
    info ""
    _check_fails=0

    _chk_pass() { echo "[PASS] $*"; }
    _chk_warn() { echo "[WARN] $*"; }
    _chk_fail() { echo "[FAIL] $*"; (( _check_fails++ )) || true; }

    # OS / arch
    if [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        _chk_pass "OS: ${PRETTY_NAME:-unknown}"
    else
        _chk_warn "OS: /etc/os-release not found (may not be Raspberry Pi OS)"
    fi
    _chk_pass "Architecture: $(uname -m)"

    # Python version
    _py_major="$("${PYTHON_BIN}" -c 'import sys; print(sys.version_info.major)')"
    _py_minor="$("${PYTHON_BIN}" -c 'import sys; print(sys.version_info.minor)')"
    # Two supported targets: 3.9.2 (Bullseye legacy) and 3.11 (Bookworm
    # installation target, container-rehearsed). See docs/RPI_RUNTIME_BASELINE.md.
    if [[ "${_py_major}" -eq 3 && "${_py_minor}" -eq 9 ]]; then
        _chk_pass "Python ${PYTHON_VERSION} (3.9.x — supported legacy target: Bullseye 3.9.2)"
    elif [[ "${_py_major}" -eq 3 && "${_py_minor}" -eq 11 ]]; then
        _chk_pass "Python ${PYTHON_VERSION} (3.11 — supported installation target: Bookworm; physical validation pending)"
    elif [[ "${_py_major}" -eq 3 && "${_py_minor}" -gt 9 ]]; then
        _chk_warn "Python ${PYTHON_VERSION} (NOT a validated target; supported targets are 3.9.2 on Bullseye and 3.11 on Bookworm)"
    else
        _chk_fail "Python ${PYTHON_VERSION} is too old (3.9 minimum; supported targets are 3.9.2 on Bullseye and 3.11 on Bookworm)"
    fi

    # Service template
    SERVICE_TEMPLATE="${REPO_ROOT}/runtime/systemd/khptz-control.service"
    if [[ -f "${SERVICE_TEMPLATE}" ]]; then
        _chk_pass "Systemd service template: ${SERVICE_TEMPLATE}"
    else
        _chk_fail "Systemd service template missing: ${SERVICE_TEMPLATE} — ${INCOMPLETE_CHECKOUT_REMEDY}"
    fi

    # Config template
    CONFIG_STARTER="${REPO_ROOT}/config/defaults/starter.yaml"
    if [[ -f "${CONFIG_STARTER}" ]]; then
        _chk_pass "Starter config template: ${CONFIG_STARTER}"
    else
        _chk_warn "Starter config template missing: ${CONFIG_STARTER}"
    fi

    # Existing installation / customer data presence
    for _dir in "${INSTALL_DIR}" "${CONFIG_DIR}" "${DATA_DIR}" "${LOG_DIR}" "${BACKUP_DIR}"; do
        if [[ -d "${_dir}" ]]; then
            _chk_warn "Existing path detected: ${_dir} (re-install will preserve config and data)"
        else
            _chk_pass "Path not yet created: ${_dir}"
        fi
    done

    # Existing config
    if [[ -f "${CONFIG_DIR}/config.yaml" ]]; then
        _chk_warn "Existing config.yaml found at ${CONFIG_DIR}/config.yaml — will NOT be overwritten"
    fi

    # DISPLAY / session hints
    if [[ -n "${DISPLAY:-}" ]]; then
        _chk_pass "DISPLAY=${DISPLAY}"
    else
        _chk_warn "DISPLAY not set — Qt app needs a display session at runtime"
    fi

    # Desktop session type (product installs only). Both GUI launchers force
    # QT_QPA_PLATFORM=xcb on DISPLAY=:0, so they need an X11 session. Bookworm
    # and Trixie boot to Wayland (wayfire/labwc) by default; there the screen
    # stays dark even when every other check passes. docs/INSTALL_RPI.md
    # requires switching to X11 before installing — enforce it at the gate
    # rather than discovering it at the first boot on site.
    if [[ "${DEV_MODE}" != "true" ]]; then
        # Select the desktop user's ACTIVE graphical session, never just the
        # first one listed: a background session of the other type (leftover
        # Wayland next to the X11 desktop, or vice versa) must not mask the
        # session that actually drives the touchscreen. Active=yes wins;
        # otherwise fall back to a graphical session in State=active (covers a
        # locked screen); anything else is uninspectable here.
        _session_type=""
        _state_type=""
        if command -v loginctl >/dev/null 2>&1 && [[ -n "${WIZARD_USER}" ]]; then
            for _sid in $(loginctl list-sessions --no-legend 2>/dev/null \
                          | awk -v u="${WIZARD_USER}" '$3 == u { print $1 }' || true); do
                _type="$(loginctl show-session "${_sid}" --property=Type --value 2>/dev/null || true)"
                [[ "${_type}" == "x11" || "${_type}" == "wayland" ]] || continue
                if [[ "$(loginctl show-session "${_sid}" --property=Active --value 2>/dev/null || true)" == "yes" ]]; then
                    _session_type="${_type}"
                    break
                fi
                if [[ -z "${_state_type}" ]] \
                   && [[ "$(loginctl show-session "${_sid}" --property=State --value 2>/dev/null || true)" == "active" ]]; then
                    _state_type="${_type}"
                fi
            done
            [[ -n "${_session_type}" ]] || _session_type="${_state_type}"
        fi
        case "${_session_type}" in
            x11)
                _chk_pass "Desktop session: X11 (required by the GUI units)" ;;
            wayland)
                _chk_fail "Desktop session: Wayland — the GUI units require X11 (QT_QPA_PLATFORM=xcb). Switch with 'sudo raspi-config' -> Advanced Options -> Wayland -> X11, reboot into the desktop and re-run --check." ;;
            *)
                # Uninspectable (fresh boot, SSH, no graphical session yet).
                # Warn by default: only an OS that provably predates Bookworm
                # defaults to X11. A WARN never blocks the gate, but it puts
                # the raspi-config step in front of the installer on exactly
                # the machines where the first boot would stay dark.
                _os_major="${VERSION_ID:-}"
                _os_major="${_os_major%%.*}"
                if [[ "${_os_major}" =~ ^[0-9]+$ ]] && [[ "${_os_major}" -lt 12 ]]; then
                    _chk_pass "No active desktop session to inspect (this OS defaults to X11)"
                else
                    _chk_warn "No active desktop session to inspect; Bookworm/Trixie boot to Wayland by default and the GUI units require X11. Confirm 'sudo raspi-config' -> Advanced Options -> Wayland -> X11 before installing."
                fi ;;
        esac
    fi

    # Scoped display authorisation (system GUI mode only).
    #
    # In system mode the GUI runs as 'khptz' and reaches the desktop user's X
    # display through `xhost +SI:localuser:khptz`. That grant is applied by
    # scripts/repair_rpi_runtime.sh, which runs from inside the wizard's
    # provisioning chain — and which apt-installs x11-xserver-utils when xhost
    # is absent. On an offline appliance that apt call fails, the chain reports
    # "runtime finalization failed" and ROLLS BACK the config and both
    # passwords the operator just entered. Surfacing it here, before anything
    # is written, turns a mid-wizard data-losing failure into a one-line apt
    # command at readiness time.
    if [[ "${GUI_MODE}" == "user" ]]; then
        _chk_pass "xhost not required (--gui-mode user: the session owns its display)"
    elif command -v xhost >/dev/null 2>&1; then
        _chk_pass "xhost present (scoped display grant for the service user)"
    elif command -v apt-get >/dev/null 2>&1; then
        _chk_warn "xhost missing — setup will apt-install x11-xserver-utils, which needs network access. Pre-install it with: sudo apt install -y x11-xserver-utils"
    else
        _chk_fail "xhost missing and apt-get unavailable — the service user can never reach the display. Install x11-xserver-utils."
    fi

    info ""
    info "=== Summary ==="
    if [[ ${_check_fails} -eq 0 ]]; then
        info "All required checks passed. Ready to install."
        if [[ "${SHOW_CHECK_NEXT_ACTION}" == "true" ]]; then
            info "Run without --check to proceed: sudo ./runtime/installer/install.sh"
        fi
    else
        info "${_check_fails} blocking check(s) failed. Resolve before installing."
    fi
    info ""
    exit $(( _check_fails > 0 ? 1 : 0 ))
fi

# ── Create dedicated service user (product mode only) ─────────────────────────

if [[ "${DEV_MODE}" == "false" ]]; then
    if ! id "${APP_USER}" &>/dev/null; then
        info "Creating service user: ${APP_USER}"
        useradd \
            --system \
            --no-create-home \
            --home-dir "${DATA_DIR}" \
            --shell /usr/sbin/nologin \
            --comment "KH PTZ Control service user" \
            "${APP_USER}"
        info "Service user '${APP_USER}' created."
    else
        info "Service user '${APP_USER}' already exists — skipping creation."
    fi
fi

# ── Directories ───────────────────────────────────────────────────────────────

info "Creating directories..."

if [[ "${DEV_MODE}" == "false" ]]; then
    # Product layout: /opt/khptz owned root:khptz, mode 0750 — service user reads, cannot write
    install -d -m 750 "${INSTALL_DIR}"
    chown root:"${APP_USER}" "${INSTALL_DIR}"

    # /etc/khptz: root:khptz, setgid (2750) — admin writes, service reads
    install -d -m 2750 "${CONFIG_DIR}"
    chown root:"${APP_USER}" "${CONFIG_DIR}"

else
    # Developer layout: use legacy data dir
    install -d -m 755 -o "${APP_USER}" "${INSTALL_DIR}"
    install -d -m 755 -o "${APP_USER}" "${DATA_DIR}"
    install -d -m 755 -o "${APP_USER}" "${LOG_DIR}"
    install -d -m 755 -o "${APP_USER}" "${BACKUP_DIR}"
fi

# ── Python dependencies ───────────────────────────────────────────────────────

if [[ "${DEV_MODE}" == "true" ]]; then
    info "Installing Python dependencies (dev mode)..."
    pip3 install --quiet -r "${REPO_ROOT}/requirements.txt"
    if [[ -f "${REPO_ROOT}/requirements-dev.txt" ]]; then
        pip3 install --quiet -r "${REPO_ROOT}/requirements-dev.txt"
    fi
else
    # Product mode: PyQt5 and all runtime deps come from apt on Raspberry Pi OS.
    # requirements-rpi.txt currently carries only comments; only install when it
    # lists a real requirement. Testing with `-s` (size > 0) would be true for a
    # comment-only file and would run pip3 on every product install — and pip3
    # is deliberately NOT a product-mode prerequisite (docs/INSTALL_RPI.md does
    # not install python3-pip), so under `set -e` that aborted the install after
    # the service user and directories existed but before the app was copied.
    info "Python dependencies: using apt-installed packages (product mode)."
    info "  PyQt5 expected from: sudo apt install -y python3-pyqt5 python3-pyqt5.qtsvg"
    if grep -qE '^[[:space:]]*[^#[:space:]]' "${REPO_ROOT}/requirements-rpi.txt" 2>/dev/null; then
        info "Installing additional pip dependencies from requirements-rpi.txt..."
        require_python_module pip python3-pip
        "${PYTHON_BIN}" -m pip install --quiet -r "${REPO_ROOT}/requirements-rpi.txt"
    else
        info "  requirements-rpi.txt lists no pip requirements — nothing to install."
    fi
fi

# ATEM support: install separately only when explicitly requested.
if [[ "${INSTALL_ATEM:-false}" == "true" ]]; then
    info "Installing ATEM dependencies (--atem requested)..."
    if [[ "${DEV_MODE}" == "true" ]]; then
        require_command pip3 python3-pip
        pip3 install --quiet -r "${REPO_ROOT}/requirements-atem.txt"
    else
        "${PYTHON_BIN}" -m pip install --quiet -r "${REPO_ROOT}/requirements-atem.txt"
    fi
fi

# ── Copy application files ────────────────────────────────────────────────────

RSYNC_EXCLUDES=(
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc'
    --exclude='.pytest-runtime' --exclude='venv' --exclude='.venv'
    # sim state is operator data, not code: while simulation mode is active
    # sim_mode.py writes sim_ip_backup.json (the is_active() marker and only
    # record of the real camera/ATEM addresses) plus the loopback values into
    # PTZ1IP.txt/PTZ2IP.txt, all inside the install dir. --delete must not
    # erase them, or an upgrade/rollback silently disables simulation mode
    # and the next boot hydrates the cameras from config.yaml — the real
    # hardware the operator had isolated.
    --exclude='sim_ip_backup.json'
    --exclude='PTZ1IP.txt'
    --exclude='PTZ2IP.txt'
)

# Quiesce session GUIs before replacing code, including user -> system.
# Enumerate systemd user@ units as well as bus/private sockets. A live
# manager may have no session D-Bus, and deleting the on-disk GUI unit does
# not unload a running service. Any identifiable but unreachable manager
# blocks the copy. Never start a user GUI from this root installer.
_stop_session_guis() {
    local runtime_root="$1" bus uid user state managers entry name _load active rest path
    local -A manager_uids=()
    managers="$(systemctl list-units --all --plain --no-legend 'user@*.service')" \
        || error "Cannot enumerate user managers; refusing to replace GUI code."
    while read -r name _load active rest; do
        if [[ "${name}" =~ ^user@([0-9]+)\.service$ ]]; then
            uid="${BASH_REMATCH[1]}"
            case "${active}" in
                inactive|failed) ;;
                *) manager_uids["${uid}"]=1 ;;
            esac
        fi
    done <<< "${managers}"
    for path in "${runtime_root}"/[0-9]*/bus "${runtime_root}"/[0-9]*/systemd/private; do
        [[ -S "${path}" ]] || continue
        entry="${path#"${runtime_root}"/}"; uid="${entry%%/*}"
        [[ "${uid}" =~ ^[0-9]+$ ]] && manager_uids["${uid}"]=1
    done
    for uid in "${!manager_uids[@]}"; do
        bus="${runtime_root}/${uid}/bus"
        [[ -S "${bus}" ]] || bus="${runtime_root}/${uid}/systemd/private"
        [[ -S "${bus}" ]] \
            || error "User manager ${uid} is identifiable but inaccessible; refusing to replace GUI code."
        user="$(getent passwd "${uid}" | cut -d: -f1)"
        [[ -n "${user}" ]] || error "Cannot resolve user manager ${uid}; refusing to replace GUI code."
        _user_gui_ctl() {
            sudo -u "${user}" env XDG_RUNTIME_DIR="${runtime_root}/${uid}" \
                DBUS_SESSION_BUS_ADDRESS="unix:path=${bus}" \
                systemctl --user "$@" khptz-gui.service
        }
        state="$(_user_gui_ctl show --property=ActiveState --value)" \
            || error "Cannot inspect khptz-gui for ${user}; refusing to replace GUI code."
        case "${state}" in
            inactive|failed) continue ;;
            active|activating|reloading|deactivating)
                _user_gui_ctl stop \
                    || error "Cannot stop khptz-gui for ${user}; refusing to replace GUI code."
                state="$(_user_gui_ctl show --property=ActiveState --value)" \
                    || error "Cannot verify khptz-gui stopped for ${user}."
                case "${state}" in
                    inactive|failed) ;;
                    *) error "khptz-gui for ${user} is still ${state}; refusing to replace GUI code." ;;
                esac
                warn "Stopped session GUI for ${user}. It stays stopped on success or failure; after a successful user-mode install, reopen the controller or log in again."
                ;;
            *) error "Unknown khptz-gui state '${state}' for ${user}; refusing to replace GUI code." ;;
        esac
    done
}

# ── Pre-update backup (product re-deploys only) ──────────────────────────────
#
# Config (CONFIG_DIR) and runtime data (DATA_DIR) live outside INSTALL_DIR
# (see docs/RUNTIME_PATH_CONTRACT.md), but the deploy below replaces the whole
# installed tree. Before ANY quiescing or copying, take the same
# manifest-based config/data archive `khptz backup` produces everywhere else
# (same invocation as rollback.sh step 1) so an update always leaves a copy of
# what it replaced. It is a config/data manifest archive — not the code, not
# the secrets, not an atomic device snapshot; restoring means re-deploying the
# recorded ref and restoring this archive on top.
#
# Runs only when an install-state.env already exists — i.e. this is an update,
# not a first install (which has nothing to back up and no service user yet).
# A failed backup aborts the installer before GUI shutdown and application-tree
# replacement; earlier setup/dependency changes (service user, directory
# creation, package installs) may already have occurred. The explicit
# --skip-pre-update-backup flag is the only way past that guard.

_state_file="${CONFIG_DIR}/install-state.env"
if [[ "${DEV_MODE}" == "false" && "${REPO_ROOT}" != "${INSTALL_DIR}" && -f "${_state_file}" ]]; then
    if [[ "${SKIP_PRE_UPDATE_BACKUP}" == "true" ]]; then
        warn "Skipping pre-update backup (--skip-pre-update-backup). The update leaves no automatic restore point."
    else
        # On an update this directory already exists from the previous install;
        # create defensively so the backup never fails on a missing dir.
        install -d -m 750 -o "${APP_USER}" -g "${APP_USER}" "${BACKUP_DIR}"
        # Same reader as the install-state stage below; trailing `|| true`
        # keeps pipefail from aborting the installer if the key is absent.
        _prev_ref="$(
            sed -n 's/^KHPTZ_INSTALLED_REF=//p' "${_state_file}" 2>/dev/null | tr -d '"' | tail -n1 || true
        )"
        PRE_UPDATE_BACKUP="${BACKUP_DIR}/pre_update_$(sanitize_ref "${_prev_ref:-unknown}")_$(date +%Y%m%d_%H%M%S).zip"
        info "Creating pre-update backup → ${PRE_UPDATE_BACKUP}"
        # Drop privileges with runuser, not sudo: the installer already runs as
        # root, and minimal Debian/Pi OS images (the CI container included) have
        # no sudo. runuser (util-linux, Essential) is always present on the
        # supported targets. PYTHONPATH points at the tree still deployed in
        # INSTALL_DIR — the copy the backup must describe — and the subshell
        # cd's to / first: `python3 -m` puts the OPERATOR'S cwd ahead of
        # PYTHONPATH, and the operator normally runs this script from the NEW
        # checkout, which would shadow the deployed tree with candidate code.
        ( cd / && runuser -u "${APP_USER}" -- env \
            KHPTZ_CONFIG_DIR="${CONFIG_DIR}" KHPTZ_DATA_DIR="${DATA_DIR}" \
            KHPTZ_LOG_DIR="${LOG_DIR}" KHPTZ_BACKUP_DIR="${BACKUP_DIR}" \
            PYTHONPATH="${INSTALL_DIR}" \
            "${PYTHON_BIN}" -m runtime.cli backup --dest "${PRE_UPDATE_BACKUP}" ) \
            || error "Pre-update backup failed — update aborted before GUI shutdown and application-tree replacement (earlier setup/dependency steps may already have run). Rerun with --skip-pre-update-backup only if you have your own current copy off the Pi."
        info "Pre-update backup complete: ${PRE_UPDATE_BACKUP}"
    fi
fi

if [[ "${DEV_MODE}" == "false" ]]; then
    _stop_session_guis /run/user
    # Do not revoke a running desktop GUI's group-write access if quiescence
    # fails. User-mode permissions are restored in the GUI-assets stage below.
    # runtime-writable directories owned by khptz
    install -d -m 750 -o "${APP_USER}" -g "${APP_USER}" "${DATA_DIR}"
    install -d -m 750 -o "${APP_USER}" -g "${APP_USER}" "${LOG_DIR}"
    install -d -m 750 -o "${APP_USER}" -g "${APP_USER}" "${BACKUP_DIR}"
fi

if [[ "${REPO_ROOT}" == "${INSTALL_DIR}" ]]; then
    # Developer install cloned straight into the install dir (git clone … khptz).
    # Source and destination are the same tree — copying would be a no-op at
    # best and, with --delete, actively dangerous.
    info "Source and install directory are the same (${INSTALL_DIR}) — skipping copy."
elif [[ "${DEV_MODE}" == "false" ]]; then
    # A running app lazily imports modules from this tree: copying over it can
    # hand it a half-written file. Stop the service for the duration of the
    # copy and restart it once the new tree is fully in place.
    SERVICE_WAS_ACTIVE=0
    if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        info "Stopping ${SERVICE_NAME} while the new release is copied..."
        systemctl stop "${SERVICE_NAME}"
        SERVICE_WAS_ACTIVE=1
        # Si CUALQUIER paso posterior falla (rsync, chown, launcher, config...),
        # set -e aborta el script y el servicio quedaría parado: el trap intenta
        # rearrancarlo (disponibilidad, no rollback atómico) y conserva el exit.
        # Se desarma tras el rearranque planificado del final del install.
        trap _restart_stopped_service_on_abort EXIT
    fi
    # --delete makes /opt/khptz an exact mirror of the release being installed.
    # Without it a downgrade (rollback.sh re-deploys an older ref) would leave
    # files from the newer release behind, so the running install would be a
    # mix of two versions. Safe here because /opt/khptz holds only application
    # code: config, data, logs and backups all live outside it (see
    # docs/RUNTIME_PATH_CONTRACT.md), so nothing customer-owned can be deleted.
    # The one exception, sim_mode's state files, are excluded above.
    info "Installing application to ${INSTALL_DIR} (exact mirror of this release)..."
    rsync -a --delete "${RSYNC_EXCLUDES[@]}" "${REPO_ROOT}/" "${INSTALL_DIR}/"
else
    # Dev layout keeps config/data inside or beside the install dir, so never
    # --delete here.
    info "Installing application to ${INSTALL_DIR}..."
    rsync -a "${RSYNC_EXCLUDES[@]}" "${REPO_ROOT}/" "${INSTALL_DIR}/"
fi

if [[ "${DEV_MODE}" == "false" ]]; then
    # App code: root:khptz, directories 0750, files 0640.
    # Shell scripts get 0750 so the service user can execute them if needed.
    chown -R root:"${APP_USER}" "${INSTALL_DIR}"
    find "${INSTALL_DIR}" -type d -exec chmod 750 {} \;
    find "${INSTALL_DIR}" -type f -exec chmod 640 {} \;
    find "${INSTALL_DIR}" -type f -name "*.sh" -exec chmod 750 {} \;
else
    chown -R "${APP_USER}:${APP_USER}" "${INSTALL_DIR}"
fi

# ── Config: do not overwrite existing ─────────────────────────────────────────

CONFIG_TARGET="${CONFIG_DIR}/config.yaml"
CONFIG_STARTER="${INSTALL_DIR}/config/defaults/starter.yaml"

if [[ ! -f "${CONFIG_TARGET}" ]]; then
    if [[ -f "${CONFIG_STARTER}" ]]; then
        info "Copying starter config template to ${CONFIG_TARGET}"
        cp "${CONFIG_STARTER}" "${CONFIG_TARGET}"

        # Generate a unique installation ID for this install.
        # Never overwrite an existing ID — this block only runs when config is first created.
        INSTALL_YEAR="$(date +%Y)"
        INSTALL_ID="$("${PYTHON_BIN}" -c "
import sys; sys.path.insert(0, '${INSTALL_DIR}')
from domain.installation_id import generate_installation_id
print(generate_installation_id(${INSTALL_YEAR}))
" 2>/dev/null || echo "")"
        if [[ -n "${INSTALL_ID}" ]]; then
            sed -i "s/installation_id: \"\"/installation_id: \"${INSTALL_ID}\"/" "${CONFIG_TARGET}"
            info "Installation ID generated: ${INSTALL_ID}"
        else
            warn "Could not generate installation ID — fill in site.installation_id manually."
        fi

        if [[ "${DEV_MODE}" == "false" ]]; then
            chown root:"${APP_USER}" "${CONFIG_TARGET}"
            chmod 640 "${CONFIG_TARGET}"
        else
            chown "${APP_USER}:${APP_USER}" "${CONFIG_TARGET}"
        fi
        warn "Edit ${CONFIG_TARGET} with real camera IPs and VISCA IDs before starting."
    fi
else
    info "Existing config.yaml found at ${CONFIG_TARGET} — not overwritten."

    # Backfill .provisioned for a working install that predates the setup
    # wizard: the old flow (manually edit config.yaml + runtime.setup_password)
    # never created this marker, but khptz-control.service now gates on it —
    # without this, a currently-working customer install would stop starting
    # the moment install.sh is re-run for an update. Only backfill when there
    # is real evidence of a working install (the entry password secret already
    # exists), never for a half-finished or corrupt config.
    if [[ "${DEV_MODE}" == "false" ]]; then
        ENTRY_SECRET="${DATA_DIR}/password.enc"
        PROVISIONED_MARKER="${CONFIG_DIR}/.provisioned"
        if [[ ! -f "${PROVISIONED_MARKER}" && -f "${ENTRY_SECRET}" ]]; then
            info "Existing install predates the setup wizard — marking as"
            info "provisioned (${PROVISIONED_MARKER}) so khptz-control.service can start."
            printf 'ok\n' > "${PROVISIONED_MARKER}"
            chmod 644 "${PROVISIONED_MARKER}"
        fi
    fi
fi

# ── khptz CLI symlink ──────────────────────────────────────────────────────────

info "Installing khptz CLI..."
KHPTZ_LAUNCHER="/usr/local/bin/khptz"
# Run from the install dir with -m so app_version / domain / runtime resolve on
# sys.path no matter the caller's cwd. Invoking cli.py by path would only put
# runtime/ on sys.path, so `khptz setup` from the desktop session (autostart /
# menu) would fail with ModuleNotFoundError: app_version.
if [[ "${DEV_MODE}" == "false" ]]; then
    # Canonical UTF-8 launcher — the same one repair_rpi_runtime.sh installs.
    # Writing the plain one-liner here too would let an installer re-run strip
    # the UTF-8 environment and the khptz-user delegation the repair added.
    cat > "${KHPTZ_LAUNCHER}" <<LAUNCHER
#!/usr/bin/env bash
set -Eeuo pipefail
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

subcommand="\${1:-}"
if [[ "\$(id -u)" -ne 0 && "\$(id -un)" != "${APP_USER}" ]]; then
    case "\${subcommand}" in
        status|uptime|cameras|doctor|fingerprint|known-good|maintenance|installability|supportability|support-bundle|backup|network-report|verify-install)
            exec /usr/bin/sudo -u ${APP_USER} -H env \
                LANG=C.UTF-8 LC_ALL=C.UTF-8 \
                PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
                /bin/bash -c 'cd ${INSTALL_DIR} && exec /usr/bin/python3 -m runtime.cli "\$@"' \
                khptz-cli "\$@"
            ;;
        restore)
            exec /usr/bin/sudo env \
                LANG=C.UTF-8 LC_ALL=C.UTF-8 \
                PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
                /bin/bash -c 'cd ${INSTALL_DIR} && exec /usr/bin/python3 -m runtime.cli "\$@"' \
                khptz-cli "\$@"
            ;;
        setup|demo)
            state_root="\${XDG_STATE_HOME:-\${HOME}/.local/state}"
            export KHPTZ_LOG_DIR="\${KHPTZ_LOG_DIR:-\${state_root}/khptz/log}"
            mkdir -p "\${KHPTZ_LOG_DIR}"
            ;;
    esac
fi

cd ${INSTALL_DIR}
exec /usr/bin/python3 -m runtime.cli "\$@"
LAUNCHER
else
    cat > "${KHPTZ_LAUNCHER}" <<LAUNCHER
#!/usr/bin/env bash
export KHPTZ_CONFIG_DIR="${CONFIG_DIR}"
export KHPTZ_DATA_DIR="${DATA_DIR}"
export KHPTZ_LOG_DIR="${LOG_DIR}"
export KHPTZ_BACKUP_DIR="${BACKUP_DIR}"
cd "${INSTALL_DIR}" && exec python3 -m runtime.cli "\$@"
LAUNCHER
fi
chmod +x "${KHPTZ_LAUNCHER}"
info "khptz CLI installed at ${KHPTZ_LAUNCHER}"

# ── systemd service ───────────────────────────────────────────────────────────

info "Installing systemd service..."
SERVICE_TEMPLATE="${REPO_ROOT}/runtime/systemd/khptz-control.service"
[[ -f "${SERVICE_TEMPLATE}" ]] || error "Service template not found: ${SERVICE_TEMPLATE} — ${INCOMPLETE_CHECKOUT_REMEDY}"

if [[ "${DEV_MODE}" == "false" ]]; then
    # Product mode: service template already uses fixed product paths
    cp "${SERVICE_TEMPLATE}" "${SERVICE_FILE}"
else
    # Dev mode: patch paths and user for the developer install location.
    # The checkout lives under /home, which ProtectHome=true hides entirely.
    # Keep homes read-only except for the explicit runtime ReadWritePaths below.
    # Also strip ConditionPathExists=.../.provisioned — dev installs never run
    # the setup wizard or the provisioning channel (both gated to product mode
    # above), so that marker is never created and the gate would otherwise
    # leave a dev install's service permanently unable to start.
    sed \
        -e "s|User=khptz|User=${APP_USER}|g" \
        -e "s|Group=khptz|Group=${APP_USER}|g" \
        -e "s|ProtectHome=true|ProtectHome=read-only|g" \
        -e "s|WorkingDirectory=/opt/khptz|WorkingDirectory=${INSTALL_DIR}|g" \
        -e "s|ExecStart=/usr/bin/python3 /opt/khptz/main.py|ExecStart=/usr/bin/python3 ${INSTALL_DIR}/main.py|g" \
        -e "s|ReadWritePaths=.*|ReadWritePaths=${DATA_DIR} ${LOG_DIR} ${BACKUP_DIR}|g" \
        -e "s|Environment=KHPTZ_DATA_DIR=/var/lib/khptz|Environment=KHPTZ_DATA_DIR=${DATA_DIR}|g" \
        -e "/^Environment=KHPTZ_DATA_DIR=/a Environment=KHPTZ_CONFIG_DIR=${CONFIG_DIR}" \
        -e "/^Environment=KHPTZ_DATA_DIR=/a Environment=KHPTZ_LOG_DIR=${LOG_DIR}" \
        -e "/^Environment=KHPTZ_DATA_DIR=/a Environment=KHPTZ_BACKUP_DIR=${BACKUP_DIR}" \
        -e "/^ConditionPathExists=\/etc\/khptz\/\.provisioned$/d" \
        "${SERVICE_TEMPLATE}" > "${SERVICE_FILE}"
fi

systemctl daemon-reload

# Exactly one launcher may be active, or the operator gets two competing
# full-screen GUIs fighting over the same cameras (#885).
if [[ "${DEV_MODE}" == "false" && "${GUI_MODE}" == "user" ]]; then
    systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
    systemctl stop    "${SERVICE_NAME}" 2>/dev/null || true
    info "GUI mode 'user': ${SERVICE_NAME} disabled — the GUI runs in the desktop session."
    info "Logs with:  journalctl --user -u khptz-gui -f   (as the desktop user)"
else
    systemctl enable "${SERVICE_NAME}" 2>/dev/null || true
    info "Service ${SERVICE_NAME} enabled."
    info "Start with: systemctl start ${SERVICE_NAME}"
    info "Logs with:  journalctl -u ${SERVICE_NAME} -f"
fi

# Credential parent must exist before privileged provisioning writes admin.enc.
if [[ "${DEV_MODE}" == "false" ]]; then
    install -d -m 0750 -o root -g "${APP_USER}" "${ADMIN_SECRET_DIR}"
fi

# ── Setup-wizard provisioning channel (product mode only) ─────────────────────
#
# The graphical setup wizard runs unprivileged in the desktop session. It cannot
# write /etc/khptz or call systemctl, so it drops a request at /run/khptz/request.json
# and the root khptz-provision path-unit reacts. This is the password-free
# privilege channel: installing these units here is the single sudo step, after
# which the wizard provisions without any further prompt.

if [[ "${DEV_MODE}" == "false" ]]; then
    info "Installing setup-wizard provisioning channel..."
    PROVISION_SERVICE_TEMPLATE="${REPO_ROOT}/runtime/systemd/khptz-provision.service"
    PROVISION_PATH_TEMPLATE="${REPO_ROOT}/runtime/systemd/khptz-provision.path"
    [[ -f "${PROVISION_SERVICE_TEMPLATE}" ]] || error "Provision service template not found: ${PROVISION_SERVICE_TEMPLATE} — ${INCOMPLETE_CHECKOUT_REMEDY}"
    [[ -f "${PROVISION_PATH_TEMPLATE}" ]]    || error "Provision path template not found: ${PROVISION_PATH_TEMPLATE} — ${INCOMPLETE_CHECKOUT_REMEDY}"

    cp "${PROVISION_SERVICE_TEMPLATE}" /etc/systemd/system/khptz-provision.service
    cp "${PROVISION_PATH_TEMPLATE}"    /etc/systemd/system/khptz-provision.path

    if [[ -n "${WIZARD_USER}" ]] && id "${WIZARD_USER}" &>/dev/null; then
        info "Provisioning channel owner (wizard user): ${WIZARD_USER}"

        # /run/khptz is tmpfs, recreated every boot by tmpfiles.d. Owned by the
        # wizard user (not root) so the desktop session can actually create
        # request.json — 0750 root:<user> would give the wizard only r-x via
        # its group, not write. Root reads/writes it anyway when the oneshot
        # runs as EUID 0, and it is never world-readable.
        # /etc/tmpfiles.d is absent on minimal systems (and in the Bullseye CI
        # container), so create it before writing rather than failing the install.
        mkdir -p /etc/tmpfiles.d
        printf 'd /run/khptz 0750 %s root -\n' "${WIZARD_USER}" > /etc/tmpfiles.d/khptz.conf

        # Fallback for a failed systemd-tmpfiles --create of the provisioning
        # channel directory. Never repairs by inference: an existing path is
        # used only when it is a REAL directory (not a symlink) owned by
        # <owner>:root with mode exactly 0750; anything else only gets a WARN.
        # A missing directory is created restrictively and then verified.
        # Exit 0 = usable now; exit 1 = channel unavailable this boot (the
        # install continues either way). Without the directory the wizard
        # cannot drop request.json and provisioning is dead for the whole
        # first session, with only this install log to explain why.
        _ensure_run_khptz() {
            local dir="$1" owner="$2"
            local mode o g

            if [[ -L "${dir}" ]]; then
                warn "${dir} is a symlink — refusing to use or modify it. Provisioning channel unavailable now; verify after reboot."
                return 1
            fi

            if [[ -d "${dir}" ]]; then
                mode="$(stat -c '%a' "${dir}" 2>/dev/null || true)"
                o="$(stat -c '%U' "${dir}" 2>/dev/null || true)"
                g="$(stat -c '%G' "${dir}" 2>/dev/null || true)"
                if [[ "${mode}" == "750" && "${o}" == "${owner}" && "${g}" == "root" ]]; then
                    info "${dir} already exists with the expected owner and mode — using it."
                    return 0
                fi
                warn "${dir} exists with unexpected owner/group/mode (${o}:${g} ${mode}, expected ${owner}:root 750) — not changing it by inference. Provisioning channel unavailable now; verify after reboot."
                return 1
            fi

            if ! install -d -m 0750 -o "${owner}" -g root "${dir}"; then
                warn "Could not create ${dir}. Provisioning channel unavailable now; verify after reboot."
                return 1
            fi
            # Verify what was just created: a partially-privileged or racing
            # system must not leave a looser directory in place unnoticed.
            mode="$(stat -c '%a' "${dir}" 2>/dev/null || true)"
            o="$(stat -c '%U' "${dir}" 2>/dev/null || true)"
            g="$(stat -c '%G' "${dir}" 2>/dev/null || true)"
            if [[ "${mode}" == "750" && "${o}" == "${owner}" && "${g}" == "root" ]]; then
                warn "systemd-tmpfiles --create failed; ${dir} created directly with the same owner and mode."
                return 0
            fi
            warn "${dir} was created but does not match ${owner}:root 0750 (got ${o}:${g} ${mode}) — not trusting it. Provisioning channel unavailable now; verify after reboot."
            return 1
        }

        if ! systemd-tmpfiles --create /etc/tmpfiles.d/khptz.conf; then
            _ensure_run_khptz /run/khptz "${WIZARD_USER}" || true
        fi

        systemctl daemon-reload
        systemctl enable khptz-provision.path 2>/dev/null || true
        systemctl start  khptz-provision.path 2>/dev/null || true
        info "Provisioning channel enabled — the setup wizard can install without a password prompt."
    else
        warn "Could not determine the desktop (wizard) user — provisioning channel not enabled."
        warn "Re-run with: sudo ./runtime/installer/install.sh --wizard-user <desktop-user>"
    fi
fi

# ── Setup-wizard launcher + first-boot autostart (product mode only) ──────────
#
# `khptz setup` opens the graphical wizard. It self-suppresses once the install is
# provisioned (.provisioned marker), so the autostart entry (no --force) can fire
# on every desktop login and quietly do nothing after first-run setup completes.
# The applications menu entry passes --force so it can still reopen Repair.

# ── Desktop user group membership (product mode only) ────────────────────────
#
# This is a precondition of the install, not a detail of the wizard launcher.
# App code is root:khptz 0750, so without membership the desktop user cannot
# traverse /opt/khptz at all: `khptz setup` cannot run, and under --gui-mode user
# khptz-gui.service cannot even start (its WorkingDirectory and ExecStart both
# live there) — an appliance with no GUI. It used to be nested inside the
# launcher's "both .desktop templates exist" branch, so a partially deployed
# tree silently skipped it.
#
# Takes effect at the next login, which is when the GUI and wizard first run.

if [[ "${DEV_MODE}" == "false" ]] \
   && [[ -n "${WIZARD_USER}" ]] \
   && id "${WIZARD_USER}" &>/dev/null \
   && [[ "${WIZARD_USER}" != "${APP_USER}" ]]; then
    if id -nG "${WIZARD_USER}" 2>/dev/null | tr ' ' '\n' | grep -qx "${APP_USER}"; then
        info "${WIZARD_USER} is already in the ${APP_USER} group."
    elif usermod -aG "${APP_USER}" "${WIZARD_USER}"; then
        info "Added ${WIZARD_USER} to the ${APP_USER} group (re-login required)."
    else
        warn "Could not add ${WIZARD_USER} to the ${APP_USER} group."
        warn "The setup wizard cannot read ${INSTALL_DIR}, and a session-owned"
        warn "GUI (--gui-mode user) will not start. Add it manually with:"
        warn "  sudo usermod -aG ${APP_USER} ${WIZARD_USER}"
    fi
fi

if [[ "${DEV_MODE}" == "false" ]]; then
    info "Installing setup-wizard launcher..."
    DESKTOP_TEMPLATE="${REPO_ROOT}/runtime/khptz-setup.desktop"
    MENU_DESKTOP_TEMPLATE="${REPO_ROOT}/runtime/khptz-setup-menu.desktop"
    if [[ -f "${DESKTOP_TEMPLATE}" && -f "${MENU_DESKTOP_TEMPLATE}" ]]; then
        install -d -m 755 /usr/share/applications
        install -m 644 "${MENU_DESKTOP_TEMPLATE}" /usr/share/applications/khptz-setup.desktop
        info "Setup launcher available in the applications menu (Repair mode)."

        # First-boot autostart for the desktop (wizard) user.
        if [[ -n "${WIZARD_USER}" ]] && id "${WIZARD_USER}" &>/dev/null; then
            WIZARD_HOME="$(getent passwd "${WIZARD_USER}" | cut -d: -f6)"
            if [[ -n "${WIZARD_HOME}" && -d "${WIZARD_HOME}" ]]; then
                AUTOSTART_DIR="${WIZARD_HOME}/.config/autostart"
                install -d -m 755 -o "${WIZARD_USER}" "${AUTOSTART_DIR}"
                install -m 644 -o "${WIZARD_USER}" "${DESKTOP_TEMPLATE}" \
                    "${AUTOSTART_DIR}/khptz-setup.desktop"
                info "First-boot setup wizard autostart enabled for ${WIZARD_USER}."
            else
                warn "Could not resolve home for ${WIZARD_USER} — autostart not installed."
            fi
        else
            warn "Wizard user unknown — first-boot setup autostart not installed."
            warn "Re-run with: sudo ./runtime/installer/install.sh --wizard-user <desktop-user>"
        fi
    else
        warn "Setup launcher template missing: ${DESKTOP_TEMPLATE} or ${MENU_DESKTOP_TEMPLATE} — ${INCOMPLETE_CHECKOUT_REMEDY}"
    fi
fi

# ── Session-owned GUI assets (--gui-mode, product mode only) ─────────────────
#
# Installing either mode removes the other's launcher, so re-running with a
# different --gui-mode is a clean, reversible switch rather than an addition.

if [[ "${DEV_MODE}" == "false" ]]; then
    GUI_UNIT_TEMPLATE="${REPO_ROOT}/runtime/systemd/user/khptz-gui.service"
    GUI_HELPER_TEMPLATE="${REPO_ROOT}/runtime/khptz-gui-session.sh"
    GUI_DESKTOP_TEMPLATE="${REPO_ROOT}/runtime/khptz-gui.desktop"
    GUI_UNIT_TARGET="/etc/systemd/user/khptz-gui.service"
    GUI_HELPER_TARGET="/usr/local/libexec/khptz-gui-session"

    GUI_AUTOSTART=""
    if [[ -n "${WIZARD_USER}" ]] && id "${WIZARD_USER}" &>/dev/null; then
        GUI_WIZARD_HOME="$(getent passwd "${WIZARD_USER}" | cut -d: -f6)"
        [[ -n "${GUI_WIZARD_HOME}" ]] \
            && GUI_AUTOSTART="${GUI_WIZARD_HOME}/.config/autostart/khptz-gui.desktop"
    fi

    if [[ "${GUI_MODE}" == "user" ]]; then
        info "Installing the session-owned GUI (--gui-mode user)..."
        for _tpl in "${GUI_UNIT_TEMPLATE}" "${GUI_HELPER_TEMPLATE}" "${GUI_DESKTOP_TEMPLATE}"; do
            [[ -f "${_tpl}" ]] || error "GUI template not found: ${_tpl} — ${INCOMPLETE_CHECKOUT_REMEDY}"
        done

        install -d -m 755 /etc/systemd/user
        install -m 644 "${GUI_UNIT_TEMPLATE}" "${GUI_UNIT_TARGET}"
        install -d -m 755 /usr/local/libexec
        install -m 755 "${GUI_HELPER_TEMPLATE}" "${GUI_HELPER_TARGET}"

        # The GUI now runs as the desktop user, which reaches its own runtime
        # data through membership of the '${APP_USER}' group (install.sh already
        # adds the wizard user to it). setgid keeps new files in that group so
        # the service identity can still read everything the GUI writes.
        chmod 2770 "${DATA_DIR}" "${LOG_DIR}" "${BACKUP_DIR}"
        info "Runtime directories are setgid group-writable for '${APP_USER}'."

        # Directory permissions alone are not enough. Data files are written
        # atomically via mkstemp, which creates 0600, so everything already in
        # /var/lib/khptz from a system-mode install is unreadable to the desktop
        # user even though it is in the right group — the GUI would start with
        # no presets, seats or layout. Grant the group the same access the
        # directories now advertise. Ownership is left alone.
        # Secrets are excluded deliberately. The encrypted password files live
        # in this same directory, and their key is derived from /etc/machine-id
        # — which is world-readable — so group-readable secrets are effectively
        # plaintext to anyone in the group. Relaxing them here would silently
        # hand the administrator password to the desktop account and defeat the
        # operator/administrator split. They stay 0600 and are managed only by
        # the privileged provisioning path.
        for _dir in "${DATA_DIR}" "${LOG_DIR}" "${BACKUP_DIR}"; do
            [[ -d "${_dir}" ]] || continue
            find "${_dir}" -type f ! -name '*.enc' -exec chmod g+rw {} + 2>/dev/null || true
            find "${_dir}" -type d -exec chmod g+rwxs {} + 2>/dev/null || true
        done
        info "Existing runtime data is reachable by the '${APP_USER}' group (secrets excluded)."

        if [[ -n "${GUI_AUTOSTART}" && -d "$(dirname "$(dirname "${GUI_AUTOSTART}")")" ]]; then
            install -d -m 755 -o "${WIZARD_USER}" "$(dirname "${GUI_AUTOSTART}")"
            install -m 644 -o "${WIZARD_USER}" "${GUI_DESKTOP_TEMPLATE}" "${GUI_AUTOSTART}"
            info "GUI autostart installed for ${WIZARD_USER}."
        else
            warn "Desktop user unknown or has no home — GUI autostart not installed."
            warn "The session GUI will not start automatically. Re-run with --wizard-user <user>."
        fi

        systemctl daemon-reload
        info "The GUI starts at the next desktop login (no xhost, no root)."
    else
        # System mode: strip any session-owned launcher left by a previous
        # --gui-mode user install, so only khptz-control.service remains.
        for _stale in "${GUI_UNIT_TARGET}" "${GUI_HELPER_TARGET}" "${GUI_AUTOSTART}"; do
            if [[ -n "${_stale}" && -e "${_stale}" ]]; then
                rm -f -- "${_stale}"
                info "Removed session-GUI leftover: ${_stale}"
            fi
        done
        # Restore the stricter runtime permissions the system service expects.
        # The setgid bit needs its own symbolic `g-s`: GNU chmod deliberately
        # PRESERVES a directory's setgid bit for a numeric mode unless it is
        # given as five digits (00750) or with a leading '=', so both `750` and
        # `0750` would leave the 2770 set by a previous --gui-mode user install
        # sitting at 2750 and the desktop group would keep inheriting new files.
        chmod 750 "${DATA_DIR}" "${LOG_DIR}" "${BACKUP_DIR}"
        chmod g-s "${DATA_DIR}" "${LOG_DIR}" "${BACKUP_DIR}"
        # Same reversal for anything the user-mode branch marked setgid deeper
        # in the tree (it runs `chmod g+rwxs` over every subdirectory), so the
        # switch back is a genuine reversal rather than a partial one. Only the
        # directory setgid bit is touched; file modes are left to the service.
        for _dir in "${DATA_DIR}" "${LOG_DIR}" "${BACKUP_DIR}"; do
            [[ -d "${_dir}" ]] || continue
            find "${_dir}" -type d -exec chmod g-s {} + 2>/dev/null || true
        done
    fi
fi

# Controller shortcuts share the existing supervised GUI launch paths. Keep
# this after mode switching (system mode removes the user session helper).
if [[ "${DEV_MODE}" == "false" ]]; then
    install -d -m 755 /usr/local/libexec
    if ! "${PYTHON_BIN}" "${REPO_ROOT}/runtime/installer/controller_launchers.py" \
        --mode "${GUI_MODE}" --user "${WIZARD_USER}"; then
        warn "Controller shortcuts incomplete; existing setup/repair launchers retained."
    fi
fi

# ── Install state (what rollback.sh needs to redeploy) ────────────────────────
#
# /opt/khptz is a deployed artifact, not a checkout: the rsync above excludes
# .git, and the tree is root:khptz 0750 so the service user cannot write it. A
# rollback therefore cannot be `git checkout` inside the install dir — it has to
# re-deploy an older ref from the source checkout this install came from. That
# is only possible if we record where that checkout is and which ref is live.
#
# This lives in CONFIG_DIR (never rewritten by rsync, survives every update)
# rather than in the install dir, which is replaced wholesale on each deploy.

STATE_FILE="${CONFIG_DIR}/install-state.env"

# Read one KEY=value out of the existing state file. The trailing `|| true`
# matters: `set -o pipefail` makes the pipeline inherit sed's exit 2 when the
# file is absent, which would abort the installer from inside a "$(...)".
state_value() {
    sed -n "s/^$1=//p" "${STATE_FILE}" 2>/dev/null | tr -d '"' | tail -n1 || true
}

PREV_INSTALLED_REF="$(state_value KHPTZ_INSTALLED_REF)"
PREV_ROLLBACK_REF="$(state_value KHPTZ_PREVIOUS_REF)"

# `safe.directory` because git refuses to read a repo owned by another user
# when invoked under sudo ("dubious ownership").
SOURCE_REF="$(git -c safe.directory='*' -C "${REPO_ROOT}" describe --tags --always HEAD 2>/dev/null || true)"
if [[ -z "${SOURCE_REF}" ]]; then
    warn "Source directory is not a git checkout — rollback will need an explicit --to <ref>."
    SOURCE_REF="unknown"
fi

if [[ "${PREV_INSTALLED_REF}" == "${SOURCE_REF}" ]]; then
    # Re-running the installer on the ref that is already deployed (permission
    # repair, re-registering units, a rollback that landed here). Carry the
    # existing rollback target forward — recording the current ref instead
    # would silently disable rollback, and blanking it would lose the only
    # pointer back to the previous release.
    PREVIOUS_REF="${PREV_ROLLBACK_REF}"
else
    # A different ref is being deployed: the one we are replacing becomes the
    # rollback target. Empty on a first install — there is nothing to go back
    # to, and recording the ref we just installed would make `rollback.sh` a
    # no-op that looks like it worked.
    if [[ "${PREV_INSTALLED_REF}" == "unknown" ]]; then
        # The previous install came from a source that was not a git checkout
        # (a tarball, a copied tree): "unknown" is a placeholder, not a ref.
        # Recording it as the rollback target would make rollback.sh try to
        # check out a ref literally named "unknown" and fail with git's
        # pathspec error. Record no target instead.
        PREVIOUS_REF=""
    else
        PREVIOUS_REF="${PREV_INSTALLED_REF}"
    fi
fi

INSTALLED_VERSION="$(tr -d '[:space:]' < "${REPO_ROOT}/VERSION" 2>/dev/null || true)"
INSTALLED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
INSTALL_MODE="$([[ ${DEV_MODE} == true ]] && echo dev || echo product)"

info "Recording install state to ${STATE_FILE}"
cat > "${STATE_FILE}" <<STATE
# KHPTZ install state — written by install.sh. Read by rollback.sh.
# Do not edit by hand unless recovering a broken install.
KHPTZ_INSTALL_MODE="${INSTALL_MODE}"
KHPTZ_INSTALLED_VERSION="${INSTALLED_VERSION}"
KHPTZ_INSTALLED_REF="${SOURCE_REF}"
KHPTZ_PREVIOUS_REF="${PREVIOUS_REF}"
KHPTZ_SOURCE_DIR="${REPO_ROOT}"
KHPTZ_WIZARD_USER="${WIZARD_USER}"
KHPTZ_GUI_MODE="${GUI_MODE}"
KHPTZ_INSTALLED_AT="${INSTALLED_AT}"
STATE

if [[ "${DEV_MODE}" == "false" ]]; then
    chown root:"${APP_USER}" "${STATE_FILE}"
    chmod 640 "${STATE_FILE}"
fi

info "  Installed ref : ${SOURCE_REF}"
info "  Rollback to   : ${PREVIOUS_REF:-<none — first install>}"

# ── Done ──────────────────────────────────────────────────────────────────────

if [[ "${DEV_MODE}" == "false" && "${SERVICE_WAS_ACTIVE:-0}" == "1" ]]; then
    trap - EXIT   # el rearranque planificado sustituye al trap de aborto
    if [[ "${GUI_MODE}" == "user" ]]; then
        # En modo usuario la GUI corre en la sesión de escritorio: el servicio
        # de sistema NO se reactiva aunque estuviera corriendo antes.
        info "GUI runs as the desktop user — not restarting the system service."
    else
        info "Restarting ${SERVICE_NAME} (was running before the update)..."
        if ! systemctl start "${SERVICE_NAME}"; then
            # Sin "Installation complete": el sistema quedó parado.
            error "Service did NOT restart after the update — ${SERVICE_NAME} is DOWN. Start it by hand: systemctl start ${SERVICE_NAME}"
        fi
    fi
fi

info ""
info "Installation complete."
info "  Install dir : ${INSTALL_DIR}"
info "  Config dir  : ${CONFIG_DIR}"
info "  Data dir    : ${DATA_DIR}"
info "  Log dir     : ${LOG_DIR}"
info "  Backup dir  : ${BACKUP_DIR}"
info "  Service     : ${SERVICE_FILE}"
info ""
info "Next steps:"
if [[ "${DEV_MODE}" == "false" ]]; then
    # Product mode: config/passwords come from the on-device wizard, not a
    # manual edit (there is no standalone CLI command for it), and
    # khptz-control.service gates on ConditionPathExists=.../.provisioned so it
    # will not start until the wizard provisions the install (it self-restarts
    # once that happens).
    info "  1. Log in to (or restart) the desktop session to run the on-device"
    info "     setup wizard automatically, or launch it from the applications"
    info "     menu (KHPTZ Setup). It configures cameras and both passwords."
    info "  2. Once setup completes, run: khptz doctor"
else
    # Dev mode: no wizard/provisioning channel is installed (gated to product
    # mode above), so config and the entry password are still set by hand.
    info "  1. Edit ${CONFIG_TARGET} with your camera IPs"
    info "  2. Run: python3 -m runtime.setup_password"
    info "  3. Run: systemctl start ${SERVICE_NAME}"
    info "  4. Run: khptz doctor"
fi
info ""
warn "VALIDATION REQUIRED: test this installation on a real Raspberry Pi."
warn "See docs/INSTALL_RPI.md and the RC checklist."
