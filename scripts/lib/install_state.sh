# shellcheck shell=bash
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
#
# scripts/lib/install_state.sh — single reader for /etc/khptz/install-state.env
#
# Sourced, never executed. Deployed to /opt/khptz/scripts/lib/ by install.sh
# along with the rest of the tree.
#
# WHY THIS EXISTS
# KHPTZ_GUI_MODE decides which process owns the GUI (#885), and getting it wrong
# is not cosmetic: a component that assumes the system service will re-enable
# khptz-control on a session-owned install, and the appliance boots two
# full-screen GUIs driving the same cameras. That value was being parsed
# independently in several scripts, which is exactly how the answers drift.
# One definition, one fallback rule, one place to test.
#
# Consumers must tolerate this file being absent (a partially deployed tree),
# so source it defensively:
#
#     _lib="$(dirname "${BASH_SOURCE[0]}")/lib/install_state.sh"
#     # shellcheck source=/dev/null
#     [[ -r "${_lib}" ]] && source "${_lib}"

# Path to the install state file. Overridable for tests.
: "${KHPTZ_INSTALL_STATE:=/etc/khptz/install-state.env}"

# khptz_state_value KEY
#
# Print the value of KEY, or nothing. Surrounding double quotes are stripped.
# Never fails: an absent or unreadable file yields an empty string, so callers
# under `set -e` are not aborted by a missing install.
khptz_state_value() {
    local key="${1:-}"
    [[ -n "${key}" ]] || return 0
    [[ -r "${KHPTZ_INSTALL_STATE}" ]] || return 0
    sed -n "s/^${key}=//p" "${KHPTZ_INSTALL_STATE}" 2>/dev/null \
        | tr -d '"' | tail -n1 || true
}

# khptz_gui_mode
#
# Print "user" or "system" — never anything else.
#
# Falls back to "system" when the key is missing, unreadable or holds an
# unrecognised value. That is the safe default in both directions: installs
# predating the flag were all system mode, and treating an unknown value as
# "user" would disable the only launcher such a machine has.
khptz_gui_mode() {
    local mode
    mode="$(khptz_state_value KHPTZ_GUI_MODE)"
    case "${mode}" in
        user)   printf 'user\n' ;;
        *)      printf 'system\n' ;;
    esac
}

# khptz_gui_mode_is_user
#
# Convenience predicate for `if khptz_gui_mode_is_user; then ...`.
khptz_gui_mode_is_user() {
    [[ "$(khptz_gui_mode)" == "user" ]]
}
