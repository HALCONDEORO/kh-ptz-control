#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_doctor_check_result.py — Tests for structured DoctorCheckResult integration (#562).

Covers:
- CheckResult.to_doctor_check(): Status.OK→DoctorSeverity.OK, WARNING, FAIL→ERROR
- CheckResult.to_doctor_check(): evidence, suggested_action, blocking pass through
- DiagnosticsReport.to_doctor_checks(): returns list of DoctorCheckResult
- DiagnosticsReport.to_json_dict(): includes overall, exit_code, checks[]
- JSON output is stable and contains expected fields
- Unknown severity maps to DoctorSeverity.UNKNOWN (edge case)
- Evidence is serialized in to_dict()
- UNKNOWN is allowed when evidence is insufficient
"""
from __future__ import annotations

import json

from application.diagnostics_service import (
    CheckResult,
    DiagnosticsReport,
    Status,
)
from domain.supportability import DoctorCheckResult, DoctorSeverity


class TestCheckResultToDoctorCheck:

    def test_status_ok_maps_to_severity_ok(self):
        cr = CheckResult("version", Status.OK, "All OK")
        dc = cr.to_doctor_check()
        assert dc.severity is DoctorSeverity.OK

    def test_status_warning_maps_to_severity_warning(self):
        cr = CheckResult("config", Status.WARNING, "Config not found")
        dc = cr.to_doctor_check()
        assert dc.severity is DoctorSeverity.WARNING

    def test_status_fail_maps_to_severity_error(self):
        cr = CheckResult("data_dir", Status.FAIL, "Cannot create directory")
        dc = cr.to_doctor_check()
        assert dc.severity is DoctorSeverity.ERROR

    def test_key_matches_name(self):
        cr = CheckResult("installation_id", Status.OK, "ID: hallptz-2026-0042")
        dc = cr.to_doctor_check()
        assert dc.key == "installation_id"

    def test_message_passes_through(self):
        msg = "Camera unreachable at 192.168.30.1"
        cr = CheckResult("camera", Status.FAIL, msg)
        dc = cr.to_doctor_check()
        assert dc.message == msg

    def test_evidence_passes_through(self):
        cr = CheckResult(
            "data_dir",
            Status.FAIL,
            "Not writable",
            evidence={"path": "/var/lib/hallptz", "error": "Permission denied"},
        )
        dc = cr.to_doctor_check()
        assert dc.evidence["path"] == "/var/lib/hallptz"
        assert dc.evidence["error"] == "Permission denied"

    def test_suggested_action_passes_through(self):
        cr = CheckResult(
            "config",
            Status.WARNING,
            "config.yaml not found",
            suggested_action="Copy config/defaults/starter.yaml to get started",
        )
        dc = cr.to_doctor_check()
        assert dc.suggested_action == "Copy config/defaults/starter.yaml to get started"

    def test_blocking_passes_through(self):
        cr = CheckResult("config", Status.FAIL, "Bad config", blocking=True)
        dc = cr.to_doctor_check()
        assert dc.blocking is True

    def test_non_blocking_by_default(self):
        cr = CheckResult("version", Status.OK, "OK")
        dc = cr.to_doctor_check()
        assert dc.blocking is False

    def test_to_doctor_check_returns_doctor_check_result_instance(self):
        cr = CheckResult("version", Status.OK, "OK")
        dc = cr.to_doctor_check()
        assert isinstance(dc, DoctorCheckResult)

    def test_to_dict_is_json_serializable(self):
        cr = CheckResult(
            "camera",
            Status.FAIL,
            "Unreachable",
            evidence={"ip": "192.168.30.1"},
        )
        dc = cr.to_doctor_check()
        d = dc.to_dict()
        # Should not raise
        json.dumps(d)
        assert d["key"] == "camera"
        assert d["severity"] == "ERROR"
        assert d["evidence"]["ip"] == "192.168.30.1"


class TestDiagnosticsReportStructured:

    def _make_report(self) -> DiagnosticsReport:
        report = DiagnosticsReport()
        report.add(CheckResult("version", Status.OK, "v3.18.0"))
        report.add(CheckResult("config", Status.WARNING, "not found"))
        report.add(CheckResult("data_dir", Status.FAIL, "not writable", blocking=True))
        return report

    def test_to_doctor_checks_returns_list_of_doctor_check_result(self):
        report = self._make_report()
        checks = report.to_doctor_checks()
        assert len(checks) == 3
        assert all(isinstance(c, DoctorCheckResult) for c in checks)

    def test_to_doctor_checks_preserves_order(self):
        report = self._make_report()
        checks = report.to_doctor_checks()
        assert checks[0].key == "version"
        assert checks[1].key == "config"
        assert checks[2].key == "data_dir"

    def test_to_json_dict_has_required_keys(self):
        report = self._make_report()
        d = report.to_json_dict()
        assert "overall" in d
        assert "exit_code" in d
        assert "checks" in d

    def test_to_json_dict_overall_is_string(self):
        report = self._make_report()
        d = report.to_json_dict()
        assert isinstance(d["overall"], str)

    def test_to_json_dict_exit_code_is_nonzero_on_failure(self):
        report = self._make_report()
        d = report.to_json_dict()
        assert d["exit_code"] != 0  # has a FAIL check

    def test_to_json_dict_exit_code_zero_on_all_ok(self):
        report = DiagnosticsReport()
        report.add(CheckResult("version", Status.OK, "v3.18.0"))
        d = report.to_json_dict()
        assert d["exit_code"] == 0

    def test_to_json_dict_is_json_serializable(self):
        report = self._make_report()
        d = report.to_json_dict()
        # Should not raise
        json.dumps(d)

    def test_to_json_dict_checks_list_contains_dicts(self):
        report = self._make_report()
        d = report.to_json_dict()
        assert all(isinstance(c, dict) for c in d["checks"])

    def test_unknown_is_supported_via_doctor_check_unknown_factory(self):
        dc = DoctorCheckResult.unknown(
            key="known_good.state",
            message="No known-good state has been recorded",
        )
        assert dc.severity is DoctorSeverity.UNKNOWN
        assert dc.blocking is False
        d = dc.to_dict()
        assert d["severity"] == "UNKNOWN"
        # JSON serializable
        json.dumps(d)

