#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/doctor_outcome.py — Deployment-facing outcome model for `khptz doctor` (#887)
#
# Pure domain module — no I/O, no Qt.
#
# During the first physical Raspberry Pi installation, `khptz doctor` collapsed
# five different classes of result into "Overall: WARN":
#
#   - fatal runtime/permission failures
#   - configuration contradictions (profile mismatch, ATEM without an IP)
#   - optional-component warnings (GPIO absent)
#   - security/deployment recommendations (flat LAN)
#   - healthy hardware and camera checks
#
# An installer could not tell from that whether the appliance was unusable,
# usable but needing configuration, or healthy with only a recommendation left.
# This module gives each of those a distinct outcome and exit code.

from __future__ import annotations

from enum import Enum


class CheckCategory(str, Enum):
    """What kind of result a check produces when it is not OK.

    OPERATIONAL   — the appliance cannot run correctly (service, paths, runtime).
    CONFIGURATION — it runs, but required configuration is missing/contradictory.
    ADVISORY      — it runs and is configured; this is a recommendation only.
    """
    OPERATIONAL   = "operational"
    CONFIGURATION = "configuration"
    ADVISORY      = "advisory"


class DoctorOutcome(str, Enum):
    """Final deployment verdict, in increasing order of severity."""
    PASS                  = "PASS"
    READY_WITH_ADVISORIES = "READY_WITH_ADVISORIES"
    CONFIG_REQUIRED       = "CONFIG_REQUIRED"
    FAIL                  = "FAIL"


# Exit codes are part of the installer contract: a wrapper script must be able
# to branch on "usable" vs "needs configuration" vs "broken" without parsing
# text. 0 means fully healthy; 10 is still operational.
_EXIT_CODES: dict[DoctorOutcome, int] = {
    DoctorOutcome.PASS:                  0,
    DoctorOutcome.READY_WITH_ADVISORIES: 10,
    DoctorOutcome.CONFIG_REQUIRED:       20,
    DoctorOutcome.FAIL:                  30,
}

_DESCRIPTIONS: dict[DoctorOutcome, str] = {
    DoctorOutcome.PASS:
        "Operational and correctly configured.",
    DoctorOutcome.READY_WITH_ADVISORIES:
        "Operational. Only non-blocking deployment recommendations remain.",
    DoctorOutcome.CONFIG_REQUIRED:
        "The runtime works, but required configuration is incomplete.",
    DoctorOutcome.FAIL:
        "The application cannot operate safely or reliably.",
}

#: Outcomes in which the appliance is usable right now.
OPERATIONAL_OUTCOMES = frozenset({
    DoctorOutcome.PASS,
    DoctorOutcome.READY_WITH_ADVISORIES,
})


def exit_code_for(outcome: DoctorOutcome) -> int:
    """Return the process exit code that represents *outcome*."""
    return _EXIT_CODES[outcome]


def describe(outcome: DoctorOutcome) -> str:
    """Return the one-line meaning of *outcome*, for human output."""
    return _DESCRIPTIONS[outcome]


def is_operational(outcome: DoctorOutcome) -> bool:
    """True if the appliance can be used as-is."""
    return outcome in OPERATIONAL_OUTCOMES


def derive_outcome(
    *,
    has_blocking_failure: bool,
    has_actionable_issue: bool,
    has_advisory: bool,
) -> DoctorOutcome:
    """Combine the per-category findings into a single verdict.

    Severity is strictly ordered, and the three inputs are exhaustive — every
    non-OK check contributes to exactly one of them, so nothing can silently
    vanish from the final outcome:

    * ``has_blocking_failure`` — a FAIL check, or a blocking operational one.
      The appliance cannot be used.
    * ``has_actionable_issue`` — a configuration gap (ATEM enabled with no IP)
      or a non-blocking operational degradation (an ATEM that does not answer).
      The runtime works, but an installer must act before sign-off.
    * ``has_advisory`` — hardening advice only (cameras on a flat LAN).

    This ordering is what stops a healthy two-camera install from reading the
    same as a broken one (#887).
    """
    if has_blocking_failure:
        return DoctorOutcome.FAIL
    if has_actionable_issue:
        return DoctorOutcome.CONFIG_REQUIRED
    if has_advisory:
        return DoctorOutcome.READY_WITH_ADVISORIES
    return DoctorOutcome.PASS
