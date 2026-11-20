# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Offline CI retry contract. No sudo, package manager or network is used."""
from pathlib import Path
import os
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/ci/install_qt.sh'


def run_fake(tmp_path, outcomes, args=('libegl1', 'libgl1')):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    def command(name, body):
        path = bindir / name
        path.write_text('#!/usr/bin/env bash\nset -eu\n' + body)
        path.chmod(0o700)
    # Consume one supplied return code per apt invocation.
    command('sudo', '''
    printf '%s\\n' "$*" >> "$RECORD"
    i=$(cat "$COUNTER")
    code=$(sed -n "$((i+1))p" "$OUTCOMES")
    echo $((i+1)) > "$COUNTER"
    exit "${code:-0}"
    ''')
    command('sleep', 'echo "sleep $*" >> "$RECORD"\n')
    command('timeout', 'echo "timeout $1 $2" >> "$RECORD"\nshift 2\nexec "$@"\n')
    counter, codes, record = [tmp_path / n for n in ('counter', 'codes', 'record')]
    counter.write_text('0')
    codes.write_text('\n'.join(map(str, outcomes)) + '\n')
    env = dict(os.environ, PATH=str(bindir) + os.pathsep + os.environ['PATH'],
               COUNTER=str(counter), OUTCOMES=str(codes), RECORD=str(record))
    result = subprocess.run(['bash', str(SCRIPT), *args], env=env, capture_output=True, timeout=5)
    return result.returncode, record.read_text() if record.exists() else ''


def test_first_attempt_success(tmp_path):
    code, log = run_fake(tmp_path, [0, 0])
    assert code == 0
    assert log.count('timeout --kill-after=5s 60s') == 1
    assert 'APT::Update::Error-Mode=any' in log
    assert 'install -y --no-install-recommends libegl1 libgl1' in log
    assert 'sleep' not in log


def test_update_failure_does_not_install_stale_indices(tmp_path):
    code, log = run_fake(tmp_path, [100, 0, 0])
    assert code == 0
    assert log.count(' update') == 2
    assert log.count(' install') == 1
    assert 'sleep 5' in log


def test_install_failure_retries_complete_pair(tmp_path):
    code, log = run_fake(tmp_path, [0, 100, 0, 0])
    assert code == 0
    assert log.count(' update') == log.count(' install') == 2


def test_final_failure_stays_failure_with_three_attempt_limit(tmp_path):
    code, log = run_fake(tmp_path, [100, 100, 100])
    assert code == 100
    assert log.count('timeout --kill-after=5s 60s') == 3
    assert 'sleep 5' in log and 'sleep 10' in log
    assert ' install' not in log


def test_empty_package_list_rejected(tmp_path):
    assert run_fake(tmp_path, [], args=())[0] == 2


@pytest.mark.parametrize('workflow', ['tests.yml', 'smoke.yml', 'atem-contract.yml',
                                      'pr-persistence.yml', 'ci.yml', 'release-check.yml'])
def test_qt_steps_share_bounded_helper_without_allow_failure(workflow):
    text = (ROOT / '.github/workflows' / workflow).read_text()
    assert 'bash scripts/ci/install_qt.sh ' in text
    assert 'apt-get' not in text
    assert 'continue-on-error: true' not in text
