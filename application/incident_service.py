#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/incident_service.py — Sanitized incident snapshot writer (#490)
#
# Creates a compact JSON incident file when a critical failure occurs.
# Used by services and the controller to record context that support can inspect.
#
# Incident creation NEVER raises into live operation — all failures are swallowed.
# Incident files DO NOT contain secrets, passwords, SSH keys or customer PII.

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from domain.blackbox_event import redact_event_dict
from domain.time_utils import utc_now_compact, utc_now_iso as _utc_now

_SCHEMA_VERSION = 1


class IncidentService:
    """
    Writes sanitized incident snapshots to a per-session incidents directory.

    Parameters
    ----------
    incidents_dir:
        Directory where incident JSON files are written.
        Defaults to <data_dir>/incidents/.
    flight_recorder:
        Optional FlightRecorder instance — used to include the last N events
        in each incident snapshot.
    max_incidents:
        Maximum number of incident files to keep (oldest deleted first). Default: 100.
    """

    def __init__(
        self,
        incidents_dir: Path | None = None,
        flight_recorder=None,
        max_incidents: int = 100,
        app_version: str = "unknown",
        installation_profile: str = "unknown",
        runtime_mode: str = "production",
        installation_id: str = "unknown",
    ) -> None:
        if incidents_dir is None:
            try:
                from runtime.path_resolver import RuntimePathResolver
                incidents_dir = RuntimePathResolver().incidents_dir
            except Exception:  # noqa: BLE001
                incidents_dir = Path.home() / ".config" / "khptz" / "incidents"
        self._dir = Path(incidents_dir)
        self._recorder = flight_recorder
        self._max = max_incidents
        self._app_version = app_version
        self._installation_profile = installation_profile
        self._runtime_mode = runtime_mode
        self._installation_id = installation_id

    def record(
        self,
        reason: str,
        severity: str = "ERROR",
        summary: str = "",
        correlation_id: str | None = None,
        session_id: str = "none",
        extra: dict[str, Any] | None = None,
    ) -> Path | None:
        """
        Write an incident snapshot and return the file path.

        Returns None on any error (never raises).
        """
        try:
            return self._write(
                reason=reason,
                severity=severity,
                summary=summary,
                correlation_id=correlation_id or str(uuid.uuid4()),
                session_id=session_id,
                extra=extra or {},
            )
        except Exception:  # noqa: BLE001
            return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _write(
        self,
        reason: str,
        severity: str,
        summary: str,
        correlation_id: str,
        session_id: str,
        extra: dict[str, Any],
    ) -> Path:
        now = _utc_now()
        stamp = utc_now_compact()
        incident_id = f"incident-{stamp}-{str(uuid.uuid4())[:8]}"

        last_events: list[dict] = []
        if self._recorder is not None:
            try:
                last_events = self._recorder.get_recent(20)
            except Exception:  # noqa: BLE001
                pass

        snapshot: dict[str, Any] = {
            "schema_version": _SCHEMA_VERSION,
            "incident_id": incident_id,
            "created_at": now,
            "reason": reason,
            "severity": severity,
            "app_version": self._app_version,
            "installation_profile": self._installation_profile,
            "runtime_mode": self._runtime_mode,
            "installation_id": self._installation_id,
            "session_id": session_id,
            "correlation_id": correlation_id,
            "summary": summary,
            "last_events": last_events,
            "redaction": "secrets_removed",
        }
        if extra:
            snapshot["extra"] = extra

        snapshot = redact_event_dict(snapshot)

        self._dir.mkdir(parents=True, exist_ok=True)
        out = self._dir / f"{incident_id}.json"
        try:
            out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        except OSError as exc:
            logger.exception("IncidentService: no se pudo escribir %s: %s", out, exc)
            raise

        self._prune()
        return out

    def _prune(self) -> None:
        """Delete oldest incident files when count exceeds max_incidents."""
        try:
            files = sorted(self._dir.glob("incident-*.json"), key=lambda p: p.stat().st_mtime)
            for old in files[: max(0, len(files) - self._max)]:
                old.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
