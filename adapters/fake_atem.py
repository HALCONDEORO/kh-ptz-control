#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# adapters/fake_atem.py — Fake ATEM adapter for demo and simulation mode
#
# FakeATEM implements AtemPort without network connections or PyATEMMax.
# It supports the Phase 1 manual command set: Program, Preview, CUT, AUTO,
# test_connection, connect, disconnect.
#
# Debounce policy:
#   Repeated set_program_input() or set_preview_input() calls with the same
#   input_id are ignored (no callback fired).  This mirrors real ATEM event
#   behaviour.
#
# Wiring to Qt (application layer, not here):
#   Use add_program_changed_callback() / add_preview_changed_callback() to
#   receive typed Python callbacks.  No Qt dependency in this adapter.

from __future__ import annotations

import enum
import logging
import threading
import time
from typing import Callable, Optional

from domain.ports import AtemCommandResult, AtemPort, SwitcherStatus

logger = logging.getLogger(__name__)

ProgramChangedCallback    = Callable[[int], None]
PreviewChangedCallback    = Callable[[int], None]
ConnectionChangedCallback = Callable[[bool], None]


class FakeAtemFault(str, enum.Enum):
    """Deterministic fault modes for FakeATEM fault injection (#805)."""
    NONE         = "none"
    DISCONNECTED = "disconnected"   # all commands fail with NOT_CONNECTED
    TIMEOUT      = "timeout"        # commands return timeout error
    REJECT       = "reject"         # commands return REJECTED error


class FakeATEM(AtemPort):
    """
    Deterministic fake ATEM switcher for demo and simulation mode.

    Implements AtemPort (Phase 1):
      connect / disconnect / test_connection
      get_program_input / set_program_input (legacy path)
      get_preview_input / set_preview_input
      cut / auto
      add/remove *_callback for program, preview, connection events

    Thread-safe.  No sockets.  No PyATEMMax dependency.
    """

    def __init__(self, automation_mode: bool = False) -> None:
        self._connected = False
        self._program_input: Optional[int] = None
        self._preview_input: Optional[int] = None
        self._pip_enabled: bool = False
        self._transitioning = False
        self._automation_mode = automation_mode
        self._last_error = ""
        self._last_command_result: Optional[AtemCommandResult] = None
        self._lock = threading.Lock()
        self._fault: FakeAtemFault = FakeAtemFault.NONE

        self._program_callbacks: list[ProgramChangedCallback] = []
        self._preview_callbacks: list[PreviewChangedCallback] = []
        self._connection_callbacks: list[ConnectionChangedCallback] = []

    # ── SwitcherPort / AtemPort: connect / disconnect ─────────────────────────

    def connect(self) -> bool:
        with self._lock:
            already = self._connected
            self._connected = True
            self._last_error = ""
        logger.info("[DEMO] FakeATEM connected")
        if not already:
            self._fire_connection_callbacks(True)
        return True

    def disconnect(self) -> None:
        with self._lock:
            already = self._connected
            self._connected = False
        logger.info("[DEMO] FakeATEM disconnected")
        if already:
            self._fire_connection_callbacks(False)

    def test_connection(self) -> AtemCommandResult:
        t0 = time.monotonic()
        fault_result = self._check_fault("test_connection")
        if fault_result is not None:
            with self._lock:
                self._last_command_result = fault_result
            return fault_result
        with self._lock:
            ok = self._connected
        dur = (time.monotonic() - t0) * 1000
        if ok:
            result = AtemCommandResult.success("test_connection", duration_ms=dur)
        else:
            result = AtemCommandResult.failure(
                "test_connection", "NOT_CONNECTED", "FakeATEM is disconnected"
            )
        with self._lock:
            self._last_command_result = result
        return result

    # ── Program input ─────────────────────────────────────────────────────────

    def get_program_input(self) -> Optional[int]:
        with self._lock:
            return self._program_input

    def set_program_input(self, input_id: int) -> None:
        """Change program input directly (legacy path).  Debounced."""
        with self._lock:
            if self._program_input == input_id:
                return
            self._program_input = input_id
            cbs = list(self._program_callbacks)
        logger.info("[DEMO] FakeATEM program input -> %d", input_id)
        self._fire_callbacks(cbs, input_id)

    # ── Preview input ─────────────────────────────────────────────────────────

    def get_preview_input(self) -> Optional[int]:
        with self._lock:
            return self._preview_input

    def set_preview_input(self, input_id: int) -> AtemCommandResult:
        """Set preview bus input.  Returns failure when disconnected or faulted."""
        t0 = time.monotonic()
        fault_result = self._check_fault("set_preview_input", target=input_id)
        if fault_result is not None:
            with self._lock:
                self._last_command_result = fault_result
            return fault_result
        with self._lock:
            if not self._connected:
                result = AtemCommandResult.failure(
                    "set_preview_input", "NOT_CONNECTED",
                    "FakeATEM is disconnected", target=input_id
                )
                self._last_command_result = result
                return result
            if self._preview_input == input_id:
                result = AtemCommandResult.success(
                    "set_preview_input", target=input_id,
                    duration_ms=(time.monotonic() - t0) * 1000,
                )
                self._last_command_result = result
                return result
            self._preview_input = input_id
            cbs = list(self._preview_callbacks)
        logger.info("[DEMO] FakeATEM preview input -> %d", input_id)
        self._fire_callbacks(cbs, input_id)
        result = AtemCommandResult.success(
            "set_preview_input", target=input_id,
            duration_ms=(time.monotonic() - t0) * 1000,
        )
        with self._lock:
            self._last_command_result = result
        return result

    # ── CUT / AUTO ────────────────────────────────────────────────────────────

    def cut(self) -> AtemCommandResult:
        """Copy preview → program instantly (CUT transition)."""
        t0 = time.monotonic()
        fault_result = self._check_fault("cut")
        if fault_result is not None:
            with self._lock:
                self._last_command_result = fault_result
            return fault_result
        with self._lock:
            if not self._connected:
                result = AtemCommandResult.failure(
                    "cut", "NOT_CONNECTED", "FakeATEM is disconnected"
                )
                self._last_command_result = result
                return result
            preview = self._preview_input
            if preview is None:
                result = AtemCommandResult.failure(
                    "cut", "NO_PREVIEW", "No preview input set"
                )
                self._last_command_result = result
                return result
            old_program = self._program_input
            self._program_input = preview
            prog_cbs = list(self._program_callbacks)
        if old_program != preview:
            logger.info("[DEMO] FakeATEM CUT: preview %d -> program", preview)
            self._fire_callbacks(prog_cbs, preview)
        result = AtemCommandResult.success(
            "cut", target=preview,
            duration_ms=(time.monotonic() - t0) * 1000,
        )
        with self._lock:
            self._last_command_result = result
        return result

    def auto(self) -> AtemCommandResult:
        """AUTO transition: preview → program with transitioning flag."""
        t0 = time.monotonic()
        fault_result = self._check_fault("auto")
        if fault_result is not None:
            with self._lock:
                self._last_command_result = fault_result
            return fault_result
        with self._lock:
            if not self._connected:
                result = AtemCommandResult.failure(
                    "auto", "NOT_CONNECTED", "FakeATEM is disconnected"
                )
                self._last_command_result = result
                return result
            preview = self._preview_input
            if preview is None:
                result = AtemCommandResult.failure(
                    "auto", "NO_PREVIEW", "No preview input set"
                )
                self._last_command_result = result
                return result
            self._transitioning = True
            old_program = self._program_input
            self._program_input = preview
            self._transitioning = False
            prog_cbs = list(self._program_callbacks)
        if old_program != preview:
            logger.info("[DEMO] FakeATEM AUTO: preview %d -> program", preview)
            self._fire_callbacks(prog_cbs, preview)
        result = AtemCommandResult.success(
            "auto", target=preview,
            duration_ms=(time.monotonic() - t0) * 1000,
        )
        with self._lock:
            self._last_command_result = result
        return result

    # ── PiP ───────────────────────────────────────────────────────────────────

    def set_pip_enabled(self, enabled: bool) -> AtemCommandResult:
        """Enable or disable PiP state in the fake switcher."""
        t0 = time.monotonic()
        fault_result = self._check_fault("set_pip_enabled")
        if fault_result is not None:
            with self._lock:
                self._last_command_result = fault_result
            return fault_result
        with self._lock:
            if not self._connected:
                result = AtemCommandResult.failure(
                    "set_pip_enabled", "NOT_CONNECTED", "FakeATEM is disconnected"
                )
                self._last_command_result = result
                return result
            self._pip_enabled = enabled
        logger.info("[DEMO] FakeATEM PiP %s", "ON" if enabled else "OFF")
        result = AtemCommandResult.success(
            "set_pip_enabled",
            duration_ms=(time.monotonic() - t0) * 1000,
        )
        with self._lock:
            self._last_command_result = result
        return result

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self) -> SwitcherStatus:
        with self._lock:
            return SwitcherStatus(
                adapter_type="fake",
                connected=self._connected,
                program_input=self._program_input,
                preview_input=self._preview_input,
                transitioning=self._transitioning,
                automation_mode=self._automation_mode,
                last_error=self._last_error,
            )

    # ── Callback registration ─────────────────────────────────────────────────

    def add_program_changed_callback(self, cb: ProgramChangedCallback) -> None:
        with self._lock:
            if not any(c == cb for c in self._program_callbacks):
                self._program_callbacks.append(cb)

    def remove_program_changed_callback(self, cb: ProgramChangedCallback) -> None:
        with self._lock:
            self._program_callbacks = [c for c in self._program_callbacks if c != cb]

    def add_preview_changed_callback(self, cb: PreviewChangedCallback) -> None:
        with self._lock:
            if not any(c == cb for c in self._preview_callbacks):
                self._preview_callbacks.append(cb)

    def remove_preview_changed_callback(self, cb: PreviewChangedCallback) -> None:
        with self._lock:
            self._preview_callbacks = [c for c in self._preview_callbacks if c != cb]

    def add_connection_changed_callback(self, cb: ConnectionChangedCallback) -> None:
        with self._lock:
            if not any(c == cb for c in self._connection_callbacks):
                self._connection_callbacks.append(cb)

    def remove_connection_changed_callback(self, cb: ConnectionChangedCallback) -> None:
        with self._lock:
            self._connection_callbacks = [c for c in self._connection_callbacks if c != cb]

    # ── State control (demo UI and test helpers) ──────────────────────────────

    def set_automation_mode(self, enabled: bool) -> None:
        with self._lock:
            self._automation_mode = enabled
        logger.info("[DEMO] FakeATEM automation_mode=%s", enabled)

    @property
    def last_command_result(self) -> Optional[AtemCommandResult]:
        with self._lock:
            return self._last_command_result

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _fire_callbacks(callbacks: list, value) -> None:
        for cb in callbacks:
            try:
                cb(value)
            except Exception as exc:
                logger.error("[DEMO] FakeATEM callback error: %s", exc, exc_info=True)

    def _fire_connection_callbacks(self, connected: bool) -> None:
        with self._lock:
            cbs = list(self._connection_callbacks)
        for cb in cbs:
            try:
                cb(connected)
            except Exception as exc:
                logger.warning("[DEMO] FakeATEM connection callback error: %s", exc)

    def _check_fault(self, command: str, target=None) -> "AtemCommandResult | None":
        """Return a failure result if a fault is active, else None."""
        with self._lock:
            fault = self._fault
        if fault == FakeAtemFault.NONE:
            return None
        if fault == FakeAtemFault.DISCONNECTED:
            return AtemCommandResult.failure(command, "NOT_CONNECTED", "FakeATEM: fault=disconnected", target=target)
        if fault == FakeAtemFault.TIMEOUT:
            return AtemCommandResult.failure(command, "TIMEOUT", "FakeATEM: fault=timeout", target=target)
        if fault == FakeAtemFault.REJECT:
            return AtemCommandResult.failure(command, "REJECTED", "FakeATEM: fault=reject", target=target)
        return None

    # ── Fault injection (#805) ─────────────────────────────────────────────────

    def inject_fault(self, fault: FakeAtemFault) -> None:
        """Inject a deterministic fault for test harness use only.

        Usage in tests:
            atem.inject_fault(FakeAtemFault.DISCONNECTED)
            # ... test failure handling ...
            atem.inject_fault(FakeAtemFault.NONE)  # or clear_fault()

        Must not affect production adapters — only FakeATEM.
        """
        with self._lock:
            self._fault = fault
        logger.info("[DEMO] FakeATEM fault injected: %s", fault.value)

    def clear_fault(self) -> None:
        """Clear any injected fault — restore normal FakeATEM behaviour."""
        with self._lock:
            self._fault = FakeAtemFault.NONE
        logger.info("[DEMO] FakeATEM fault cleared")

    @property
    def active_fault(self) -> FakeAtemFault:
        with self._lock:
            return self._fault

    # ── Safety Reset contract (#782) ──────────────────────────────────────────

    def reset_transient_state(self) -> None:
        """Reset all volatile ATEM state to safe/unknown values.

        Called by SafetyResetService (#782).  Does not change IP/config.
        Does not send any ATEM commands.  Safe when disconnected.
        Idempotent — calling twice leaves same state.
        """
        with self._lock:
            self._preview_input = None
            self._transitioning = False
            self._last_command_result = None
        logger.info("[DEMO] FakeATEM transient state reset")

    def cancel_pending_commands(self) -> None:
        """No-op for FakeATEM — all commands are synchronous.

        Provided for interface compatibility with SafetyResetService (#782).
        """
        logger.info("[DEMO] FakeATEM cancel_pending_commands (no-op)")
