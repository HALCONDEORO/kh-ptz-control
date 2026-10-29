#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_release_gate_contracts.py — Real tests for RELEASE_GATE contracts (#520).

from __future__ import annotations

import os
from pathlib import Path

import application.diagnostics_service as ds_module
from application.diagnostics_service import DiagnosticsService, Status


def _make_svc(tmp_path: Path) -> DiagnosticsService:
    install_dir = tmp_path / "app"
    install_dir.mkdir()
    (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return DiagnosticsService(
        install_dir=install_dir,
        data_dir=data_dir,
        config_path=install_dir / "missing.yaml",
    )


# ── doctor fails when data directory is not writable (#520/#452) ──────────────

class TestDataDirWriteCheck:
    def test_not_writable_returns_fail(self, tmp_path, monkeypatch):
        svc = _make_svc(tmp_path)
        real_access = os.access
        monkeypatch.setattr(
            ds_module.os, "access",
            lambda path, mode, **kw: False if mode == os.W_OK else real_access(path, mode, **kw),
        )
        assert svc._check_data_dir().status == Status.FAIL

    def test_not_writable_message_names_write(self, tmp_path, monkeypatch):
        svc = _make_svc(tmp_path)
        real_access = os.access
        monkeypatch.setattr(
            ds_module.os, "access",
            lambda path, mode, **kw: False if mode == os.W_OK else real_access(path, mode, **kw),
        )
        assert "write" in svc._check_data_dir().message.lower()

    def test_not_readable_returns_fail(self, tmp_path, monkeypatch):
        svc = _make_svc(tmp_path)
        real_access = os.access
        monkeypatch.setattr(
            ds_module.os, "access",
            lambda path, mode, **kw: False if mode == os.R_OK else real_access(path, mode, **kw),
        )
        assert svc._check_data_dir().status == Status.FAIL

    def test_not_readable_message_names_read(self, tmp_path, monkeypatch):
        svc = _make_svc(tmp_path)
        real_access = os.access
        monkeypatch.setattr(
            ds_module.os, "access",
            lambda path, mode, **kw: False if mode == os.R_OK else real_access(path, mode, **kw),
        )
        assert "read" in svc._check_data_dir().message.lower()

    def test_readable_and_writable_returns_ok(self, tmp_path, monkeypatch):
        svc = _make_svc(tmp_path)
        monkeypatch.setattr(ds_module.os, "access", lambda path, mode, **kw: True)
        assert svc._check_data_dir().status == Status.OK

    def test_missing_dir_is_created_and_ok(self, tmp_path):
        install_dir = tmp_path / "app"
        install_dir.mkdir()
        (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
        data_dir = tmp_path / "new_data"
        svc = DiagnosticsService(
            install_dir=install_dir,
            data_dir=data_dir,
            config_path=install_dir / "missing.yaml",
        )
        result = svc._check_data_dir()
        assert result.status == Status.OK
        assert data_dir.exists()

    def test_cannot_create_dir_returns_fail(self, tmp_path, monkeypatch):
        install_dir = tmp_path / "app"
        install_dir.mkdir()
        (install_dir / "VERSION").write_text("1.0.0", encoding="utf-8")
        data_dir = tmp_path / "no_such_parent" / "data"
        svc = DiagnosticsService(
            install_dir=install_dir,
            data_dir=data_dir,
            config_path=install_dir / "missing.yaml",
        )

        def _raise(*a, **kw):
            raise OSError("read-only filesystem")

        monkeypatch.setattr(ds_module.Path, "mkdir", _raise)
        result = svc._check_data_dir()
        assert result.status == Status.FAIL


# ── status output exposes no secrets (#520/#452) ──────────────────────────────

_SECRET_PATTERNS = [
    "password=",
    "passwd=",
    "token=",
    "secret=",
    "private_key=",
    "credential=",
]


class TestNoSecretsInOutput:
    def test_version_check_message_clean(self, tmp_path):
        svc = _make_svc(tmp_path)
        msg = svc._check_version().message.lower()
        for pat in _SECRET_PATTERNS:
            assert pat not in msg, f"Pattern {pat!r} in version message"

    def test_data_dir_check_message_clean(self, tmp_path):
        svc = _make_svc(tmp_path)
        msg = svc._check_data_dir().message.lower()
        for pat in _SECRET_PATTERNS:
            assert pat not in msg, f"Pattern {pat!r} in data_dir message"

    def test_config_missing_message_clean(self, tmp_path):
        svc = _make_svc(tmp_path)
        msg = svc._check_config(None).message.lower()
        for pat in _SECRET_PATTERNS:
            assert pat not in msg, f"Pattern {pat!r} in config message"

    def test_ip_config_missing_settings_message_clean(self, tmp_path):
        svc = _make_svc(tmp_path)
        msg = svc._check_ip_config(None).message.lower()
        for pat in _SECRET_PATTERNS:
            assert pat not in msg, f"Pattern {pat!r} in ip_config message"

    def test_installation_id_missing_settings_message_clean(self, tmp_path):
        svc = _make_svc(tmp_path)
        msg = svc._check_installation_id(None).message.lower()
        for pat in _SECRET_PATTERNS:
            assert pat not in msg, f"Pattern {pat!r} in installation_id message"

    def test_installation_profile_missing_settings_message_clean(self, tmp_path):
        svc = _make_svc(tmp_path)
        msg = svc._check_installation_profile(None).message.lower()
        for pat in _SECRET_PATTERNS:
            assert pat not in msg, f"Pattern {pat!r} in installation_profile message"

    def test_network_profile_missing_settings_message_clean(self, tmp_path):
        svc = _make_svc(tmp_path)
        msg = svc._check_network_profile(None).message.lower()
        for pat in _SECRET_PATTERNS:
            assert pat not in msg, f"Pattern {pat!r} in network_profile message"

