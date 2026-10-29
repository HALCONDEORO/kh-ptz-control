#!/usr/bin/env bash
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
#
# tests/installer/readiness_harness.sh — executable coverage for the install.sh
# readiness gate (#888).
#
# The first physical install showed that `install.sh --check` is the gate every
# deployment passes through, yet it had zero executable coverage. A full
# write-side install needs a container (useradd, rsync, a live systemd); the
# readiness check does not — it is read-only. This harness runs the REAL
# `--check` logic by supplying stub implementations of the privileged/host
# commands it probes for (id, git, rsync, systemctl), so the classification
# logic (Python version, required templates, existing-path preservation, exit
# codes) is exercised on any host, including CI, without root or a Pi.
#
# It changes nothing in install.sh: the stubs live in a throwaway directory that
# is only prepended to PATH for the duration of one check run.
#
# Usage:
#   readiness_harness.sh real     — run --check against the real repository
#   readiness_harness.sh stripped — run --check against a copy missing the
#                                   systemd service template (must FAIL)
#
# Exit code and stdout are those of install.sh --check itself.

set -euo pipefail

MODE="${1:-real}"

HARNESS_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -P "${HARNESS_DIR}/../.." && pwd)"
INSTALLER="${REPO_ROOT}/runtime/installer/install.sh"

[[ -f "${INSTALLER}" ]] || { echo "installer not found: ${INSTALLER}" >&2; exit 2; }

# ── Stub directory ────────────────────────────────────────────────────────────
# Privileged / host commands install.sh --check probes for. Each stub is inert
# and deterministic so the check's own logic — not the host — decides the
# result.

STUB_DIR="$(mktemp -d)"
trap 'rm -rf "${STUB_DIR}"' EXIT

# id -u must report root, so the "must be run as root" gate passes. In --check
# mode `id -u` is the only id call install.sh makes (the `id "${APP_USER}"`
# lookup lives after the check-mode exit), so an inert stub is sufficient and
# fully portable.
cat > "${STUB_DIR}/id" <<'STUB'
#!/usr/bin/env bash
[[ "$1" == "-u" ]] && { echo 0; exit 0; }
exit 0
STUB

# git, rsync, systemctl only need to *exist* for require_command in --check mode;
# the readiness check never actually invokes them. Make them succeed silently.
for _cmd in git rsync systemctl; do
    cat > "${STUB_DIR}/${_cmd}" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
done

chmod +x "${STUB_DIR}"/*

# ── Target selection ──────────────────────────────────────────────────────────
# install.sh derives REPO_ROOT from its own location (../..). To test the
# "required template missing -> FAIL" branch we run a copy of install.sh whose
# computed repo root legitimately lacks the template, rather than deleting
# anything from the real tree.

RUN_INSTALLER="${INSTALLER}"
STRIP_ROOT=""
if [[ "${MODE}" == "stripped" ]]; then
    STRIP_ROOT="$(mktemp -d)"
    trap 'rm -rf "${STUB_DIR}" "${STRIP_ROOT}"' EXIT
    mkdir -p "${STRIP_ROOT}/runtime/installer"
    cp "${INSTALLER}" "${STRIP_ROOT}/runtime/installer/install.sh"
    # Deliberately do NOT copy runtime/systemd/hallptz-control.service, so the
    # service-template check must report FAIL.
    RUN_INSTALLER="${STRIP_ROOT}/runtime/installer/install.sh"
fi

# ── Run the real readiness check with only the stubs in front ─────────────────

PATH="${STUB_DIR}:${PATH}" bash "${RUN_INSTALLER}" --check

