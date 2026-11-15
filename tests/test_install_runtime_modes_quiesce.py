"""Run real runtime-directory commands, but only against temporary directories."""
from pathlib import Path
import os
import stat
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('guard_ok', [True, False])
def test_runtime_permissions_do_not_change_before_quiesce(tmp_path, guard_ok):
    source = (ROOT / 'runtime/installer/install.sh').read_text()
    lines = source.splitlines()
    # Preserve real command order. Ignore unrelated privileged installer work.
    selected = [line for line in lines if
                ('install -d -m 750 -o' in line and any(
                    f'"${{{name}}}"' in line for name in ('DATA_DIR', 'LOG_DIR', 'BACKUP_DIR')))
                or line.strip() == '_stop_session_guis /run/user']
    # 3 unconditional post-quiesce hardenings + the quiesce call + the guarded
    # pre-backup creation (a no-op here: the harness pre-creates the dirs, and
    # the stub's 2770 check still catches any UNguarded tightening before it).
    assert len(selected) == 5
    dirs = [tmp_path / name for name in ('data', 'log', 'backup')]
    for directory in dirs:
        directory.mkdir()
        directory.chmod(0o2770)
    # Strip only owner/group options: this unprivileged test owns the temp dirs.
    commands = '\n'.join(selected).replace('-o "${APP_USER}" -g "${APP_USER}" ', '')
    script = '''set -euo pipefail
_stop_session_guis() {
    for directory in "$DATA_DIR" "$LOG_DIR" "$BACKUP_DIR"; do
        [[ "$(stat -c %a "$directory")" == 2770 ]] || exit 99
    done
    [[ "$GUARD_OK" == true ]] || exit 7
}
'''+commands
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
        env=dict(os.environ, DATA_DIR=str(dirs[0]), LOG_DIR=str(dirs[1]),
                 BACKUP_DIR=str(dirs[2]), GUARD_OK=str(guard_ok).lower()))
    assert result.returncode == (0 if guard_ok else 7), result.stderr
    for directory in dirs:
        mode = stat.S_IMODE(directory.stat().st_mode)
        assert bool(mode & stat.S_IWGRP) is (not guard_ok)
