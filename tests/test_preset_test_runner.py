# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for PresetTestRunner — no real hardware, no Qt."""
import threading
import time
from application.preset_test_models import (
    PresetTestItem,
    STATUS_OK,
    STATUS_WARNING,
)
from application.preset_test_runner import PresetTestRunner


def _item(label, preset=None, enabled=True, has_verified_ptz=True):
    return PresetTestItem(
        item_id=f"seat_{label}",
        label=str(label),
        camera_role="comments",
        camera_index=2,
        preset=preset if preset is not None else int(label),
        enabled=enabled,
        has_verified_ptz=has_verified_ptz,
    )


def _resolve(_preset_number):
    return "127.0.0.1", "81"


def _make_runner(items, send_fn=None, delay=0.0):
    send = send_fn if send_fn is not None else (lambda ip, cam_id, preset_hex: True)
    return PresetTestRunner(items, send, _resolve, delay_seconds=delay)


def _collect(runner, timeout=3.0):
    """Run the runner and collect all callback events, returning the summary."""
    done = threading.Event()
    summary_cell: list = [None]

    def on_finished(s):
        summary_cell[0] = s
        done.set()

    def on_cancelled(s):
        summary_cell[0] = s
        done.set()

    runner.on_finished = on_finished
    runner.on_cancelled = on_cancelled
    runner.start()
    done.wait(timeout=timeout)
    return summary_cell[0]


# ── Empty list ─────────────────────────────────────────────────────────────

def test_empty_list():
    runner = _make_runner([])
    summary = _collect(runner)
    assert summary is not None
    assert summary.total == 0
    assert summary.ok == 0
    assert not summary.cancelled


# ── All valid ──────────────────────────────────────────────────────────────

def test_all_ok():
    items = [_item(i) for i in range(1, 4)]
    runner = _make_runner(items)
    summary = _collect(runner)
    assert summary.ok == 3
    assert summary.error == 0
    assert summary.skipped == 0
    assert not summary.cancelled


# ── Missing preset (enabled=False) ────────────────────────────────────────

def test_missing_preset_skipped():
    items = [_item(1, preset=None, enabled=False)]
    runner = _make_runner(items)
    summary = _collect(runner)
    assert summary.skipped == 1
    assert summary.ok == 0


# ── Camera command failure ─────────────────────────────────────────────────

def test_camera_failure():
    items = [_item(1)]
    runner = _make_runner(items, send_fn=lambda ip, cam_id, preset_hex: False)
    summary = _collect(runner)
    assert summary.error == 1
    assert summary.ok == 0


# ── Cancellation mid-run ───────────────────────────────────────────────────

def test_cancel_mid_run():
    items = [_item(i) for i in range(1, 20)]

    done = threading.Event()
    summary_cell: list = [None]
    started_cell: list = [0]

    def on_item_started(item, idx, total):
        started_cell[0] = idx

    def on_cancelled(s):
        summary_cell[0] = s
        done.set()

    # Use a minimal delay so cancel lands during the run.
    runner = _make_runner(items, delay=0.05)
    runner.on_item_started = on_item_started
    runner.on_cancelled = on_cancelled

    runner.start()
    time.sleep(0.08)   # let at least one item start
    runner.cancel()
    done.wait(timeout=3.0)

    summary = summary_cell[0]
    assert summary is not None
    assert summary.cancelled
    assert summary.total < len(items)


# ── Summary counts match results ──────────────────────────────────────────

def test_summary_counts_match_results():
    calls = iter([True, False, True])

    def send(ip, cam_id, preset_hex):
        return next(calls, True)

    items = [_item(i, preset=i) for i in [4, 5, 6]]
    runner = _make_runner(items, send_fn=send)
    summary = _collect(runner)

    assert summary.ok == 2
    assert summary.error == 1
    assert len(summary.results) == 3


# ── Callback ordering ─────────────────────────────────────────────────────

def test_callback_ordering():
    events = []

    items = [_item(i) for i in range(1, 3)]
    runner = _make_runner(items)
    runner.on_started      = lambda total: events.append(('started', total))
    runner.on_item_started = lambda item, idx, total: events.append(('item_started', idx))
    runner.on_item_result  = lambda result: events.append(('item_result', result.status))
    runner.on_finished     = lambda summary: events.append(('finished',))

    done = threading.Event()
    original_finished = runner.on_finished

    def _finished(s):
        original_finished(s)
        done.set()

    runner.on_finished = _finished
    runner.start()
    done.wait(timeout=3.0)

    assert events[0] == ('started', 2)
    assert events[1] == ('item_started', 0)
    assert events[2] == ('item_result', STATUS_OK)
    assert events[3] == ('item_started', 1)
    assert events[4] == ('item_result', STATUS_OK)
    assert events[5] == ('finished',)


# ── PTZ metadata tri-state (issue #711) ───────────────────────────────────

def test_ok_when_command_succeeds_and_ptz_verified():
    items = [_item(4, has_verified_ptz=True)]
    runner = _make_runner(items)
    summary = _collect(runner)
    assert summary.ok == 1
    assert summary.warning == 0


def test_warning_when_command_succeeds_but_no_ptz_metadata():
    items = [_item(4, has_verified_ptz=None)]
    runner = _make_runner(items)
    summary = _collect(runner)
    assert summary.warning == 1
    assert summary.ok == 0
    assert summary.error == 0
    assert summary.results[0].status == STATUS_WARNING


def test_warning_when_has_verified_ptz_false():
    items = [_item(4, has_verified_ptz=False)]
    runner = _make_runner(items)
    summary = _collect(runner)
    assert summary.warning == 1


def test_error_still_red_regardless_of_ptz_metadata():
    items = [_item(4, has_verified_ptz=True)]
    runner = _make_runner(items, send_fn=lambda ip, cam_id, hex: False)
    summary = _collect(runner)
    assert summary.error == 1
    assert summary.warning == 0
    assert summary.ok == 0


def test_mixed_ok_warning_error():
    """Items with PTZ=True → OK; PTZ=None → WARNING; send fails → ERROR."""
    call_results = iter([True, True, False])

    def send(ip, cam_id, preset_hex):
        return next(call_results)

    items = [
        _item(4, has_verified_ptz=True),
        _item(5, has_verified_ptz=None),
        _item(6, has_verified_ptz=True),
    ]
    runner = _make_runner(items, send_fn=send)
    summary = _collect(runner)
    assert summary.ok == 1
    assert summary.warning == 1
    assert summary.error == 1


# ── assigned_name field (issue #710) ──────────────────────────────────────

def test_assigned_name_preserved_in_result():
    item = PresetTestItem(
        item_id="seat_004",
        label="4",
        camera_role="comments",
        camera_index=2,
        preset=4,
        enabled=True,
        assigned_name="Mary Smith",
        has_verified_ptz=True,
    )
    runner = _make_runner([item])
    summary = _collect(runner)
    assert summary.results[0].item.assigned_name == "Mary Smith"

