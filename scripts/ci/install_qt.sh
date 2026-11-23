#!/usr/bin/env bash
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# CI only. Use signed official Ubuntu archives, never suppress final failure.
set -euo pipefail

if [[ "${1:-}" == --attempt ]]; then
    shift
    export DEBIAN_FRONTEND=noninteractive
    : "${KH_CI_APT_SOURCES:?Internal source list is required}"
    options=(-o Acquire::Retries=0 -o Acquire::http::Timeout=10
             -o Acquire::https::Timeout=10 -o APT::Update::Error-Mode=any
             -o "Dir::Etc::sourcelist=$KH_CI_APT_SOURCES"
             -o Dir::Etc::sourceparts=- -o Acquire::Languages=none
             -o 'Acquire::IndexTargets::deb::CNF::DefaultEnabled=false')
    sudo --preserve-env=DEBIAN_FRONTEND apt-get "${options[@]}" update
    sudo --preserve-env=DEBIAN_FRONTEND apt-get "${options[@]}" install -y --no-install-recommends "$@"
    exit 0
fi

if [[ $# == 0 ]]; then
    echo 'Usage: install_qt.sh PACKAGE [PACKAGE ...]' >&2
    exit 2
fi

# This helper only supports the workflow's Ubuntu24.04 amd64 runner. Never
# reuse a host's codename in an arbitrary package URL, or modify host sources.
. /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 || "$(dpkg --print-architecture)" != amd64 ]]; then
    echo 'Unsupported CI runner for Qt system dependencies' >&2
    exit 2
fi
keyring=/usr/share/keyrings/ubuntu-archive-keyring.gpg
[[ -r "$keyring" ]] || { echo 'Ubuntu archive signing keyring is missing' >&2; exit 2; }
KH_CI_APT_SOURCES=$(mktemp)
export KH_CI_APT_SOURCES
trap 'rm -f "$KH_CI_APT_SOURCES"' EXIT
chmod 644 "$KH_CI_APT_SOURCES"
printf '%s\n' \
    "deb [arch=amd64 signed-by=$keyring] https://archive.ubuntu.com/ubuntu noble main universe" \
    "deb [arch=amd64 signed-by=$keyring] https://archive.ubuntu.com/ubuntu noble-updates main universe" \
    "deb [arch=amd64 signed-by=$keyring] https://security.ubuntu.com/ubuntu noble-security main universe" \
    > "$KH_CI_APT_SOURCES"

# One195second attempt plus kill grace stays within200seconds. Avoid
# EC2 mirror timeouts consuming most of every fresh attempt. Package signatures,
# fresh index requirements and final failure remain mandatory. No source edits.
# No translation/CNF indexes or unrelated restricted/multiverse repositories.
# A single uninterrupted budget lets downloads finish instead of killing/restarting.
if timeout --kill-after=5s 195s bash "$0" --attempt "$@"; then
    exit 0
else
    result=$?
    echo "Qt package installation attempt 1/1 failed (exit ${result})" >&2
fi
exit "$result"
