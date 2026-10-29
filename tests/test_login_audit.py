#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_login_audit.py — Persistent login audit log (#login-audit)

from __future__ import annotations

import application.login_audit as login_audit


def _use_tmp_audit(monkeypatch, tmp_path):
    audit_file = tmp_path / "login_audit.json"
    monkeypatch.setattr(login_audit, "_audit_file", lambda: audit_file)
    return audit_file


def test_record_then_read_last_login(monkeypatch, tmp_path):
    _use_tmp_audit(monkeypatch, tmp_path)
    assert login_audit.read_last_login_timestamp() == ""  # nothing yet

    login_audit.record_login_event(success=True, attempts=0)
    assert login_audit.read_last_login_timestamp().startswith("Last access: ")


def test_failures_do_not_count_as_last_access(monkeypatch, tmp_path):
    _use_tmp_audit(monkeypatch, tmp_path)
    login_audit.record_login_event(success=False, attempts=3)
    assert login_audit.read_last_login_timestamp() == ""


def test_log_is_capped(monkeypatch, tmp_path):
    _use_tmp_audit(monkeypatch, tmp_path)
    from core.json_io import load_json

    for _ in range(login_audit._MAX_EVENTS + 50):
        login_audit.record_login_event(success=True, attempts=0)
    events = load_json(login_audit._audit_file(), default=[])
    assert len(events) == login_audit._MAX_EVENTS


def test_record_never_raises_on_io_error(monkeypatch):
    # An unwritable audit path must not propagate an exception into login.
    def _boom():
        raise OSError("disk full")

    monkeypatch.setattr(login_audit, "_audit_file", _boom)
    login_audit.record_login_event(success=True, attempts=0)  # must not raise
    assert login_audit.read_last_login_timestamp() == ""
