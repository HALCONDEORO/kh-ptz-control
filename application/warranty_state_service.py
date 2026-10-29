#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/warranty_state_service.py — WarrantyStateService, IncidentClassifier,
# SupportHintEngine.
#
# Translates diagnostic and known-good evidence into neutral support/warranty states
# and suspected incident categories.
#
# Rules are advisory (suspected, not final blame). Wording is customer-neutral.
# This service never blocks live/core operation.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from domain.supportability import (
    BillableHint,
    IncidentCategory,
    IncidentClassification,
    IncidentImpact,
    IncidentSeverity,
    WarrantyState,
)

logger = logging.getLogger(__name__)


# ── WarrantyStateResult ───────────────────────────────────────────────────────

@dataclass
class WarrantyStateResult:
    """Result of a warranty state assessment."""
    state: WarrantyState = WarrantyState.UNKNOWN
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    customer_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "reason": self.reason,
            "evidence": self.evidence,
            "customer_message": self.customer_message,
        }

    def human_summary(self) -> list[str]:
        lines = [
            f"  Warranty state:    {self.state.value}",
            f"  Reason:            {self.reason}",
        ]
        if self.customer_message:
            lines.append(f"  Message:           {self.customer_message}")
        return lines


# ── IncidentSuspicion ─────────────────────────────────────────────────────────

@dataclass
class IncidentSuspicion:
    """A single suspected incident with advisory classification."""
    classification: IncidentClassification
    trigger: str       # the check name or evidence key that triggered this
    advisory: str      # human-readable hint

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification.to_dict(),
            "trigger": self.trigger,
            "advisory": self.advisory,
        }


# ── SupportHint ───────────────────────────────────────────────────────────────

@dataclass
class SupportHint:
    """An advisory support hint derived from evidence."""
    priority: int           # lower = more urgent, 1–10
    hint: str
    trigger: str
    action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "priority": self.priority,
            "hint": self.hint,
            "trigger": self.trigger,
            "action": self.action,
        }


# ── WarrantyStateService ──────────────────────────────────────────────────────

class WarrantyStateService:
    """
    Determine the warranty/support state of the installation.

    Sources considered:
    - KnownGoodStateService.diff() — has the state changed since validation?
    - DiagnosticsService.run()     — are there blocking failures?
    """

    def __init__(
        self,
        known_good_svc=None,
        diagnostics_svc=None,
    ) -> None:
        self._kg_svc = known_good_svc
        self._diag_svc = diagnostics_svc

    def assess(self) -> WarrantyStateResult:
        """
        Assess and return the current warranty state.

        Never raises — falls back to UNKNOWN on any error.
        """
        try:
            return self._assess()
        except Exception as exc:
            logger.warning("WarrantyStateService.assess() failed: %s", exc)
            return WarrantyStateResult(
                state=WarrantyState.UNKNOWN,
                reason=f"Assessment failed: {exc}",
                customer_message="The system could not determine the current support state.",
            )

    def _assess(self) -> WarrantyStateResult:
        kg_svc = self._get_kg_svc()
        diag_svc = self._get_diag_svc()

        # Run doctor
        from application.diagnostics_service import Status
        try:
            report = diag_svc.run()
            has_blocking_fail = any(c.blocking and c.status == Status.FAIL for c in report.checks)
            has_fail = any(c.status == Status.FAIL for c in report.checks)
            has_warning = any(c.status == Status.WARNING for c in report.checks)
            fail_names = [c.name for c in report.checks if c.status == Status.FAIL]
        except Exception:
            has_blocking_fail = False
            has_fail = False
            has_warning = False
            fail_names = []

        # Check known-good state
        try:
            diff = kg_svc.diff()
            has_known_good = diff.has_known_good
            state_changed = has_known_good and not diff.is_clean
            changed_fields = [c.field for c in diff.changes] if state_changed else []
        except Exception:
            has_known_good = False
            state_changed = False
            changed_fields = []

        # Determine state
        if has_blocking_fail:
            return WarrantyStateResult(
                state=WarrantyState.REVALIDATION_REQUIRED,
                reason=f"Blocking diagnostic failure(s): {', '.join(fail_names)}",
                evidence={"failing_checks": fail_names},
                customer_message=(
                    "The system has one or more diagnostic failures that require "
                    "attention before the installation can be considered validated."
                ),
            )

        if state_changed:
            return WarrantyStateResult(
                state=WarrantyState.CHANGED_SINCE_VALIDATION,
                reason=f"State differs from known-good snapshot: {', '.join(changed_fields)}",
                evidence={"changed_fields": changed_fields},
                customer_message=(
                    "The installation configuration has changed since it was last validated. "
                    "Please re-run validation or contact support."
                ),
            )

        if not has_known_good:
            if has_fail:
                return WarrantyStateResult(
                    state=WarrantyState.REVALIDATION_REQUIRED,
                    reason="No known-good state and diagnostic failures present",
                    evidence={"failing_checks": fail_names},
                    customer_message=(
                        "No validated baseline has been recorded and the system has "
                        "diagnostic failures. Please contact support."
                    ),
                )
            return WarrantyStateResult(
                state=WarrantyState.UNKNOWN,
                reason="No known-good state has been recorded",
                customer_message=(
                    "No validated baseline has been recorded for this installation. "
                    "Run 'hallptz known-good mark' after a successful doctor pass."
                ),
            )

        if has_fail:
            return WarrantyStateResult(
                state=WarrantyState.REVALIDATION_REQUIRED,
                reason=f"Diagnostic failure(s) since validation: {', '.join(fail_names)}",
                evidence={"failing_checks": fail_names},
                customer_message=(
                    "Diagnostic failures have occurred since the last validated state. "
                    "Please contact support."
                ),
            )

        if has_warning:
            return WarrantyStateResult(
                state=WarrantyState.VALIDATED_WITH_WARNINGS,
                reason="State matches known-good; non-blocking warnings present",
                customer_message="The installation is validated with minor advisory warnings.",
            )

        return WarrantyStateResult(
            state=WarrantyState.VALIDATED,
            reason="State matches known-good; no failures or warnings",
            customer_message="The installation is validated and in a known-good state.",
        )

    def _get_kg_svc(self):
        if self._kg_svc is not None:
            return self._kg_svc
        from application.known_good_state_service import KnownGoodStateService
        return KnownGoodStateService()

    def _get_diag_svc(self):
        if self._diag_svc is not None:
            return self._diag_svc
        from application.diagnostics_service import DiagnosticsService
        return DiagnosticsService()


# ── IncidentClassifier ────────────────────────────────────────────────────────

# Primitive suspicion rules: check name → suspected incident classification.
# Rules are advisory only — not definitive blame.
_INCIDENT_RULES: list[tuple[str, IncidentClassification, str]] = [
    (
        "ip_config",
        IncidentClassification(
            category=IncidentCategory.NETWORK_CHANGE,
            severity=IncidentSeverity.HIGH,
            impact=IncidentImpact.LIVE_EVENT_RISK,
            billable_hint=BillableHint.UNKNOWN,
            follow_up="Verify camera and switcher IP addresses match config.yaml",
        ),
        "IP configuration issues often follow network infrastructure changes.",
    ),
    (
        "config",
        IncidentClassification(
            category=IncidentCategory.CONFIGURATION_ERROR,
            severity=IncidentSeverity.MEDIUM,
            impact=IncidentImpact.CUSTOMER_READY_BLOCKED,
            billable_hint=BillableHint.UNKNOWN,
            follow_up="Check config.yaml is present and valid",
        ),
        "Missing or invalid config.yaml may indicate a deployment or upgrade issue.",
    ),
    (
        "data_dir",
        IncidentClassification(
            category=IncidentCategory.INSTALLER_ERROR,
            severity=IncidentSeverity.HIGH,
            impact=IncidentImpact.SYSTEM_UNUSABLE,
            billable_hint=BillableHint.NO,
            follow_up="Check data directory permissions",
        ),
        "Data directory permission errors suggest an installer or OS-level issue.",
    ),
    (
        "simulation",
        IncidentClassification(
            category=IncidentCategory.CUSTOMER_CHANGE,
            severity=IncidentSeverity.LOW,
            impact=IncidentImpact.OPERATOR_INCONVENIENCE,
            billable_hint=BillableHint.UNKNOWN,
            follow_up="Exit simulation mode before live use",
        ),
        "Simulation mode left active may cause confusion during live events.",
    ),
    (
        "installation_profile",
        IncidentClassification(
            category=IncidentCategory.CONFIGURATION_ERROR,
            severity=IncidentSeverity.MEDIUM,
            impact=IncidentImpact.REDUCED_FUNCTIONALITY,
            billable_hint=BillableHint.UNKNOWN,
            follow_up="Verify site.installation_profile in config.yaml",
        ),
        "Profile mismatch suggests cameras or hardware do not match the configured profile.",
    ),
    (
        "connectivity_mode",
        IncidentClassification(
            category=IncidentCategory.NETWORK_CHANGE,
            severity=IncidentSeverity.LOW,
            impact=IncidentImpact.OPERATOR_INCONVENIENCE,
            billable_hint=BillableHint.UNKNOWN,
            follow_up="Verify runtime.connectivity_mode in config.yaml",
        ),
        "Unknown connectivity mode may indicate an unsupported configuration.",
    ),
]

_CHANGE_RULES: dict[str, tuple[IncidentClassification, str]] = {
    "config_hash": (
        IncidentClassification(
            category=IncidentCategory.CUSTOMER_CHANGE,
            severity=IncidentSeverity.MEDIUM,
            impact=IncidentImpact.REDUCED_FUNCTIONALITY,
            billable_hint=BillableHint.UNKNOWN,
            follow_up="Review config.yaml changes since last validation",
        ),
        "Configuration changed since last known-good state.",
    ),
    "layout_hash": (
        IncidentClassification(
            category=IncidentCategory.CUSTOMER_CHANGE,
            severity=IncidentSeverity.LOW,
            impact=IncidentImpact.OPERATOR_INCONVENIENCE,
            billable_hint=BillableHint.UNKNOWN,
            follow_up="Review room_layout.json changes since last validation",
        ),
        "Room layout changed since last known-good state.",
    ),
    "cameras": (
        IncidentClassification(
            category=IncidentCategory.NETWORK_CHANGE,
            severity=IncidentSeverity.HIGH,
            impact=IncidentImpact.LIVE_EVENT_RISK,
            billable_hint=BillableHint.UNKNOWN,
            follow_up="Verify camera connection and IP configuration",
        ),
        "Camera configuration changed since last known-good state.",
    ),
    "git_commit": (
        IncidentClassification(
            category=IncidentCategory.SOFTWARE_BUG,
            severity=IncidentSeverity.LOW,
            impact=IncidentImpact.OPERATOR_INCONVENIENCE,
            billable_hint=BillableHint.NO,
            follow_up="Review release notes for the new version",
        ),
        "Software version changed since last known-good state.",
    ),
}


class IncidentClassifier:
    """
    Map doctor findings and state diff to suspected incident categories.

    Rules are advisory only — never definitive blame.
    """

    def classify_from_doctor(
        self,
        failing_check_names: list[str],
    ) -> list[IncidentSuspicion]:
        """Return suspected incidents for the given failing check names."""
        suspicions: list[IncidentSuspicion] = []
        for check_name in failing_check_names:
            for rule_name, classification, advisory in _INCIDENT_RULES:
                if rule_name == check_name:
                    suspicions.append(IncidentSuspicion(
                        classification=classification,
                        trigger=check_name,
                        advisory=advisory,
                    ))
        return suspicions

    def classify_from_diff(
        self,
        changed_fields: list[str],
    ) -> list[IncidentSuspicion]:
        """Return suspected incidents for the given changed state fields."""
        suspicions: list[IncidentSuspicion] = []
        for field_name in changed_fields:
            if field_name in _CHANGE_RULES:
                classification, advisory = _CHANGE_RULES[field_name]
                suspicions.append(IncidentSuspicion(
                    classification=classification,
                    trigger=field_name,
                    advisory=advisory,
                ))
        return suspicions


# ── SupportHintEngine ─────────────────────────────────────────────────────────

class SupportHintEngine:
    """
    Generate advisory support hints from warranty state and incident suspicions.

    Hints are evidence-based and action-oriented. Never block live operation.
    """

    def hints_for(
        self,
        warranty_state: WarrantyStateResult,
        suspicions: list[IncidentSuspicion],
    ) -> list[SupportHint]:
        """Return a prioritised list of support hints."""
        hints: list[SupportHint] = []

        # Warranty state hints
        if warranty_state.state == WarrantyState.UNKNOWN:
            hints.append(SupportHint(
                priority=3,
                hint="No validated baseline recorded for this installation.",
                trigger="warranty_state:unknown",
                action="Run 'hallptz doctor' and then 'hallptz known-good mark --after-doctor-pass'.",
            ))
        elif warranty_state.state == WarrantyState.CHANGED_SINCE_VALIDATION:
            hints.append(SupportHint(
                priority=2,
                hint="Installation state has changed since last validation.",
                trigger="warranty_state:changed_since_validation",
                action="Review the changes with 'hallptz known-good diff', then re-validate.",
            ))
        elif warranty_state.state == WarrantyState.REVALIDATION_REQUIRED:
            hints.append(SupportHint(
                priority=1,
                hint="Revalidation required before this installation can be considered supported.",
                trigger="warranty_state:revalidation_required",
                action="Fix all blocking doctor checks, then run 'hallptz known-good mark'.",
            ))

        # Incident suspicion hints
        for suspicion in suspicions:
            action = suspicion.classification.follow_up
            hints.append(SupportHint(
                priority=5,
                hint=suspicion.advisory,
                trigger=f"incident:{suspicion.trigger}",
                action=action,
            ))

        # Sort by priority ascending (lower = more urgent)
        hints.sort(key=lambda h: h.priority)
        return hints
