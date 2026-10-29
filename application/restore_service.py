#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/restore_service.py — safe restore workflow with pre-restore backup
#
# Safety contract:
#   - Validates manifest before touching any files.
#   - Creates a pre-restore backup of current data before overwriting anything.
#   - Only restores files listed in the manifest AND present in the ZIP.
#   - Rejects ZIPs with unknown/unsafe paths (path traversal, unexpected dirs).
#   - Uses atomic writes (.tmp → os.replace) to prevent partial-restore corruption.
#   - A corrupt or missing manifest always fails without modifying data.

from __future__ import annotations

import hashlib
import json
import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from core.atomic_write import write_bytes_atomic
from domain.backup_contract import (
    CONFIG_ARCHIVE_NAME,
    MANIFEST_ARCHIVE_NAME,
    RESTORABLE_ARCHIVE_NAMES,
)

logger = logging.getLogger(__name__)


# Imported, never re-listed. This allow-list and BackupService's candidate list
# are the same fact, and maintaining them separately is how a backup ends up
# carrying a member restore refuses: preset_brightness.json was added to the
# backup side only, and because an unlisted member is treated as tampering the
# whole archive — config.yaml, presets and layout included — was rejected at
# the one moment it mattered. See domain/backup_contract.py.
_KNOWN_ARC_NAMES = RESTORABLE_ARCHIVE_NAMES


@dataclass
class RestoreResult:
    pre_restore_backup: Optional[Path]
    restored: List[str]
    skipped: List[str]
    failed: List[str]

    def summary(self) -> str:
        lines = [
            f"Pre-restore backup: {self.pre_restore_backup or 'none'}",
            f"Restored ({len(self.restored)}): {', '.join(self.restored) or 'none'}",
        ]
        if self.skipped:
            lines.append(f"Skipped  ({len(self.skipped)}): {', '.join(self.skipped)}")
        if self.failed:
            lines.append(f"Failed   ({len(self.failed)}): {', '.join(self.failed)}")
        return "\n".join(lines)


class RestoreError(Exception):
    """Raised when a restore cannot proceed safely."""


class RestoreService:
    """
    Restores customer data from a manifest-based ZIP backup.

    Parameters
    ----------
    install_dir:
        Root directory of the installed application.
    data_dir:
        User data directory (seat names, presets, etc.).
    config_path:
        Path to config.yaml.
    backup_dir:
        Directory for the automatic pre-restore backup.
    version_file:
        Path to the VERSION file.
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def __init__(
        self,
        install_dir:  Path | None = None,
        data_dir:     Path | None = None,
        config_path:  Path | None = None,
        backup_dir:   Path | None = None,
        version_file: Path | None = None,
        flight_recorder=None,
    ) -> None:
        self._install_dir = install_dir or Path(__file__).parent.parent
        self._version_file = version_file or (self._install_dir / "VERSION")
        self._recorder = flight_recorder

        if data_dir is None:
            from runtime.path_resolver import RuntimePathResolver
            data_dir = RuntimePathResolver().data_dir
        self._data_dir = Path(data_dir)

        if config_path is None or backup_dir is None:
            from runtime.path_resolver import RuntimePathResolver
            resolver = RuntimePathResolver()
            config_path = config_path or (resolver.config_dir / "config.yaml")
            backup_dir = backup_dir or resolver.backup_dir

        self._config_path = Path(config_path)
        self._backup_dir  = Path(backup_dir)

    def restore(self, zip_path: Path, *, dry_run: bool = False) -> RestoreResult:
        """
        Restore from ``zip_path``.

        Validates the ZIP and manifest, creates a pre-restore backup, then
        atomically overwrites each recognised file.

        Parameters
        ----------
        zip_path:
            Path to the backup ZIP to restore.
        dry_run:
            When True, validate the ZIP and report what would be restored but
            do not write any files or create a pre-restore backup.

        Raises
        ------
        RestoreError
            If the ZIP is missing, corrupt, lacks a manifest, or contains
            unknown/unsafe archive paths.
        """
        zip_path = Path(zip_path)
        if dry_run:
            return self._dry_run_inner(zip_path)
        # Capture evidence snapshot before the risky action.
        try:
            from application.evidence_snapshot_service import EvidenceSnapshotService
            EvidenceSnapshotService().capture(
                "restore", notes=f"zip: {zip_path.name}"
            )
        except Exception as exc:
            logger.warning("Evidence snapshot before restore failed (non-blocking): %s", exc)
        self._record_event("RestoreStarted", zip_path=str(zip_path))
        try:
            result = self._restore_inner(zip_path)
        except RestoreError as exc:
            self._record_event("RestoreFailed", error=str(exc), zip_path=str(zip_path))
            raise
        self._record_event(
            "RestoreSucceeded",
            zip_path=str(zip_path),
            files_restored=len(result.restored),
        )
        return result

    def _dry_run_inner(self, zip_path: Path) -> "RestoreResult":
        """Validate ZIP and return what would be restored without writing anything."""
        if not zip_path.exists():
            raise RestoreError(f"Backup file not found: {zip_path}")

        if not zipfile.is_zipfile(zip_path):
            raise RestoreError(f"Not a valid ZIP file: {zip_path}")

        with zipfile.ZipFile(zip_path, "r") as zf:
            manifest = self._load_manifest(zf)
            self._validate_zip_names(zf)
            self._verify_hashes(zf, manifest)

            included_in_manifest = set(manifest.get("included", []))
            arc_names_in_zip = set(zf.namelist()) - {"manifest.json"}

            to_restore = [
                n for n in arc_names_in_zip
                if n in _KNOWN_ARC_NAMES and n in included_in_manifest
            ]
            skipped = [
                n for n in arc_names_in_zip
                if n not in to_restore
            ]

        return RestoreResult(
            pre_restore_backup=None,
            restored=sorted(to_restore),
            skipped=sorted(skipped),
            failed=[],
        )

    def _restore_inner(self, zip_path: Path) -> "RestoreResult":
        if not zip_path.exists():
            raise RestoreError(f"Backup file not found: {zip_path}")

        if not zipfile.is_zipfile(zip_path):
            raise RestoreError(f"Not a valid ZIP file: {zip_path}")

        with zipfile.ZipFile(zip_path, "r") as zf:
            manifest = self._load_manifest(zf)
            self._validate_zip_names(zf)
            self._verify_hashes(zf, manifest)  # raises RestoreError on mismatch

            included_in_manifest = set(manifest.get("included", []))
            arc_names_in_zip     = set(zf.namelist()) - {"manifest.json"}

            to_restore = [
                n for n in arc_names_in_zip
                if n in _KNOWN_ARC_NAMES and n in included_in_manifest
            ]

            pre_backup = self._create_pre_restore_backup()

            restored: list[str] = []
            skipped:  list[str] = []
            failed:   list[str] = []

            for arc_name in sorted(to_restore):
                dest = self._resolve_dest(arc_name)
                if dest is None:
                    skipped.append(arc_name)
                    continue
                try:
                    self._atomic_write(zf.read(arc_name), dest)
                    restored.append(arc_name)
                except OSError as exc:
                    failed.append(f"{arc_name} ({exc})")

        return RestoreResult(
            pre_restore_backup=pre_backup,
            restored=restored,
            skipped=skipped,
            failed=failed,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _load_manifest(self, zf: zipfile.ZipFile) -> dict:
        if "manifest.json" not in zf.namelist():
            raise RestoreError(
                "Backup ZIP has no manifest.json — this backup may be from an older version "
                "or may be corrupt. Restore aborted."
            )
        try:
            return json.loads(zf.read("manifest.json").decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RestoreError(f"manifest.json is corrupt: {exc}") from exc

    def _verify_hashes(self, zf: zipfile.ZipFile, manifest: dict) -> None:
        """
        If the manifest includes a ``files`` list with SHA-256 hashes, verify each
        file in the archive matches its declared hash.

        Does nothing when the manifest was created before hash support was added
        (schema_version < 2 or ``files`` key absent).

        Raises
        ------
        RestoreError
            If any file's computed hash does not match the manifest hash.
        """
        file_records = manifest.get("files")
        if not file_records:
            return  # old-format backup — no hashes to verify

        hash_map = {rec["path"]: rec["sha256"] for rec in file_records if "sha256" in rec}
        if not hash_map:
            return  # nothing to verify

        for arc_name, expected_hash in hash_map.items():
            if arc_name not in zf.namelist():
                continue  # file was skipped (not in archive) — nothing to verify
            actual_data = zf.read(arc_name)
            actual_hash = hashlib.sha256(actual_data).hexdigest()
            if actual_hash != expected_hash:
                raise RestoreError(
                    f"Hash mismatch for '{arc_name}': "
                    f"expected {expected_hash!r}, got {actual_hash!r}. "
                    "The backup may be corrupt. Restore aborted."
                )

    def _validate_zip_names(self, zf: zipfile.ZipFile) -> None:
        for name in zf.namelist():
            if name == MANIFEST_ARCHIVE_NAME:
                continue
            if name not in _KNOWN_ARC_NAMES:
                raise RestoreError(
                    f"Backup contains unexpected path '{name}'. "
                    "Restore aborted to prevent unknown files from being written."
                )
            if ".." in name or name.startswith("/"):
                raise RestoreError(
                    f"Unsafe path in backup: '{name}'. Restore aborted."
                )

    def _resolve_dest(self, arc_name: str) -> Path | None:
        if arc_name == CONFIG_ARCHIVE_NAME:
            return self._config_path
        return self._data_dir / arc_name

    def _create_pre_restore_backup(self) -> Path | None:
        try:
            from application.backup_service import BackupService
            svc = BackupService(
                install_dir=self._install_dir,
                data_dir=self._data_dir,
                config_path=self._config_path,
                backup_dir=self._backup_dir,
                version_file=self._version_file,
            )
            result = svc.create_backup()
            return result.path
        except Exception:  # noqa: BLE001
            logger.exception("Pre-restore backup failed — proceeding without safety backup")
            return None

    @staticmethod
    def _atomic_write(data: bytes, dest: Path) -> None:
        write_bytes_atomic(dest, data)

    def _record_event(self, event_type: str, **extra) -> None:
        if self._recorder is None:
            return
        try:
            from domain.blackbox_event import EventLevel, EventResult, EventSource
            from datetime import datetime, timezone
            level = EventLevel.ERROR if "Failed" in event_type else EventLevel.INFO
            result = (
                EventResult.FAILED if "Failed" in event_type
                else EventResult.SUCCEEDED if "Succeeded" in event_type
                else EventResult.REQUESTED
            )
            self._recorder.record_dict({
                "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "level": level,
                "event_type": event_type,
                "source": EventSource.SYSTEM,
                "result": result,
                **extra,
            })
        except Exception:  # noqa: BLE001
            pass
