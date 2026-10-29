#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/known_good_state_service.py — KnownGoodStateService and StateDiffService.
#
# Stores the last validated installation state and diffs it against current state.
# Secrets are never stored or exposed. The known-good file contains only safe fields.
#
# See docs/RUNTIME_PATH_CONTRACT.md.

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.path_resolver import RuntimePathResolver

logger = logging.getLogger(__name__)


# ── KnownGoodSnapshot ─────────────────────────────────────────────────────────

@dataclass
class KnownGoodSnapshot:
    """
    A safe, secret-free snapshot of a validated installation state.

    All fields default to 'unknown'. Stored as JSON; never contains secrets.
    """
    marked_at: str = "unknown"          # ISO-8601 UTC timestamp
    installation_id: str = "unknown"
    app_version: str = "unknown"
    git_commit: str = "unknown"
    profile: str = "unknown"
    config_hash: str = "unknown"
    layout_hash: str = "unknown"
    fingerprint_hash: str = "unknown"
    cameras: list = field(default_factory=list)
    atem_enabled: str = "unknown"
    atem_configured: str = "unknown"
    mark_note: str = ""                 # optional human note

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> KnownGoodSnapshot:
        known_fields = cls.__dataclass_fields__
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def human_summary(self) -> list[str]:
        lines = [
            f"  Marked at:         {self.marked_at}",
            f"  Installation ID:   {self.installation_id}",
            f"  App version:       {self.app_version}",
            f"  Git commit:        {self.git_commit}",
            f"  Profile:           {self.profile}",
        ]
        cfg = self.config_hash
        lines.append(
            f"  Config hash:       {cfg[:16]}…" if len(cfg) > 16 else f"  Config hash:       {cfg}"
        )
        lay = self.layout_hash
        lines.append(
            f"  Layout hash:       {lay[:16]}…" if len(lay) > 16 else f"  Layout hash:       {lay}"
        )
        fph = self.fingerprint_hash
        lines.append(
            f"  Fingerprint hash:  {fph[:16]}…" if len(fph) > 16 else f"  Fingerprint hash:  {fph}"
        )
        for cam in self.cameras:
            lines.append(f"  Camera {cam.get('role','?')}:         {cam.get('configured','?')}")
        if self.mark_note:
            lines.append(f"  Note:              {self.mark_note}")
        return lines


# ── MarkResult ────────────────────────────────────────────────────────────────

@dataclass
class MarkResult:
    """Result of a known-good mark operation."""
    success: bool
    message: str
    snapshot: KnownGoodSnapshot | None = None
    previous_backed_up: bool = False
    blocked_by: list[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "OK" if self.success else "FAIL"
        lines = [f"  [{status}] {self.message}"]
        if self.previous_backed_up:
            lines.append("         Previous snapshot backed up.")
        for b in self.blocked_by:
            lines.append(f"         Blocked by: {b}")
        return "\n".join(lines)


# ── StateDiff ─────────────────────────────────────────────────────────────────

@dataclass
class FieldDiff:
    field: str
    known_good: str
    current: str

    def to_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "known_good": self.known_good,
            "current": self.current,
        }


@dataclass
class StateDiff:
    """Result of diffing current fingerprint against the known-good snapshot."""
    has_known_good: bool
    no_known_good_reason: str = ""
    changes: list[FieldDiff] = field(default_factory=list)
    unchanged_fields: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.has_known_good and len(self.changes) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_known_good": self.has_known_good,
            "no_known_good_reason": self.no_known_good_reason,
            "is_clean": self.is_clean,
            "changes": [c.to_dict() for c in self.changes],
            "unchanged_fields": self.unchanged_fields,
        }

    def human_summary(self) -> list[str]:
        if not self.has_known_good:
            return [f"  No known-good state: {self.no_known_good_reason}"]
        if self.is_clean:
            return ["  State matches known-good snapshot — no changes detected."]
        lines = [f"  {len(self.changes)} change(s) detected since known-good:"]
        for ch in self.changes:
            lines.append(f"    {ch.field}:")
            lines.append(f"      known-good: {ch.known_good[:32]}{'…' if len(ch.known_good) > 32 else ''}")
            lines.append(f"      current:    {ch.current[:32]}{'…' if len(ch.current) > 32 else ''}")
        return lines


# ── KnownGoodStateService ─────────────────────────────────────────────────────

class KnownGoodStateService:
    """
    Read, write and diff the known-good state file.

    The state file is stored at RuntimePathResolver.known_good_state_file.
    Secrets are never stored. Mark is refused if there are blocking doctor checks.
    """

    def __init__(self, paths: RuntimePathResolver | None = None) -> None:
        self._paths = paths or RuntimePathResolver()

    @property
    def _state_file(self) -> Path:
        return self._paths.known_good_state_file

    # ── Read ──────────────────────────────────────────────────────────────────

    def load(self) -> KnownGoodSnapshot | None:
        """Return the stored snapshot, or None if none exists or file is corrupt."""
        if not self._state_file.exists():
            return None
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            return KnownGoodSnapshot.from_dict(data)
        except Exception as exc:
            logger.warning("Could not read known-good state file: %s", exc)
            return None

    # ── Mark ─────────────────────────────────────────────────────────────────

    def mark(
        self,
        *,
        note: str = "",
        allow_warnings: bool = True,  # reserved for future warning-gate logic — see note below
        force: bool = False,
    ) -> MarkResult:
        """
        Capture the current fingerprint as the new known-good state.

        Blocking doctor checks prevent marking unless force=True.
        The previous snapshot (if any) is backed up with a timestamp suffix.

        Note: ``allow_warnings`` is currently a no-op placeholder reserved for a
        future warning-gate (it will let callers refuse to mark while non-blocking
        doctor warnings exist). It has no effect today regardless of value.
        """
        # Run diagnostics to check for blockers
        if not force:
            blockers = self._find_blockers()
            if blockers:
                return MarkResult(
                    success=False,
                    message="Mark refused — blocking doctor checks present",
                    blocked_by=blockers,
                )

        # Generate current fingerprint
        from application.fingerprint_service import FingerprintService
        fp = FingerprintService(paths=self._paths).generate()

        # Build snapshot
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        snapshot = KnownGoodSnapshot(
            marked_at=now,
            installation_id=fp.installation_id,
            app_version=fp.app_version,
            git_commit=fp.git_commit,
            profile=fp.profile,
            config_hash=fp.config_hash,
            layout_hash=fp.layout_hash,
            fingerprint_hash=fp.fingerprint_hash(),
            cameras=fp.cameras,
            atem_enabled=fp.atem_enabled,
            atem_configured=fp.atem_configured,
            mark_note=note,
        )

        # Back up previous snapshot
        backed_up = self._backup_previous()

        # Write new snapshot
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(snapshot.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            return MarkResult(
                success=False,
                message=f"Could not write known-good state: {exc}",
            )

        return MarkResult(
            success=True,
            message=f"Known-good state marked at {now}",
            snapshot=snapshot,
            previous_backed_up=backed_up,
        )

    # ── Diff ─────────────────────────────────────────────────────────────────

    def diff(self) -> StateDiff:
        """Compare the current fingerprint against the known-good snapshot."""
        snapshot = self.load()
        if snapshot is None:
            return StateDiff(
                has_known_good=False,
                no_known_good_reason="No known-good state has been recorded. "
                                     "Run 'hallptz known-good mark --after-doctor-pass' to set one.",
            )

        from application.fingerprint_service import FingerprintService
        fp = FingerprintService(paths=self._paths).generate()

        # Fields to compare (exclude metadata fields)
        _COMPARE_FIELDS = [
            ("installation_id", snapshot.installation_id, fp.installation_id),
            ("app_version",     snapshot.app_version,     fp.app_version),
            ("git_commit",      snapshot.git_commit,      fp.git_commit),
            ("profile",         snapshot.profile,         fp.profile),
            ("config_hash",     snapshot.config_hash,     fp.config_hash),
            ("layout_hash",     snapshot.layout_hash,     fp.layout_hash),
            ("fingerprint_hash", snapshot.fingerprint_hash, fp.fingerprint_hash()),
            ("atem_enabled",    snapshot.atem_enabled,    fp.atem_enabled),
            ("atem_configured", snapshot.atem_configured, fp.atem_configured),
        ]

        changes: list[FieldDiff] = []
        unchanged: list[str] = []

        for name, kg_val, cur_val in _COMPARE_FIELDS:
            if str(kg_val) != str(cur_val):
                changes.append(FieldDiff(field=name, known_good=str(kg_val), current=str(cur_val)))
            else:
                unchanged.append(name)

        # Camera diff (compare as sorted role:configured strings)
        kg_cams = sorted(f"{c.get('role','?')}:{c.get('configured','?')}" for c in snapshot.cameras)
        cur_cams = sorted(f"{c.get('role','?')}:{c.get('configured','?')}" for c in fp.cameras)
        if kg_cams != cur_cams:
            changes.append(FieldDiff(
                field="cameras",
                known_good=",".join(kg_cams) or "none",
                current=",".join(cur_cams) or "none",
            ))
        else:
            unchanged.append("cameras")

        return StateDiff(
            has_known_good=True,
            changes=changes,
            unchanged_fields=unchanged,
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _find_blockers(self) -> list[str]:
        """Return a list of blocking doctor check names, empty if none."""
        try:
            from application.diagnostics_service import DiagnosticsService, Status
            report = DiagnosticsService(data_dir=self._paths.data_dir).run()
            return [
                c.name for c in report.checks
                if c.blocking and c.status == Status.FAIL
            ]
        except Exception as exc:
            logger.warning("Could not run doctor checks for blocker scan: %s", exc)
            return []

    def _backup_previous(self) -> bool:
        """Back up the existing state file with a timestamp suffix. Returns True if backed up."""
        if not self._state_file.exists():
            return False
        try:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = self._state_file.with_name(
                f"{self._state_file.stem}.{ts}.bak.json"
            )
            shutil.copy2(self._state_file, backup)
            return True
        except OSError as exc:
            logger.warning("Could not back up previous known-good state: %s", exc)
            return False
