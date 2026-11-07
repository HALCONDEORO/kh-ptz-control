#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application.authentication — entry/admin password verification.

The crypto layer is machine-bound; tests isolate it by pointing secret_manager's
module-level paths at a temp dir (the same pattern test_provision_entrypoint
uses) and writing real encrypted secrets with encrypt_secret.
"""

from __future__ import annotations

import pytest

from application import authentication as auth
from runtime import secret_manager


@pytest.fixture
def isolated_secrets(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(secret_manager, "_CONFIG_DIR", data_dir)
    monkeypatch.setattr(secret_manager, "_ENC_FILE", data_dir / "password.enc")
    return data_dir


class TestVerifyEntry:

    def test_accepts_correct_entry_password(self, isolated_secrets):
        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, "op-pass")
        assert auth.verify_entry("op-pass") is True

    def test_rejects_wrong_entry_password(self, isolated_secrets):
        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, "op-pass")
        assert auth.verify_entry("nope") is False

    def test_rejects_when_nothing_configured(self, isolated_secrets):
        assert auth.verify_entry("anything") is False


class TestAdminConfigured:

    def test_false_before_admin_set(self, isolated_secrets):
        assert auth.admin_secret_configured() is False

    def test_true_after_admin_set(self, isolated_secrets):
        secret_manager.encrypt_secret(secret_manager.SECRET_ADMIN, "admin-pass")
        assert auth.admin_secret_configured() is True


class TestVerifyAdmin:

    def test_accepts_admin_password_when_set(self, isolated_secrets):
        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, "op-pass")
        secret_manager.encrypt_secret(secret_manager.SECRET_ADMIN, "admin-pass")
        assert auth.verify_admin("admin-pass") is True

    def test_rejects_entry_password_once_admin_is_set(self, isolated_secrets):
        # The whole point of the split: with a dedicated admin password, the
        # operator's entry password must NOT elevate to Technician.
        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, "op-pass")
        secret_manager.encrypt_secret(secret_manager.SECRET_ADMIN, "admin-pass")
        assert auth.verify_admin("op-pass") is False

    def test_no_implicit_migration_from_entry_when_no_admin(self, isolated_secrets):
        # Pre-split install: only operator exists. Administrator access stays
        # closed until an explicit privileged reset supplies a separate secret.
        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, "op-pass")
        assert auth.admin_secret_configured() is False
        assert auth.verify_admin("op-pass") is False

    def test_rejects_wrong_password_in_fallback(self, isolated_secrets):
        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, "op-pass")
        assert auth.verify_admin("wrong") is False

    def test_rejects_when_nothing_configured(self, isolated_secrets):
        assert auth.verify_admin("anything") is False


class TestHiddenMasterLoginRemoved:
    """The hidden fixed-user master login no longer exists in any form."""

    def test_verifier_and_constants_are_gone(self):
        public = {n for n in dir(auth) if n.startswith("verify_")}
        assert public == {"verify_entry", "verify_admin"}
        for name in dir(auth):
            assert not name.endswith(("_PASSWORD_HASH", "_SALT", "_ITERATIONS")), name
            assert "USERNAME" not in name, name

    def test_fixed_user_name_does_not_open_admin_or_entry(self, isolated_secrets):
        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, "op-pass")
        secret_manager.encrypt_secret(secret_manager.SECRET_ADMIN, "admin-pass")
        for candidate in ("fixed-user-login", "", "admin"):
            assert auth.verify_admin(candidate) is False
            assert auth.verify_entry(candidate) is False

    def test_no_credential_when_nothing_is_configured(self, isolated_secrets):
        assert auth.verify_admin("fixed-user-login") is False
        assert auth.verify_entry("fixed-user-login") is False

    def test_regular_admin_login_still_works(self, isolated_secrets):
        secret_manager.encrypt_secret(secret_manager.SECRET_ADMIN, "admin-pass")
        assert auth.verify_admin("admin-pass") is True
        assert auth.verify_admin("wrong") is False
