#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/evidence_snapshot_service.py — Pre-action evidence snapshots.
#
# Usage: call capture() before any risky action (restore, config commit, known-good mark).
# The snapshot captures identity, fingerprint hash, doctor summary and warranty state.
# Secrets are excluded — the snapshot is safe for support bundle inclusion.
#
# Safety rules:
#   - Never blocks the risky action if snapshot creation fails.
#   - Never exposes secrets in any snapshot field.
#   - Snapshot files are written atomically (.tmp → os.replace).
#   - Absence of a snapshot is a warning, not a fatal error.

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from runtime.path_resolver import RuntimePathResolver

logger = logging.getLogger(__name__)


@dataclass
class EvidenceSnapshot:
    """
    Redacted state snapshot captured before a risky action.

    All fields default to 'unknown' so the snapshot is always safe
    to serialize without None-checks.
    """
    snapshot_id: str
    correlation_id: str
    taken_before: str
    taken_at: str
    installation_id: str = "unknown"
    app_version: str = "unknown"
    git_commit: str = "unknown"
    fingerprint_hash: str = "unknown"
    doctor_overall: str = "unknown"
    warranty_state: str = "unknown"
    notes: str = ""
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_clean(self) -> bool:
        """Return True if snapshot was captured without errors."""
        return len(self.errors) == 0


class EvidenceSnapshotService:
    """
    Captures a redacted system-state snapshot before risky actions.

    The snapshot is written to RuntimePathResolver.log_dir/evidence/ as a JSON
    file named by snapshot_id. The path is returned for support bundle linking.

    All sub-service failures are caught and recorded in snapshot.errors — the
    snapshot is always returned, even if some fields could not be populated.
    """

    def __init__(self, path_resolver: Optional[RuntimePathResolver] = None) -> None:
        self._resolver = path_resolver or RuntimePathResolver()

    def capture(
        self,
        taken_before: str,
        *,
        correlation_id: Optional[str] = None,
        notes: str = "",
    ) -> EvidenceSnapshot:
        """
        Capture a pre-action evidence snapshot.

        Parameters
        ----------
        taken_before:
            Short description of the risky action about to be performed.
            Example: "restore", "config_commit", "known_good_mark".
        correlation_id:
            Optional caller-provided correlation ID to link the snapshot to a
            specific command or session. A UUID is generated if not provided.
        notes:
            Optional free-text notes from the caller.

        Returns
        -------
        EvidenceSnapshot
            Always returns a snapshot, even if partial (errors are recorded).
        """
        snapshot_id = str(uuid.uuid4())
        corr_id = correlation_id or str(uuid.uuid4())
        taken_at = datetime.now(tz=timezone.utc).isoformat()
        errors: list[str] = []

        installation_id = "unknown"
        app_version = "unknown"
        git_commit = "unknown"
        fingerprint_hash = "unknown"
        doctor_overall = "unknown"
        warranty_state = "unknown"

        # Best-effort population — each block is isolated so one failure
        # does not prevent the rest from being captured.
        try:
            from runtime.build_info import build_info
            info = build_info(data_dir=self._resolver.data_dir)
            installation_id = info.installation_id
            app_version = info.app_version
            git_commit = info.git_commit
        except Exception as exc:
            errors.append(f"build_info: {exc}")

        try:
            from application.fingerprint_service import FingerprintService
            fp = FingerprintService(paths=self._resolver).generate()
            fingerprint_hash = fp.fingerprint_hash()
        except Exception as exc:
            errors.append(f"fingerprint: {exc}")

        try:
            from application.diagnostics_service import DiagnosticsService
            report = DiagnosticsService().run()
            doctor_overall = report.overall.name if hasattr(report.overall, "name") \
                else str(report.overall)
        except Exception as exc:
            errors.append(f"doctor: {exc}")

        try:
            from application.warranty_state_service import WarrantyStateService
            ws = WarrantyStateService().assess()
            warranty_state = ws.state.value if hasattr(ws.state, "value") else str(ws.state)
        except Exception as exc:
            errors.append(f"warranty: {exc}")

        snapshot = EvidenceSnapshot(
            snapshot_id=snapshot_id,
            correlation_id=corr_id,
            taken_before=taken_before,
            taken_at=taken_at,
            installation_id=installation_id,
            app_version=app_version,
            git_commit=git_commit,
            fingerprint_hash=fingerprint_hash,
            doctor_overall=doctor_overall,
            warranty_state=warranty_state,
            notes=notes,
            errors=errors,
        )

        self._persist(snapshot)
        return snapshot

    def _persist(self, snapshot: EvidenceSnapshot) -> None:
        evidence_dir = self._resolver.log_dir / "evidence"
        tmp: "Path | None" = None
        try:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            path = evidence_dir / f"{snapshot.snapshot_id}.json"
            tmp = path.with_suffix(".tmp")
            text = json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False)
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
            tmp = None  # replace succeeded — no cleanup needed
            logger.info(
                "Evidence snapshot %s captured before '%s' → %s",
                snapshot.snapshot_id[:8], snapshot.taken_before, path,
            )
        except OSError as exc:
            logger.warning(
                "Could not persist evidence snapshot %s: %s",
                snapshot.snapshot_id[:8], exc,
            )
        finally:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
