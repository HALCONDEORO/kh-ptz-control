# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
import errno
from pathlib import Path
import pytest
from core.persistence_status import PersistenceStatus
from core.json_io import save_json
from core.atomic_write import write_bytes_atomic


def test_unrelated_success_does_not_clear_failure():
    state = PersistenceStatus()
    state.record(Path("a"), confirmed=False)
    state.record(Path("b"), confirmed=True)
    assert state.snapshot().unresolved_count == 1
    assert state.snapshot().last_confirmed is not None
    state.record(Path("a"), confirmed=True)
    assert state.snapshot().unresolved_count == 0


def test_capacity_cannot_silently_drop_failure():
    state = PersistenceStatus()
    for n in range(129):
        state.record(Path(str(n)), confirmed=False)
    for n in range(129):
        state.record(Path(str(n)), confirmed=True)
    assert state.snapshot().overflow


@pytest.mark.parametrize("kind", ["json", "bytes"])
def test_helper_success_and_failure_are_observed(tmp_path, monkeypatch, kind):
    state = PersistenceStatus()
    monkeypatch.setattr("core.persistence_status.status", state)
    dest = tmp_path / "state.json"
    def write():
        if kind == "json":
            return save_json(dest, {"new": True})
        return write_bytes_atomic(dest, b"new")
    write()
    assert state.snapshot().last_confirmed is not None
    monkeypatch.setattr("os.fsync", lambda fd: (_ for _ in ()).throw(OSError(errno.EIO, "injected")))
    try:
        write()
    except OSError:
        pass
    assert state.snapshot().unresolved_count == 1


def test_same_destination_publication_and_receipt_are_serialized(tmp_path, monkeypatch):
    import threading
    import core.atomic_write as atomic
    state = PersistenceStatus()
    entered, release, b_published = threading.Event(), threading.Event(), threading.Event()
    dest = tmp_path / 'state'
    def record(path, *, confirmed):
        if confirmed:
            entered.set()
            assert release.wait(3)
        state.record(path, confirmed=confirmed)
    def publish(path, data, **kwargs):
        if data == b'B':
            b_published.set()
            raise OSError(errno.EIO, 'injected')
    monkeypatch.setattr('core.persistence_status.status.record', record)
    monkeypatch.setattr(atomic, '_write_bytes_atomic', publish)
    failures = []
    a = threading.Thread(target=lambda: atomic.write_bytes_atomic(dest, b'A'))
    def run_b():
        try:
            atomic.write_bytes_atomic(tmp_path / '.' / 'state', b'B')
        except OSError:
            failures.append(True)
    a.start()
    assert entered.wait(3)
    b = threading.Thread(target=run_b)
    b.start()
    try:
        assert not b_published.wait(0.1)
    finally:
        release.set()
    a.join(3)
    b.join(3)
    assert not a.is_alive() and not b.is_alive()
    assert failures == [True]
    assert state.snapshot().unresolved_count == 1


def test_parent_aliases_share_lock_and_receipt(tmp_path):
    from core.persistence_status import publication_lock
    alias = tmp_path / 'alias'
    real = tmp_path / 'real'
    real.mkdir()
    alias.symlink_to(real, target_is_directory=True)
    assert publication_lock(alias / 'state') is publication_lock(real / 'state')
    state = PersistenceStatus()
    state.record(alias / 'state', confirmed=False)
    state.record(real / 'state', confirmed=True)
    assert state.snapshot().unresolved_count == 0


@pytest.mark.parametrize('kind', ['json', 'bytes'])
def test_observer_failure_does_not_change_success(tmp_path, monkeypatch, kind):
    from core.persistence_status import observer_failed
    monkeypatch.setattr('core.persistence_status.status.record', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('observer')))
    try:
        if kind == 'json':
            assert save_json(tmp_path / 'state', {'a': 1})
        else:
            assert write_bytes_atomic(tmp_path / 'state', b'data') is None
        assert observer_failed.is_set()
    finally:
        observer_failed.clear()


@pytest.mark.parametrize('kind', ['json', 'bytes'])
def test_windows_success_remains_unconfirmed(tmp_path, monkeypatch, kind):
    import types
    import core.atomic_write as atomic
    import core.json_io as json_io
    state = PersistenceStatus()
    monkeypatch.setattr('core.persistence_status.status', state)
    if kind == 'json':
        monkeypatch.setattr(json_io, '_save_json', lambda *a, **k: True)
        monkeypatch.setattr(json_io, 'os', types.SimpleNamespace(name='nt'))
        assert json_io.save_json(tmp_path / 'state', {})
    else:
        monkeypatch.setattr(atomic, '_write_bytes_atomic', lambda *a, **k: None)
        monkeypatch.setattr(atomic, 'os', types.SimpleNamespace(name='nt'))
        atomic.write_bytes_atomic(tmp_path / 'state', b'data')
    assert state.snapshot().last_confirmed is None
    assert state.snapshot().unresolved_count == 1


def test_other_destination_is_not_blocked_by_slow_io(tmp_path, monkeypatch):
    import threading
    import core.atomic_write as atomic
    entered, release, other = threading.Event(), threading.Event(), threading.Event()
    def publish(path, data, **kwargs):
        if data == b'A':
            entered.set()
            assert release.wait(3)
        else:
            other.set()
    monkeypatch.setattr(atomic, '_write_bytes_atomic', publish)
    a = threading.Thread(target=lambda: atomic.write_bytes_atomic(tmp_path / 'a', b'A'))
    a.start()
    assert entered.wait(3)
    b = threading.Thread(target=lambda: atomic.write_bytes_atomic(tmp_path / 'b', b'B'))
    b.start()
    try:
        assert other.wait(2)
    finally:
        release.set()
        a.join(3)
        b.join(3)
    assert not a.is_alive() and not b.is_alive()
