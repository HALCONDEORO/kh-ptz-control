#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/redaction.py — RedactionGuard and SupportBundleManifest.
#
# Pure domain — no I/O, no Qt, no network.
# See docs/SUPPORT_BUNDLE_CONTRACT.md for the full redaction policy.

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping

# ── Secret patterns ───────────────────────────────────────────────────────────

# Keys that must never appear with their raw values in support output.
# Case-insensitive exact or substring match against JSON/YAML key names.
_SECRET_KEYS: frozenset[str] = frozenset({
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "auth",
    "credential",
    "credentials",
    "private_key",
    "privatekey",
    "signing_key",
    "licence_key",
    "license_key",
    "access_key",
    "secret_key",
    "client_secret",
    "bearer",
    "authorization",
    "ssh_key",          # explicit SSH key field names
    "ssh_password",
    "ssh_credential",
})

# Patterns that indicate secret material in free text (case-insensitive).
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    # SSH private key blocks
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
    # Generic bearer / JWT token shapes
    re.compile(r"\bBearer\s+[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_.+/=]*\b"),
    # Base64-encoded blobs that look like encoded keys (64+ chars, no whitespace)
    re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{64,}={0,2}(?![A-Za-z0-9+/=])"),
    # Anything that looks like a password/token assignment in text
    re.compile(
        r"(?i)\b(password|passwd|token|secret|api[_-]?key|private[_-]?key)\s*[:=]\s*\S+",
    ),
]

_REDACTED = "<REDACTED>"
_SSH_KEY_REDACTED = "<SSH_KEY_REDACTED>"
_TOKEN_REDACTED = "<TOKEN_REDACTED>"


def _is_secret_key(key: str) -> bool:
    """Return True if the mapping key name matches a known secret pattern."""
    lower = key.lower()
    return any(secret in lower for secret in _SECRET_KEYS)


# ── RedactionGuard ────────────────────────────────────────────────────────────

class RedactionGuard:
    """
    Reusable redaction layer for support bundles and log export.

    All methods are pure functions — no I/O, no state.

    Contract (see docs/SUPPORT_BUNDLE_CONTRACT.md):
    - Passwords, tokens, private keys and raw credentials are redacted.
    - Fail closed: if a format cannot be safely parsed, raise RedactionError
      rather than return a partially redacted result.
    - Not a legal/compliance guarantee.
    """

    def redact_text(self, text: str) -> str:
        """
        Redact secret patterns from a free-text string.

        Applies pattern-based redaction. Returns the redacted string.
        Raises RedactionError if a catastrophically unsafe pattern is detected
        and cannot be reliably redacted.
        """
        # SSH private key blocks — replace entire block
        result = re.sub(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            _SSH_KEY_REDACTED,
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Bearer/JWT tokens
        result = re.sub(
            r"\bBearer\s+[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_=]+\.[A-Za-z0-9\-_.+/=]*\b",
            f"Bearer {_TOKEN_REDACTED}",
            result,
        )
        # password/token/secret assignments in text
        result = re.sub(
            r"(?i)(\b(?:password|passwd|token|secret|api[_-]?key|private[_-]?key)\s*[:=]\s*)\S+",
            r"\g<1>" + _REDACTED,
            result,
        )
        return result

    def redact_mapping(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """
        Redact a flat or nested mapping (dict/JSON-like structure).

        - Keys matching _SECRET_KEYS have their values replaced with _REDACTED.
        - Nested dicts are recursively redacted.
        - List values have each item redacted if the parent key is secret.
        - Non-secret string values are passed through redact_text.

        Raises RedactionError if the input cannot be processed safely.
        """
        result: dict[str, Any] = {}
        for key, value in data.items():
            if _is_secret_key(str(key)):
                result[key] = _REDACTED
            elif isinstance(value, Mapping):
                result[key] = self.redact_mapping(value)
            elif isinstance(value, (list, tuple)):
                redacted_items = []
                for item in value:
                    if isinstance(item, Mapping):
                        redacted_items.append(self.redact_mapping(item))
                    elif isinstance(item, str):
                        redacted_items.append(self.redact_text(item))
                    else:
                        redacted_items.append(item)
                result[key] = redacted_items
            elif isinstance(value, str):
                result[key] = self.redact_text(value)
            else:
                result[key] = value
        return result

    def scan_for_secrets(self, text: str) -> list[str]:
        """
        Scan text for possible secret material.

        Returns a list of human-readable descriptions of matches found.
        Returns an empty list if no secrets are detected.
        Does not raise — callers decide what to do with the findings.
        """
        findings: list[str] = []
        if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text, re.IGNORECASE):
            findings.append("SSH/TLS private key block detected")
        if re.search(r"\bBearer\s+\S+\.\S+\.\S+", text):
            findings.append("JWT bearer token detected")
        if re.search(
            r"(?i)\b(?:password|passwd|token|secret|api[_-]?key|private[_-]?key)\s*[:=]\s*\S+",
            text,
        ):
            findings.append("Secret key=value assignment detected")
        if re.search(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{64,}={0,2}(?![A-Za-z0-9+/=])", text):
            findings.append("Long base64-encoded string detected (possible key material)")
        return findings

    def is_safe_for_export(self, text: str) -> bool:
        """
        Return True if no obvious secret patterns are detected in *text*.

        Convenience wrapper around scan_for_secrets for simple pass/fail checks.
        """
        return not self.scan_for_secrets(text)


class RedactionError(Exception):
    """Raised when redaction cannot be safely completed. Fail closed."""


# ── SupportBundleManifest ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class SupportBundleManifest:
    """
    Manifest for a KH PTZ Control support bundle ZIP.

    All fields default to 'unknown' rather than None — safe to log without
    None-checks. restore_capable is always False for support bundles.

    See docs/SUPPORT_BUNDLE_CONTRACT.md.
    """

    bundle_id: str = "unknown"
    generated_at: str = "unknown"
    installation_id: str = "unknown"
    app_version: str = "unknown"
    git_commit: str = "unknown"
    profile: str = "unknown"
    redaction_status: str = "applied"     # "applied" | "failed" | "skipped"
    included_files: tuple[str, ...] = ()
    excluded_files: tuple[str, ...] = ()
    redaction_warnings: tuple[str, ...] = ()
    restore_capable: bool = False
    bundle_purpose: str = "support"

    def __post_init__(self) -> None:
        if self.restore_capable:
            raise ValueError(
                "SupportBundleManifest.restore_capable must always be False. "
                "Support bundles are not restore backups."
            )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Convert tuples to lists for JSON serialization
        for key in ("included_files", "excluded_files", "redaction_warnings"):
            d[key] = list(d[key])
        return d

    def has_no_secrets(self) -> bool:
        """
        Return True if the manifest itself contains no obvious secret material.

        Checks that none of the string fields contain secret-pattern text.
        """
        guard = RedactionGuard()
        for value in (
            self.bundle_id,
            self.installation_id,
            self.app_version,
            self.git_commit,
            self.profile,
        ):
            if not guard.is_safe_for_export(str(value)):
                return False
        return True
