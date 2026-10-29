#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_camera_worker_priority_stop.py — CameraWorker priority STOP semantics (#781)
#
# These tests exercise the queue-drain behavior of send_priority() without
# needing a real camera. They inspect the internal queue directly because
# the drain must happen before the worker thread picks up the next command.

from __future__ import annotations



from ptz.visca import CameraWorker, ViscaCommand


# ── Helpers ───────────────────────────────────────────────────────────────────

# Arbitrary VISCA payloads — content does not matter for queue tests.
_MOVE_PAYLOAD  = bytes.fromhex("8101060101010202FF")  # move right
_STOP_PAYLOAD  = bytes.fromhex("8101060100000303FF")  # stop pan/tilt
_ZOOM_PAYLOAD  = bytes.fromhex("810104072400FF")      # zoom tele


def _move_cmd() -> ViscaCommand:
    return ViscaCommand(camera=1, payload=_MOVE_PAYLOAD, coalesce=True)


def _stop_cmd() -> ViscaCommand:
    return ViscaCommand(camera=1, payload=_STOP_PAYLOAD, priority=True)


def _zoom_cmd() -> ViscaCommand:
    return ViscaCommand(camera=1, payload=_ZOOM_PAYLOAD, coalesce=True)


def _make_worker() -> CameraWorker:
    """Create a worker pointed at a non-routable IP — TCP never connects."""
    return CameraWorker("192.0.2.1")  # TEST-NET-1, RFC 5737 — guaranteed unreachable


# ── Queue drain semantics ─────────────────────────────────────────────────────

def test_priority_stop_drains_non_stop_queue():
    """send_priority() must empty the queue before placing STOP.

    Items are inserted directly (bypassing coalesce logic) so the queue
    size is deterministic before the drain.
    """
    w = _make_worker()
    try:
        for _ in range(3):
            w._queue.put_nowait(ViscaCommand(camera=1, payload=_MOVE_PAYLOAD))
        w.send_priority(_stop_cmd())
        assert w._queue.qsize() == 1
    finally:
        w.stop()


def test_priority_stop_bypasses_pending_movement_commands():
    """The command at the head of the queue after send_priority is the STOP."""
    w = _make_worker()
    try:
        w.send(_move_cmd())
        w.send(_move_cmd())
        w.send_priority(_stop_cmd())

        with w._queue.mutex:
            head = w._queue.queue[0]

        assert head.priority is True
        assert head.payload == _STOP_PAYLOAD
    finally:
        w.stop()


def test_stop_does_not_allow_old_move_to_run_after_stop():
    """After send_priority, no move commands remain in the queue."""
    w = _make_worker()
    try:
        for _ in range(5):
            w.send(_move_cmd())
        w.send_priority(_stop_cmd())

        with w._queue.mutex:
            pending = list(w._queue.queue)

        non_stop = [c for c in pending if c.payload != _STOP_PAYLOAD]
        assert len(non_stop) == 0, f"Stale move commands still in queue: {non_stop}"
    finally:
        w.stop()


def test_repeated_stop_is_idempotent():
    """Calling send_priority twice must not crash or corrupt worker state."""
    w = _make_worker()
    try:
        w.send(_move_cmd())
        w.send_priority(_stop_cmd())
        w.send_priority(_stop_cmd())
        assert w._queue.qsize() == 1
    finally:
        w.stop()


def test_stop_reports_disconnected_camera_without_crash():
    """send_priority on a worker that has never connected must not raise."""
    w = _make_worker()
    try:
        w.send_priority(_stop_cmd())
        # Worker thread will try to connect and fail gracefully
        assert w._queue.qsize() == 1
    finally:
        w.stop()


# ── stop_all across multiple workers ─────────────────────────────────────────

def test_stop_all_sends_priority_stop_to_all_workers():
    """Two workers both receive their STOP commands after stop_all drain."""
    w1 = _make_worker()
    w2 = _make_worker()
    try:
        w1.send(_move_cmd())
        w2.send(_move_cmd())

        # Simulate stop_all by sending priority STOP to each worker
        w1.send_priority(_stop_cmd())
        w2.send_priority(_stop_cmd())

        # Both queues drained to a single STOP
        assert w1._queue.qsize() == 1
        assert w2._queue.qsize() == 1
    finally:
        w1.stop()
        w2.stop()

