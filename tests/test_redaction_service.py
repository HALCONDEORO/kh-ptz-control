#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application/redaction_service.py and domain/redaction.py enhancements (#497).

Covers:
- RedactionService.redact_dict: secret keys, nested, non-secret passthrough
- RedactionService.redact_text: SSH keys, bearer token, password= assignments
- RedactionService.is_safe_for_export: clean vs secret-containing text
- RedactionService.scan_for_secrets: detects all listed secret patterns
- RedactionService.redact_doctor_report: doctor dict redacted + post-scan
- Never-raise contract: all methods succeed even when guard raises
- New _SECRET_KEYS: ssh_key, ssh_password, ssh_credential
- Original values never appear in redacted output
"""
from __future__ import annotations

import pytest

from application.redaction_service import RedactionResult, RedactionService
from domain.redaction import RedactionGuard


_SVC = RedactionService()


# ── RedactionResult ────────────────────────────────────────────────────────────

class TestRedactionResult:

    def test_defaults_applied(self):
        r = RedactionResult(value="x")
        assert r.applied is True
        assert r.is_clean is True

    def test_warnings_makes_not_clean(self):
        r = RedactionResult(value="x", warnings=["something"])
        assert r.is_clean is False

    def test_not_applied_makes_not_clean(self):
        r = RedactionResult(value="x", applied=False)
        assert r.is_clean is False


# ── RedactionService.redact_dict ──────────────────────────────────────────────

class TestRedactDict:

    def test_password_key_redacted(self):
        result = _SVC.redact_dict({"host": "192.168.1.1", "password": "hunter2"})
        assert result.applied
        assert result.value["password"] == "<REDACTED>"
        assert result.value["host"] == "192.168.1.1"

    def test_token_key_redacted(self):
        result = _SVC.redact_dict({"token": "abc-def"})
        assert result.value["token"] == "<REDACTED>"

    def test_ssh_key_field_redacted(self):
        result = _SVC.redact_dict({"ssh_key": "-----BEGIN RSA PRIVATE KEY-----"})
        assert result.value["ssh_key"] == "<REDACTED>"

    def test_ssh_password_field_redacted(self):
        result = _SVC.redact_dict({"ssh_password": "secret123"})
        assert result.value["ssh_password"] == "<REDACTED>"

    def test_private_key_field_redacted(self):
        result = _SVC.redact_dict({"private_key": "key-material"})
        assert result.value["private_key"] == "<REDACTED>"

    def test_license_private_key_redacted(self):
        # "private_key" is a substring of "license_private_key" so it matches
        result = _SVC.redact_dict({"license_private_key": "secret"})
        assert result.value["license_private_key"] == "<REDACTED>"

    def test_licence_private_key_redacted(self):
        result = _SVC.redact_dict({"licence_private_key": "secret"})
        assert result.value["licence_private_key"] == "<REDACTED>"

    def test_signing_key_redacted(self):
        result = _SVC.redact_dict({"signing_key": "key-data"})
        assert result.value["signing_key"] == "<REDACTED>"

    def test_api_key_redacted(self):
        result = _SVC.redact_dict({"api_key": "my-api-key"})
        assert result.value["api_key"] == "<REDACTED>"

    def test_non_secret_values_pass_through(self):
        result = _SVC.redact_dict({"version": "3.18.0", "profile": "production"})
        assert result.value["version"] == "3.18.0"
        assert result.value["profile"] == "production"

    def test_nested_dict_recursively_redacted(self):
        result = _SVC.redact_dict({"connection": {"host": "192.168.1.1", "password": "p"}})
        assert result.value["connection"]["host"] == "192.168.1.1"
        assert result.value["connection"]["password"] == "<REDACTED>"

    def test_original_value_absent_from_result(self):
        result = _SVC.redact_dict({"password": "do_not_leak_me"})
        assert "do_not_leak_me" not in str(result.value)

    def test_empty_dict_returns_empty(self):
        result = _SVC.redact_dict({})
        assert result.value == {}
        assert result.applied

    def test_returns_redaction_result(self):
        result = _SVC.redact_dict({"x": 1})
        assert isinstance(result, RedactionResult)


# ── RedactionService.redact_text ──────────────────────────────────────────────

class TestRedactText:

    def test_ssh_private_key_block_redacted(self):
        text = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0+jnmyxkABC123==\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = _SVC.redact_text(text)
        assert result.applied
        assert "MIIEowIBAAKCAQEA" not in result.value
        assert "<SSH_KEY_REDACTED>" in result.value

    def test_bearer_jwt_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.sig"
        result = _SVC.redact_text(text)
        assert "eyJhbGciOiJSUzI1NiJ9" not in result.value
        assert "<TOKEN_REDACTED>" in result.value

    def test_password_assignment_redacted(self):
        text = "config: password=secret123 host=example.com"
        result = _SVC.redact_text(text)
        assert "secret123" not in result.value
        assert "<REDACTED>" in result.value
        assert "host=example.com" in result.value  # non-secret preserved

    def test_clean_text_unchanged(self):
        text = "Hall PTZ Control version 3.18.0 — all systems nominal."
        result = _SVC.redact_text(text)
        assert result.value == text
        assert result.is_clean

    def test_returns_redaction_result(self):
        result = _SVC.redact_text("hello")
        assert isinstance(result, RedactionResult)


# ── RedactionService.is_safe_for_export ──────────────────────────────────────

class TestIsSafeForExport:

    def test_clean_text_is_safe(self):
        assert _SVC.is_safe_for_export("HALLPTZ doctor: all checks OK")

    def test_password_assignment_is_not_safe(self):
        assert not _SVC.is_safe_for_export("password=opensesame")

    def test_ssh_key_is_not_safe(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\ndata\n-----END RSA PRIVATE KEY-----"
        assert not _SVC.is_safe_for_export(text)

    def test_empty_text_is_safe(self):
        assert _SVC.is_safe_for_export("")


# ── RedactionService.scan_for_secrets ────────────────────────────────────────

class TestScanForSecrets:

    def test_clean_text_empty_list(self):
        assert _SVC.scan_for_secrets("No secrets here.") == []

    def test_ssh_key_detected(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\nABC\n-----END RSA PRIVATE KEY-----"
        findings = _SVC.scan_for_secrets(text)
        assert findings

    def test_password_assignment_detected(self):
        findings = _SVC.scan_for_secrets("password=mysecret")
        assert findings

    def test_empty_text_empty_list(self):
        assert _SVC.scan_for_secrets("") == []


# ── RedactionService.redact_doctor_report ─────────────────────────────────────

class TestRedactDoctorReport:

    def test_clean_report_is_clean(self):
        report = {
            "overall": "OK",
            "checks": [
                {"name": "version", "status": "OK", "message": "v3.18.0"},
                {"name": "config", "status": "OK", "message": "config loaded"},
            ],
        }
        result = _SVC.redact_doctor_report(report)
        assert result.applied
        assert result.value["overall"] == "OK"

    def test_password_in_check_message_is_redacted(self):
        report = {
            "overall": "WARN",
            "checks": [{"name": "config", "status": "WARN", "message": "password=leaked"}],
        }
        result = _SVC.redact_doctor_report(report)
        import json
        serialized = json.dumps(result.value)
        assert "leaked" not in serialized

    def test_runtime_state_secret_error_is_redacted(self):
        report = {
            "overall": "WARN",
            "runtime_state": {
                "session": {"chairman_name": "[REDACTED]"},
                "cameras": {
                    "cam1": {
                        "last_error": "auth failed password=do_not_export",
                    },
                },
            },
        }

        result = _SVC.redact_doctor_report(report)

        assert "do_not_export" not in str(result.value)
        assert "password=<REDACTED>" in str(result.value)

    def test_runtime_state_redacted_chairman_marker_is_preserved(self):
        report = {
            "overall": "OK",
            "runtime_state": {
                "session": {"chairman_name": "[REDACTED]"},
            },
        }

        result = _SVC.redact_doctor_report(report)

        assert result.value["runtime_state"]["session"]["chairman_name"] == "[REDACTED]"

    def test_returns_redaction_result(self):
        result = _SVC.redact_doctor_report({})
        assert isinstance(result, RedactionResult)


# ── Never-raise contract ──────────────────────────────────────────────────────

class TestNeverRaise:

    def test_redact_dict_does_not_raise_on_non_dict_values(self):
        result = _SVC.redact_dict({"x": None, "y": 42, "z": [1, 2]})
        assert isinstance(result, RedactionResult)

    def test_is_safe_for_export_does_not_raise_on_empty(self):
        assert isinstance(_SVC.is_safe_for_export(""), bool)

    def test_scan_for_secrets_does_not_raise_on_empty(self):
        assert isinstance(_SVC.scan_for_secrets(""), list)


# ── Fail-closed: original secrets must not appear on guard failure (#609) ─────

class TestFailClosed:
    """When the guard raises, the original secret must never appear in result.value."""

    SECRET_TEXT = "password=super_secret_do_not_leak"
    SECRET_DICT = {"password": "super_secret_do_not_leak", "host": "192.168.1.1"}

    def _broken_svc(self, monkeypatch):
        svc = RedactionService()
        monkeypatch.setattr(svc._guard, "redact_mapping", lambda *_: (_ for _ in ()).throw(RuntimeError("guard broke")))
        monkeypatch.setattr(svc._guard, "redact_text", lambda *_: (_ for _ in ()).throw(RuntimeError("guard broke")))
        return svc

    def test_redact_text_failure_does_not_return_original(self, monkeypatch):
        svc = self._broken_svc(monkeypatch)
        result = svc.redact_text(self.SECRET_TEXT)
        assert "super_secret_do_not_leak" not in result.value
        assert result.value == "<REDACTION_FAILED>"

    def test_redact_text_failure_applied_false(self, monkeypatch):
        svc = self._broken_svc(monkeypatch)
        result = svc.redact_text(self.SECRET_TEXT)
        assert result.applied is False
        assert result.warnings

    def test_redact_dict_failure_does_not_return_original(self, monkeypatch):
        svc = self._broken_svc(monkeypatch)
        result = svc.redact_dict(self.SECRET_DICT)
        assert "super_secret_do_not_leak" not in str(result.value)
        assert "192.168.1.1" not in str(result.value)

    def test_redact_dict_failure_applied_false(self, monkeypatch):
        svc = self._broken_svc(monkeypatch)
        result = svc.redact_dict(self.SECRET_DICT)
        assert result.applied is False
        assert result.warnings

    def test_redact_dict_failure_value_is_safe_placeholder(self, monkeypatch):
        svc = self._broken_svc(monkeypatch)
        result = svc.redact_dict(self.SECRET_DICT)
        assert result.value == {"<REDACTION_FAILED>": "<REDACTION_FAILED>"}

    def test_redact_text_still_does_not_raise(self, monkeypatch):
        svc = self._broken_svc(monkeypatch)
        result = svc.redact_text(self.SECRET_TEXT)
        assert isinstance(result, RedactionResult)

    def test_redact_dict_still_does_not_raise(self, monkeypatch):
        svc = self._broken_svc(monkeypatch)
        result = svc.redact_dict(self.SECRET_DICT)
        assert isinstance(result, RedactionResult)


# ── domain/redaction._SECRET_KEYS coverage ───────────────────────────────────

class TestSecretKeysSet:

    @pytest.mark.parametrize("key_name", [
        "password", "passwd", "token", "secret", "private_key", "api_key",
        "signing_key", "ssh_key", "ssh_password", "ssh_credential",
        "license_key", "licence_key", "bearer", "authorization",
    ])
    def test_key_is_detected_as_secret(self, key_name):
        guard = RedactionGuard()
        d = {key_name: "should_be_redacted"}
        result = guard.redact_mapping(d)
        assert result[key_name] == "<REDACTED>", f"{key_name!r} was not redacted"

    @pytest.mark.parametrize("key_name", [
        "host", "ip", "version", "profile", "site_name", "camera_id",
        "installation_profile", "connectivity_mode",
    ])
    def test_non_secret_key_is_not_redacted(self, key_name):
        guard = RedactionGuard()
        d = {key_name: "safe_value"}
        result = guard.redact_mapping(d)
        assert result[key_name] == "safe_value", f"{key_name!r} was incorrectly redacted"

