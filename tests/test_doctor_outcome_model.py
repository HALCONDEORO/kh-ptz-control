#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_doctor_outcome_model.py — Regression tests for #887
#
# The scenarios below are the exact result combinations captured during the
# first physical Raspberry Pi installation on 2026-07-22, where every one of
# them collapsed into an undifferentiated "Overall: WARN" or a false
# "Overall: FAIL".

from __future__ import annotations

from pathlib import Path

from application.diagnostics_service import CheckResult, DiagnosticsReport, Status
from domain.doctor_outcome import (
    CheckCategory,
    DoctorOutcome,
    derive_outcome,
    describe,
    exit_code_for,
    is_operational,
)


def _report(*checks: CheckResult) -> DiagnosticsReport:
    report = DiagnosticsReport()
    for check in checks:
        report.add(check)
    return report


def _ok(name: str) -> CheckResult:
    return CheckResult(name, Status.OK, "fine")


def _advisory(name: str, action: str = "harden it") -> CheckResult:
    return CheckResult(name, Status.WARNING, "recommendation",
                       suggested_action=action, category=CheckCategory.ADVISORY)


def _config(name: str, action: str = "configure it") -> CheckResult:
    return CheckResult(name, Status.WARNING, "incomplete configuration",
                       suggested_action=action, category=CheckCategory.CONFIGURATION)


def _operational(name: str) -> CheckResult:
    return CheckResult(name, Status.WARNING, "degraded",
                       category=CheckCategory.OPERATIONAL)


def _fatal(name: str) -> CheckResult:
    return CheckResult(name, Status.FAIL, "broken",
                       category=CheckCategory.OPERATIONAL)


# ═══════════════════════════════════════════════════════════════════════════════
# The pure severity model
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeriveOutcome:
    def test_all_clear_is_pass(self):
        assert derive_outcome(has_blocking_failure=False, has_actionable_issue=False,
                              has_advisory=False) is DoctorOutcome.PASS

    def test_advisory_only_is_ready_with_advisories(self):
        assert derive_outcome(has_blocking_failure=False, has_actionable_issue=False,
                              has_advisory=True) is DoctorOutcome.READY_WITH_ADVISORIES

    def test_actionable_issue_is_config_required(self):
        assert derive_outcome(has_blocking_failure=False, has_actionable_issue=True,
                              has_advisory=True) is DoctorOutcome.CONFIG_REQUIRED

    def test_blocking_failure_outranks_everything(self):
        assert derive_outcome(has_blocking_failure=True, has_actionable_issue=True,
                              has_advisory=True) is DoctorOutcome.FAIL


class TestExitCodes:
    def test_each_outcome_has_a_distinct_exit_code(self):
        codes = {exit_code_for(o) for o in DoctorOutcome}
        assert len(codes) == len(list(DoctorOutcome))

    def test_only_pass_is_zero(self):
        assert exit_code_for(DoctorOutcome.PASS) == 0
        for outcome in DoctorOutcome:
            if outcome is not DoctorOutcome.PASS:
                assert exit_code_for(outcome) != 0

    def test_codes_increase_with_severity(self):
        ordered = [
            DoctorOutcome.PASS,
            DoctorOutcome.READY_WITH_ADVISORIES,
            DoctorOutcome.CONFIG_REQUIRED,
            DoctorOutcome.FAIL,
        ]
        codes = [exit_code_for(o) for o in ordered]
        assert codes == sorted(codes)

    def test_every_outcome_has_a_description(self):
        for outcome in DoctorOutcome:
            assert describe(outcome).strip()

    def test_operational_outcomes_are_pass_and_advisories(self):
        assert is_operational(DoctorOutcome.PASS)
        assert is_operational(DoctorOutcome.READY_WITH_ADVISORIES)
        assert not is_operational(DoctorOutcome.CONFIG_REQUIRED)
        assert not is_operational(DoctorOutcome.FAIL)


# ═══════════════════════════════════════════════════════════════════════════════
# Real-device result combinations from the 2026-07-22 session
# ═══════════════════════════════════════════════════════════════════════════════

class TestRealDeviceScenarios:
    def test_healthy_appliance_on_flat_lan_is_ready_not_warn(self):
        """image-1784736290603: service and cameras healthy, only flat_lan left.

        This previously read "Overall: WARN", indistinguishable from a broken
        install.
        """
        report = _report(
            _ok("service_state"), _ok("cameras"), _ok("display"),
            _advisory("network_profile"),
        )
        assert report.outcome is DoctorOutcome.READY_WITH_ADVISORIES
        assert report.exit_code == 10
        assert is_operational(report.outcome)

    def test_atem_enabled_without_ip_is_config_required(self):
        """image-1784735737244: healthy runtime, ATEM enabled with no address."""
        report = _report(
            _ok("service_state"), _ok("cameras"),
            _config("atem_reachable", "Set the ATEM IP with `hallptz setup --force`"),
            _advisory("network_profile"),
        )
        assert report.outcome is DoctorOutcome.CONFIG_REQUIRED
        assert report.exit_code == 20
        assert not is_operational(report.outcome)

    def test_profile_mismatch_is_config_required_not_advisory(self):
        """image-1784733005323: two cameras saved against starter_1_camera."""
        report = _report(_ok("cameras"), _config("installation_profile"))
        assert report.outcome is DoctorOutcome.CONFIG_REQUIRED

    def test_fully_configured_appliance_passes(self):
        """The target state after the wizard fixes of #886."""
        report = _report(
            _ok("service_state"), _ok("cameras"), _ok("atem_reachable"),
            _ok("installation_profile"), _ok("network_profile"),
        )
        assert report.outcome is DoctorOutcome.PASS
        assert report.exit_code == 0

    def test_runtime_failure_is_fail(self):
        report = _report(_ok("cameras"), _fatal("data_dir"))
        assert report.outcome is DoctorOutcome.FAIL
        assert report.exit_code == 30

    def test_optional_gpio_absence_does_not_make_the_appliance_fail(self):
        """Optional-component state is reported independently (#882/#887)."""
        report = _report(_ok("service_state"), _advisory("gpio_monitor"))
        assert is_operational(report.outcome)

    def test_degraded_hardware_is_actionable_not_merely_advisory(self):
        """An unreachable ATEM must not be filed away as a recommendation."""
        report = _report(_ok("service_state"), _operational("atem_reachable"))
        assert report.outcome is DoctorOutcome.CONFIG_REQUIRED

    def test_advisory_never_masks_a_configuration_issue(self):
        report = _report(_advisory("network_profile"), _config("atem_reachable"))
        assert report.outcome is DoctorOutcome.CONFIG_REQUIRED

    def test_configuration_issue_never_masks_a_failure(self):
        report = _report(_config("atem_reachable"), _fatal("service_state"))
        assert report.outcome is DoctorOutcome.FAIL


# ═══════════════════════════════════════════════════════════════════════════════
# Diagnostics must not report service-owned paths as the caller's failure
# ═══════════════════════════════════════════════════════════════════════════════

class TestIdentityAwarePermissions:
    def test_service_owned_data_dir_is_not_a_failure_for_desktop_user(
        self, tmp_path, monkeypatch,
    ):
        """image-1784733389048: running doctor as the desktop user reported
        service-owned paths as FAIL, producing a false "Overall: FAIL"."""
        import application.diagnostics_service as ds

        data_dir = tmp_path / "var-lib-hallptz"
        data_dir.mkdir()

        # The mocked caller uid must differ from the uid that owns tmp_path,
        # otherwise _is_owned_by_other_user() is False and the test only
        # passes on machines where the developer's real uid is not 1000
        # (CI runners use 1001; a uid-1000 workstation made this fail).
        import os
        monkeypatch.setattr(ds, "_current_uid", lambda: os.getuid() + 1)
        monkeypatch.setattr(ds, "_owner_label", lambda p: "hallptz")
        monkeypatch.setattr(ds, "_current_user_label", lambda: "hallptz")
        monkeypatch.setattr(ds.os, "access", lambda p, mode: False)

        svc = ds.DiagnosticsService.__new__(ds.DiagnosticsService)
        svc._data_dir = data_dir
        result = svc._check_data_dir()

        assert result.status is Status.OK
        assert "service-owned" in result.message

    def test_root_unable_to_write_is_still_a_real_failure(self, tmp_path, monkeypatch):
        import application.diagnostics_service as ds

        data_dir = tmp_path / "var-lib-hallptz"
        data_dir.mkdir()

        monkeypatch.setattr(ds, "_current_uid", lambda: 0)  # root
        monkeypatch.setattr(ds.os, "access", lambda p, mode: False)

        svc = ds.DiagnosticsService.__new__(ds.DiagnosticsService)
        svc._data_dir = data_dir
        result = svc._check_data_dir()

        assert result.status is Status.FAIL

    def test_is_owned_by_other_user_is_false_without_posix_ownership(self, tmp_path,
                                                                    monkeypatch):
        import application.diagnostics_service as ds

        monkeypatch.setattr(ds, "_current_uid", lambda: None)  # Windows
        assert ds._is_owned_by_other_user(tmp_path) is False

    def test_owner_label_never_raises_on_missing_path(self):
        import application.diagnostics_service as ds

        assert ds._owner_label(Path("/definitely/not/here")) == "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# Action list and machine-readable output
# ═══════════════════════════════════════════════════════════════════════════════

class TestActionList:
    def test_empty_when_everything_passes(self):
        assert _report(_ok("a"), _ok("b")).action_list() == []

    def test_lists_remediation_for_each_issue(self):
        report = _report(_config("atem_reachable", "Set the ATEM IP"))
        assert report.action_list() == ["atem_reachable: Set the ATEM IP"]

    def test_most_severe_action_comes_first(self):
        report = _report(
            _advisory("network_profile", "use a VLAN"),
            _config("atem_reachable", "set the IP"),
            _fatal("service_state"),
        )
        actions = report.action_list()
        assert actions[0].startswith("service_state")
        assert actions[-1].startswith("network_profile")

    def test_falls_back_to_the_message_when_no_action_given(self):
        report = _report(CheckResult("x", Status.WARNING, "something is off"))
        assert report.action_list() == ["x: something is off"]


class TestJsonOutputSharesTheSeverityModel:
    def test_json_includes_outcome_and_actions(self):
        report = _report(_ok("service_state"), _advisory("network_profile"))
        data = report.to_json_dict()
        assert data["outcome"] == "READY_WITH_ADVISORIES"
        assert data["exit_code"] == 10
        assert data["outcome_description"]
        assert data["actions"]

    def test_json_exit_code_matches_the_property(self):
        report = _report(_config("atem_reachable"))
        assert report.to_json_dict()["exit_code"] == report.exit_code

    def test_each_check_carries_its_category(self):
        report = _report(_advisory("network_profile"), _config("atem_reachable"))
        categories = {c["key"]: c["category"] for c in report.to_json_dict()["checks"]}
        assert categories["network_profile"] == "advisory"
        assert categories["atem_reachable"] == "configuration"

    def test_json_and_human_output_agree_on_outcome(self):
        report = _report(_config("atem_reachable"))
        assert report.to_json_dict()["outcome"] == report.outcome.value

