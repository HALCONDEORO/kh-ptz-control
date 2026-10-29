#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ports/atem_port.py — Application-level AtemPort protocol (#551)
#
# Defines two protocols for video switcher (ATEM) hardware boundary:
#
#   AtemReadPort  — read-only: status, program, preview, test_connection
#   AtemWritePort — write: set_preview, cut, auto (extends AtemReadPort)
#
# These are runtime_checkable Protocols — adapters do not need to inherit,
# duck-typing is used.  FakeATEM (adapters/fake_atem.py) implements both.
#
# Dry-run mode:
#   FakeATEM supports dry_run via ATEMDispatcher.dry_run().  Production
#   adapters need not implement it — guard with hasattr().
#
# Safety contract (CUT / AUTO — no automatic retry):
#   - cut() and auto() MUST NOT retry on failure.
#   - Each call represents a deliberate operator or admin action.
#   - Callers must surface the AtemCommandResult and wait for operator input.
#   - Automatic retry would risk unexpected on-air transitions.
#
# Read/write separation:
#   AtemReadPort never sends Preview/CUT/AUTO commands.
#   AtemWritePort adds the three live-switching commands.
#   Use AtemReadPort for diagnostics services; AtemWritePort for AtemCommandService.

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from domain.ports import AtemCommandResult, SwitcherStatus


@runtime_checkable
class AtemReadPort(Protocol):
    """Read-only ATEM adapter contract.

    Implementations MUST NEVER call set_preview, cut or auto.
    Used for diagnostics, status display and doctor checks.
    FakeATEM satisfies this protocol.
    """

    def connect(self) -> bool: ...

    def disconnect(self) -> None: ...

    def get_program_input(self) -> Optional[int]: ...

    def get_preview_input(self) -> Optional[int]: ...

    def test_connection(self) -> AtemCommandResult: ...

    def get_status(self) -> SwitcherStatus: ...


@runtime_checkable
class AtemWritePort(AtemReadPort, Protocol):
    """Full read+write ATEM adapter contract.

    Extends AtemReadPort with manual write commands.

    CUT and AUTO MUST NOT be called automatically — only via explicit
    operator or admin action through AtemCommandService.
    """

    def set_preview_input(self, input_id: int) -> AtemCommandResult: ...

    def cut(self) -> AtemCommandResult:
        """CUT transition. No automatic retry. Deliberate action only."""
        ...

    def auto(self) -> AtemCommandResult:
        """AUTO transition. No automatic retry. Deliberate action only."""
        ...

    def set_pip_enabled(self, enabled: bool) -> AtemCommandResult:
        """Enable or disable Picture-in-Picture on ME1. No automatic retry."""
        ...
