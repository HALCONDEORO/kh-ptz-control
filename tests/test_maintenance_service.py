#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_maintenance_service.py — Tests for MaintenanceService and InstallabilityService (#566).

Covers:
- MaintenanceRecord: to_dict, from_dict round-trip
- MaintenanceStatusResult: to_dict JSON-serializable, human_summary
- MaintenanceService.status(): overdue when no record, current when recent
- MaintenanceService.mark_complete(): writes file, returns record with timestamp
- Overdue detection: record older than cycle_days → overdue
- InstallabilityResult: to_dict, human_summary, risk_flags
- InstallabilityService.assess(): deterministic score from flags
- No-wired-network increases risk score
- No-static-ips increases risk score
- Unsupported hardware has highest weight
- Unknown flags produce risk_flags entries
- Risk score is additive and deterministic
- CLI: khptz maintenance status / mark-complete
- CLI: khptz installability score --json
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


from application.maintenance_service import (
    InstallabilityService,
    MaintenanceRecord,
    MaintenanceService,
    MaintenanceStatusResult,
    _install_hours,
)
from domain.supportability import MaintenanceResult


# ── MaintenanceRecord ─────────────────────────────────────────────────────────

class TestMaintenanceRecord:

    def test_to_dict_is_json_serializable(self):
        r = MaintenanceRecord(completed_at="2026-05-01T10:00:00+00:00")
        json.dumps(r.to_dict())

    def test_from_dict_roundtrip(self):
        r = MaintenanceRecord(
            completed_at="2026-05-01T10:00:00+00:00",
            completed_by="marco",
            notes="Monthly check",
            result="passed",
        )
        recovered = MaintenanceRecord.from_dict(r.to_dict())
        assert recovered.completed_at == r.completed_at
        assert recovered.completed_by == r.completed_by

    def test_from_dict_missing_keys_use_defaults(self):
        r = MaintenanceRecord.from_dict({})
        assert r.completed_at == "unknown"
        assert r.result == MaintenanceResult.UNKNOWN.value


# ── MaintenanceStatusResult ───────────────────────────────────────────────────

class TestMaintenanceStatusResult:

    def test_to_dict_is_json_serializable(self):
        r = MaintenanceStatusResult(
            last_completed_at="2026-05-01T10:00:00+00:00",
            overdue=False,
        )
        json.dumps(r.to_dict())

    def test_to_dict_last_result_is_string(self):
        r = MaintenanceStatusResult(last_result=MaintenanceResult.PASSED)
        assert r.to_dict()["last_result"] == "passed"

    def test_human_summary_returns_list_of_strings(self):
        r = MaintenanceStatusResult()
        lines = r.human_summary()
        assert isinstance(lines, list)
        assert all(isinstance(l, str) for l in lines)

    def test_human_summary_shows_never_when_no_record(self):
        r = MaintenanceStatusResult(last_completed_at=None)
        summary = "\n".join(r.human_summary())
        assert "never" in summary

    def test_human_summary_shows_overdue(self):
        r = MaintenanceStatusResult(overdue=True, overdue_days=5)
        summary = "\n".join(r.human_summary())
        assert "OVERDUE" in summary
        assert "5" in summary


# ── MaintenanceService ────────────────────────────────────────────────────────

class TestMaintenanceServiceStatus:

    def test_status_overdue_when_no_record(self, tmp_path):
        svc = MaintenanceService(data_dir=tmp_path)
        result = svc.status()
        assert result.overdue is True

    def test_status_current_when_recent_record(self, tmp_path):
        svc = MaintenanceService(data_dir=tmp_path)
        # Write a record from today
        now = datetime.now(timezone.utc)
        record = MaintenanceRecord(completed_at=now.isoformat(timespec="seconds"))
        (tmp_path / "maintenance.json").write_text(
            json.dumps(record.to_dict()), encoding="utf-8"
        )
        result = svc.status(cycle_days=30)
        assert result.overdue is False

    def test_status_overdue_when_old_record(self, tmp_path):
        svc = MaintenanceService(data_dir=tmp_path)
        # Write a record from 60 days ago
        old = datetime.now(timezone.utc) - timedelta(days=60)
        record = MaintenanceRecord(completed_at=old.isoformat(timespec="seconds"))
        (tmp_path / "maintenance.json").write_text(
            json.dumps(record.to_dict()), encoding="utf-8"
        )
        result = svc.status(cycle_days=30)
        assert result.overdue is True
        assert result.overdue_days >= 29

    def test_status_next_due_is_set_when_record_present(self, tmp_path):
        svc = MaintenanceService(data_dir=tmp_path)
        now = datetime.now(timezone.utc)
        record = MaintenanceRecord(completed_at=now.isoformat(timespec="seconds"))
        (tmp_path / "maintenance.json").write_text(
            json.dumps(record.to_dict()), encoding="utf-8"
        )
        result = svc.status(cycle_days=30)
        assert result.next_due is not None

    def test_status_returns_last_result(self, tmp_path):
        svc = MaintenanceService(data_dir=tmp_path)
        now = datetime.now(timezone.utc)
        record = MaintenanceRecord(
            completed_at=now.isoformat(timespec="seconds"),
            result=MaintenanceResult.PASSED.value,
        )
        (tmp_path / "maintenance.json").write_text(
            json.dumps(record.to_dict()), encoding="utf-8"
        )
        result = svc.status()
        assert result.last_result is MaintenanceResult.PASSED


class TestMaintenanceServiceMarkComplete:

    def test_mark_complete_creates_file(self, tmp_path):
        svc = MaintenanceService(data_dir=tmp_path)
        svc.mark_complete()
        assert (tmp_path / "maintenance.json").exists()

    def test_mark_complete_returns_record_with_timestamp(self, tmp_path):
        svc = MaintenanceService(data_dir=tmp_path)
        record = svc.mark_complete()
        assert record.completed_at != "unknown"
        # Should be parseable as ISO datetime
        datetime.fromisoformat(record.completed_at)

    def test_mark_complete_stores_completed_by(self, tmp_path):
        svc = MaintenanceService(data_dir=tmp_path)
        svc.mark_complete(completed_by="marco")
        loaded = json.loads((tmp_path / "maintenance.json").read_text(encoding="utf-8"))
        assert loaded["completed_by"] == "marco"

    def test_mark_complete_stores_notes(self, tmp_path):
        svc = MaintenanceService(data_dir=tmp_path)
        svc.mark_complete(notes="Quarterly review completed")
        loaded = json.loads((tmp_path / "maintenance.json").read_text(encoding="utf-8"))
        assert loaded["notes"] == "Quarterly review completed"

    def test_mark_complete_file_is_valid_json(self, tmp_path):
        svc = MaintenanceService(data_dir=tmp_path)
        svc.mark_complete()
        data = json.loads((tmp_path / "maintenance.json").read_text(encoding="utf-8"))
        assert "completed_at" in data


# ── _install_hours ────────────────────────────────────────────────────────────

class TestInstallHoursBands:

    def test_zero_risk(self):
        assert _install_hours(0) == "unknown"

    def test_low_risk(self):
        assert _install_hours(1) == "1–2 h"

    def test_medium_risk(self):
        assert _install_hours(4) == "3–5 h"

    def test_high_risk(self):
        h = _install_hours(12)
        assert "8" in h


# ── InstallabilityService ─────────────────────────────────────────────────────

class TestInstallabilityService:

    def setup_method(self):
        self.svc = InstallabilityService()

    def test_all_defaults_returns_zero_score(self):
        result = self.svc.assess()
        assert result.risk_score == 0

    def test_no_wired_network_increases_score(self):
        r_no = self.svc.assess(wired_network_available=False)
        r_yes = self.svc.assess(wired_network_available=True)
        assert r_no.risk_score > r_yes.risk_score

    def test_no_static_ips_increases_score(self):
        r_no = self.svc.assess(static_ips_possible=False)
        r_yes = self.svc.assess(static_ips_possible=True)
        assert r_no.risk_score > r_yes.risk_score

    def test_unsupported_hardware_has_highest_single_weight(self):
        r = self.svc.assess(unsupported_hardware=True)
        assert r.risk_score >= 5  # _RISK_WEIGHTS["unsupported_hardware"] == 5

    def test_score_is_additive(self):
        r_none = self.svc.assess()
        r_one = self.svc.assess(atem_present=True)
        r_two = self.svc.assess(atem_present=True, customer_it_required=True)
        assert r_none.risk_score < r_one.risk_score < r_two.risk_score

    def test_score_is_deterministic(self):
        r1 = self.svc.assess(wired_network_available=False, atem_present=True)
        r2 = self.svc.assess(wired_network_available=False, atem_present=True)
        assert r1.risk_score == r2.risk_score

    def test_unknown_network_produces_risk_flag(self):
        result = self.svc.assess(wired_network_available=None)
        flags = "\n".join(result.risk_flags)
        assert "unknown" in flags.lower() or "wired" in flags.lower()

    def test_known_true_network_produces_no_network_flag(self):
        result = self.svc.assess(wired_network_available=True, static_ips_possible=True)
        flags = "\n".join(result.risk_flags).lower()
        assert "wired" not in flags
        assert "static" not in flags

    def test_extra_risk_flags_included(self):
        result = self.svc.assess(extra_risk_flags=["Custom concern"])
        assert "Custom concern" in result.risk_flags

    def test_to_dict_is_json_serializable(self):
        result = self.svc.assess(wired_network_available=False, atem_present=True)
        json.dumps(result.to_dict())

    def test_to_dict_has_required_keys(self):
        result = self.svc.assess()
        d = result.to_dict()
        for key in ("risk_score", "estimated_install_hours", "risk_flags", "atem_present"):
            assert key in d

    def test_human_summary_returns_list_of_strings(self):
        result = self.svc.assess()
        lines = result.human_summary()
        assert isinstance(lines, list)
        assert all(isinstance(l, str) for l in lines)


# ── CLI integration ───────────────────────────────────────────────────────────

class TestMaintenanceCLI:

    def test_maintenance_status_exits_one_when_overdue(self, tmp_path, capsys):
        from unittest.mock import patch
        from runtime.cli import main
        from application.maintenance_service import MaintenanceStatusResult
        result = MaintenanceStatusResult(overdue=True, overdue_days=5)
        with patch("application.maintenance_service.MaintenanceService.status", return_value=result):
            rc = main(["maintenance", "status"])
        assert rc == 1

    def test_maintenance_status_exits_zero_when_current(self, tmp_path, capsys):
        from unittest.mock import patch
        from runtime.cli import main
        from application.maintenance_service import MaintenanceStatusResult
        result = MaintenanceStatusResult(overdue=False)
        with patch("application.maintenance_service.MaintenanceService.status", return_value=result):
            rc = main(["maintenance", "status"])
        assert rc == 0

    def test_maintenance_status_json_is_valid(self, tmp_path, capsys):
        from unittest.mock import patch
        from runtime.cli import main
        from application.maintenance_service import MaintenanceStatusResult
        result = MaintenanceStatusResult(overdue=False, last_completed_at="2026-05-01T10:00:00+00:00")
        with patch("application.maintenance_service.MaintenanceService.status", return_value=result):
            main(["maintenance", "status", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "overdue" in data
        assert "last_completed_at" in data

    def test_maintenance_mark_complete_exits_zero(self, tmp_path):
        from unittest.mock import patch
        from runtime.cli import main
        record = MaintenanceRecord(
            completed_at="2026-05-12T10:00:00+00:00",
            completed_by="marco",
        )
        with patch("application.maintenance_service.MaintenanceService.mark_complete",
                   return_value=record):
            rc = main(["maintenance", "mark-complete", "--by", "marco"])
        assert rc == 0


class TestInstallabilityCLI:

    def test_installability_score_exits_zero(self, capsys):
        from runtime.cli import main
        rc = main(["installability", "score"])
        assert rc == 0

    def test_installability_score_json_is_valid(self, capsys):
        from runtime.cli import main
        rc = main(["installability", "score", "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert "risk_score" in data
        assert "risk_flags" in data

    def test_installability_score_with_flags(self, capsys):
        from runtime.cli import main
        rc = main(["installability", "score",
                   "--wired-network", "no",
                   "--atem",
                   "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["risk_score"] > 0

    def test_installability_status_exits_zero(self, capsys):
        from runtime.cli import main
        rc = main(["installability", "status"])
        assert rc == 0

