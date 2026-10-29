#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_setup_password.py — Unit tests for runtime/setup_password.py main() logic.

The function is interactive (getpass), so stdin and the file-system operations
are mocked.  No real password files are read or written.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_main(**patches):
    """Import and call main() with the given patches active."""
    import runtime.setup_password as _sp
    with patch.multiple("runtime.setup_password", **patches):
        _sp.main()


# ── Migration path (password.txt → password.enc) ──────────────────────────────
#
# The migration path reads old_file = Path(__file__).parent / "password.txt"
# relative to the installed module, making it hard to redirect cleanly with
# monkeypatching.  Coverage of the happy-path migration is provided by the
# integration test in test_khptz_cli.py (secret_manager).  Here we only test
# the exit-on-failure branch via full Path mocking.

class TestMigrationFromLegacyFile:
    def test_migration_exits_1_if_verify_fails(self, tmp_path, monkeypatch):
        """sys.exit(1) is called when migrate+verify fails (decrypt raises)."""
        import runtime.setup_password as _sp
        from runtime.secret_manager import PasswordNotConfiguredError

        enc = tmp_path / "password.enc"
        monkeypatch.setattr(_sp, "_ENC_FILE", enc)

        # Simulate: old password.txt exists, enc does NOT
        old_inst = MagicMock()
        old_inst.exists.return_value = True
        old_inst.read_text.return_value = "secret"

        parent_mock = MagicMock()
        parent_mock.__truediv__ = MagicMock(return_value=old_inst)
        file_mock = MagicMock()
        file_mock.parent = parent_mock

        # enc.exists() must return False so the migration branch is taken
        with patch("runtime.setup_password.Path", return_value=file_mock), \
             patch.object(_sp, "_ENC_FILE", MagicMock(exists=MagicMock(return_value=False))), \
             patch("runtime.setup_password.encrypt_password"), \
             patch("runtime.setup_password.decrypt_password",
                   side_effect=PasswordNotConfiguredError):
            with pytest.raises(SystemExit) as exc_info:
                _sp.main()
            assert exc_info.value.code == 1


# ── Change-password path ───────────────────────────────────────────────────────

class TestChangePassword:
    def test_accepts_valid_new_password(self, tmp_path, monkeypatch):
        import runtime.setup_password as _sp
        enc = tmp_path / "password.enc"
        enc.write_text("x", encoding="utf-8")
        monkeypatch.setattr(_sp, "_ENC_FILE", enc)

        with patch("runtime.setup_password.decrypt_password", return_value="current"), \
             patch("runtime.setup_password.encrypt_password") as mock_enc, \
             patch("getpass.getpass", side_effect=["current", "newpass", "newpass"]):
            _sp.main()

        mock_enc.assert_called_once_with("newpass")

    def test_rejects_wrong_current_password(self, tmp_path, monkeypatch):
        import runtime.setup_password as _sp
        enc = tmp_path / "password.enc"
        enc.write_text("x", encoding="utf-8")
        monkeypatch.setattr(_sp, "_ENC_FILE", enc)

        with patch("runtime.setup_password.decrypt_password", return_value="correct"), \
             patch("getpass.getpass", return_value="wrong"):
            with pytest.raises(SystemExit) as exc_info:
                _sp.main()
            assert exc_info.value.code == 1

    def test_retries_on_mismatched_confirmation(self, tmp_path, monkeypatch):
        import runtime.setup_password as _sp
        enc = tmp_path / "password.enc"
        enc.write_text("x", encoding="utf-8")
        monkeypatch.setattr(_sp, "_ENC_FILE", enc)

        # First attempt: new != confirm.  Second attempt: match.
        with patch("runtime.setup_password.decrypt_password", return_value="current"), \
             patch("runtime.setup_password.encrypt_password") as mock_enc, \
             patch("getpass.getpass",
                   side_effect=["current", "newpass", "WRONG", "newpass", "newpass"]):
            _sp.main()

        mock_enc.assert_called_once_with("newpass")

    def test_rejects_empty_new_password(self, tmp_path, monkeypatch):
        import runtime.setup_password as _sp
        enc = tmp_path / "password.enc"
        enc.write_text("x", encoding="utf-8")
        monkeypatch.setattr(_sp, "_ENC_FILE", enc)

        # First new_pwd is empty → loop retries; second attempt succeeds
        with patch("runtime.setup_password.decrypt_password", return_value="current"), \
             patch("runtime.setup_password.encrypt_password") as mock_enc, \
             patch("getpass.getpass",
                   side_effect=["current", "", "goodpwd", "goodpwd"]):
            _sp.main()

        mock_enc.assert_called_once_with("goodpwd")

    def test_proceeds_when_enc_unreadable(self, tmp_path, monkeypatch):
        import runtime.setup_password as _sp
        from runtime.secret_manager import PasswordNotConfiguredError

        enc = tmp_path / "password.enc"
        enc.write_text("corrupted", encoding="utf-8")
        monkeypatch.setattr(_sp, "_ENC_FILE", enc)

        # decrypt raises → warning printed, no current-password prompt
        with patch("runtime.setup_password.decrypt_password",
                   side_effect=PasswordNotConfiguredError), \
             patch("runtime.setup_password.encrypt_password") as mock_enc, \
             patch("getpass.getpass", side_effect=["newpass", "newpass"]):
            _sp.main()

        mock_enc.assert_called_once_with("newpass")
