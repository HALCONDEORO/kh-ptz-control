# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Abrupt child-process exit at write boundaries, not real power-loss proof.

The child terminates without Python cleanup. The host filesystem stays online,
so these tests verify atomic publication/recovery shape, NOT physical flushes,
SD-controller caches, filesystem crash recovery or Pi acceptance.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHILD = r'''
import os, stat, sys
from pathlib import Path
root, kind, phase = sys.argv[1:]
sys.path.insert(0, root)
from core.atomic_write import write_bytes_atomic
from core.json_io import save_json
path = Path(os.environ["KH_TEST_DEST"])
real_sync, real_replace, real_write = os.fsync, os.replace, os.write

def stop():
    os._exit(91)

def sync(fd):
    directory = stat.S_ISDIR(os.fstat(fd).st_mode)
    boundary = "directory" if directory else "file"
    if phase == "before_" + boundary + "_sync":
        stop()
    real_sync(fd)
    if phase == "after_" + boundary + "_sync":
        stop()

def replace(src, dest):
    if phase == "before_replace":
        stop()
    real_replace(src, dest)
    if phase == "after_replace":
        stop()

os.fsync, os.replace = sync, replace
if kind == "json":
    assert save_json(path, {"state": "new", "items": list(range(400))})
else:
    write_bytes_atomic(path, b"new complete payload" * 4096)
'''


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory-sync boundaries")
@pytest.mark.parametrize("kind", ["json", "bytes"])
@pytest.mark.parametrize("phase,published", [
    ("before_file_sync", False), ("after_file_sync", False),
    ("before_replace", False), ("after_replace", True),
    ("before_directory_sync", True), ("after_directory_sync", True),
])
def test_abrupt_exit_leaves_old_or_complete_new_file(tmp_path, kind, phase, published):
    dest = tmp_path / "state.json"
    old = b'{"state": "old"}' if kind == "json" else b"old complete payload"
    dest.write_bytes(old)
    env = dict(os.environ, KH_TEST_DEST=str(dest))
    result = subprocess.run([sys.executable, "-I", "-B", "-c", CHILD,
                             str(ROOT), kind, phase], env=env, timeout=10,
                            capture_output=True)
    assert result.returncode == 91, "child must reach the intended interruption boundary"
    actual = dest.read_bytes()
    if not published:
        assert actual == old
    elif kind == "json":
        assert json.loads(actual) == {"state": "new", "items": list(range(400))}
    else:
        assert actual == b"new complete payload" * 4096
    if kind == "json":
        assert json.loads(dest.with_suffix(".bak").read_bytes()) == {"state": "old"}
    # Private orphan data is possible before replace. Never mistake orphans
    # for the published state, delete them automatically or call this rollback.
    orphans = list(tmp_path.glob("*.tmp")) + list(tmp_path.glob(".tmp_*.json"))
    if published:
        assert not orphans
    for orphan in orphans:
        assert orphan.stat().st_mode & 0o077 == 0
