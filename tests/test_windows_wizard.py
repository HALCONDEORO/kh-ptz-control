# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from __future__ import annotations

from tools.windows_wizard import WIZARD_NAME, WIZARD_VERSION
from tools.windows_wizard.paths import ensure_state_dirs
from tools.windows_wizard.wizard_app import main


def test_wizard_version(capsys):
    assert main(["--version"]) == 0
    out = capsys.readouterr().out
    assert WIZARD_NAME in out
    assert WIZARD_VERSION in out


def test_wizard_smoke_creates_local_state(tmp_path, capsys):
    assert main(["--state-dir", str(tmp_path), "--smoke"]) == 0
    out = capsys.readouterr().out

    assert "smoke OK" in out
    assert (tmp_path / "logs" / "wizard.log").exists()
    assert (tmp_path / "settings").is_dir()


def test_ensure_state_dirs(tmp_path):
    state_dir = ensure_state_dirs(tmp_path)

    assert state_dir == tmp_path
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "settings").is_dir()
