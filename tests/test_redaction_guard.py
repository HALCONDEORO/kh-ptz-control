#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_redaction_guard.py — Tests for RedactionGuard and SupportBundleManifest (#561).

Covers:
- redact_text: SSH private key, JWT bearer token, password= assignment
- redact_mapping: secret keys redacted, nested dicts, non-secret passthrough
- scan_for_secrets: detects SSH keys, JWTs, password assignments, base64 blobs
- is_safe_for_export: True for clean text, False for secret-containing text
- SupportBundleManifest: defaults are safe, no secrets in fields,
  restore_capable is always False, to_dict converts tuples to lists
"""
from __future__ import annotations

import pytest

from domain.redaction import (
    RedactionGuard,
    SupportBundleManifest,
)

_GUARD = RedactionGuard()


# ── redact_text ───────────────────────────────────────────────────────────────

class TestRedactText:

    def test_ssh_private_key_block_is_redacted(self):
        text = (
            "some text\n"
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0+jnmyxkABC123==\n"
            "-----END RSA PRIVATE KEY-----\n"
            "more text"
        )
        result = _GUARD.redact_text(text)
        assert "BEGIN RSA PRIVATE KEY" not in result
        assert "MIIEowIBAAKCAQEA" not in result
        assert "<SSH_KEY_REDACTED>" in result
        assert "some text" in result
        assert "more text" in result

    def test_bearer_jwt_token_is_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.signature"
        result = _GUARD.redact_text(text)
        assert "eyJhbGciOiJSUzI1NiJ9" not in result
        assert "<TOKEN_REDACTED>" in result

    def test_password_assignment_is_redacted(self):
        text = "config: password=secret123 host=example.com"
        result = _GUARD.redact_text(text)
        assert "secret123" not in result
        assert "<REDACTED>" in result
        assert "host=example.com" in result

    def test_token_colon_assignment_is_redacted(self):
        text = "token: abc-def-ghi-jkl"
        result = _GUARD.redact_text(text)
        assert "abc-def-ghi-jkl" not in result
        assert "<REDACTED>" in result

    def test_clean_text_is_unchanged(self):
        text = "Hall PTZ Control version 3.18.0 — all systems nominal."
        result = _GUARD.redact_text(text)
        assert result == text

    def test_empty_string_is_safe(self):
        assert _GUARD.redact_text("") == ""


# ── redact_mapping ────────────────────────────────────────────────────────────

class TestRedactMapping:

    def test_password_key_is_redacted(self):
        d = {"host": "192.168.1.1", "password": "hunter2"}
        result = _GUARD.redact_mapping(d)
        assert result["host"] == "192.168.1.1"
        assert result["password"] == "<REDACTED>"

    def test_token_key_is_redacted(self):
        d = {"api_key": "supersecrettoken"}
        result = _GUARD.redact_mapping(d)
        assert result["api_key"] == "<REDACTED>"

    def test_private_key_substring_in_key_is_redacted(self):
        d = {"private_key": "-----BEGIN EC PRIVATE KEY-----"}
        result = _GUARD.redact_mapping(d)
        assert result["private_key"] == "<REDACTED>"

    def test_nested_dict_is_recursively_redacted(self):
        d = {"auth": {"token": "secret", "user": "alice"}}
        result = _GUARD.redact_mapping(d)
        # "auth" is a secret key — its value is replaced entirely
        assert result["auth"] == "<REDACTED>"

    def test_non_secret_nested_dict_is_recursively_processed(self):
        d = {"connection": {"host": "192.168.1.1", "password": "x"}}
        result = _GUARD.redact_mapping(d)
        assert result["connection"]["host"] == "192.168.1.1"
        assert result["connection"]["password"] == "<REDACTED>"

    def test_non_secret_string_value_passes_through_text_redaction(self):
        d = {"description": "password=leaked here"}
        result = _GUARD.redact_mapping(d)
        assert "leaked" not in result["description"]
        assert "<REDACTED>" in result["description"]

    def test_non_string_value_passes_through_unchanged(self):
        d = {"count": 42, "enabled": True, "ratio": 3.14}
        result = _GUARD.redact_mapping(d)
        assert result["count"] == 42
        assert result["enabled"] is True
        assert result["ratio"] == 3.14

    def test_empty_mapping_returns_empty_dict(self):
        assert _GUARD.redact_mapping({}) == {}

    def test_list_value_under_secret_key_is_redacted(self):
        # When the key is secret, the entire value (including lists) is replaced.
        d = {"credentials": ["user:pass", "admin:secret"]}
        result = _GUARD.redact_mapping(d)
        assert result["credentials"] == "<REDACTED>"

    def test_list_value_under_non_secret_key_items_are_redacted_individually(self):
        # Non-secret key with list: each string item is passed through redact_text.
        d = {"messages": ["token=abc123", "all clear"]}
        result = _GUARD.redact_mapping(d)
        assert isinstance(result["messages"], list)
        assert "<REDACTED>" in result["messages"][0]
        assert result["messages"][1] == "all clear"


# ── scan_for_secrets ──────────────────────────────────────────────────────────

class TestScanForSecrets:

    def test_clean_text_returns_empty_list(self):
        assert _GUARD.scan_for_secrets("No secrets here.") == []

    def test_ssh_key_is_detected(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nABC123\n-----END RSA PRIVATE KEY-----"
        findings = _GUARD.scan_for_secrets(text)
        assert any("private key" in f.lower() or "ssh" in f.lower() for f in findings)

    def test_jwt_bearer_is_detected(self):
        text = "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.SIG"
        findings = _GUARD.scan_for_secrets(text)
        assert any("jwt" in f.lower() or "bearer" in f.lower() or "token" in f.lower()
                   for f in findings)

    def test_password_assignment_is_detected(self):
        text = "password=mysecret"
        findings = _GUARD.scan_for_secrets(text)
        assert findings

    def test_empty_text_returns_empty_list(self):
        assert _GUARD.scan_for_secrets("") == []


# ── is_safe_for_export ────────────────────────────────────────────────────────

class TestIsSafeForExport:

    def test_clean_text_is_safe(self):
        assert _GUARD.is_safe_for_export("Hall PTZ Control doctor output.")

    def test_text_with_password_is_not_safe(self):
        assert not _GUARD.is_safe_for_export("password=opensesame")

    def test_text_with_ssh_key_is_not_safe(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\ndata\n-----END RSA PRIVATE KEY-----"
        assert not _GUARD.is_safe_for_export(text)

    def test_empty_text_is_safe(self):
        assert _GUARD.is_safe_for_export("")


# ── SupportBundleManifest ─────────────────────────────────────────────────────

class TestSupportBundleManifest:

    def test_defaults_are_safe_unknown_strings(self):
        m = SupportBundleManifest()
        assert m.bundle_id == "unknown"
        assert m.installation_id == "unknown"
        assert m.app_version == "unknown"
        assert m.redaction_status == "applied"
        assert m.restore_capable is False
        assert m.bundle_purpose == "support"

    def test_restore_capable_always_false_raises_on_true(self):
        with pytest.raises(ValueError, match="restore_capable"):
            SupportBundleManifest(restore_capable=True)

    def test_to_dict_converts_tuples_to_lists(self):
        m = SupportBundleManifest(
            included_files=("doctor.txt", "version.txt"),
            excluded_files=("secrets.yaml",),
        )
        d = m.to_dict()
        assert isinstance(d["included_files"], list)
        assert isinstance(d["excluded_files"], list)
        assert d["included_files"] == ["doctor.txt", "version.txt"]
        assert d["excluded_files"] == ["secrets.yaml"]

    def test_has_no_secrets_passes_for_safe_manifest(self):
        m = SupportBundleManifest(
            bundle_id="bundle-001",
            installation_id="hallptz-2026-0042",
            app_version="3.18.0",
        )
        assert m.has_no_secrets()

    def test_manifest_fields_do_not_contain_password_token_secret(self):
        m = SupportBundleManifest(
            bundle_id="bundle-001",
            installation_id="hallptz-2026-0042",
            app_version="3.18.0",
            git_commit="abc1234",
            profile="production",
        )
        d = m.to_dict()
        for key in ("bundle_id", "installation_id", "app_version", "git_commit", "profile"):
            val = str(d[key])
            assert "password" not in val.lower(), f"{key!r} contains 'password'"
            assert "token" not in val.lower(), f"{key!r} contains 'token'"
            assert "secret" not in val.lower(), f"{key!r} contains 'secret'"

    def test_to_dict_is_json_serializable(self):
        import json
        m = SupportBundleManifest(
            bundle_id="bundle-001",
            included_files=("doctor.txt",),
        )
        d = m.to_dict()
        # Should not raise
        json.dumps(d)
