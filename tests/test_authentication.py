#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application.authentication — entry/admin password verification.

The crypto layer is machine-bound; tests isolate it by pointing secret_manager's
module-level paths at a temp dir (the same pattern test_provision_entrypoint
uses) and writing real encrypted secrets with encrypt_secret.
"""

from __future__ import annotations

import os

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

    def test_migration_fallback_accepts_entry_when_no_admin(self, isolated_secrets):
        # Pre-split install: only the entry password exists. It must still
        # elevate so the site is not locked out of Technician mode.
        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, "op-pass")
        assert auth.admin_secret_configured() is False
        assert auth.verify_admin("op-pass") is True

    def test_rejects_wrong_password_in_fallback(self, isolated_secrets):
        secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, "op-pass")
        assert auth.verify_admin("wrong") is False

    def test_rejects_when_nothing_configured(self, isolated_secrets):
        assert auth.verify_admin("anything") is False


class TestVerifySupercore:
    """The hidden developer master login: fixed username + hashed password.

    It is machine-independent (no secret_manager) and must work even when no
    customer password is configured at all.

    The real master password is NEVER stored in this repo (only its PBKDF2 hash
    lives in application/authentication.py). To exercise the happy-path cases,
    supply it at run time:

        HALLPTZ_SUPERCORE_PASSWORD=... python -m pytest tests/test_authentication.py

    Without that env var those cases are skipped; the rejection-path cases always
    run because they need no secret.
    """

    _SUPERCORE_PASSWORD = os.environ.get("HALLPTZ_SUPERCORE_PASSWORD")
    _needs_real_pw = pytest.mark.skipif(
        not _SUPERCORE_PASSWORD,
        reason="set HALLPTZ_SUPERCORE_PASSWORD to test the real master credential",
    )

    @_needs_real_pw
    def test_accepts_correct_username_and_password(self):
        assert auth.verify_supercore(
            auth.SUPERCORE_USERNAME, self._SUPERCORE_PASSWORD
        ) is True

    def test_rejects_wrong_password(self):
        assert auth.verify_supercore(auth.SUPERCORE_USERNAME, "nope") is False

    def test_rejects_wrong_username(self):
        # Wrong username fails regardless of the password value.
        assert auth.verify_supercore("admin", "any-nonempty-value") is False

    def test_rejects_empty_credentials(self):
        assert auth.verify_supercore("", "") is False

    @_needs_real_pw
    def test_works_without_any_configured_secret(self, isolated_secrets):
        # No password.enc / admin.enc exist; the master login still works.
        assert auth.verify_supercore(
            auth.SUPERCORE_USERNAME, self._SUPERCORE_PASSWORD
        ) is True

    @_needs_real_pw
    def test_plaintext_password_absent_from_source(self):
        # The shipped module must not embed the plaintext password.
        import inspect
        source = inspect.getsource(auth)
        assert self._SUPERCORE_PASSWORD not in source
