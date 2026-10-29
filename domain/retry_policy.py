# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/retry_policy.py — Bounded retry policy (pure domain rule, no I/O)
#
# Shared by CameraWorker (TCP reconnect) and ATEMMonitor (switcher reconnect).
# Each retry session has a fixed number of attempts with explicit backoff
# steps between them.  After the policy is exhausted the caller decides what
# to do (give up, emit a DISCONNECTED state, or wait for the next heartbeat
# to start a fresh session).

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """
    Immutable bounded-retry policy with fixed back-off steps.

    ``max_attempts`` = 1 (initial) + len(backoffs) (retries).

    Example::

        policy = RetryPolicy(backoffs=(2, 5, 15))
        policy.max_attempts  # → 4
        policy.backoffs[0]   # → 2  (seconds before 2nd attempt)
        policy.backoffs[1]   # → 5  (seconds before 3rd attempt)
        policy.backoffs[2]   # → 15 (seconds before 4th attempt)
    """

    backoffs: tuple[int, ...]  # seconds to wait *before* each retry

    @property
    def max_attempts(self) -> int:
        """Total number of connection attempts (initial + all retries)."""
        return 1 + len(self.backoffs)


# ── Application-level defaults ────────────────────────────────────────────────

# Camera TCP connections: cameras may take 5–30 s to boot after power-on.
# 3 retries give ~50 s of patience at startup without blocking indefinitely.
CAMERA_RETRY_POLICY = RetryPolicy(backoffs=(5, 15, 30))

# ATEM switcher: responds faster; a tighter policy limits startup delay.
ATEM_RETRY_POLICY = RetryPolicy(backoffs=(2, 5, 15))
