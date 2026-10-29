#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/backup_service.py — manifest-based ZIP backup for customer installations
#
# Creates a ZIP archive containing all customer data needed to reproduce or
# restore an installation.  A manifest.json inside the ZIP records which files
# were included and which were skipped, along with the app version and timestamp.
#
# Missing optional files are silently skipped (never crash).
# No secrets or private keys are included.

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List


_MANIFEST_SCHEMA_VERSION = 2
_HASH_ALGORITHM = "sha256"


def _sha256_of_path(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()



@dataclass
class BackupResult:
    path: Path
    included: List[str]
    skipped: List[str]
    manifest: dict


class BackupService:
    """
    Creates manifest-based ZIP backups for customer installations.

    Parameters
    ----------
    install_dir:
        Root directory of the installed application.
        Defaults to the project root derived from this file's location.
    data_dir:
        User data directory (seat names, presets, etc.).
        Defaults to HALLPTZ_DATA_DIR or ~/.config/hallptz.
    config_path:
        Ruta a config.yaml. Por defecto usa el directorio runtime de configuración.
    backup_dir:
        Directory where backups are written.
        Por defecto usa el directorio runtime de backups.
    version_file:
        Path to the VERSION file.
        Defaults to <install_dir>/VERSION.
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def __init__(
        self,
        install_dir: Path | None = None,
        data_dir:    Path | None = None,
        config_path: Path | None = None,
        backup_dir:  Path | None = None,
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

    def create_backup(self, dest: Path | None = None) -> BackupResult:
        """
        Create a manifest-based ZIP backup.

        Parameters
        ----------
        dest:
            Explicit destination path.  When omitted a timestamped file is
            created inside ``backup_dir``.

        Returns
        -------
        BackupResult
            Contains the final ZIP path, lists of included/skipped files,
            and the raw manifest dict written into the ZIP.
        """
        if dest is None:
            self._backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            dest = self._backup_dir / f"hallptz_backup_{stamp}.zip"

        candidates = self._collect_candidates()
        included: list[str] = []
        skipped:  list[str] = []
        file_records: list[dict] = []

        for arc_name, path in candidates:
            if path.exists():
                included.append(arc_name)
                size = path.stat().st_size
                digest = _sha256_of_path(path)
                file_records.append({
                    "path": arc_name,
                    "sha256": digest,
                    "size_bytes": size,
                })
            else:
                skipped.append(arc_name)

        installation_id = self._read_installation_id()
        manifest = {
            "schema_version": _MANIFEST_SCHEMA_VERSION,
            "app_version": self._read_version(),
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "installation_id": installation_id,
            "hash_algorithm": _HASH_ALGORITHM,
            "files": file_records,
            # Legacy fields kept for older restore code compatibility
            "included": included,
            "skipped": skipped,
        }

        try:
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
                for arc_name, path in candidates:
                    if path.exists():
                        zf.write(path, arc_name)
        except Exception as exc:
            self._record_event("BackupFailed", error=str(exc))
            raise

        result = BackupResult(
            path=dest,
            included=included,
            skipped=skipped,
            manifest=manifest,
        )
        self._record_event("BackupCreated", path=str(dest), files_included=len(included))
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _read_version(self) -> str:
        try:
            return self._version_file.read_text(encoding="utf-8").strip()
        except OSError:
            return "unknown"

    def _read_installation_id(self) -> str:
        """Read installation_id from config.yaml without crashing."""
        try:
            from config.loader import load_config
            settings = load_config(self._config_path)
            return getattr(settings.site, "installation_id", "") or ""
        except Exception:  # noqa: BLE001
            return ""

    def _collect_candidates(self) -> list[tuple[str, Path]]:
        """Return (archive_name, filesystem_path) pairs for all candidate files.

        The member list comes from domain/backup_contract.py rather than being
        spelled out here, because RestoreService validates against that same
        definition. When the two were maintained separately they drifted:
        backup added preset_brightness.json, restore did not learn about it,
        and restore aborts on an unlisted member — so the whole archive,
        config.yaml included, became unrestorable on any appliance where that
        file existed.
        """
        from domain.backup_contract import CONFIG_ARCHIVE_NAME, DATA_ARCHIVE_NAMES

        data = self._data_dir
        candidates: list[tuple[str, Path]] = [
            (CONFIG_ARCHIVE_NAME, self._config_path),
        ]
        candidates.extend((name, data / name) for name in DATA_ARCHIVE_NAMES)
        return candidates

    def _record_event(self, event_type: str, **extra) -> None:
        if self._recorder is None:
            return
        try:
            from domain.blackbox_event import EventLevel, EventResult, EventSource
            from domain.time_utils import utc_now_iso
            level = EventLevel.ERROR if "Failed" in event_type else EventLevel.INFO
            result = EventResult.FAILED if "Failed" in event_type else EventResult.SUCCEEDED
            self._recorder.record_dict({
                "timestamp": utc_now_iso(),
                "level": level,
                "event_type": event_type,
                "source": EventSource.SYSTEM,
                "result": result,
                **extra,
            })
        except Exception:  # noqa: BLE001
            pass
