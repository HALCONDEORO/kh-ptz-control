#!/usr/bin/env bash
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
#
# tests/installer/legacy_match_harness.sh — executable coverage for the legacy
# startup classifier in scripts/cleanup_legacy_rpi_autostart.sh (#892).
#
# is_conflict() decides what gets quarantined on a customer appliance. A false
# positive disables something the operator needs — including, in the worst case,
# HALLPTZ's own launcher; a false negative leaves the old HallPTZ/PTZ controller
# starting instead of HALLPTZ. That logic must be tested, but the script itself
# needs root, a Pi and an installed product to reach it.
#
# So extract just the two classification functions and exercise them directly.
# Nothing else from the script runs: no preflight, no filesystem changes.

set -uo pipefail

HARNESS_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -P "${HARNESS_DIR}/../.." && pwd)"
SCRIPT="${REPO_ROOT}/scripts/cleanup_legacy_rpi_autostart.sh"

[[ -f "${SCRIPT}" ]] || { echo "cleanup script not found: ${SCRIPT}" >&2; exit 2; }

# ── Extract the classifiers ───────────────────────────────────────────────────
# Both are top-level `name() {` ... `}` blocks, so a closing brace in column 0
# terminates them.

EXTRACT="$(mktemp)"
trap 'rm -f "${EXTRACT}"' EXIT

awk '
    /^is_canonical\(\)/ , /^\}/ { print }
' "${SCRIPT}" > "${EXTRACT}"
awk '
    /^is_conflict\(\)/ , /^\}/ { print }
' "${SCRIPT}" >> "${EXTRACT}"

grep -q 'is_canonical()' "${EXTRACT}" || { echo "could not extract is_canonical" >&2; exit 2; }
grep -q 'is_conflict()'  "${EXTRACT}" || { echo "could not extract is_conflict"  >&2; exit 2; }

# Values the classifiers close over, matching what the real script sets.
DISPLAY_HELPER="/usr/local/libexec/hallptz-display-session"
AUTOSTART_NAME="hallptz-display-session.desktop"
HOME_DIR="/home/hallptz"
# is_conflict() reads EXTRA_PATTERN, but it is sourced from the generated
# ${EXTRACT} file, so ShellCheck cannot see the use (SC2034 false positive).
# shellcheck disable=SC2034
EXTRA_PATTERN=""

# shellcheck disable=SC1090
source "${EXTRACT}"

# ── Assertions ────────────────────────────────────────────────────────────────

_failures=0
_checks=0

# expect_conflict <description> <text>
expect_conflict() {
    _checks=$((_checks + 1))
    if is_conflict "$2"; then
        echo "  [PASS] flagged: $1"
    else
        echo "  [FAIL] MISSED (legacy startup would survive): $1" >&2
        _failures=$((_failures + 1))
    fi
}

# expect_safe <description> <text>
expect_safe() {
    _checks=$((_checks + 1))
    if is_conflict "$2"; then
        echo "  [FAIL] WOULD QUARANTINE something it must not touch: $1" >&2
        _failures=$((_failures + 1))
    else
        echo "  [PASS] left alone: $1"
    fi
}

echo "=============================================================="
echo " Legacy startup classifier — scripts/cleanup_legacy_rpi_autostart.sh"
echo "=============================================================="

echo
echo "==> HALLPTZ's own startup must never be quarantined"
expect_safe "system service unit"        "/etc/systemd/system/hallptz-control.service"
expect_safe "provision path unit"        "hallptz-provision.path"
expect_safe "display-session autostart"  "${HOME_DIR}/.config/autostart/${AUTOSTART_NAME}"
expect_safe "display helper"             "Exec=${DISPLAY_HELPER}"
expect_safe "display-ready unit"         "hallptz-display-ready.service"
expect_safe "CLI launcher"               "/usr/local/bin/hallptz setup"
expect_safe "runtime channel"            "/run/hallptz/request.json"
# Session-owned GUI (#885) — these did not exist when the classifier was written.
expect_safe "session GUI unit"           "/etc/systemd/user/hallptz-gui.service"
expect_safe "session GUI autostart"      "${HOME_DIR}/.config/autostart/hallptz-gui.desktop"
expect_safe "session GUI launcher"       "Exec=/usr/local/libexec/hallptz-gui-session"
expect_safe "session GUI desktop body"   "$(printf '%s\n%s' "${HOME_DIR}/.config/autostart/hallptz-gui.desktop" "Exec=/usr/local/libexec/hallptz-gui-session")"
# The load-bearing case: the unit's own ExecStart names /opt/hallptz/main.py, which
# the classifier treats as "a direct desktop launch of the installed GUI". The
# scanners hand it file path + contents together, so without an explicit
# canonical match HALLPTZ would quarantine its own session launcher and the
# appliance would boot to no GUI at all.
expect_safe "session GUI unit + contents" "$(printf '%s\n%s\n%s' \
    "${HOME_DIR}/.config/systemd/user/hallptz-gui.service" \
    "[Service]" \
    "ExecStart=/usr/bin/python3 /opt/hallptz/main.py")"
expect_safe "system unit + contents"      "$(printf '%s\n%s' \
    "/etc/systemd/system/hallptz-control.service" \
    "ExecStart=/usr/bin/python3 /opt/hallptz/main.py")"
# Control for the two cases above: an identical body under a NON-canonical unit
# name must still be flagged. Together these prove the canonical list is what
# saves HALLPTZ's own launchers, rather than them being missed for some other
# reason — a protection that is never exercised is not a protection.
expect_conflict "same body, non-canonical unit" "$(printf '%s\n%s' \
    "${HOME_DIR}/.config/systemd/user/legacy-cam.service" \
    "ExecStart=/usr/bin/python3 /opt/hallptz/main.py")"

echo
echo "==> Legacy HallPTZ / PTZ controllers must be flagged"
expect_conflict "HallPTZ desktop entry"  "${HOME_DIR}/.config/autostart/HallPTZ.desktop"
expect_conflict "hallptz-control"       "Exec=/home/hallptz/hallptz-control/main.py"
expect_conflict "PTZ control (spaced)"     "Name=PTZ control"
expect_conflict "PTZ_controller"           "/home/hallptz/PTZ_controller/start.sh"
expect_conflict "camera controller"        "Exec=python3 /home/hallptz/camera-controller/app.py"
expect_conflict "old checkout main.py"     "@reboot python3 /home/hallptz/ptz_app/main.py"
expect_conflict "direct GUI launch"        "Exec=python3 /opt/hallptz/main.py"

echo
echo "==> Unrelated software must be left alone"
expect_safe "browser autostart"     "${HOME_DIR}/.config/autostart/chromium.desktop"
expect_safe "screensaver"           "Exec=xscreensaver -no-splash"
expect_safe "user's own notes app"  "${HOME_DIR}/.config/autostart/notes.desktop"
expect_safe "generic python script" "${HOME_DIR}/scripts/backup.py"
expect_safe "unrelated main.py"     "/usr/share/someapp/main.py"
expect_safe "commented reference"   "a line merely mentioning dublin in prose"

echo
echo "==> --legacy-pattern extends matching without weakening the defaults"
EXTRA_PATTERN="acme[-_]?vision"
expect_conflict "custom pattern hit" "Exec=/opt/acme_vision/run.sh"
expect_safe     "still unrelated"    "Exec=/usr/bin/thunar"
# Consumed by the sourced is_conflict(); see the declaration above.
# shellcheck disable=SC2034
EXTRA_PATTERN=""

echo
echo "=============================================================="
if [[ ${_failures} -eq 0 ]]; then
    echo " RESULT: all ${_checks} classification checks passed"
    echo "=============================================================="
    exit 0
fi
echo " RESULT: ${_failures} of ${_checks} classification checks FAILED"
echo "=============================================================="
exit 1

