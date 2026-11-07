# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Exercise real cleanup code and atomic writers using harmless canaries."""
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from core.atomic_write import write_bytes_atomic


def cleanup_source():
    script = Path(__file__).parents[1] / "scripts/provision_with_rpi_integration.sh"
    return script.read_text().split("secure_remove_request() {", 1)[1].split(
        "<<'PY'\n", 1
    )[1].split("\nPY", 1)[0]


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks and FIFOs")
def test_wrapper_cleanup_does_not_follow_symlink(tmp_path):
    target = tmp_path / "canary"
    target.write_bytes(b"DUMMY-CANARY")
    request = tmp_path / "request.json"
    request.symlink_to(target)
    subprocess.run([sys.executable, "-c", cleanup_source(), str(request)],
                   check=True, timeout=3)
    assert target.read_bytes() == b"DUMMY-CANARY"
    assert not request.is_symlink()


@pytest.mark.skipif(os.name != "posix", reason="POSIX FIFO")
def test_wrapper_cleanup_does_not_block_on_fifo(tmp_path):
    request = tmp_path / "request.json"
    os.mkfifo(request)
    subprocess.run([sys.executable, "-c", cleanup_source(), str(request)],
                   check=True, timeout=1)
    assert not request.exists()


def test_wrapper_cleanup_removes_regular_request(tmp_path):
    request = tmp_path / "request.json"
    request.write_bytes(b"DUMMY-REQUEST")
    subprocess.run([sys.executable, "-c", cleanup_source(), str(request)],
                   check=True, timeout=3)
    assert not request.exists()


def test_two_atomic_writers_do_not_share_a_temporary_file(tmp_path):
    dest = tmp_path / "data.json"
    real_write = os.write
    interleaved = False

    def write_with_second_writer(fd, data):
        nonlocal interleaved
        if not interleaved:
            interleaved = True
            write_bytes_atomic(dest, b"SECOND")
        return real_write(fd, data)

    with patch("core.atomic_write.os.write", write_with_second_writer):
        write_bytes_atomic(dest, b"FIRST")
    assert dest.read_bytes() == b"FIRST"


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink")
def test_planted_legacy_temp_is_not_followed_or_removed(tmp_path):
    dest = tmp_path / "secret.enc"
    canary = tmp_path / "canary"
    canary.write_bytes(b"DUMMY-CANARY")
    planted = dest.with_suffix(dest.suffix + ".tmp")
    planted.symlink_to(canary)
    write_bytes_atomic(dest, b"NEW", mode=0o600)
    assert canary.read_bytes() == b"DUMMY-CANARY"
    assert planted.is_symlink(), "a writer must clean up only its own unique temp"
    assert dest.read_bytes() == b"NEW"


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink")
def test_symlink_raced_before_exclusive_create_is_never_followed(tmp_path):
    dest = tmp_path / "secret.enc"
    canary = tmp_path / "canary"
    canary.write_bytes(b"DUMMY-CANARY")
    real_open = os.open
    planted = []

    def racing_open(path, flags, *args, **kwargs):
        if flags & os.O_CREAT and not planted:
            planted.append(Path(path))
            Path(path).symlink_to(canary)
        return real_open(path, flags, *args, **kwargs)

    with patch("core.atomic_write.os.open", racing_open):
        write_bytes_atomic(dest, b"NEW", mode=0o600)
    assert canary.read_bytes() == b"DUMMY-CANARY"
    assert dest.read_bytes() == b"NEW"
    assert planted[0].is_symlink()


def test_partial_writes_are_completed(tmp_path):
    dest = tmp_path / "data"
    real_write = os.write
    with patch("core.atomic_write.os.write", lambda fd, data: real_write(fd, data[:2])):
        write_bytes_atomic(dest, b"COMPLETE")
    assert dest.read_bytes() == b"COMPLETE"
