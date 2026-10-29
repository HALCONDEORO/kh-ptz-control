#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
domain/startup_errors.py — Startup error classification for Hall PTZ Control (#103).

All startup failures fall into one of two categories:

RECOVERABLE — the app continues in a degraded or limited mode.
  The failure affects optional hardware or non-critical state.
  The operator is informed via the splash screen and status UI.
  No exception propagates to the main event loop.

FATAL — the app cannot start in a meaningful state and must exit.
  These are always programming/environment faults, not hardware faults.
  A clear error dialog is shown before exiting.

Classification table
--------------------

| Failure                          | Category    | Behaviour                               |
|----------------------------------|-------------|------------------------------------------|
| Camera disconnected / timeout    | RECOVERABLE | Degraded-mode splash; status shows red   |
| ATEM unavailable                 | RECOVERABLE | ATEM state → DISCONNECTED; UI continues  |
| PyATEMMax missing                | RECOVERABLE | ATEM state → DEPENDENCY_MISSING          |
| Schedule file corrupt            | RECOVERABLE | load_json() falls back to .bak / default |
| Preset file corrupt              | RECOVERABLE | load_json() falls back to .bak / default |
| Seat names file corrupt          | RECOVERABLE | load_json() falls back to .bak / default |
| VERSION file missing             | RECOVERABLE | "unknown" version shown; warning logged  |
| PyQt5 missing                    | FATAL        | Cannot start GUI — exit immediately      |
| Data directory not writable      | FATAL        | Cannot save any state — exit cleanly     |
| Password not configured          | FATAL (login)| Login screen shows setup message         |

Rules for adding new errors
----------------------------
- Camera/network hardware failures are ALWAYS recoverable.
- Third-party library absence is recoverable if the feature is optional.
- Core Python/Qt environment failures are fatal.
- Data directory access failures are fatal (cannot save state).
- Config parse errors are recoverable when a safe default exists.
"""
from __future__ import annotations

import enum


class StartupErrorKind(enum.Enum):
    RECOVERABLE = "recoverable"
    FATAL = "fatal"


class StartupError:
    """Lightweight value object describing a classified startup failure."""

    def __init__(self, kind: StartupErrorKind, component: str, detail: str):
        self.kind = kind
        self.component = component
        self.detail = detail

    @property
    def is_fatal(self) -> bool:
        return self.kind is StartupErrorKind.FATAL

    def __str__(self) -> str:
        return f"[{self.kind.value.upper()}] {self.component}: {self.detail}"

    def __repr__(self) -> str:
        return f"StartupError({self.kind!r}, {self.component!r}, {self.detail!r})"


def recoverable(component: str, detail: str) -> StartupError:
    return StartupError(StartupErrorKind.RECOVERABLE, component, detail)


def fatal(component: str, detail: str) -> StartupError:
    return StartupError(StartupErrorKind.FATAL, component, detail)
