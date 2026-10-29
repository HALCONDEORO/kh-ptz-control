#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/runtime_state.py — Canonical runtime state domain model
#
# Issue: #789 — Epic #787 (single source of truth for runtime state)
#
# Rules:
#   - No PyQt, no I/O, no sockets, no threads.
#   - Serialisable to plain dict/JSON for diagnostics (to_dict()).
#   - Immutable snapshots — all fields are read-only after construction.
#   - Customer secrets (IPs, names) are redacted in to_redacted_dict().

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
#  Sub-models
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LifecycleState:
    """Application lifecycle phase."""
    startup_complete: bool = False
    shutdown_in_progress: bool = False
    last_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "startup_complete": self.startup_complete,
            "shutdown_in_progress": self.shutdown_in_progress,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class SessionRuntimeState:
    """Session lifecycle state."""
    active: bool = False
    session_id: Optional[str] = None
    chairman_name: Optional[str] = None
    started_at: Optional[str] = None  # ISO-8601 UTC string

    def to_dict(self) -> dict:
        return {
            "active": self.active,
            "session_id": self.session_id,
            "chairman_name": self.chairman_name,
            "started_at": self.started_at,
        }

    def to_redacted_dict(self) -> dict:
        """Chairman name redacted — may contain customer PII."""
        d = self.to_dict()
        if d.get("chairman_name"):
            d["chairman_name"] = "[REDACTED]"
        return d


@dataclass(frozen=True)
class CameraRuntimeState:
    """Runtime state for a single PTZ camera."""
    camera_id: str
    configured: bool = False
    connected: bool = False
    movement_state: str = "unknown"   # PTZCameraState.value
    active_preset: Optional[int] = None
    last_error: Optional[str] = None
    last_seen_at: Optional[str] = None  # ISO-8601 UTC string

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "configured": self.configured,
            "connected": self.connected,
            "movement_state": self.movement_state,
            "active_preset": self.active_preset,
            "last_error": self.last_error,
            "last_seen_at": self.last_seen_at,
        }


@dataclass(frozen=True)
class AtemRuntimeState:
    """ATEM switcher runtime state."""
    enabled: bool = False
    connection_state: str = "not_configured"   # ATEMState.name.lower()
    program_input: Optional[int] = None
    preview_input: Optional[int] = None
    last_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "connection_state": self.connection_state,
            "program_input": self.program_input,
            "preview_input": self.preview_input,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class OperationsState:
    """Pending/active operations and safety gate state."""
    safety_reset_in_progress: bool = False
    active_operator_action: Optional[str] = None  # e.g. "moving", "preset_recall"

    def to_dict(self) -> dict:
        return {
            "safety_reset_in_progress": self.safety_reset_in_progress,
            "active_operator_action": self.active_operator_action,
        }


@dataclass(frozen=True)
class DiagnosticsRuntimeState:
    """Runtime health / degraded mode flags."""
    degraded: bool = False
    degraded_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Root: RuntimeState
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RuntimeState:
    """
    Canonical snapshot of all in-process runtime state.

    This is an immutable value object.  ``RuntimeStateStore`` builds new
    instances on every mutation.  Consumers receive snapshots and must not
    cache them across event boundaries.

    Never store customer IPs, passwords or private keys here — use
    ``to_redacted_dict()`` for any external export.
    """

    lifecycle: LifecycleState = field(default_factory=LifecycleState)
    session: SessionRuntimeState = field(default_factory=SessionRuntimeState)
    cameras: dict[str, CameraRuntimeState] = field(default_factory=dict)
    atem: AtemRuntimeState = field(default_factory=AtemRuntimeState)
    operations: OperationsState = field(default_factory=OperationsState)
    diagnostics: DiagnosticsRuntimeState = field(default_factory=DiagnosticsRuntimeState)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Full snapshot dict — do not expose externally without redaction."""
        return {
            "lifecycle": self.lifecycle.to_dict(),
            "session": self.session.to_dict(),
            "cameras": {k: v.to_dict() for k, v in self.cameras.items()},
            "atem": self.atem.to_dict(),
            "operations": self.operations.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
        }

    def to_redacted_dict(self) -> dict:
        """
        Safe export for diagnostics and support bundles.

        - Chairman name replaced with [REDACTED].
        - Camera IPs and ATEM IPs are not stored in RuntimeState at all.
        - session_id is kept (non-sensitive UUID fragment).
        """
        return {
            "lifecycle": self.lifecycle.to_dict(),
            "session": self.session.to_redacted_dict(),
            "cameras": {k: v.to_dict() for k, v in self.cameras.items()},
            "atem": self.atem.to_dict(),
            "operations": self.operations.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
        }

    # ── Clean-state factory ───────────────────────────────────────────────────

    @classmethod
    def clean_state(cls, camera_ids: 'list[str] | None' = None) -> 'RuntimeState':
        """
        Return the known-good clean state after Safety Reset or app start.

        All session/camera/ATEM transient state is cleared.
        Configured cameras are listed with connected=False, movement_state=unknown.
        """
        cameras = {}
        for cam_id in (camera_ids or []):
            cameras[cam_id] = CameraRuntimeState(
                camera_id=cam_id,
                configured=True,
                connected=False,
                movement_state="unknown",
            )
        return cls(
            lifecycle=LifecycleState(startup_complete=False),
            session=SessionRuntimeState(active=False),
            cameras=cameras,
            atem=AtemRuntimeState(enabled=False),
            operations=OperationsState(safety_reset_in_progress=False),
            diagnostics=DiagnosticsRuntimeState(degraded=False),
        )
