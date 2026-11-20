#!/usr/bin/env bash
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# CI only. Retry transient repository errors, never suppress a final failure.
set -euo pipefail

if [[ "${1:-}" == --attempt ]]; then
    shift
    export DEBIAN_FRONTEND=noninteractive
    options=(-o Acquire::Retries=1 -o Acquire::http::Timeout=10
             -o Acquire::https::Timeout=10 -o APT::Update::Error-Mode=any)
    sudo --preserve-env=DEBIAN_FRONTEND apt-get "${options[@]}" update
    sudo --preserve-env=DEBIAN_FRONTEND apt-get "${options[@]}" install -y --no-install-recommends "$@"
    exit 0
fi

if [[ $# == 0 ]]; then
    echo 'Usage: install_qt.sh PACKAGE [PACKAGE ...]' >&2
    exit 2
fi

# Each attempt includes BOTH fresh indices and package installation. 3*(60+5)
# seconds plus 5+10 seconds backoff gives a <=210 second installation budget,
# leaving time for tests in the smallest existing five-minute job. No mirror
# rewrites, unauthenticated packages, third-party caches or allowed failures.
for attempt in 1 2 3; do
    if timeout --kill-after=5s 60s bash "$0" --attempt "$@"; then
        exit 0
    else
        result=$?
        echo "Qt package installation attempt ${attempt}/3 failed (exit ${result})" >&2
    fi
    if [[ $attempt != 3 ]]; then
        sleep "$((attempt * 5))"
    fi
done
exit "$result"
