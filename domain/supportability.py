#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/supportability.py - Contratos puros para soporte, diagnostico y evidencia.

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


class DoctorSeverity(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    ERROR = "ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class IncidentCategory(str, Enum):
    SOFTWARE_BUG = "software_bug"
    HARDWARE_FAILURE = "hardware_failure"
    NETWORK_CHANGE = "network_change"
    CUSTOMER_CHANGE = "customer_change"
    INSTALLER_ERROR = "installer_error"
    CONFIGURATION_ERROR = "configuration_error"
    UNSUPPORTED_HARDWARE = "unsupported_hardware"
    TRAINING_ISSUE = "training_issue"
    DOCUMENTATION_GAP = "documentation_gap"
    LICENCE_OR_SUPPORT_ISSUE = "licence_or_support_issue"
    THIRD_PARTY_AV_CHANGE = "third_party_av_change"
    UNKNOWN = "unknown"


class IncidentSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentImpact(str, Enum):
    COSMETIC = "cosmetic"
    OPERATOR_INCONVENIENCE = "operator_inconvenience"
    REDUCED_FUNCTIONALITY = "reduced_functionality"
    LIVE_EVENT_RISK = "live_event_risk"
    SYSTEM_UNUSABLE = "system_unusable"
    CUSTOMER_READY_BLOCKED = "customer_ready_blocked"


class BillableHint(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class WarrantyState(str, Enum):
    VALIDATED = "validated"
    VALIDATED_WITH_WARNINGS = "validated_with_warnings"
    CHANGED_SINCE_VALIDATION = "changed_since_validation"
    CUSTOM_UNVALIDATED = "custom_unvalidated"
    SUPPORT_LIMITED = "support_limited"
    REVALIDATION_REQUIRED = "revalidation_required"
    UNKNOWN = "unknown"


class MaintenanceResult(str, Enum):
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    FAILED = "failed"
    UNKNOWN = "unknown"


def _enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    return value


def _to_plain_dict(data: Mapping[str, Any]) -> dict[str, Any]:
    plain: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, Enum):
            plain[key] = value.value
        elif isinstance(value, Mapping):
            plain[key] = _to_plain_dict(value)
        elif isinstance(value, (list, tuple)):
            plain[key] = [_enum_value(item) for item in value]
        else:
            plain[key] = value
    return plain


class _SerializableDC:
    """Mixin: serialise a frozen dataclass to a plain, enum-free dict."""

    def to_dict(self) -> dict[str, Any]:
        return _to_plain_dict(asdict(self))


@dataclass(frozen=True)
class CustomerSafeError(_SerializableDC):
    code: str
    public_message: str
    technical_message: str
    suggested_action: str | None = None
    support_context: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandResult(_SerializableDC):
    ok: bool
    command: str
    target: str | None
    duration_ms: int | None
    correlation_id: str
    error_code: str | None
    message: str
    evidence: Mapping[str, str] | None = None


@dataclass(frozen=True)
class DoctorCheckResult(_SerializableDC):
    key: str
    severity: DoctorSeverity
    message: str
    evidence: Mapping[str, str] = field(default_factory=dict)
    suggested_action: str | None = None
    blocking: bool = False

    @classmethod
    def unknown(cls, key: str, message: str) -> "DoctorCheckResult":
        return cls(key=key, severity=DoctorSeverity.UNKNOWN, message=message)


@dataclass(frozen=True)
class IncidentClassification(_SerializableDC):
    category: IncidentCategory = IncidentCategory.UNKNOWN
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    impact: IncidentImpact = IncidentImpact.OPERATOR_INCONVENIENCE
    evidence: tuple[str, ...] = ()
    billable_hint: BillableHint = BillableHint.UNKNOWN
    follow_up: str | None = None


@dataclass(frozen=True)
class MaintenanceStatus(_SerializableDC):
    support_plan: str = "unknown"
    last_maintenance_at: str | None = None
    next_maintenance_due: str | None = None
    overdue: bool = False
    last_result: MaintenanceResult = MaintenanceResult.UNKNOWN
    checks: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class InstallabilityProfile(_SerializableDC):
    wired_network_available: bool | None = None
    static_ips_possible: bool | None = None
    customer_it_required: bool = False
    atem_present: bool = False
    unsupported_hardware: bool = False
    risk_score: int = 0
    estimated_install_hours: str = "unknown"
    risk_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupportabilitySummary(_SerializableDC):
    installation_id: str = "unknown"
    version: str = "unknown"
    profile: str = "unknown"
    known_good_status: str = "unknown"
    warranty_state: WarrantyState = WarrantyState.UNKNOWN
    doctor_summary: str = "unknown"
    maintenance_status: MaintenanceStatus = field(default_factory=MaintenanceStatus)
    incident_suspicions: tuple[IncidentClassification, ...] = ()
    support_bundle_ready: bool = False
    next_recommended_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["incident_suspicions"] = [
            incident.to_dict() for incident in self.incident_suspicions
        ]
        return _to_plain_dict(data)


class OperationCode(str, Enum):
    """Stable result/error codes for runtime commands, hardware and recovery.

    Codes are stable identifiers — they appear in support bundles, UI messages
    and test assertions. Do not remove or rename existing codes; add new ones
    at the end of each group. See _RESULT_CATALOG for severity and retryability
    guidance for each code.
    """

    # ── Success ───────────────────────────────────────────────────────────────
    OK = "OK"
    PARTIAL_OK = "PARTIAL_OK"          # completed with non-fatal subsystem errors

    # ── Input / config ────────────────────────────────────────────────────────
    INVALID_INPUT = "INVALID_INPUT"
    CONFIG_INVALID = "CONFIG_INVALID"
    CONFIG_MISSING = "CONFIG_MISSING"
    LAYOUT_INVALID = "LAYOUT_INVALID"

    # ── Session ───────────────────────────────────────────────────────────────
    SESSION_INACTIVE = "SESSION_INACTIVE"

    # ── General command ───────────────────────────────────────────────────────
    COMMAND_REJECTED = "COMMAND_REJECTED"   # guard blocked the command
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"

    # ── Camera / PTZ ─────────────────────────────────────────────────────────
    CAMERA_UNAVAILABLE = "CAMERA_UNAVAILABLE"      # kept for backward compat
    CAMERA_DISCONNECTED = "CAMERA_DISCONNECTED"    # TCP/network unreachable
    CAMERA_TIMEOUT = "CAMERA_TIMEOUT"              # no response within deadline
    CAMERA_COMMAND_FAILED = "CAMERA_COMMAND_FAILED"
    CAMERA_QUEUE_DRAINED = "CAMERA_QUEUE_DRAINED"  # queue emptied by Safety Reset
    CAMERA_QUEUE_TIMEOUT = "CAMERA_QUEUE_TIMEOUT"  # command expired in queue

    # ── ATEM ──────────────────────────────────────────────────────────────────
    ATEM_UNAVAILABLE = "ATEM_UNAVAILABLE"          # kept for backward compat
    ATEM_DISABLED = "ATEM_DISABLED"                # feature not enabled/installed
    ATEM_DISCONNECTED = "ATEM_DISCONNECTED"        # TCP/network unreachable
    ATEM_TIMEOUT = "ATEM_TIMEOUT"                  # no response within deadline
    ATEM_COMMAND_FAILED = "ATEM_COMMAND_FAILED"    # switcher rejected the command

    # ── Safety Reset ─────────────────────────────────────────────────────────
    SAFETY_RESET_STARTED = "SAFETY_RESET_STARTED"
    SAFETY_RESET_COMPLETED = "SAFETY_RESET_COMPLETED"
    SAFETY_RESET_PARTIAL_FAILURE = "SAFETY_RESET_PARTIAL_FAILURE"
    SAFETY_RESET_FAILED = "SAFETY_RESET_FAILED"

    # ── Runtime / persistence ─────────────────────────────────────────────────
    RUNTIME_STATE_INVARIANT_FAILED = "RUNTIME_STATE_INVARIANT_FAILED"
    PERSISTENCE_WRITE_FAILED = "PERSISTENCE_WRITE_FAILED"

    # ── General ───────────────────────────────────────────────────────────────
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TIMEOUT = "TIMEOUT"
    UNSUPPORTED_MODE = "UNSUPPORTED_MODE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class OperationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ── Result catalog ────────────────────────────────────────────────────────────
# Maps each OperationCode to (default_severity, retryable, safe_to_continue).
# UI, support diagnostics and recovery logic should consult this table rather
# than hard-coding per-code decisions. Tests may assert against it.

_ResultMeta = tuple[OperationSeverity, bool, bool]   # severity, retryable, safe

_RESULT_CATALOG: dict[OperationCode, _ResultMeta] = {
    # code                              severity                 retry  safe
    OperationCode.OK:                  (OperationSeverity.INFO,     True,  True),
    OperationCode.PARTIAL_OK:          (OperationSeverity.WARNING,  False, True),
    OperationCode.INVALID_INPUT:       (OperationSeverity.WARNING,  False, True),
    OperationCode.CONFIG_INVALID:      (OperationSeverity.ERROR,    False, False),
    OperationCode.CONFIG_MISSING:      (OperationSeverity.ERROR,    False, False),
    OperationCode.LAYOUT_INVALID:      (OperationSeverity.ERROR,    False, True),
    OperationCode.SESSION_INACTIVE:    (OperationSeverity.WARNING,  False, True),
    OperationCode.COMMAND_REJECTED:    (OperationSeverity.WARNING,  False, True),
    OperationCode.TARGET_NOT_FOUND:    (OperationSeverity.WARNING,  False, True),
    OperationCode.CAMERA_UNAVAILABLE:  (OperationSeverity.ERROR,    True,  True),
    OperationCode.CAMERA_DISCONNECTED: (OperationSeverity.ERROR,    True,  True),
    OperationCode.CAMERA_TIMEOUT:      (OperationSeverity.ERROR,    True,  True),
    OperationCode.CAMERA_COMMAND_FAILED: (OperationSeverity.ERROR,  True,  True),
    OperationCode.CAMERA_QUEUE_DRAINED:  (OperationSeverity.WARNING, False, True),
    OperationCode.CAMERA_QUEUE_TIMEOUT:  (OperationSeverity.WARNING, False, True),
    OperationCode.ATEM_UNAVAILABLE:    (OperationSeverity.ERROR,    True,  True),
    OperationCode.ATEM_DISABLED:       (OperationSeverity.INFO,     False, True),
    OperationCode.ATEM_DISCONNECTED:   (OperationSeverity.ERROR,    True,  True),
    OperationCode.ATEM_TIMEOUT:        (OperationSeverity.ERROR,    True,  True),
    OperationCode.ATEM_COMMAND_FAILED: (OperationSeverity.ERROR,    False, True),
    OperationCode.SAFETY_RESET_STARTED:          (OperationSeverity.WARNING,  False, True),
    OperationCode.SAFETY_RESET_COMPLETED:        (OperationSeverity.WARNING,  False, True),
    OperationCode.SAFETY_RESET_PARTIAL_FAILURE:  (OperationSeverity.WARNING,  False, True),
    OperationCode.SAFETY_RESET_FAILED:           (OperationSeverity.CRITICAL, False, False),
    OperationCode.RUNTIME_STATE_INVARIANT_FAILED: (OperationSeverity.CRITICAL, False, False),
    OperationCode.PERSISTENCE_WRITE_FAILED:       (OperationSeverity.ERROR,   True,  True),
    OperationCode.DEPENDENCY_MISSING:  (OperationSeverity.ERROR,    False, False),
    OperationCode.PERMISSION_DENIED:   (OperationSeverity.WARNING,  False, True),
    OperationCode.TIMEOUT:             (OperationSeverity.ERROR,    True,  True),
    OperationCode.UNSUPPORTED_MODE:    (OperationSeverity.WARNING,  False, True),
    OperationCode.INTERNAL_ERROR:      (OperationSeverity.CRITICAL, False, False),
    OperationCode.UNKNOWN_ERROR:       (OperationSeverity.ERROR,    False, False),
}


@dataclass(frozen=True)
class OperationResult(_SerializableDC):
    """Application-level result for service and controller actions.

    CommandResult (hardware commands) is compatible with this contract:
    use OperationResult.from_command_result() to convert.

    New fields retryable, safe_to_continue and subsystem carry semantic meaning
    from _RESULT_CATALOG and can be overridden per-call when the context demands
    a different policy than the catalog default.
    """

    ok: bool
    code: OperationCode
    message: str
    severity: OperationSeverity = OperationSeverity.INFO
    operation: str | None = None
    target: str | None = None
    correlation_id: str | None = None
    duration_ms: int | None = None
    details: dict[str, str] | None = None
    data: dict | None = None
    # Semantic fields — populated from _RESULT_CATALOG when using factory methods,
    # and may be overridden by callers that need non-default behaviour.
    retryable: bool = True
    safe_to_continue: bool = True
    subsystem: str | None = None   # "camera", "atem", "safety_reset", etc.

    # ── Factories ─────────────────────────────────────────────────────────────

    @classmethod
    def success(
        cls,
        operation: str | None = None,
        target: str | None = None,
        message: str = "OK",
        **kwargs,
    ) -> "OperationResult":
        return cls(
            ok=True,
            code=OperationCode.OK,
            message=message,
            severity=OperationSeverity.INFO,
            operation=operation,
            target=target,
            retryable=True,
            safe_to_continue=True,
            **kwargs,
        )

    @classmethod
    def partial(
        cls,
        message: str,
        operation: str | None = None,
        target: str | None = None,
        **kwargs,
    ) -> "OperationResult":
        """Partial success — completed with non-fatal subsystem errors."""
        meta = _RESULT_CATALOG[OperationCode.PARTIAL_OK]
        return cls(
            ok=True,
            code=OperationCode.PARTIAL_OK,
            message=message,
            severity=meta[0],
            operation=operation,
            target=target,
            retryable=meta[1],
            safe_to_continue=meta[2],
            **kwargs,
        )

    @classmethod
    def failure(
        cls,
        code: OperationCode,
        message: str,
        severity: OperationSeverity | None = None,
        operation: str | None = None,
        target: str | None = None,
        **kwargs,
    ) -> "OperationResult":
        meta = _RESULT_CATALOG.get(code)
        resolved_severity = severity if severity is not None else (meta[0] if meta else OperationSeverity.ERROR)
        retryable = kwargs.pop("retryable", meta[1] if meta else False)
        safe_to_continue = kwargs.pop("safe_to_continue", meta[2] if meta else False)
        return cls(
            ok=False,
            code=code,
            message=message,
            severity=resolved_severity,
            operation=operation,
            target=target,
            retryable=retryable,
            safe_to_continue=safe_to_continue,
            **kwargs,
        )

    @classmethod
    def from_command_result(
        cls, result: "CommandResult", operation: str | None = None
    ) -> "OperationResult":
        """Convert a CommandResult to OperationResult.

        Maps CommandResult.error_code to a specific OperationCode where possible
        so callers get structured codes instead of the generic CAMERA_COMMAND_FAILED.
        """
        if result.ok:
            return cls.success(
                operation=operation or result.command,
                target=result.target,
                correlation_id=result.correlation_id,
                duration_ms=result.duration_ms,
            )
        # Map known camera error codes to specific OperationCode values.
        error_code_map: dict[str, OperationCode] = {
            "CAMERA_TIMEOUT":      OperationCode.CAMERA_TIMEOUT,
            "CAMERA_DISCONNECTED": OperationCode.CAMERA_DISCONNECTED,
            "CAMERA_ERROR":        OperationCode.CAMERA_COMMAND_FAILED,
        }
        op_code = error_code_map.get(
            result.error_code or "", OperationCode.CAMERA_COMMAND_FAILED
        )
        return cls.failure(
            code=op_code,
            message=result.message,
            operation=operation or result.command,
            target=result.target,
            correlation_id=result.correlation_id,
            duration_ms=result.duration_ms,
            subsystem="camera",
        )

    # ── Catalog helpers ───────────────────────────────────────────────────────

    @classmethod
    def catalog_meta(cls, code: OperationCode) -> _ResultMeta:
        """Return the (severity, retryable, safe_to_continue) tuple for *code*."""
        return _RESULT_CATALOG.get(
            code,
            (OperationSeverity.ERROR, False, False),
        )
