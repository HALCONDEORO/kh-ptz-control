# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Actual sync failures must never be reported as durable saves."""
import errno
import os
import stat
from unittest.mock import patch

import pytest

from core.atomic_write import PublishedButNotDurableError, _fsync_dir, write_bytes_atomic
from core.json_io import save_json


@pytest.mark.parametrize("code", [errno.EIO, errno.ENOSPC])
@pytest.mark.parametrize("kind", ["json", "bytes"])
def test_file_sync_failure_aborts_before_replace(tmp_path, monkeypatch, code, kind):
    dest = tmp_path / "state.json"
    original = b'{"old": true}'
    dest.write_bytes(original)

    def fail_sync(fd):
        raise OSError(code, "injected sync failure")

    monkeypatch.setattr(os, "fsync", fail_sync)
    if kind == "json":
        assert save_json(dest, {"new": True}) is False
    else:
        with pytest.raises(OSError) as caught:
            write_bytes_atomic(dest, b"new")
        assert caught.value.errno == code
        assert not isinstance(caught.value, PublishedButNotDurableError)
    assert dest.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob(".tmp_*"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory sync policy")
@pytest.mark.parametrize("code", [errno.EIO, errno.ENOSPC, errno.EACCES])
@pytest.mark.parametrize("kind", ["json", "bytes"])
def test_directory_sync_failure_is_published_not_success(tmp_path, monkeypatch, caplog, code, kind):
    dest = tmp_path / "state.json"
    dest.write_text('{"old": true}')
    real_sync = os.fsync
    closed_fd = []

    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            closed_fd.append(fd)
            raise OSError(code, "injected directory failure")
        return real_sync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory)
    if kind == "json":
        assert save_json(dest, {"new": True}) is False
        assert '"new": true' in dest.read_text()
        assert "published" in caplog.text and "durability unconfirmed" in caplog.text
    else:
        with pytest.raises(PublishedButNotDurableError) as caught:
            write_bytes_atomic(dest, b"new")
        assert caught.value.errno == code
        assert caught.value.published is True
        assert dest.read_bytes() == b"new"
    assert len(closed_fd) == 1
    with pytest.raises(OSError):
        os.fstat(closed_fd[0])
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob(".tmp_*"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory sync policy")
def test_directory_open_error_is_not_silenced(tmp_path):
    with patch("core.atomic_write.os.open", side_effect=OSError(errno.EIO, "injected")):
        with pytest.raises(OSError) as caught:
            _fsync_dir(tmp_path)
    assert caught.value.errno == errno.EIO


def test_windows_directory_sync_explicitly_unsupported(tmp_path):
    with patch("core.atomic_write.os.name", "nt"), patch("core.atomic_write.os.open") as opened:
        _fsync_dir(tmp_path)
    opened.assert_not_called()
