#!/usr/bin/env bash
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
#
# tests/installer/container_install_test.sh — write-side assertions for install.sh
#
# Runs inside tests/installer/Dockerfile.bullseye (Debian Bullseye, Python 3.9.2
# — the supported Raspberry Pi target). Performs a real product-mode install and
# then asserts the guarantees the first physical install proved matter:
# permissions that let the service read but not write its own code, runtime
# directories it CAN write, and above all that re-running never destroys
# customer configuration.
#
# Every expected value below is taken from runtime/installer/install.sh, not
# guessed. Exits non-zero on the first failed assertion.

set -uo pipefail

REPO_ROOT="/src"
INSTALLER="${REPO_ROOT}/runtime/installer/install.sh"

_failures=0
_checks=0

ok()   { _checks=$((_checks + 1)); echo "  [PASS] $*"; }
bad()  { _checks=$((_checks + 1)); _failures=$((_failures + 1)); echo "  [FAIL] $*" >&2; }

# assert_mode <path> <expected "mode owner:group">
assert_mode() {
    local path="$1" expected="$2" actual
    if [[ ! -e "${path}" ]]; then
        bad "${path} does not exist (expected ${expected})"
        return
    fi
    actual="$(stat -c '%a %U:%G' "${path}")"
    if [[ "${actual}" == "${expected}" ]]; then
        ok "${path} is ${actual}"
    else
        bad "${path} is '${actual}', expected '${expected}'"
    fi
}

assert_exists() {
    if [[ -e "$1" ]]; then ok "$1 exists"; else bad "$1 is missing"; fi
}

assert_absent() {
    if [[ ! -e "$1" ]]; then ok "$1 correctly absent"; else bad "$1 should not exist"; fi
}

echo "=============================================================="
echo " HALLPTZ install.sh write-side test — $(. /etc/os-release && echo "${PRETTY_NAME}")"
echo " Python: $(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
echo "=============================================================="

# ── First install ─────────────────────────────────────────────────────────────

echo
echo "==> First install (product mode)"
if ! bash "${INSTALLER}" --wizard-user root; then
    echo "[FATAL] install.sh failed on a clean system" >&2
    exit 1
fi

echo
echo "==> Runtime imports the appliance cannot start without"
# Product mode installs no pip packages, so every third-party import has to
# come from apt. An install that "succeeds" and then raises ModuleNotFoundError
# on first use is the failure mode this guards.
for _module in PyQt5 yaml; do
    if python3 -c "import ${_module}" 2>/dev/null; then
        ok "python3 can import ${_module}"
    else
        bad "python3 cannot import ${_module} — the installed appliance cannot start"
    fi
done

# The installer must refuse rather than leave that discovery to the operator.
# Shadowing python3 with a wrapper that fails only on `import yaml` reproduces
# a Pi without python3-yaml without uninstalling anything.
cat > /usr/local/bin/python3-noyaml <<'STUB'
#!/bin/sh
case "$*" in *"import yaml"*) exit 1 ;; esac
exec /usr/bin/python3 "$@"
STUB
chmod 0755 /usr/local/bin/python3-noyaml
cp /usr/local/bin/python3-noyaml /usr/local/bin/python3
if bash "${INSTALLER}" --check >/tmp/noyaml.out 2>&1; then
    bad "readiness passed without PyYAML — the install would fail on first use"
else
    if grep -q "python3-yaml" /tmp/noyaml.out; then
        ok "readiness refuses without PyYAML and names the apt package"
    else
        bad "readiness failed without PyYAML but did not say how to fix it"
        tail -5 /tmp/noyaml.out
    fi
fi
rm -f /usr/local/bin/python3 /usr/local/bin/python3-noyaml

echo
echo "==> Service identity"
if id hallptz >/dev/null 2>&1; then
    ok "service user 'hallptz' exists"
    shell="$(getent passwd hallptz | cut -d: -f7)"
    [[ "${shell}" == "/usr/sbin/nologin" ]] \
        && ok "hallptz shell is nologin" \
        || bad "hallptz shell is '${shell}', expected /usr/sbin/nologin"
else
    bad "service user 'hallptz' was not created"
fi

echo
echo "==> Directory contract"
# Application code: the service reads it and must NOT be able to write it.
assert_mode /opt/hallptz           "750 root:hallptz"
# Site config: admin writes, service reads. setgid keeps group on new files.
assert_mode /etc/hallptz           "2750 root:hallptz"
# Runtime-writable, owned by the service.
assert_mode /var/lib/hallptz       "750 hallptz:hallptz"
assert_mode /var/log/hallptz       "750 hallptz:hallptz"
assert_mode /var/backups/hallptz   "750 hallptz:hallptz"

echo
echo "==> Application payload"
assert_exists /opt/hallptz/main.py
assert_exists /opt/hallptz/runtime/cli.py
assert_exists /opt/hallptz/config/defaults/starter.yaml
# repair_rpi_runtime.sh sources this at provisioning time to decide whether the
# system service may be enabled. If it is not deployed the fallback assumes
# system mode, which would re-arm a second launcher on a session-owned install.
assert_exists /opt/hallptz/scripts/lib/install_state.sh
# rsync excludes these; shipping .git to a customer appliance would leak history.
assert_absent /opt/hallptz/.git
assert_absent /opt/hallptz/venv

echo
echo "==> CLI launcher"
assert_exists /usr/local/bin/hallptz
[[ -x /usr/local/bin/hallptz ]] && ok "hallptz launcher is executable" \
                             || bad "hallptz launcher is not executable"

echo
echo "==> systemd unit"
assert_exists /etc/systemd/system/hallptz-control.service
if diff -q "${REPO_ROOT}/runtime/systemd/hallptz-control.service" \
           /etc/systemd/system/hallptz-control.service >/dev/null 2>&1; then
    ok "product-mode unit matches the template verbatim"
else
    bad "installed unit differs from the template (product mode copies it as-is)"
fi

echo
echo "==> Config seeded from the starter template"
assert_mode /etc/hallptz/config.yaml "640 root:hallptz"

# ── Idempotency / customer-data safety ────────────────────────────────────────
# The single most important property: an update must never destroy site config.

echo
echo "==> Second install (idempotency + config preservation)"
MARKER="# HALLPTZ-TEST-SENTINEL-DO-NOT-REMOVE"
echo "${MARKER}" >> /etc/hallptz/config.yaml
cp /etc/hallptz/config.yaml /tmp/config.before

if ! bash "${INSTALLER}" --wizard-user root; then
    echo "[FATAL] install.sh failed when re-run on an installed system" >&2
    exit 1
fi

if grep -qF "${MARKER}" /etc/hallptz/config.yaml; then
    ok "existing config.yaml was preserved on re-install"
else
    bad "re-install DESTROYED the existing config.yaml (customer data loss)"
fi

if diff -q /tmp/config.before /etc/hallptz/config.yaml >/dev/null 2>&1; then
    ok "config.yaml is byte-identical after re-install"
else
    bad "config.yaml changed on re-install"
    diff /tmp/config.before /etc/hallptz/config.yaml || true
fi

# Permissions must not drift on re-run either.
assert_mode /opt/hallptz     "750 root:hallptz"
assert_mode /etc/hallptz     "2750 root:hallptz"
assert_mode /var/lib/hallptz "750 hallptz:hallptz"

# ── GUI mode switch (#885) ────────────────────────────────────────────────────
# Exactly one launcher may exist. Switching modes must install one and strip the
# other, in both directions, or the operator gets two full-screen GUIs driving
# the same cameras.

GUI_UNIT=/etc/systemd/user/hallptz-gui.service
GUI_HELPER=/usr/local/libexec/hallptz-gui-session
GUI_AUTOSTART=/root/.config/autostart/hallptz-gui.desktop

echo
echo "==> Default (system) mode installs no session launcher"
assert_absent "${GUI_UNIT}"
assert_absent "${GUI_HELPER}"

echo
echo "==> Switching to --gui-mode user"
if ! bash "${INSTALLER}" --wizard-user root --gui-mode user; then
    echo "[FATAL] install.sh --gui-mode user failed" >&2
    exit 1
fi
assert_exists "${GUI_UNIT}"
assert_exists "${GUI_HELPER}"
assert_exists "${GUI_AUTOSTART}"
[[ -x "${GUI_HELPER}" ]] && ok "session launcher is executable" \
                         || bad "session launcher is not executable"
# Runtime data must be reachable by the desktop user through the hallptz group.
assert_mode /var/lib/hallptz "2770 hallptz:hallptz"
assert_mode /var/log/hallptz "2770 hallptz:hallptz"

# Directory bits alone are not enough: data files are written via mkstemp,
# which creates 0600, so anything already present from a system-mode install
# stays invisible to the GUI and it would start with no presets or layout.
echo "seed" > /var/lib/hallptz/pre-existing.json
chmod 600 /var/lib/hallptz/pre-existing.json
bash "${INSTALLER}" --wizard-user root --gui-mode user >/dev/null 2>&1
_pre_mode="$(stat -c '%a' /var/lib/hallptz/pre-existing.json)"
# Match the GROUP digit (second from the right), not the world digit: the
# installer grants g+rw and deliberately leaves other with no access, so a
# correct result is 660 — which an end-anchored *6|*7 would reject.
case "${_pre_mode}" in
    *6?|*7?) ok "pre-existing data file relaxed to group-accessible (${_pre_mode})" ;;
    *)       bad "pre-existing data file is still ${_pre_mode} - the GUI cannot read it" ;;
esac
# Application code stays read-only for the group either way.
assert_mode /opt/hallptz     "750 root:hallptz"
# Config is still preserved across a mode switch.
if grep -qF "${MARKER}" /etc/hallptz/config.yaml; then
    ok "config.yaml survived the GUI mode switch"
else
    bad "switching GUI mode destroyed config.yaml"
fi

echo
echo "==> Switching back to --gui-mode system"
if ! bash "${INSTALLER}" --wizard-user root --gui-mode system; then
    echo "[FATAL] install.sh --gui-mode system failed" >&2
    exit 1
fi
assert_absent "${GUI_UNIT}"
assert_absent "${GUI_HELPER}"
assert_absent "${GUI_AUTOSTART}"
assert_mode /var/lib/hallptz "750 hallptz:hallptz"
assert_mode /var/log/hallptz "750 hallptz:hallptz"

echo
echo "==> Invalid GUI mode is rejected"
if bash "${INSTALLER}" --wizard-user root --gui-mode bogus >/dev/null 2>&1; then
    bad "install.sh accepted an invalid --gui-mode"
else
    ok "install.sh rejected an invalid --gui-mode"
fi

# ── Readiness gate agrees with the installed system ───────────────────────────

echo
echo "==> install.sh --check on an installed system"
bash "${INSTALLER}" --check >/tmp/check.out 2>&1
_check_rc=$?
if [[ ${_check_rc} -eq 0 ]]; then
    ok "--check still reports ready (exit 0)"
else
    bad "--check failed on an installed system (exit ${_check_rc})"
    tail -20 /tmp/check.out
fi
# Paths now exist, so the check must say so rather than claiming a fresh system.
if grep -q "Existing path detected: /opt/hallptz" /tmp/check.out; then
    ok "--check detects the existing installation"
else
    bad "--check did not report the existing /opt/hallptz"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo
echo "=============================================================="
if [[ ${_failures} -eq 0 ]]; then
    echo " RESULT: all ${_checks} checks passed"
    echo "=============================================================="
    exit 0
fi
echo " RESULT: ${_failures} of ${_checks} checks FAILED"
echo "=============================================================="
exit 1

