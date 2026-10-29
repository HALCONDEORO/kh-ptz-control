#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_cli_gui_mode_awareness.py — diagnostics respect the GUI mode (#885/#887)
#
# `khptz verify-install` used to assume khptz-control.service owns the GUI. Under
# --gui-mode user that service is deliberately disabled, so the old check
# reported "inactive -> sudo systemctl start khptz-control" — advice that would
# launch a SECOND GUI competing for the same cameras. These tests pin the
# corrected behaviour, which is decided entirely by KHPTZ_GUI_MODE in
# /etc/khptz/install-state.env.

from __future__ import annotations

from types import SimpleNamespace

import pytest

from runtime.cli import _installed_gui_mode


class _Resolver:
    def __init__(self, config_dir):
        self.config_dir = config_dir


def _state(tmp_path, contents: str):
    (tmp_path / "install-state.env").write_text(contents, encoding="utf-8")
    return _Resolver(tmp_path)


class TestInstalledGuiMode:
    def test_reads_user_mode(self, tmp_path):
        r = _state(tmp_path, 'KHPTZ_GUI_MODE="user"\n')
        assert _installed_gui_mode(r) == "user"

    def test_reads_system_mode(self, tmp_path):
        r = _state(tmp_path, 'KHPTZ_GUI_MODE="system"\n')
        assert _installed_gui_mode(r) == "system"

    def test_tolerates_unquoted_values(self, tmp_path):
        r = _state(tmp_path, "KHPTZ_GUI_MODE=user\n")
        assert _installed_gui_mode(r) == "user"

    def test_picks_the_key_out_of_a_full_state_file(self, tmp_path):
        r = _state(tmp_path, "\n".join([
            'KHPTZ_INSTALL_MODE="product"',
            'KHPTZ_INSTALLED_VERSION="3.38.3"',
            'KHPTZ_WIZARD_USER="khptz"',
            'KHPTZ_GUI_MODE="user"',
            'KHPTZ_INSTALLED_AT="2026-07-25T00:00:00Z"',
        ]) + "\n")
        assert _installed_gui_mode(r) == "user"

    def test_defaults_to_system_when_the_file_is_absent(self, tmp_path):
        """Installs predating the flag were all system mode."""
        assert _installed_gui_mode(_Resolver(tmp_path)) == "system"

    def test_defaults_to_system_when_the_key_is_absent(self, tmp_path):
        r = _state(tmp_path, 'KHPTZ_WIZARD_USER="khptz"\n')
        assert _installed_gui_mode(r) == "system"

    def test_rejects_an_unrecognised_value(self, tmp_path):
        """A corrupt state file must not invent a third mode."""
        r = _state(tmp_path, 'KHPTZ_GUI_MODE="banana"\n')
        assert _installed_gui_mode(r) == "system"

    def test_survives_an_unreadable_config_dir(self, tmp_path):
        """Diagnostics must never crash on a permission error (#884)."""
        assert _installed_gui_mode(_Resolver(tmp_path / "does-not-exist")) == "system"


class TestVerifyInstallRespectsTheMode:
    """The advice `verify-install` prints must not create a second GUI."""

    @pytest.fixture
    def run_verify(self, tmp_path, monkeypatch, capsys):
        def _run(gui_mode: str, active_state: str):
            import runtime.cli as cli
            import runtime.path_resolver as pr

            (tmp_path / "install-state.env").write_text(
                f'KHPTZ_GUI_MODE="{gui_mode}"\n', encoding="utf-8"
            )

            # cmd_verify_install imports RuntimePathResolver *inside* the
            # function, so the source module is what must be patched. Subclass
            # the real resolver so every other check keeps working and only the
            # config dir (where install-state.env lives) is redirected.
            class _R(pr.RuntimePathResolver):
                @property
                def config_dir(self):
                    return tmp_path

            monkeypatch.setattr(pr, "RuntimePathResolver", _R)

            import subprocess

            def _fake_run(cmd, *a, **k):
                if cmd[:2] == ["systemctl", "is-active"]:
                    return SimpleNamespace(stdout=active_state, returncode=0)
                return SimpleNamespace(stdout="", returncode=1)

            monkeypatch.setattr(subprocess, "run", _fake_run)
            cli.cmd_verify_install(SimpleNamespace(json=False))
            return capsys.readouterr().out

        return _run

    def test_user_mode_never_advises_starting_the_system_service(self, run_verify):
        out = run_verify("user", "inactive")
        assert "sudo systemctl start khptz-control" not in out

    def test_user_mode_flags_an_active_system_service(self, run_verify):
        out = run_verify("user", "active")
        assert "disable" in out

    def test_system_mode_still_advises_starting_it(self, run_verify):
        out = run_verify("system", "inactive")
        assert "systemctl start khptz-control" in out
