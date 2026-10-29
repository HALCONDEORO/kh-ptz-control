# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from domain.supportability import (
    BillableHint,
    CommandResult,
    CustomerSafeError,
    DoctorCheckResult,
    DoctorSeverity,
    IncidentCategory,
    IncidentClassification,
    IncidentImpact,
    IncidentSeverity,
    InstallabilityProfile,
    MaintenanceResult,
    MaintenanceStatus,
    SupportabilitySummary,
    WarrantyState,
)


def test_command_result_serializes_enums_and_evidence():
    result = CommandResult(
        ok=False,
        command="set_preview",
        target="platform",
        duration_ms=120,
        correlation_id="cmd_123",
        error_code="atem_offline",
        message="ATEM unavailable - camera controls still available",
        evidence={"atem_state": "OFFLINE"},
    )

    assert result.to_dict() == {
        "ok": False,
        "command": "set_preview",
        "target": "platform",
        "duration_ms": 120,
        "correlation_id": "cmd_123",
        "error_code": "atem_offline",
        "message": "ATEM unavailable - camera controls still available",
        "evidence": {"atem_state": "OFFLINE"},
    }


def test_doctor_check_unknown_is_explicit_and_non_blocking():
    result = DoctorCheckResult.unknown(
        key="known_good.state",
        message="No known-good state has been recorded",
    )

    assert result.severity is DoctorSeverity.UNKNOWN
    assert result.blocking is False
    assert result.to_dict()["severity"] == "UNKNOWN"


def test_customer_safe_error_keeps_public_and_support_text_separate():
    error = CustomerSafeError(
        code="config_invalid",
        public_message="Configuration needs support review.",
        technical_message="Missing atem.inputs.cam1.input_id.",
        suggested_action="Run khptz doctor and contact support.",
        support_context={"config_path": "/etc/khptz/config.yaml"},
    )

    payload = error.to_dict()

    assert payload["public_message"] == "Configuration needs support review."
    assert payload["technical_message"] == "Missing atem.inputs.cam1.input_id."
    assert "password" not in payload
    assert "token" not in payload
    assert "secret" not in payload


def test_incident_classification_defaults_to_unknown_billable_hint():
    classification = IncidentClassification()

    assert classification.category is IncidentCategory.UNKNOWN
    assert classification.billable_hint is BillableHint.UNKNOWN
    assert classification.to_dict() == {
        "category": "unknown",
        "severity": "medium",
        "impact": "operator_inconvenience",
        "evidence": [],
        "billable_hint": "unknown",
        "follow_up": None,
    }


def test_incident_classification_can_represent_suspected_network_change():
    classification = IncidentClassification(
        category=IncidentCategory.NETWORK_CHANGE,
        severity=IncidentSeverity.HIGH,
        impact=IncidentImpact.SYSTEM_UNUSABLE,
        evidence=("khptz_doctor", "known_good_diff"),
        billable_hint=BillableHint.UNKNOWN,
        follow_up="revalidation_required",
    )

    payload = classification.to_dict()

    assert payload["category"] == "network_change"
    assert payload["evidence"] == ["khptz_doctor", "known_good_diff"]
    assert payload["billable_hint"] == "unknown"


def test_supportability_summary_uses_safe_unknown_defaults():
    summary = SupportabilitySummary()

    payload = summary.to_dict()

    assert payload["installation_id"] == "unknown"
    assert payload["warranty_state"] == "unknown"
    assert payload["maintenance_status"]["last_result"] == "unknown"
    assert payload["incident_suspicions"] == []
    assert "password" not in payload
    assert "token" not in payload
    assert "secret" not in payload


def test_maintenance_and_installability_models_serialize_plain_values():
    maintenance = MaintenanceStatus(
        support_plan="monthly",
        overdue=True,
        last_result=MaintenanceResult.PASSED_WITH_WARNINGS,
        checks={"backup": "ok", "known_good_state": "changed"},
    )
    profile = InstallabilityProfile(
        wired_network_available=True,
        static_ips_possible=True,
        customer_it_required=False,
        atem_present=True,
        unsupported_hardware=False,
        risk_score=22,
        estimated_install_hours="3-5",
        risk_flags=("shared_office_switch",),
    )

    assert maintenance.to_dict()["last_result"] == "passed_with_warnings"
    assert profile.to_dict()["risk_flags"] == ["shared_office_switch"]
    assert WarrantyState.REVALIDATION_REQUIRED.value == "revalidation_required"

