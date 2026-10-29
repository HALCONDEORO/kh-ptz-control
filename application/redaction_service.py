#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/redaction_service.py — Application-level secret redaction service
#
# Thin application wrapper around domain/redaction.RedactionGuard.
#
# Use this service for:
#   - hallptz doctor output before logging or export
#   - support bundle content before ZIP
#   - black box events and incident snapshots
#   - handover reports and setup completion reports
#   - any log that might include external command/config summaries
#
# This service adds:
#   1. Never-raise wrappers (redaction failures log to errors list, not exceptions)
#   2. Structured output with an applied flag and any warnings
#
# See domain/redaction.py for the underlying RedactionGuard and _SECRET_KEYS.
# See docs/SUPPORT_BUNDLE_CONTRACT.md for the overall redaction policy.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RedactionResult:
    """
    The result of a redaction pass.

    ``value`` is the redacted data (same type as input).
    ``applied`` is True when redaction succeeded with no errors.
    ``warnings`` lists descriptions of any redaction problems.
    """

    value: Any
    applied: bool = True
    warnings: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """Return True when redaction applied without any warnings."""
        return self.applied and not self.warnings


class RedactionService:
    """
    Application-level wrapper for secret redaction.

    All public methods are safe to call without a try/except — they
    never raise.  Errors are captured in RedactionResult.warnings.

    Usage example::

        svc = RedactionService()
        result = svc.redact_dict(doctor_json_dict)
        if not result.is_clean:
            log.warning("Redaction warnings: %s", result.warnings)
        safe_dict = result.value  # guaranteed to be redacted
    """

    def __init__(self) -> None:
        from domain.redaction import RedactionGuard
        self._guard = RedactionGuard()

    # ── Public API (never raise) ──────────────────────────────────────────────

    def redact_dict(self, data: dict) -> RedactionResult:
        """
        Redact sensitive keys from a dict (recursively).

        Delegates to RedactionGuard.redact_mapping(). Never raises — on any
        exception the original data is NOT returned; a safe placeholder is
        used instead (fail-closed).
        """
        try:
            return RedactionResult(value=self._guard.redact_mapping(data))
        except Exception as exc:  # noqa: BLE001
            return RedactionResult(
                value={"<REDACTION_FAILED>": "<REDACTION_FAILED>"},
                applied=False,
                warnings=[f"redact_dict failed: {exc}"],
            )

    def redact_text(self, text: str) -> RedactionResult:
        """
        Redact secret patterns from a free-text string.

        Delegates to RedactionGuard.redact_text(). Never raises — on any
        exception the original text is NOT returned; a safe placeholder is
        used instead (fail-closed).
        """
        try:
            return RedactionResult(value=self._guard.redact_text(text))
        except Exception as exc:  # noqa: BLE001
            return RedactionResult(
                value="<REDACTION_FAILED>",
                applied=False,
                warnings=[f"redact_text failed: {exc}"],
            )

    def is_safe_for_export(self, text: str) -> bool:
        """
        Return True when no obvious secret patterns are found in *text*.

        Never raises — returns False on any error (fail closed).
        """
        try:
            return self._guard.is_safe_for_export(text)
        except Exception:  # noqa: BLE001
            return False  # fail closed

    def scan_for_secrets(self, text: str) -> list[str]:
        """
        Return a list of human-readable descriptions of detected secret material.

        Returns empty list on any error (never raises).
        """
        try:
            return self._guard.scan_for_secrets(text)
        except Exception:  # noqa: BLE001
            return []

    def redact_doctor_report(self, report_dict: dict) -> RedactionResult:
        """
        Redact a `hallptz doctor --json` output dict before export.

        Convenience wrapper: applies dict redaction, then verifies the JSON
        serialized output is free from obvious secrets.
        """
        import json
        result = self.redact_dict(report_dict)
        try:
            serialized = json.dumps(result.value)
            findings = self._guard.scan_for_secrets(serialized)
            if findings:
                result.warnings.extend(
                    [f"Post-redaction secret scan found: {f}" for f in findings]
                )
                result.applied = False
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"Post-redaction scan failed: {exc}")
        return result
