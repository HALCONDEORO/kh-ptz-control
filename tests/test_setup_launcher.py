#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for runtime.setup_launcher and the `hallptz setup` CLI command.

These stay Qt-free: the provisioned guard and the CLI dispatch are tested without
building real wizard pages, so the suite never needs a display here.
"""

from __future__ import annotations

import pytest

import runtime.setup_launcher as setup_launcher
from runtime.path_resolver import RuntimePathResolver
from runtime.setup_launcher import setup_wizard_needed


@pytest.fixture
def resolver(tmp_path, monkeypatch):
    monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(tmp_path / "etc"))
    monkeypatch.setenv("HALLPTZ_DATA_DIR", str(tmp_path / "data"))
    r = RuntimePathResolver()
    r.config_dir.mkdir(parents=True, exist_ok=True)
    return r


# ── setup_wizard_needed (pure guard) ──────────────────────────────────────────

def test_needed_when_not_provisioned(resolver):
    assert setup_wizard_needed(resolver) is True


def test_not_needed_when_provisioned(resolver):
    resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")
    assert setup_wizard_needed(resolver) is False


def test_force_overrides_provisioned(resolver):
    resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")
    assert setup_wizard_needed(resolver, force=True) is True


def test_uses_default_resolver_when_none(monkeypatch, tmp_path):
    monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(tmp_path / "etc"))
    # No marker on disk → wizard needed, resolver built internally.
    assert setup_wizard_needed() is True


# ── run_setup_wizard (injected factory, no real pages) ────────────────────────

class _FakeWizard:
    def __init__(self, result):
        self._result = result

    def exec_(self):
        return self._result


def test_run_returns_zero_when_accepted():
    from PyQt5.QtWidgets import QDialog
    code = setup_launcher.run_setup_wizard(lambda: _FakeWizard(QDialog.Accepted))
    assert code == 0


def test_run_returns_one_when_rejected():
    from PyQt5.QtWidgets import QDialog
    code = setup_launcher.run_setup_wizard(lambda: _FakeWizard(QDialog.Rejected))
    assert code == 1


# ── cmd_setup (CLI dispatch) ──────────────────────────────────────────────────

class _Args:
    profile = None
    force = False


def test_cmd_setup_short_circuits_when_provisioned(resolver, monkeypatch, capsys):
    resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")

    def _boom(**_):
        raise AssertionError("wizard must not launch when already provisioned")

    monkeypatch.setattr(setup_launcher, "run_setup_wizard", _boom)
    from runtime.cli import cmd_setup
    rc = cmd_setup(_Args())
    assert rc == 0
    assert "Already provisioned" in capsys.readouterr().out


def test_cmd_setup_launches_when_not_provisioned(resolver, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        setup_launcher, "run_setup_wizard",
        lambda answers=None, require_admin_auth=False: seen.update(answers=answers) or 7,
    )
    from runtime.cli import cmd_setup
    rc = cmd_setup(_Args())
    assert rc == 7
    # Fresh install, no config.yaml on disk at all → no pre-filled answers.
    assert seen == {"answers": None}


def test_cmd_setup_fresh_install_preserves_installer_written_config(resolver, monkeypatch):
    """install.sh writes config.yaml (with a generated installation_id) before
    the wizard ever runs. A plain first-run `hallptz setup` (no marker yet) must
    still pick that up, or apply_files() would overwrite the stable ID."""
    from application.provisioning_service import ProvisioningAnswers, ProvisioningService
    from config.writer import write_full_config
    svc = ProvisioningService()
    seeded = ProvisioningAnswers(installation_id="HALLPTZ-2026-ABCD1234")
    write_full_config(svc.to_app_settings(seeded), resolver.config_dir / "config.yaml")
    assert not resolver.provisioned_marker_file.exists()  # fresh install, pre-wizard

    seen = {}
    monkeypatch.setattr(
        setup_launcher, "run_setup_wizard",
        lambda answers=None, require_admin_auth=False: seen.update(answers=answers) or 0,
    )
    from runtime.cli import cmd_setup
    assert cmd_setup(_Args()) == 0
    assert seen["answers"] is not None
    assert seen["answers"].installation_id == "HALLPTZ-2026-ABCD1234"


def test_cmd_setup_force_launches_even_when_provisioned(resolver, monkeypatch):
    resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")
    monkeypatch.setattr(setup_launcher, "run_setup_wizard", lambda answers=None, require_admin_auth=False: 0)

    args = _Args()
    args.force = True
    from runtime.cli import cmd_setup
    assert cmd_setup(args) == 0


def test_cmd_setup_repair_prefills_from_existing_config(resolver, monkeypatch, capsys):
    """--force on a provisioned install pre-fills answers from config.yaml."""
    from application.provisioning_service import ProvisioningAnswers, ProvisioningService
    from config.writer import write_full_config
    # Write just config.yaml + marker — load_existing_answers reads config only,
    # never the secrets, so we avoid touching secret_manager's paths here.
    svc = ProvisioningService()
    original = ProvisioningAnswers(site_name="Repaired Venue", site_contact="Local IT")
    write_full_config(svc.to_app_settings(original), resolver.config_dir / "config.yaml")
    resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")

    seen = {}
    monkeypatch.setattr(
        setup_launcher, "run_setup_wizard",
        lambda answers=None, require_admin_auth=False: seen.update(
            answers=answers, require_admin_auth=require_admin_auth
        ) or 0,
    )
    args = _Args()
    args.force = True
    from runtime.cli import cmd_setup
    rc = cmd_setup(args)

    assert rc == 0
    assert seen["answers"] is not None
    assert seen["answers"].site_name == "Repaired Venue"
    # Passwords are not recoverable from secrets — operator re-confirms them.
    assert seen["answers"].entry_password == ""
    assert "Repair mode" in capsys.readouterr().out
    # Reconfiguring an already-provisioned install must require admin auth —
    # desktop-session access to the wizard user alone is not authorization.
    assert seen["require_admin_auth"] is True


def test_cmd_setup_fresh_install_does_not_require_admin_auth(resolver, monkeypatch):
    """A fresh (unprovisioned) install has nothing to protect yet — the admin
    sign-in gate must not apply there."""
    seen = {}
    monkeypatch.setattr(
        setup_launcher, "run_setup_wizard",
        lambda answers=None, require_admin_auth=False: seen.update(
            require_admin_auth=require_admin_auth
        ) or 0,
    )
    from runtime.cli import cmd_setup
    assert cmd_setup(_Args()) == 0
    assert seen["require_admin_auth"] is False


def test_cmd_setup_repair_refuses_when_config_unreadable(resolver, monkeypatch, capsys):
    """--force on a provisioned install with a config.yaml that exists but
    fails to load must refuse to open the wizard — opening it anyway would
    pre-fill wizard defaults and a save would silently overwrite the real
    cameras/ATEM/network settings. See PR #867 review."""
    resolver.config_dir.mkdir(parents=True, exist_ok=True)
    (resolver.config_dir / "config.yaml").write_text("not: valid: yaml: [", encoding="utf-8")
    resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")

    def _boom(**_):
        raise AssertionError("wizard must not open when Repair config is unreadable")

    monkeypatch.setattr(setup_launcher, "run_setup_wizard", _boom)
    args = _Args()
    args.force = True
    from runtime.cli import cmd_setup
    rc = cmd_setup(args)

    assert rc == 1
    out = capsys.readouterr().out
    assert "could not be loaded" in out
    assert "hallptz doctor" in out


def test_cmd_setup_fresh_install_still_opens_with_unreadable_config(resolver, monkeypatch):
    """Not yet provisioned — even with a corrupt config.yaml on disk, there is
    no working install to silently overwrite, so the wizard still opens with
    defaults rather than refusing (only the provisioned/Repair case aborts)."""
    resolver.config_dir.mkdir(parents=True, exist_ok=True)
    (resolver.config_dir / "config.yaml").write_text("not: valid: yaml: [", encoding="utf-8")
    assert not resolver.provisioned_marker_file.exists()

    seen = {}
    monkeypatch.setattr(
        setup_launcher, "run_setup_wizard",
        lambda answers=None, require_admin_auth=False: seen.update(answers=answers) or 0,
    )
    from runtime.cli import cmd_setup
    rc = cmd_setup(_Args())
    assert rc == 0
    assert seen["answers"] is None
