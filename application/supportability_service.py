#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/supportability_service.py — SupportabilityService.
#
# Assembles the one-stop supportability summary for CLI, UI, and support bundles.
# Combines identity, doctor, known-good diff, warranty state, and maintenance.
# Never blocks normal operation — all sub-services fall back gracefully.

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# -- SupportabilitySummaryResult -----------------------------------------------

@dataclass
class SupportabilitySummaryResult:
    """
    Combined supportability summary for CLI, UI, and support bundle consumers.

    All fields default to safe values — none are None.
    JSON output is stable enough for support tools.
    """
    installation_id: str = "unknown"
    app_version: str = "unknown"
    git_commit: str = "unknown"
    profile: str = "unknown"
    fingerprint_hash: str = "unknown"

    doctor_overall: str = "unknown"
    doctor_exit_code: int = 1

    known_good_has_snapshot: bool = False
    known_good_marked_at: str = "unknown"
    state_is_clean: bool = False
    state_changed_fields: list[str] = field(default_factory=list)

    warranty_state: str = "unknown"
    warranty_reason: str = ""
    warranty_customer_message: str = ""

    maintenance_overdue: bool = False
    maintenance_last_at: str | None = None

    incident_suspicions: list[dict] = field(default_factory=list)
    support_hints: list[dict] = field(default_factory=list)

    next_recommended_action: str = ""

    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "installation_id": self.installation_id,
            "app_version": self.app_version,
            "git_commit": self.git_commit,
            "profile": self.profile,
            "fingerprint_hash": self.fingerprint_hash,
            "doctor_overall": self.doctor_overall,
            "doctor_exit_code": self.doctor_exit_code,
            "known_good": {
                "has_snapshot": self.known_good_has_snapshot,
                "marked_at": self.known_good_marked_at,
                "state_is_clean": self.state_is_clean,
                "changed_fields": self.state_changed_fields,
            },
            "warranty_state": self.warranty_state,
            "warranty_reason": self.warranty_reason,
            "warranty_customer_message": self.warranty_customer_message,
            "maintenance": {
                "overdue": self.maintenance_overdue,
                "last_completed_at": self.maintenance_last_at,
            },
            "incident_suspicions": self.incident_suspicions,
            "support_hints": self.support_hints,
            "next_recommended_action": self.next_recommended_action,
        }

    def human_summary(self) -> list[str]:
        lines = [
            "  -- Installation -------------------------",
            f"  ID:                {self.installation_id}",
            f"  App version:       {self.app_version}",
            f"  Git commit:        {self.git_commit}",
            f"  Profile:           {self.profile}",
        ]
        if self.fingerprint_hash != "unknown":
            lines.append(f"  Fingerprint:       {self.fingerprint_hash[:16]}...")
        lines += [
            "  -- Doctor -------------------------------",
            f"  Overall:           {self.doctor_overall}",
            "  -- Known-good ---------------------------",
        ]
        if self.known_good_has_snapshot:
            lines.append(f"  Marked at:         {self.known_good_marked_at}")
            if self.state_is_clean:
                lines.append("  State:             clean (matches known-good)")
            else:
                fields = ", ".join(self.state_changed_fields) or "unknown"
                lines.append(f"  State:             CHANGED ({fields})")
        else:
            lines.append("  State:             no snapshot recorded")
        lines += [
            "  -- Warranty -----------------------------",
            f"  Warranty state:    {self.warranty_state}",
        ]
        if self.warranty_customer_message:
            lines.append(f"  {self.warranty_customer_message}")
        lines += [
            "  -- Maintenance --------------------------",
            f"  Overdue:           {'yes' if self.maintenance_overdue else 'no'}",
        ]
        if self.maintenance_last_at:
            lines.append(f"  Last completed:    {self.maintenance_last_at}")
        if self.support_hints:
            lines.append("  -- Recommended actions ------------------")
            for hint in self.support_hints[:3]:  # top 3
                lines.append(f"  * {hint.get('hint', '')}")
                if hint.get("action"):
                    lines.append(f"    -> {hint['action']}")
        if self.next_recommended_action:
            lines.append(f"  Next action:       {self.next_recommended_action}")
        return lines


# -- SupportabilityService -----------------------------------------------------

class SupportabilityService:
    """
    Assemble the one-stop supportability summary.

    Combines: fingerprint, doctor, known-good diff, warranty state, maintenance.
    Never raises — all sub-services fall back gracefully.
    """

    def __init__(
        self,
        fingerprint_svc=None,
        diagnostics_svc=None,
        known_good_svc=None,
        warranty_svc=None,
        maintenance_svc=None,
        incident_classifier=None,
        hint_engine=None,
    ) -> None:
        self._fp_svc = fingerprint_svc
        self._diag_svc = diagnostics_svc
        self._kg_svc = known_good_svc
        self._warranty_svc = warranty_svc
        self._maint_svc = maintenance_svc
        self._clf = incident_classifier
        self._hints = hint_engine

    def generate(self) -> SupportabilitySummaryResult:
        """Generate the full summary. Never raises."""
        result = SupportabilitySummaryResult()
        errors: list[str] = []

        # -- Fingerprint -------------------------------------------------------
        try:
            from application.fingerprint_service import FingerprintService
            fp_svc = self._fp_svc or FingerprintService()
            fp = fp_svc.generate()
            result.installation_id = fp.installation_id
            result.app_version = fp.app_version
            result.git_commit = fp.git_commit
            result.profile = fp.profile
            result.fingerprint_hash = fp.fingerprint_hash()
        except Exception as exc:
            errors.append(f"fingerprint: {exc}")
            logger.warning("SupportabilityService: fingerprint failed: %s", exc)

        # -- Doctor ------------------------------------------------------------
        failing_checks: list[str] = []
        try:
            from application.diagnostics_service import DiagnosticsService, Status
            diag_svc = self._diag_svc or DiagnosticsService()
            report = diag_svc.run()
            _LABEL = {Status.OK: "OK", Status.WARNING: "WARNING", Status.FAIL: "FAIL"}
            result.doctor_overall = _LABEL.get(report.overall, "UNKNOWN")
            result.doctor_exit_code = report.exit_code
            failing_checks = [c.name for c in report.checks if c.status == Status.FAIL]
        except Exception as exc:
            errors.append(f"doctor: {exc}")
            logger.warning("SupportabilityService: doctor failed: %s", exc)

        # -- Known-good --------------------------------------------------------
        changed_fields: list[str] = []
        try:
            from application.known_good_state_service import KnownGoodStateService
            kg_svc = self._kg_svc or KnownGoodStateService()
            snap = kg_svc.load()
            diff = kg_svc.diff()
            if snap is not None:
                result.known_good_has_snapshot = True
                result.known_good_marked_at = snap.marked_at
            result.state_is_clean = diff.is_clean
            result.state_changed_fields = [c.field for c in diff.changes]
            changed_fields = result.state_changed_fields
        except Exception as exc:
            errors.append(f"known_good: {exc}")
            logger.warning("SupportabilityService: known-good failed: %s", exc)

        # -- Warranty ----------------------------------------------------------
        warranty_result = None
        try:
            from application.warranty_state_service import WarrantyStateService
            w_svc = self._warranty_svc or WarrantyStateService()
            warranty_result = w_svc.assess()
            result.warranty_state = warranty_result.state.value
            result.warranty_reason = warranty_result.reason
            result.warranty_customer_message = warranty_result.customer_message
        except Exception as exc:
            errors.append(f"warranty: {exc}")
            logger.warning("SupportabilityService: warranty failed: %s", exc)

        # -- Maintenance -------------------------------------------------------
        try:
            from application.maintenance_service import MaintenanceService
            maint_svc = self._maint_svc or MaintenanceService()
            maint = maint_svc.status()
            result.maintenance_overdue = maint.overdue
            result.maintenance_last_at = maint.last_completed_at
        except Exception as exc:
            errors.append(f"maintenance: {exc}")
            logger.warning("SupportabilityService: maintenance failed: %s", exc)

        # -- Incident suspicions -----------------------------------------------
        suspicions = []
        try:
            from application.warranty_state_service import IncidentClassifier
            clf = self._clf or IncidentClassifier()
            suspicions = clf.classify_from_doctor(failing_checks) + \
                         clf.classify_from_diff(changed_fields)
            result.incident_suspicions = [s.to_dict() for s in suspicions]
        except Exception as exc:
            errors.append(f"incident_classifier: {exc}")
            logger.warning("SupportabilityService: incident classifier failed: %s", exc)

        # -- Support hints -----------------------------------------------------
        try:
            from application.warranty_state_service import SupportHintEngine
            from application.warranty_state_service import WarrantyStateResult
            hint_engine = self._hints or SupportHintEngine()
            if warranty_result is None:
                warranty_result = WarrantyStateResult()
            hints = hint_engine.hints_for(warranty_result, suspicions)
            result.support_hints = [h.to_dict() for h in hints]
            if hints:
                result.next_recommended_action = hints[0].action or hints[0].hint
        except Exception as exc:
            errors.append(f"hints: {exc}")
            logger.warning("SupportabilityService: hints failed: %s", exc)

        result.errors = errors
        return result
