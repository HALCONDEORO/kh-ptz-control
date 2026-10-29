#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_secrets_never_group_readable.py — encrypted passwords stay private
#
# The encrypted password files live in KHPTZ_DATA_DIR (/var/lib/khptz), the same
# directory whose data files --gui-mode user deliberately makes group-writable
# so the session GUI and the service can share them (#885).
#
# Secrets must be excluded from that. Their key is derived from
# /etc/machine-id, which is world-readable, so a group-readable admin.enc is
# effectively plaintext to every member of the khptz group — including the
# desktop account. That would hand the administrator password to the operator
# and defeat the operator/administrator split the whole role model rests on.
#
# This was a real regression: the first version of the group-relaxation step
# ran `find "${DATA_DIR}" -type f -exec chmod g+rw` with no exclusion.

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = REPO_ROOT / "runtime" / "installer" / "install.sh"


@pytest.fixture(scope="module")
def installer() -> str:
    return INSTALLER.read_text(encoding="utf-8")


class TestInstallerExcludesSecrets:
    def test_group_relaxation_skips_enc_files(self, installer):
        # Only the FILE relaxation matters here. Matching "chmod g+rw" loosely
        # also catches the directory line's "chmod g+rwxs", which legitimately
        # has no -name filter.
        relax = [
            line for line in installer.splitlines()
            if "find" in line and "-type f" in line and "chmod g+rw" in line
        ]
        assert relax, "the group-relaxation step disappeared"
        for line in relax:
            assert "! -name '*.enc'" in line, (
                f"secrets are not excluded from the group relaxation: {line}"
            )

    def test_exclusion_is_explained(self, installer):
        """A future edit must be able to see why, not just what."""
        assert "machine-id" in installer
        assert re.search(r"administrator password", installer, re.IGNORECASE)

    def test_directories_are_still_shared(self, installer):
        """Excluding secrets must not break the data sharing it sits next to."""
        assert "chmod g+rwxs" in installer


class TestSecretWritesStayPrivate:
    """The Python side must not widen them either."""

    def test_encrypt_secret_requests_private_mode(self):
        source = (REPO_ROOT / "runtime" / "secret_manager.py").read_text(encoding="utf-8")
        assert "mode=0o600" in source, "secrets are written without an explicit mode"

    def test_atomic_write_honours_the_explicit_mode(self, tmp_path):
        """The shared group policy applies only when no mode is requested, so a
        group-writable directory must not widen a secret."""
        from core import atomic_write

        with patch.object(atomic_write, "group_shared_mode", return_value=0o660):
            with patch.object(atomic_write.os, "fchmod") as fchmod:
                atomic_write.write_text_atomic(
                    tmp_path / "admin.enc", "blob", mode=0o600
                )
        assert [c.args[1] for c in fchmod.call_args_list] == [0o600]

    def test_data_files_still_get_the_shared_mode(self, tmp_path):
        """Guard against over-correcting: ordinary data must stay shareable."""
        from core import atomic_write

        with patch.object(atomic_write, "group_shared_mode", return_value=0o660):
            with patch.object(atomic_write.os, "fchmod") as fchmod:
                atomic_write.write_text_atomic(tmp_path / "presets.json", "{}")
        assert [c.args[1] for c in fchmod.call_args_list] == [0o660]
