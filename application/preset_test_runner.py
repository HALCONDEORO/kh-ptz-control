#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# application/preset_test_runner.py — Preset test runner, independent of PyQt.
#
# Callbacks are invoked from the worker thread; callers must marshal to the UI
# thread themselves (e.g. QTimer.singleShot(0, ...) or Qt signals).

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from application.preset_test_models import (
    PresetTestItem,
    PresetTestResult,
    PresetTestSummary,
    STATUS_OK,
    STATUS_WARNING,
    STATUS_ERROR,
    STATUS_SKIPPED,
    STATUS_CANCELLED,
)

logger = logging.getLogger(__name__)

# Seconds between preset calls; long enough for the camera to accept and settle.
DEFAULT_DELAY_SECONDS = 1.8

SendFn = Callable[[str, str, str], bool]  # (ip, cam_id, preset_hex) -> success


class PresetTestRunner:
    """
    Iterates through a list of PresetTestItems, calling each preset in sequence.

    Usage::

        runner = PresetTestRunner(items, send_fn, resolve_fn)
        runner.on_started    = lambda total: ...
        runner.on_item_started = lambda item, idx, total: ...
        runner.on_item_result  = lambda result: ...
        runner.on_finished   = lambda summary: ...
        runner.on_cancelled  = lambda summary: ...
        runner.on_highlight  = lambda item, state: ...
        runner.start()
        # later...
        runner.cancel()

    The runner is single-use — create a new instance for each test run.
    """

    def __init__(
        self,
        items: list[PresetTestItem],
        send_fn: SendFn,
        resolve_fn: Callable[[int], tuple[str, str]],  # preset_number -> (ip, cam_id)
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
    ) -> None:
        self._items = list(items)
        self._send_fn = send_fn
        self._resolve_fn = resolve_fn
        self._delay = delay_seconds
        self._cancel_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Public callbacks — assign before calling start().
        self.on_started:      Optional[Callable[[int], None]] = None
        self.on_item_started: Optional[Callable[[PresetTestItem, int, int], None]] = None
        self.on_item_result:  Optional[Callable[[PresetTestResult], None]] = None
        self.on_finished:     Optional[Callable[[PresetTestSummary], None]] = None
        self.on_cancelled:    Optional[Callable[[PresetTestSummary], None]] = None
        self.on_highlight:    Optional[Callable[[PresetTestItem, str], None]] = None

    # ── Public API ────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.warning("PresetTestRunner: already running — start() ignored")
            return
        self._cancel_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="PresetTestRunner")
        self._thread.start()

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── Internal ──────────────────────────────────────────────────────────

    def _cb(self, fn, *args):
        if fn is not None:
            try:
                fn(*args)
            except Exception:  # noqa: BLE001
                logger.exception("PresetTestRunner: callback error")

    def _run(self) -> None:
        total = len(self._items)
        self._cb(self.on_started, total)

        results: list[PresetTestResult] = []
        counts = {STATUS_OK: 0, STATUS_ERROR: 0, "WARNING": 0, STATUS_SKIPPED: 0}

        for idx, item in enumerate(self._items):
            if self._cancel_event.is_set():
                result = PresetTestResult(
                    item=item, status=STATUS_CANCELLED, message="Cancelled by user"
                )
                results.append(result)
                break

            self._cb(self.on_item_started, item, idx, total)
            self._cb(self.on_highlight, item, "active")

            result = self._test_item(item)
            results.append(result)

            status = result.status
            if status in counts:
                counts[status] += 1

            self._cb(self.on_highlight, item, status.lower())
            self._cb(self.on_item_result, result)

            if self._cancel_event.is_set():
                break

            if idx < total - 1:
                self._cancel_event.wait(timeout=self._delay)

        cancelled = self._cancel_event.is_set()
        summary = PresetTestSummary(
            total=len(results),
            ok=counts[STATUS_OK],
            warning=counts["WARNING"],
            error=counts[STATUS_ERROR],
            skipped=counts[STATUS_SKIPPED],
            cancelled=cancelled,
            results=results,
        )

        if cancelled:
            self._cb(self.on_cancelled, summary)
        else:
            self._cb(self.on_finished, summary)

    def _test_item(self, item: PresetTestItem) -> PresetTestResult:
        if not item.enabled or item.preset is None:
            return PresetTestResult(
                item=item, status=STATUS_SKIPPED, message="No preset assigned"
            )

        try:
            ip, cam_id = self._resolve_fn(item.preset)
        except Exception as exc:  # noqa: BLE001
            return PresetTestResult(
                item=item, status=STATUS_ERROR, message=f"Routing error: {exc}"
            )

        from config import PRESET_MAP
        preset_hex = PRESET_MAP.get(item.preset)
        if not preset_hex:
            return PresetTestResult(
                item=item, status=STATUS_SKIPPED, message="Preset not in PRESET_MAP"
            )

        t0 = time.monotonic()
        try:
            ok = self._send_fn(ip, cam_id, preset_hex)
        except Exception as exc:  # noqa: BLE001
            return PresetTestResult(
                item=item, status=STATUS_ERROR, message=f"Send error: {exc}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        duration_ms = int((time.monotonic() - t0) * 1000)
        if not ok:
            return PresetTestResult(
                item=item, status=STATUS_ERROR, message="Camera unavailable or timeout",
                duration_ms=duration_ms,
            )
        if item.has_verified_ptz is True:
            return PresetTestResult(
                item=item, status=STATUS_OK, message="Command accepted",
                duration_ms=duration_ms,
            )
        return PresetTestResult(
            item=item, status=STATUS_WARNING,
            message="Command accepted — no PTZ calibration metadata",
            duration_ms=duration_ms,
        )
