#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_warranty_state_service.py — Tests for WarrantyStateService, IncidentClassifier,
SupportHintEngine (#565).

Covers:
- WarrantyStateResult: to_dict is JSON-serializable, human_summary returns strings
- WarrantyStateService: VALIDATED, VALIDATED_WITH_WARNINGS, CHANGED_SINCE_VALIDATION,
  REVALIDATION_REQUIRED, UNKNOWN states
- assess() never raises (fallback to UNKNOWN)
- IncidentClassifier: classify_from_doctor, classify_from_diff
- classify returns empty list for unknown check name
- Network change suspected when ip_config fails
- Config change suspected when config_hash changes since known-good
- SupportHintEngine: hints_for returns hints, priority ordering, UNKNOWN/changed hint
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock


from application.warranty_state_service import (
    IncidentClassifier,
    SupportHintEngine,
    WarrantyStateResult,
    WarrantyStateService,
)
from domain.supportability import (
    IncidentCategory,
    WarrantyState,
)


# ── WarrantyStateResult ───────────────────────────────────────────────────────

class TestWarrantyStateResult:

    def test_defaults(self):
        r = WarrantyStateResult()
        assert r.state is WarrantyState.UNKNOWN
        assert r.reason == ""

    def test_to_dict_is_json_serializable(self):
        r = WarrantyStateResult(
            state=WarrantyState.VALIDATED,
            reason="OK",
            evidence={"checks": ["version"]},
            customer_message="All good.",
        )
        json.dumps(r.to_dict())  # must not raise

    def test_to_dict_state_is_string(self):
        r = WarrantyStateResult(state=WarrantyState.CHANGED_SINCE_VALIDATION)
        assert r.to_dict()["state"] == "changed_since_validation"

    def test_human_summary_returns_list_of_strings(self):
        r = WarrantyStateResult(state=WarrantyState.VALIDATED, reason="OK")
        lines = r.human_summary()
        assert isinstance(lines, list)
        assert all(isinstance(line, str) for line in lines)


# ── WarrantyStateService ──────────────────────────────────────────────────────

def _make_diff(has_known_good=True, changes=None):
    from application.known_good_state_service import StateDiff
    return StateDiff(
        has_known_good=has_known_good,
        no_known_good_reason="" if has_known_good else "No known-good state recorded",
        changes=changes or [],
        unchanged_fields=["config_hash"] if has_known_good and not changes else [],
    )


def _make_report(statuses):
    """Build a fake DiagnosticsReport. statuses: list of (name, Status, blocking)."""
    from application.diagnostics_service import CheckResult, DiagnosticsReport
    report = DiagnosticsReport()
    for name, status, blocking in statuses:
        report.add(CheckResult(name, status, f"{name}: {status.name}", blocking=blocking))
    return report


def _make_svc(diff=None, report=None):
    kg = MagicMock()
    kg.diff.return_value = diff if diff is not None else _make_diff()
    diag = MagicMock()
    diag.run.return_value = report if report is not None else _make_report([])
    return WarrantyStateService(known_good_svc=kg, diagnostics_svc=diag)


class TestWarrantyStateServiceValidated:

    def test_validated_when_clean_and_no_failures(self):
        from application.diagnostics_service import Status
        svc = _make_svc(
            diff=_make_diff(has_known_good=True, changes=[]),
            report=_make_report([("version", Status.OK, False)]),
        )
        result = svc.assess()
        assert result.state is WarrantyState.VALIDATED

    def test_validated_with_warnings_when_warnings_present(self):
        from application.diagnostics_service import Status
        svc = _make_svc(
            diff=_make_diff(has_known_good=True, changes=[]),
            report=_make_report([("config", Status.WARNING, False)]),
        )
        result = svc.assess()
        assert result.state is WarrantyState.VALIDATED_WITH_WARNINGS


class TestWarrantyStateServiceChangedSinceValidation:

    def test_changed_since_validation_when_diff_has_changes(self):
        from application.diagnostics_service import Status
        from application.known_good_state_service import FieldDiff
        diff = _make_diff(has_known_good=True, changes=[FieldDiff("config_hash", "old", "new")])
        svc = _make_svc(
            diff=diff,
            report=_make_report([("version", Status.OK, False)]),
        )
        result = svc.assess()
        assert result.state is WarrantyState.CHANGED_SINCE_VALIDATION

    def test_changed_since_validation_includes_changed_fields_in_evidence(self):
        from application.diagnostics_service import Status
        from application.known_good_state_service import FieldDiff
        diff = _make_diff(
            has_known_good=True,
            changes=[
                FieldDiff("config_hash", "old", "new"),
                FieldDiff("cameras", "cam1:yes", "none"),
            ],
        )
        svc = _make_svc(diff=diff, report=_make_report([("version", Status.OK, False)]))
        result = svc.assess()
        assert "config_hash" in result.evidence.get("changed_fields", [])


class TestWarrantyStateServiceRevalidation:

    def test_revalidation_required_when_blocking_fail(self):
        from application.diagnostics_service import Status
        svc = _make_svc(
            diff=_make_diff(has_known_good=True, changes=[]),
            report=_make_report([("data_dir", Status.FAIL, True)]),
        )
        result = svc.assess()
        assert result.state is WarrantyState.REVALIDATION_REQUIRED

    def test_revalidation_required_takes_precedence_over_state_change(self):
        from application.diagnostics_service import Status
        from application.known_good_state_service import FieldDiff
        diff = _make_diff(has_known_good=True, changes=[FieldDiff("config_hash", "old", "new")])
        svc = _make_svc(
            diff=diff,
            report=_make_report([("data_dir", Status.FAIL, True)]),
        )
        result = svc.assess()
        assert result.state is WarrantyState.REVALIDATION_REQUIRED

    def test_revalidation_required_when_no_known_good_and_fail(self):
        from application.diagnostics_service import Status
        svc = _make_svc(
            diff=_make_diff(has_known_good=False),
            report=_make_report([("data_dir", Status.FAIL, False)]),
        )
        result = svc.assess()
        assert result.state is WarrantyState.REVALIDATION_REQUIRED


class TestWarrantyStateServiceUnknown:

    def test_unknown_when_no_known_good_and_no_failures(self):
        from application.diagnostics_service import Status
        svc = _make_svc(
            diff=_make_diff(has_known_good=False),
            report=_make_report([("version", Status.OK, False)]),
        )
        result = svc.assess()
        assert result.state is WarrantyState.UNKNOWN

    def test_assess_never_raises_on_kg_error(self):
        kg = MagicMock()
        kg.diff.side_effect = RuntimeError("KG exploded")
        diag = MagicMock()
        diag.run.return_value = _make_report([])
        svc = WarrantyStateService(known_good_svc=kg, diagnostics_svc=diag)
        result = svc.assess()  # must not raise
        # Falls through to UNKNOWN or VALIDATED (diff failed gracefully)
        assert result.state in (WarrantyState.UNKNOWN, WarrantyState.VALIDATED)

    def test_assess_never_raises_on_diag_error(self):
        kg = MagicMock()
        kg.diff.return_value = _make_diff(has_known_good=False)
        diag = MagicMock()
        diag.run.side_effect = RuntimeError("Doctor exploded")
        svc = WarrantyStateService(known_good_svc=kg, diagnostics_svc=diag)
        result = svc.assess()  # must not raise
        assert result.state is not None

    def test_assess_never_raises_on_total_failure(self):
        svc = WarrantyStateService()  # real services — may fail in test env
        result = svc.assess()  # must not raise
        assert result.state is not None

    def test_customer_message_is_set(self):
        from application.diagnostics_service import Status
        svc = _make_svc(
            diff=_make_diff(has_known_good=True, changes=[]),
            report=_make_report([("version", Status.OK, False)]),
        )
        result = svc.assess()
        assert isinstance(result.customer_message, str)
        assert len(result.customer_message) > 0


# ── IncidentClassifier ────────────────────────────────────────────────────────

class TestIncidentClassifier:

    def setup_method(self):
        self.clf = IncidentClassifier()

    def test_empty_check_list_returns_empty(self):
        assert self.clf.classify_from_doctor([]) == []

    def test_unknown_check_name_returns_empty(self):
        assert self.clf.classify_from_doctor(["nonexistent_check"]) == []

    def test_ip_config_maps_to_network_change(self):
        suspicions = self.clf.classify_from_doctor(["ip_config"])
        assert len(suspicions) == 1
        assert suspicions[0].classification.category is IncidentCategory.NETWORK_CHANGE

    def test_config_check_maps_to_configuration_error(self):
        suspicions = self.clf.classify_from_doctor(["config"])
        assert any(s.classification.category is IncidentCategory.CONFIGURATION_ERROR
                   for s in suspicions)

    def test_data_dir_maps_to_installer_error(self):
        suspicions = self.clf.classify_from_doctor(["data_dir"])
        assert any(s.classification.category is IncidentCategory.INSTALLER_ERROR
                   for s in suspicions)

    def test_multiple_checks_produce_multiple_suspicions(self):
        suspicions = self.clf.classify_from_doctor(["ip_config", "config"])
        assert len(suspicions) == 2

    def test_classify_from_diff_empty_returns_empty(self):
        assert self.clf.classify_from_diff([]) == []

    def test_classify_from_diff_unknown_field_returns_empty(self):
        assert self.clf.classify_from_diff(["nonexistent_field"]) == []

    def test_classify_from_diff_config_hash_returns_suspicion(self):
        suspicions = self.clf.classify_from_diff(["config_hash"])
        assert len(suspicions) == 1
        assert suspicions[0].trigger == "config_hash"

    def test_classify_from_diff_cameras_maps_to_network_change(self):
        suspicions = self.clf.classify_from_diff(["cameras"])
        assert any(s.classification.category is IncidentCategory.NETWORK_CHANGE
                   for s in suspicions)

    def test_classify_from_diff_git_commit_maps_to_software_bug(self):
        suspicions = self.clf.classify_from_diff(["git_commit"])
        assert any(s.classification.category is IncidentCategory.SOFTWARE_BUG
                   for s in suspicions)

    def test_suspicion_to_dict_is_json_serializable(self):
        suspicions = self.clf.classify_from_doctor(["ip_config"])
        json.dumps(suspicions[0].to_dict())  # must not raise

    def test_suspicion_advisory_is_non_empty_string(self):
        suspicions = self.clf.classify_from_doctor(["ip_config"])
        assert isinstance(suspicions[0].advisory, str)
        assert len(suspicions[0].advisory) > 0


# ── SupportHintEngine ─────────────────────────────────────────────────────────

class TestSupportHintEngine:

    def setup_method(self):
        self.engine = SupportHintEngine()

    def _warranty(self, state: WarrantyState) -> WarrantyStateResult:
        return WarrantyStateResult(state=state, reason="test")

    def test_no_suspicions_unknown_state_returns_hint(self):
        hints = self.engine.hints_for(self._warranty(WarrantyState.UNKNOWN), [])
        assert len(hints) >= 1

    def test_validated_state_no_suspicions_returns_no_hints(self):
        hints = self.engine.hints_for(self._warranty(WarrantyState.VALIDATED), [])
        assert len(hints) == 0

    def test_changed_since_validation_returns_hint(self):
        hints = self.engine.hints_for(
            self._warranty(WarrantyState.CHANGED_SINCE_VALIDATION), []
        )
        assert any("changed" in h.hint.lower() or "changed" in h.trigger for h in hints)

    def test_revalidation_required_returns_hint(self):
        hints = self.engine.hints_for(
            self._warranty(WarrantyState.REVALIDATION_REQUIRED), []
        )
        assert any("revalidation" in h.hint.lower() or "revalidation" in h.trigger
                   for h in hints)

    def test_hints_sorted_by_priority(self):
        from application.warranty_state_service import IncidentClassifier
        clf = IncidentClassifier()
        suspicions = clf.classify_from_doctor(["ip_config"])
        hints = self.engine.hints_for(
            self._warranty(WarrantyState.REVALIDATION_REQUIRED), suspicions
        )
        priorities = [h.priority for h in hints]
        assert priorities == sorted(priorities)

    def test_suspicion_hints_have_trigger(self):
        from application.warranty_state_service import IncidentClassifier
        clf = IncidentClassifier()
        suspicions = clf.classify_from_doctor(["ip_config"])
        hints = self.engine.hints_for(self._warranty(WarrantyState.VALIDATED), suspicions)
        assert any("ip_config" in h.trigger for h in hints)

    def test_hints_to_dict_is_json_serializable(self):
        from application.warranty_state_service import IncidentClassifier
        clf = IncidentClassifier()
        suspicions = clf.classify_from_doctor(["ip_config"])
        hints = self.engine.hints_for(
            self._warranty(WarrantyState.REVALIDATION_REQUIRED), suspicions
        )
        for h in hints:
            json.dumps(h.to_dict())  # must not raise

