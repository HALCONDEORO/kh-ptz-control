#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application.provision_handoff — the wizard side of provisioning.

No Qt, no systemd: the request/result paths are temp files and the privileged
side is simulated. The injected ``sleep`` is the seam tests use to make the
result appear between polls. One integration test wires the real
runtime.provision.run_provision in as the privileged half to prove both ends
agree on the wire format.
"""

from __future__ import annotations

import json

import pytest

from application.provision_handoff import ProvisionHandoff, build_request_payload
from application.provisioning_service import ProvisioningAnswers
from runtime import provision, secret_manager
from runtime.path_resolver import RuntimePathResolver


def _answers():
    a = ProvisioningAnswers()
    a.entry_password = "op-pass"
    a.admin_password = "admin-pass"
    return a


class TestRequestPayload:

    def test_payload_round_trips_through_privileged_parser(self):
        # The handoff payload must be exactly what the privileged side parses.
        answers = _answers()
        back = provision.answers_from_dict(build_request_payload(answers))
        assert back.entry_password == "op-pass"
        assert back.admin_password == "admin-pass"
        assert [c.id for c in back.cameras] == [c.id for c in answers.cameras]


class TestBegin:

    def test_begin_writes_request_with_answers(self, tmp_path):
        req, res = tmp_path / "request.json", tmp_path / "result.json"
        h = ProvisionHandoff(req, res)
        h.begin(_answers())
        data = json.loads(req.read_text(encoding="utf-8"))
        assert data["entry_password"] == "op-pass"
        assert data["site_name"] == ProvisioningAnswers().site_name

    def test_begin_clears_stale_result(self, tmp_path):
        req, res = tmp_path / "request.json", tmp_path / "result.json"
        res.write_text('{"ok": true}', encoding="utf-8")
        ProvisionHandoff(req, res).begin(_answers())
        assert not res.exists(), "a previous run's result must not survive begin()"


class TestSubmit:

    def test_happy_path(self, tmp_path):
        req, res = tmp_path / "request.json", tmp_path / "result.json"

        def fake_sleep(_):  # privileged side reacts between polls
            res.write_text(json.dumps({"ok": True, "written": ["/etc/hallptz/config.yaml"]}),
                           encoding="utf-8")

        result = ProvisionHandoff(req, res, sleep=fake_sleep).submit(_answers())
        assert result.ok is True
        assert result.written == ["/etc/hallptz/config.yaml"]
        assert "complete" in result.summary().lower()

    def test_failure_with_issues(self, tmp_path):
        req, res = tmp_path / "request.json", tmp_path / "result.json"

        def fake_sleep(_):
            res.write_text(json.dumps(
                {"ok": False, "issues": [{"field": "entry_password", "message": "required"}]}
            ), encoding="utf-8")

        result = ProvisionHandoff(req, res, sleep=fake_sleep).submit(_answers())
        assert result.ok is False
        assert result.issues[0]["field"] == "entry_password"
        assert "required" in result.summary()

    def test_error_result(self, tmp_path):
        req, res = tmp_path / "request.json", tmp_path / "result.json"

        def fake_sleep(_):
            res.write_text(json.dumps({"ok": False, "error": "boom"}), encoding="utf-8")

        result = ProvisionHandoff(req, res, sleep=fake_sleep).submit(_answers())
        assert result.ok is False
        assert "boom" in result.error

    def test_timeout_when_no_result_appears(self, tmp_path):
        req, res = tmp_path / "request.json", tmp_path / "result.json"
        clock = [0.0]

        def mono():
            return clock[0]

        def fake_sleep(_):  # time passes but no result ever lands
            clock[0] += 60.0

        result = ProvisionHandoff(
            req, res, timeout_s=30.0, monotonic=mono, sleep=fake_sleep
        ).submit(_answers())
        assert result.ok is False
        assert result.timed_out is True

    def test_unreadable_result_reported_as_error(self, tmp_path):
        req, res = tmp_path / "request.json", tmp_path / "result.json"

        def fake_sleep(_):
            res.write_text("not json{", encoding="utf-8")

        result = ProvisionHandoff(req, res, sleep=fake_sleep).submit(_answers())
        assert result.ok is False
        assert "unreadable" in result.error


class TestPoll:

    def test_poll_returns_none_before_deadline(self, tmp_path):
        req, res = tmp_path / "request.json", tmp_path / "result.json"
        h = ProvisionHandoff(req, res, timeout_s=999.0)
        h.begin(_answers())
        assert h.poll() is None


class TestEndToEndWithPrivilegedSide:
    """Wire the real run_provision in as the privileged half."""

    @pytest.fixture
    def isolated(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(tmp_path / "etc"))
        monkeypatch.setenv("HALLPTZ_DATA_DIR", str(data_dir))
        monkeypatch.setattr(secret_manager, "_CONFIG_DIR", data_dir)
        monkeypatch.setattr(secret_manager, "_ENC_FILE", data_dir / "password.enc")
        return RuntimePathResolver(), tmp_path

    def test_request_from_handoff_is_applied_and_result_read_back(self, isolated):
        resolver, tmp_path = isolated
        req, res = tmp_path / "request.json", tmp_path / "result.json"
        handoff = ProvisionHandoff(req, res)

        handoff.begin(_answers())                       # wizard drops the request
        provision.run_provision(                        # privileged side reacts
            req, res, resolver=resolver, do_system=False
        )
        result = handoff.poll()                         # wizard reads the result

        assert result is not None and result.ok is True
        assert (resolver.config_dir / "config.yaml").exists()
        assert not req.exists(), "privileged side must shred the request"
