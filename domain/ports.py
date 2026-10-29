#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/ports.py — Adapter port contracts for camera and switcher hardware
#
# CameraPort and SwitcherPort define the minimal interface that both real
# hardware adapters and fake/demo adapters must implement. Application
# services should depend on these ports, not on concrete implementations.
#
# Real adapters (VISCA-over-IP, PyATEMmax) and fake adapters (FakeCamera,
# FakeATEM) must satisfy these contracts so that demo mode and production
# mode share identical application paths.

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional


# ── Status dataclasses ────────────────────────────────────────────────────────

@dataclass
class CameraStatus:
    camera_id: str
    role: str                        # "platform" | "comments"
    adapter_type: str                # "visca" | "fake" | "simulation"
    connected: bool = False
    moving: bool = False
    current_preset: Optional[int] = None
    last_error: str = ""


@dataclass
class SwitcherStatus:
    adapter_type: str                # "atem" | "fake" | "simulation"
    connected: bool = False
    program_input: Optional[int] = None
    preview_input: Optional[int] = None
    transitioning: bool = False
    automation_mode: bool = False
    last_error: str = ""


@dataclass
class AtemCommandResult:
    """Result of an ATEM command (read or write)."""
    ok: bool
    command: str
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    duration_ms: float = 0.0
    target: Optional[int] = None     # input_id for set_preview, None for cut/auto/status
    error_code: str = ""
    message: str = ""

    @classmethod
    def success(cls, command: str, *, target: Optional[int] = None, duration_ms: float = 0.0) -> "AtemCommandResult":
        return cls(ok=True, command=command, target=target, duration_ms=duration_ms)

    @classmethod
    def failure(cls, command: str, error_code: str, message: str, *, target: Optional[int] = None) -> "AtemCommandResult":
        return cls(ok=False, command=command, error_code=error_code, message=message, target=target)


# ── Port contracts ────────────────────────────────────────────────────────────

class CameraPort(ABC):
    """
    Minimal contract for PTZ camera adapters.

    Both the production VISCA-over-IP adapter and FakeCamera (#296) must
    implement this interface. UI and application services must only call
    methods defined here — never adapter-specific APIs.
    """

    @abstractmethod
    def power_on(self) -> bool:
        """Power camera on. Returns True on success."""

    @abstractmethod
    def standby(self) -> bool:
        """Put camera into standby. Returns True on success."""

    @abstractmethod
    def recall_preset(self, preset: int) -> bool:
        """Move camera to saved preset position. Returns True on success."""

    @abstractmethod
    def save_preset(self, preset: int) -> bool:
        """Save current camera position to preset slot. Returns True on success."""

    @abstractmethod
    def go_home(self) -> bool:
        """Move camera to home position. Returns True on success."""

    @abstractmethod
    def stop(self) -> bool:
        """Stop any active camera movement. Returns True on success."""

    @abstractmethod
    def get_status(self) -> CameraStatus:
        """Return current camera status snapshot."""


class SwitcherPort(ABC):
    """
    Minimal contract for video switcher (ATEM) adapters.

    Both the production PyATEMmax adapter and FakeATEM (#297) must implement
    this interface. set_program_input() may be a no-op for real ATEM adapters
    if the real integration is monitor-only (events only, no command path).
    """

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the switcher. Returns True on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the switcher."""

    @abstractmethod
    def get_program_input(self) -> Optional[int]:
        """Return current program input number, or None if unknown/disconnected."""

    @abstractmethod
    def set_program_input(self, input_id: int) -> None:
        """
        Set program input. May raise NotImplementedError on real ATEM adapters
        if the production integration is monitor-only. Always supported on
        fake/demo adapters.
        """

    @abstractmethod
    def get_status(self) -> SwitcherStatus:
        """Return current switcher status snapshot."""


ProgramChangedCb = Callable[[int], None]
PreviewChangedCb = Callable[[int], None]
ConnectionChangedCb = Callable[[bool], None]


class AtemPort(SwitcherPort):
    """
    Full ATEM command contract extending SwitcherPort.

    Adds Preview bus, CUT/AUTO transitions, test_connection, and typed
    AtemCommandResult returns. FakeATEM (demo/sim) implements this; real
    ATEMMonitor (production) uses the Qt signal path instead.
    """

    @abstractmethod
    def get_preview_input(self) -> Optional[int]:
        """Return current preview input, or None if unknown/disconnected."""

    @abstractmethod
    def set_preview_input(self, input_id: int) -> AtemCommandResult:
        """Set preview bus input. Returns failure result if disconnected."""

    @abstractmethod
    def cut(self) -> AtemCommandResult:
        """Execute CUT transition (preview → program instantly)."""

    @abstractmethod
    def auto(self) -> AtemCommandResult:
        """Execute AUTO transition (preview → program with transition effect)."""

    @abstractmethod
    def test_connection(self) -> AtemCommandResult:
        """Verify the connection is alive. Returns ok=False when disconnected."""

    @abstractmethod
    def add_program_changed_callback(self, cb: ProgramChangedCb) -> None:
        """Register callback fired on every program input change."""

    @abstractmethod
    def remove_program_changed_callback(self, cb: ProgramChangedCb) -> None:
        """Remove a previously registered program-changed callback."""

    @abstractmethod
    def add_preview_changed_callback(self, cb: PreviewChangedCb) -> None:
        """Register callback fired on every preview input change."""

    @abstractmethod
    def remove_preview_changed_callback(self, cb: PreviewChangedCb) -> None:
        """Remove a previously registered preview-changed callback."""

    @abstractmethod
    def add_connection_changed_callback(self, cb: ConnectionChangedCb) -> None:
        """Register callback fired when connection state changes."""

    @abstractmethod
    def remove_connection_changed_callback(self, cb: ConnectionChangedCb) -> None:
        """Remove a previously registered connection-changed callback."""
