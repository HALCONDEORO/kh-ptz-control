#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Dynamic regression tests for the install.sh pre-update backup block.

The static tests in test_installer_static.py assert the block's shape; these
tests EXECUTE the extracted block against stub install trees to prove the
behavior that matters:

- run from the NEW checkout (the operator's normal cwd), the backup must be
  produced by the OLD, still-installed tree — `python3 -m` puts cwd ahead of
  PYTHONPATH, so without the neutral-cd guard the candidate code would run;
- a failing backup aborts the installer before the deploy stage runs;
- first installs and --skip-pre-update-backup do not attempt a backup.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT  = Path(__file__).parent.parent
INSTALL_SH = REPO_ROOT / "runtime" / "installer" / "install.sh"

_PREFIX = """set -euo pipefail
info() { echo "$*"; }
warn() { echo "$*" >&2; }
error() { echo "$*" >&2; exit 1; }
sanitize_ref() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }
runuser() { shift 3; "$@"; }
install() { mkdir -p "${@: -1}"; }
"""

_STUB_CLI = (
    "import os, sys, pathlib\n"
    "print({label!r})\n"
    'if os.environ.get("FAKE_BACKUP_FAIL"): sys.exit(23)\n'
    "pathlib.Path(sys.argv[-1]).write_text({label!r})\n"
)


def _extract_backup_block() -> str:
    sh = INSTALL_SH.read_text(encoding="utf-8")
    start = sh.index('_state_file="${CONFIG_DIR}/install-state.env"')
    end = sh.index("\nfi\n", start)
    return sh[start:end + 4]


def _make_tree(root: Path, label: str) -> Path:
    tree = root / label
    (tree / "runtime").mkdir(parents=True)
    (tree / "runtime" / "__init__.py").write_text("")
    (tree / "runtime" / "cli.py").write_text(_STUB_CLI.format(label=label))
    return tree


def _run_block(tmp_path: Path, *, cwd: Path, state: bool, skip: bool,
               fail: bool) -> subprocess.CompletedProcess:
    old = _make_tree(tmp_path, "OLD_INSTALLED")
    new = _make_tree(tmp_path, "NEW_CANDIDATE")
    config = tmp_path / "config"
    backup = tmp_path / "backup"
    config.mkdir()
    backup.mkdir()
    if state:
        (config / "install-state.env").write_text("KHPTZ_INSTALLED_REF=v1.2.2\n")
    assignments = "\n".join(f"{k}={json.dumps(str(v))}" for k, v in {
        "DEV_MODE": "false", "REPO_ROOT": new, "INSTALL_DIR": old,
        "CONFIG_DIR": config, "DATA_DIR": tmp_path / "data",
        "LOG_DIR": tmp_path / "log", "BACKUP_DIR": backup,
        "APP_USER": "synthetic", "PYTHON_BIN": "/usr/bin/python3",
        "SKIP_PRE_UPDATE_BACKUP": "true" if skip else "false",
    }.items())
    script = _PREFIX + assignments + "\n" + _extract_backup_block() + "\necho DEPLOY_REACHED\n"
    env = dict(os.environ)
    if fail:
        env["FAKE_BACKUP_FAIL"] = "1"
    return subprocess.run(["bash", "-c", script], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=30)


class TestPreUpdateBackupDynamic:

    def test_backup_uses_installed_tree_from_new_checkout_cwd(self, tmp_path):
        """Regression: cwd (new checkout) must NOT shadow the installed tree."""
        proc = _run_block(tmp_path, cwd=tmp_path / "NEW_CANDIDATE",
                          state=True, skip=False, fail=False)
        assert proc.returncode == 0, proc.stderr
        assert "DEPLOY_REACHED" in proc.stdout
        archives = list((tmp_path / "backup").iterdir())
        assert len(archives) == 1
        assert archives[0].name.startswith("pre_update_v1.2.2_")
        assert archives[0].read_text() == "OLD_INSTALLED"
        assert "NEW_CANDIDATE" not in proc.stdout

    def test_failed_backup_aborts_before_deploy(self, tmp_path):
        proc = _run_block(tmp_path, cwd=tmp_path / "NEW_CANDIDATE",
                          state=True, skip=False, fail=True)
        assert proc.returncode != 0
        assert "DEPLOY_REACHED" not in proc.stdout
        assert "Pre-update backup failed" in proc.stderr
        assert list((tmp_path / "backup").iterdir()) == []

    def test_first_install_takes_no_backup(self, tmp_path):
        proc = _run_block(tmp_path, cwd=tmp_path / "NEW_CANDIDATE",
                          state=False, skip=False, fail=False)
        assert proc.returncode == 0, proc.stderr
        assert "DEPLOY_REACHED" in proc.stdout
        assert list((tmp_path / "backup").iterdir()) == []

    def test_skip_flag_takes_no_backup(self, tmp_path):
        proc = _run_block(tmp_path, cwd=tmp_path / "NEW_CANDIDATE",
                          state=True, skip=True, fail=False)
        assert proc.returncode == 0, proc.stderr
        assert "DEPLOY_REACHED" in proc.stdout
        assert "Skipping pre-update backup" in proc.stderr
        assert list((tmp_path / "backup").iterdir()) == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
