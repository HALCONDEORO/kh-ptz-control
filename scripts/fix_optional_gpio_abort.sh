#!/usr/bin/env bash
# Install the fail-safe GPIO monitor from this checkout into an existing
# KH PTZ Control product installation, then restart and verify the service.
#
# Usage:
#   sudo bash scripts/fix_optional_gpio_abort.sh

set -Eeuo pipefail
IFS=$'\n\t'

readonly INSTALL_DIR="/opt/khptz"
# Assigned separately from `readonly` so a failing cd/pwd is not masked (SC2155).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SOURCE_FILE="${REPO_ROOT}/adapters/gpio_monitor.py"
readonly TARGET_FILE="${INSTALL_DIR}/adapters/gpio_monitor.py"
readonly SERVICE="khptz-control.service"

info() { printf '[INFO]  %s\n' "$*"; }
fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail "Run this script with sudo."
[[ -f "${SOURCE_FILE}" ]] || fail "Fixed source file not found: ${SOURCE_FILE}"
[[ -f "${TARGET_FILE}" ]] || fail "Installed GPIO monitor not found: ${TARGET_FILE}"
command -v python3 >/dev/null 2>&1 || fail "python3 is required."
command -v systemctl >/dev/null 2>&1 || fail "systemctl is required."

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${TARGET_FILE}.before-issue-882-${STAMP}"

info "Stopping ${SERVICE}..."
systemctl stop "${SERVICE}" || true

info "Backing up installed GPIO monitor to ${BACKUP}"
cp -a "${TARGET_FILE}" "${BACKUP}"

info "Installing fail-safe GPIO monitor..."
install -m 0640 -o root -g khptz "${SOURCE_FILE}" "${TARGET_FILE}"

info "Checking Python syntax..."
python3 -m py_compile "${TARGET_FILE}"

info "Starting ${SERVICE}..."
systemctl reset-failed "${SERVICE}" || true
systemctl start "${SERVICE}"

for _ in $(seq 1 15); do
    if systemctl is-active --quiet "${SERVICE}"; then
        info "${SERVICE} is active."
        info "GPIO failures are now non-fatal; the optional button will disable itself."
        exit 0
    fi
    sleep 1
done

systemctl status "${SERVICE}" --no-pager -l || true
journalctl -u "${SERVICE}" -n 60 --no-pager || true
fail "${SERVICE} did not remain active. Restore with: sudo cp '${BACKUP}' '${TARGET_FILE}'"
