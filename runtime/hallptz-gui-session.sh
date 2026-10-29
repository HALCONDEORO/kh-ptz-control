#!/usr/bin/env bash
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
#
# hallptz-gui-session — start the HALLPTZ GUI inside the desktop session (#885)
#
# Installed to /usr/local/libexec/hallptz-gui-session by install.sh --gui-mode user
# and invoked by the XDG autostart entry (hallptz-gui.desktop).
#
# XDG autostart is the dependable "a graphical session just began" signal on
# Raspberry Pi OS Bullseye/LXDE, which does not reliably activate
# graphical-session.target. Running here means DISPLAY, XAUTHORITY,
# XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS are the session's real values —
# the whole point of #885 — so they are handed to the user manager before the
# unit starts.
#
# Starting an already-running unit is a no-op, so a second autostart (or a
# manual re-run) cannot produce a second GUI.

set -euo pipefail

readonly UNIT="hallptz-gui.service"

log() {
    command -v logger >/dev/null 2>&1 && logger -t hallptz-gui-session "$*"
    echo "[hallptz-gui-session] $*"
}

if [[ -z "${DISPLAY:-}" ]]; then
    log "No DISPLAY in this session — not starting the GUI."
    exit 0
fi

if ! command -v systemctl >/dev/null 2>&1; then
    log "systemctl not found — cannot start ${UNIT}."
    exit 1
fi

# Hand the live session environment to the user manager. Only export variables
# that are actually set: importing an unset name is pointless and noisy, and
# XAUTHORITY in particular is absent on some Bullseye display-manager setups
# (the cookie then lives under XDG_RUNTIME_DIR instead).
_vars=()
for _name in DISPLAY XAUTHORITY XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS XDG_SESSION_TYPE XDG_CURRENT_DESKTOP; do
    [[ -n "${!_name:-}" ]] && _vars+=("${_name}")
done

if ! systemctl --user import-environment "${_vars[@]}"; then
    log "Could not import the session environment into the user manager."
    exit 1
fi

# --no-block: the autostart must not stall the desktop session waiting for Qt to
# come up. systemd owns supervision and restart limits from here.
if systemctl --user start --no-block "${UNIT}"; then
    log "Requested start of ${UNIT} on ${DISPLAY} for $(id -un)."
else
    log "Failed to start ${UNIT} — see: systemctl --user status ${UNIT}"
    exit 1
fi
