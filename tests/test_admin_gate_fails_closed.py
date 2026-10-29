#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_admin_gate_fails_closed.py — an unreadable admin secret denies access
#
# The defect: verify_admin() gated on admin_secret_configured(), which is
# secret_is_configured() -> decrypt_secret(). decrypt_secret deliberately turns
# ANY failure into PasswordNotConfiguredError — its docstring says "missing,
# corrupt, or unreadable" — so a secret the process simply could not read
# answered "not configured", and verify_admin fell through to the pre-split
# migration fallback: verify_entry(candidate).
#
# The result was privilege escalation. An unreadable admin.enc meant the
# OPERATOR password passed an ADMINISTRATOR gate — and every admin gate in the
# product routes through this function: Repair provisioning
# (runtime.provision), the password-change dialog, admin login and the role
# elevation overlay.
#
# Reachable exactly as the permission defects fixed earlier in this branch:
# secrets live in /var/lib/khptz owned khptz:khptz, and under --gui-mode user the
# GUI runs as the desktop user.
#
# The distinction that matters: a genuinely ABSENT admin.enc may still fall back
# (that is the documented migration path for single-password sites); one that
# EXISTS but cannot be read must deny.

from __future__ import annotations

from unittest.mock import patch

import pytest

from application import authentication
from runtime import secret_manager


ADMIN_PASSWORD = "admin-secret-pw"
ENTRY_PASSWORD = "operator-pw"


@pytest.fixture
def secrets(tmp_path, monkeypatch):
    """Real encrypted secrets on disk, isolated from the developer's own."""
    monkeypatch.setattr(secret_manager, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(secret_manager, "_ENC_FILE", tmp_path / "password.enc")
    secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, ENTRY_PASSWORD)
    secret_manager.encrypt_secret(secret_manager.SECRET_ADMIN, ADMIN_PASSWORD)
    return tmp_path


class TestNormalBehaviourIsUnchanged:
    def test_admin_password_is_accepted(self, secrets):
        assert authentication.verify_admin(ADMIN_PASSWORD) is True

    def test_operator_password_is_rejected(self, secrets):
        """With a real admin secret, the entry password must never elevate."""
        assert authentication.verify_admin(ENTRY_PASSWORD) is False

    def test_wrong_password_is_rejected(self, secrets):
        assert authentication.verify_admin("nope") is False


class TestUnreadableAdminSecretDeniesAccess:
    """The regression this file exists for."""

    @staticmethod
    def _only_admin_unreadable():
        """Fail just the admin secret, leaving the entry secret readable.

        Patching decrypt_secret wholesale would also break verify_entry, so the
        fallback would return False for its own reason and the test would pass
        even with the bug present — proving nothing.
        """
        real = secret_manager.decrypt_secret

        def _decrypt(name):
            if name == secret_manager.SECRET_ADMIN:
                raise secret_manager.PasswordNotConfiguredError("unreadable")
            return real(name)

        return patch.object(secret_manager, "decrypt_secret", _decrypt)

    def test_operator_password_does_not_elevate(self, secrets):
        with self._only_admin_unreadable():
            assert authentication.verify_admin(ENTRY_PASSWORD) is False, (
                "an unreadable admin.enc let the operator password pass an "
                "administrator gate"
            )

    def test_admin_password_also_denied_when_unreadable(self, secrets):
        """Fail closed means closed for everyone — the correct password cannot
        be checked either, so it must not be assumed correct."""
        with self._only_admin_unreadable():
            assert authentication.verify_admin(ADMIN_PASSWORD) is False

    def test_permission_error_denies(self, secrets):
        """The realistic case: the file is 0600 and owned by another identity."""
        real_read = type(secrets / "x").read_text

        def _denied(self, *a, **kw):
            if self.name == "admin.enc":
                raise PermissionError(13, "Permission denied")
            return real_read(self, *a, **kw)

        with patch("pathlib.Path.read_text", _denied):
            assert authentication.verify_admin(ENTRY_PASSWORD) is False
            assert authentication.verify_admin(ADMIN_PASSWORD) is False

    def test_corrupt_admin_secret_denies(self, secrets):
        (secrets / "admin.enc").write_text("not-a-valid-blob", encoding="ascii")
        assert authentication.verify_admin(ENTRY_PASSWORD) is False
        assert authentication.verify_admin(ADMIN_PASSWORD) is False


class TestMigrationFallbackStillWorks:
    """A single-password site with no admin.enc must not be locked out."""

    def test_entry_password_elevates_when_no_admin_secret_exists(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(secret_manager, "_CONFIG_DIR", tmp_path)
        monkeypatch.setattr(secret_manager, "_ENC_FILE", tmp_path / "password.enc")
        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, ENTRY_PASSWORD)
        assert not (tmp_path / "admin.enc").exists()

        assert authentication.verify_admin(ENTRY_PASSWORD) is True

    def test_wrong_password_still_rejected_in_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setattr(secret_manager, "_CONFIG_DIR", tmp_path)
        monkeypatch.setattr(secret_manager, "_ENC_FILE", tmp_path / "password.enc")
        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, ENTRY_PASSWORD)

        assert authentication.verify_admin("nope") is False


class TestExistenceCheckIsSafe:
    def test_existence_never_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(secret_manager, "_CONFIG_DIR", tmp_path)
        assert secret_manager.secret_file_exists(secret_manager.SECRET_ADMIN) is False

    def test_unstattable_path_is_treated_as_present(self, tmp_path, monkeypatch):
        """Fail closed: an unknown state must not open the fallback."""
        monkeypatch.setattr(secret_manager, "_CONFIG_DIR", tmp_path)
        with patch("pathlib.Path.exists", side_effect=OSError("stat failed")):
            assert secret_manager.secret_file_exists(secret_manager.SECRET_ADMIN) is True

    def test_invalid_name_is_treated_as_present(self):
        assert secret_manager.secret_file_exists("../escape") is True
