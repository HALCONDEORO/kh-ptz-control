"""Overlapping saves must never publish or remove another writer's temp file."""
import threading

import pytest

from core import atomic_write


@pytest.mark.parametrize("second_fails", [False, True])
def test_overlapping_writers_keep_independent_temporary_files(tmp_path, monkeypatch, second_fails):
    destination = tmp_path / "config.yaml"
    destination.write_bytes(b"original")
    first_ready = threading.Event()
    first_resume = threading.Event()
    original_replace = atomic_write.os.replace
    results = []
    published = []

    def replace(source, target):
        if threading.current_thread().name == "first-save":
            first_ready.set()
            assert first_resume.wait(5), "second save never completed"
        elif second_fails:
            raise OSError("synthetic second-writer failure")
        published.append(source.read_bytes())
        original_replace(source, target)

    def save(payload):
        try:
            # Exercise the underlying temporary-file ownership invariant.
            # The public helper now serializes publication+receipt per path;
            # its ordering is tested in test_persistence_status.py.
            atomic_write._write_bytes_atomic(destination, payload, mode=0o600)
            results.append((payload, "ok"))
        except OSError:
            results.append((payload, "error"))

    monkeypatch.setattr(atomic_write.os, "replace", replace)
    first = threading.Thread(target=save, args=(b"first complete",), name="first-save")
    first.start()
    try:
        assert first_ready.wait(5)
        save(b"second complete")
    finally:
        first_resume.set()
        first.join(5)
    assert not first.is_alive()
    assert (b"first complete", "ok") in results
    assert (b"second complete", "error" if second_fails else "ok") in results
    assert destination.read_bytes() == b"first complete"
    assert published == ([b"first complete"] if second_fails else
                         [b"second complete", b"first complete"])
    assert list(tmp_path.glob("*.tmp")) == []
