#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/blackbox_event.py — Black box event schema for Hall PTZ Control flight recorder (#487)
#
# Pure domain module: no I/O, no config loading, no external dependencies.
# See docs/BLACK_BOX_SCHEMA.md for the full specification and retention policy.

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


# ── Level ─────────────────────────────────────────────────────────────────────

class EventLevel(str, Enum):
    INFO    = "INFO"
    WARNING = "WARNING"
    ERROR   = "ERROR"


# ── Event types ───────────────────────────────────────────────────────────────

class EventType(str, Enum):
    # Application lifecycle
    APP_STARTED              = "AppStarted"
    APP_STOPPED              = "AppStopped"
    APP_CRASH_DETECTED       = "AppCrashDetected"
    VERSION_LOADED           = "VersionLoaded"
    CONFIG_LOADED            = "ConfigLoaded"
    CONFIG_VALIDATION_FAILED = "ConfigValidationFailed"

    # Session
    SESSION_STARTED          = "SessionStarted"
    SESSION_ENDED            = "SessionEnded"

    # Camera commands
    SEAT_PRESET_RECALL_REQUESTED   = "SeatPresetRecallRequested"
    CAMERA_COMMAND_SENT            = "CameraCommandSent"
    CAMERA_COMMAND_SUCCEEDED       = "CameraCommandSucceeded"
    CAMERA_COMMAND_FAILED          = "CameraCommandFailed"
    SPECIAL_PRESET_RECALL_REQUESTED = "SpecialPresetRecallRequested"
    EMERGENCY_STOP_PRESSED         = "EmergencyStopPressed"

    # Support / operations
    DOCTOR_RUN               = "DoctorRun"
    BACKUP_CREATED           = "BackupCreated"
    RESTORE_STARTED          = "RestoreStarted"
    RESTORE_FAILED           = "RestoreFailed"
    SUPPORT_BUNDLE_EXPORTED  = "SupportBundleExported"


# ── Result constants ──────────────────────────────────────────────────────────

class EventResult(str, Enum):
    REQUESTED = "requested"
    SENT      = "sent"
    SUCCEEDED = "succeeded"
    FAILED    = "failed"
    SKIPPED   = "skipped"
    UNKNOWN   = "unknown"


# ── Source constants ──────────────────────────────────────────────────────────

class EventSource(str, Enum):
    OPERATOR_UI = "operator_ui"
    SETUP       = "setup"
    CLI         = "cli"
    ATEM        = "atem"
    SUPPORT     = "support"
    SYSTEM      = "system"


# ── Schema version ────────────────────────────────────────────────────────────

SCHEMA_VERSION = 1


# ── Event dataclass ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BlackBoxEvent:
    """
    A single structured black box event.

    Required fields mirror the schema defined in docs/BLACK_BOX_SCHEMA.md.
    All string values should be stable technical identifiers — no personal names.
    Secrets must never appear in any field; callers are responsible for redaction.
    """

    # ── Required ──────────────────────────────────────────────────────────────
    timestamp: str          # ISO-8601 UTC, e.g. "2026-05-08T15:42:12.231Z"
    level: str              # EventLevel value
    event_type: str         # EventType value
    app_version: str        # e.g. "3.22.0"
    installation_profile: str   # e.g. "starter_1_camera", "demo"
    runtime_mode: str       # "production" | "demo" | "simulation"
    session_id: str         # active session id, or "none"
    correlation_id: str     # command / request trace id
    source: str             # EventSource value
    result: str             # EventResult value

    # ── Optional context ──────────────────────────────────────────────────────
    schema_version: int             = SCHEMA_VERSION
    installation_id: str            = "unknown"
    git_commit: str | None          = None
    message: str                    = ""
    seat_id: str | None             = None
    seat_label: str | None          = None
    camera_role: str | None         = None
    camera_id: str | None           = None
    preset: str | None              = None
    error_code: str | None          = None
    duration_ms: int | None         = None
    extra: dict[str, Any]           = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable plain dict (no Enum instances)."""
        d = asdict(self)
        # schema_version is int — already JSON-safe; enums are str subclasses
        return d


# ── Redacted-field sentinel ───────────────────────────────────────────────────

_SECRET_KEYS = frozenset({
    "password", "token", "secret", "private_key",
    "ssh_key", "license_private_key", "api_key", "credential",
})


def redact_event_dict(data: dict[str, Any]) -> dict[str, Any]:
    """
    Return a copy of *data* with obvious secret fields replaced by '[REDACTED]'.

    Rules:
    - Scalar values whose key is an exact or substring match of a secret keyword
      are replaced with '[REDACTED]'.
    - Nested dicts are always recursed into first; secret-key check applies to
      their leaf values, not to the container key itself.
    - Non-dict, non-string values that match a secret key are also redacted.

    This is a lightweight best-effort guard. Full redaction policy lives in
    domain/redaction.py and application/redaction_service.py.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        key_str = str(key).lower()
        is_secret_key = key in _SECRET_KEYS or any(s in key_str for s in _SECRET_KEYS)
        if isinstance(value, dict):
            # Always recurse into nested dicts regardless of key name
            result[key] = redact_event_dict(value)
        elif is_secret_key:
            result[key] = "[REDACTED]"
        else:
            result[key] = value
    return result
