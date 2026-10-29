#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_supportability_service.py — Tests for SupportabilityService (#568).

Covers:
- SupportabilitySummaryResult: defaults are safe strings, to_dict is JSON-serializable
- human_summary() returns list of strings
- to_dict() has all required keys
- SupportabilityService.generate() returns SupportabilitySummaryResult
- Sub-service failures are tolerated (no exception propagation)
- Fingerprint fields are present when sub-service succeeds
- Doctor fields are present when sub-service succeeds
- Known-good fields are present when sub-service succeeds
- Warranty state is reflected in summary
- Maintenance overdue is reflected in summary
- next_recommended_action is set when hints present
- khptz supportability exits with doctor exit code
- khptz supportability --json produces valid JSON with required keys
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


from application.supportability_service import (
    SupportabilitySummaryResult,
    SupportabilityService,
)


# ── SupportabilitySummaryResult ───────────────────────────────────────────────

class TestSupportabilitySummaryResult:

    def test_defaults_are_safe(self):
        r = SupportabilitySummaryResult()
        assert r.installation_id == "unknown"
        assert r.app_version == "unknown"
        assert r.warranty_state == "unknown"
        assert r.doctor_overall == "unknown"
        assert r.doctor_exit_code == 1
        assert r.errors == []

    def test_to_dict_is_json_serializable(self):
        r = SupportabilitySummaryResult(
            installation_id="khptz-2026-0042",
            app_version="3.18.0",
        )
        json.dumps(r.to_dict())  # must not raise

    def test_to_dict_has_required_top_level_keys(self):
        r = SupportabilitySummaryResult()
        d = r.to_dict()
        for key in (
            "installation_id", "app_version", "git_commit", "profile",
            "fingerprint_hash", "doctor_overall", "doctor_exit_code",
            "known_good", "warranty_state", "maintenance",
            "incident_suspicions", "support_hints", "next_recommended_action",
        ):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_known_good_has_subkeys(self):
        r = SupportabilitySummaryResult()
        d = r.to_dict()
        kg = d["known_good"]
        assert "has_snapshot" in kg
        assert "marked_at" in kg
        assert "state_is_clean" in kg
        assert "changed_fields" in kg

    def test_to_dict_maintenance_has_subkeys(self):
        r = SupportabilitySummaryResult()
        d = r.to_dict()
        m = d["maintenance"]
        assert "overdue" in m
        assert "last_completed_at" in m

    def test_human_summary_returns_list_of_strings(self):
        r = SupportabilitySummaryResult()
        lines = r.human_summary()
        assert isinstance(lines, list)
        assert all(isinstance(l, str) for l in lines)

    def test_human_summary_contains_installation_id(self):
        r = SupportabilitySummaryResult(installation_id="khptz-2026-0042")
        summary = "\n".join(r.human_summary())
        assert "khptz-2026-0042" in summary

    def test_human_summary_shows_changed_when_not_clean(self):
        r = SupportabilitySummaryResult(
            known_good_has_snapshot=True,
            state_is_clean=False,
            state_changed_fields=["config_hash"],
        )
        summary = "\n".join(r.human_summary())
        assert "CHANGED" in summary or "config_hash" in summary

    def test_human_summary_shows_next_action(self):
        r = SupportabilitySummaryResult(
            next_recommended_action="Run khptz doctor",
        )
        summary = "\n".join(r.human_summary())
        assert "khptz doctor" in summary

    def test_human_summary_shows_top_hints(self):
        r = SupportabilitySummaryResult(
            support_hints=[
                {"priority": 1, "hint": "Revalidate the system.", "trigger": "x", "action": "Run doctor."},
            ]
        )
        summary = "\n".join(r.human_summary())
        assert "Revalidate the system." in summary


# ── SupportabilityService ─────────────────────────────────────────────────────

def _fake_fp(installation_id="khptz-test", app_version="3.18.0", git_commit="abc", profile="production"):
    from application.fingerprint_service import InstallationFingerprint
    fp = InstallationFingerprint(
        installation_id=installation_id,
        app_version=app_version,
        git_commit=git_commit,
        profile=profile,
    )
    return fp


def _fake_report(overall="OK", exit_code=0):
    from application.diagnostics_service import CheckResult, DiagnosticsReport, Status
    report = DiagnosticsReport()
    if overall != "OK":
        report.add(CheckResult("test_check", Status.FAIL, "Failed"))
    else:
        report.add(CheckResult("test_check", Status.OK, "OK"))
    return report


def _fake_snap(marked_at="2026-05-01T10:00:00+00:00"):
    from application.known_good_state_service import KnownGoodSnapshot
    return KnownGoodSnapshot(marked_at=marked_at, installation_id="khptz-test")


def _fake_diff(has_known_good=True, is_clean=True, changes=None):
    from application.known_good_state_service import StateDiff
    return StateDiff(
        has_known_good=has_known_good,
        changes=changes or [],
        unchanged_fields=["config_hash"] if is_clean else [],
    )


def _fake_warranty(state_value="validated"):
    from application.warranty_state_service import WarrantyStateResult
    from domain.supportability import WarrantyState
    return WarrantyStateResult(
        state=WarrantyState(state_value),
        reason="test reason",
        customer_message="All good.",
    )


def _fake_maintenance(overdue=False, last_at="2026-05-01T10:00:00+00:00"):
    from application.maintenance_service import MaintenanceStatusResult
    return MaintenanceStatusResult(overdue=overdue, last_completed_at=last_at)


def _make_svc(**kwargs):
    """Build a SupportabilityService with all sub-services mocked."""
    fp_svc = MagicMock()
    fp_svc.generate.return_value = kwargs.get("fp", _fake_fp())

    diag_svc = MagicMock()
    diag_svc.run.return_value = kwargs.get("report", _fake_report())

    kg_svc = MagicMock()
    kg_svc.load.return_value = kwargs.get("snap", _fake_snap())
    kg_svc.diff.return_value = kwargs.get("diff", _fake_diff())

    warranty_svc = MagicMock()
    warranty_svc.assess.return_value = kwargs.get("warranty", _fake_warranty())

    maint_svc = MagicMock()
    maint_svc.status.return_value = kwargs.get("maintenance", _fake_maintenance())

    return SupportabilityService(
        fingerprint_svc=fp_svc,
        diagnostics_svc=diag_svc,
        known_good_svc=kg_svc,
        warranty_svc=warranty_svc,
        maintenance_svc=maint_svc,
    )


class TestSupportabilityServiceGenerate:

    def test_generate_returns_summary_result(self):
        svc = _make_svc()
        result = svc.generate()
        assert isinstance(result, SupportabilitySummaryResult)

    def test_fingerprint_fields_populated(self):
        svc = _make_svc(fp=_fake_fp(installation_id="khptz-2026-0042"))
        result = svc.generate()
        assert result.installation_id == "khptz-2026-0042"
        assert result.app_version == "3.18.0"

    def test_doctor_fields_populated(self):
        svc = _make_svc(report=_fake_report(overall="OK"))
        result = svc.generate()
        assert result.doctor_overall == "OK"
        assert result.doctor_exit_code == 0

    def test_doctor_fail_reflected_in_exit_code(self):
        """A FAIL check yields the FAIL exit code (30) since #887."""
        svc = _make_svc(report=_fake_report(overall="FAIL", exit_code=1))
        result = svc.generate()
        assert result.doctor_exit_code == 30
        assert result.doctor_exit_code != 0

    def test_known_good_snapshot_reflected(self):
        svc = _make_svc(
            snap=_fake_snap("2026-05-01T10:00:00+00:00"),
            diff=_fake_diff(has_known_good=True, is_clean=True),
        )
        result = svc.generate()
        assert result.known_good_has_snapshot is True
        assert result.known_good_marked_at == "2026-05-01T10:00:00+00:00"

    def test_no_known_good_snapshot_reflected(self):
        kg_svc = MagicMock()
        kg_svc.load.return_value = None
        kg_svc.diff.return_value = _fake_diff(has_known_good=False)
        svc = SupportabilityService(
            fingerprint_svc=MagicMock(generate=MagicMock(return_value=_fake_fp())),
            diagnostics_svc=MagicMock(run=MagicMock(return_value=_fake_report())),
            known_good_svc=kg_svc,
            warranty_svc=MagicMock(assess=MagicMock(return_value=_fake_warranty())),
            maintenance_svc=MagicMock(status=MagicMock(return_value=_fake_maintenance())),
        )
        result = svc.generate()
        assert result.known_good_has_snapshot is False

    def test_state_changes_reflected(self):
        from application.known_good_state_service import FieldDiff
        diff = _fake_diff(has_known_good=True, is_clean=False,
                          changes=[FieldDiff("config_hash", "old", "new")])
        svc = _make_svc(diff=diff)
        result = svc.generate()
        assert result.state_is_clean is False
        assert "config_hash" in result.state_changed_fields

    def test_warranty_state_reflected(self):
        svc = _make_svc(warranty=_fake_warranty("changed_since_validation"))
        result = svc.generate()
        assert result.warranty_state == "changed_since_validation"

    def test_maintenance_overdue_reflected(self):
        svc = _make_svc(maintenance=_fake_maintenance(overdue=True))
        result = svc.generate()
        assert result.maintenance_overdue is True

    def test_generate_result_is_json_serializable(self):
        svc = _make_svc()
        result = svc.generate()
        json.dumps(result.to_dict())  # must not raise

    def test_generate_never_raises_on_fingerprint_failure(self):
        fp_svc = MagicMock()
        fp_svc.generate.side_effect = RuntimeError("FP exploded")
        svc = SupportabilityService(fingerprint_svc=fp_svc)
        result = svc.generate()  # must not raise
        assert isinstance(result, SupportabilitySummaryResult)
        assert any("fingerprint" in e for e in result.errors)

    def test_generate_never_raises_on_doctor_failure(self):
        diag_svc = MagicMock()
        diag_svc.run.side_effect = RuntimeError("Doctor exploded")
        svc = SupportabilityService(
            fingerprint_svc=MagicMock(generate=MagicMock(return_value=_fake_fp())),
            diagnostics_svc=diag_svc,
        )
        result = svc.generate()  # must not raise
        assert any("doctor" in e for e in result.errors)

    def test_generate_never_raises_on_known_good_failure(self):
        kg_svc = MagicMock()
        kg_svc.load.side_effect = RuntimeError("KG exploded")
        kg_svc.diff.side_effect = RuntimeError("KG exploded")
        svc = SupportabilityService(known_good_svc=kg_svc)
        result = svc.generate()  # must not raise
        assert any("known_good" in e for e in result.errors)

    def test_generate_never_raises_on_warranty_failure(self):
        warranty_svc = MagicMock()
        warranty_svc.assess.side_effect = RuntimeError("Warranty exploded")
        svc = SupportabilityService(warranty_svc=warranty_svc)
        result = svc.generate()  # must not raise
        assert any("warranty" in e for e in result.errors)

    def test_generate_never_raises_on_maintenance_failure(self):
        maint_svc = MagicMock()
        maint_svc.status.side_effect = RuntimeError("Maint exploded")
        svc = SupportabilityService(maintenance_svc=maint_svc)
        result = svc.generate()  # must not raise
        assert any("maintenance" in e for e in result.errors)

    def test_support_hints_present_when_warranty_unknown(self):
        from application.warranty_state_service import WarrantyStateResult
        from domain.supportability import WarrantyState
        svc = _make_svc(
            warranty=WarrantyStateResult(state=WarrantyState.UNKNOWN, reason="no baseline"),
        )
        result = svc.generate()
        assert len(result.support_hints) >= 1

    def test_next_recommended_action_set_when_hints_present(self):
        from application.warranty_state_service import WarrantyStateResult
        from domain.supportability import WarrantyState
        svc = _make_svc(
            warranty=WarrantyStateResult(state=WarrantyState.UNKNOWN, reason="no baseline"),
        )
        result = svc.generate()
        assert result.next_recommended_action != ""


# ── CLI integration ───────────────────────────────────────────────────────────

class TestSupportabilityCLI:

    def test_supportability_exits_with_doctor_exit_code(self, capsys):
        from runtime.cli import main
        with patch("application.supportability_service.SupportabilityService.generate") as mock_gen:
            mock_gen.return_value = SupportabilitySummaryResult(doctor_exit_code=0)
            rc = main(["supportability"])
        assert rc == 0

    def test_supportability_exits_one_when_doctor_fails(self, capsys):
        from runtime.cli import main
        with patch("application.supportability_service.SupportabilityService.generate") as mock_gen:
            mock_gen.return_value = SupportabilitySummaryResult(
                doctor_overall="FAIL",
                doctor_exit_code=1,
            )
            rc = main(["supportability"])
        assert rc == 1

    def test_supportability_json_produces_valid_json(self, capsys):
        from runtime.cli import main
        with patch("application.supportability_service.SupportabilityService.generate") as mock_gen:
            mock_gen.return_value = SupportabilitySummaryResult(
                installation_id="khptz-2026-0042",
                doctor_exit_code=0,
            )
            rc = main(["supportability", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["installation_id"] == "khptz-2026-0042"
        assert "doctor_overall" in data
        assert "known_good" in data
        assert "warranty_state" in data

