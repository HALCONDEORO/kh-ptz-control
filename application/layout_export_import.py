#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/layout_export_import.py — layout-only export and import service
#
# Separate from full BackupService/RestoreService (which cover all customer data).
# This is for layout templates: move a seating map between devices or reuse it
# in multiple rooms without touching attendee names or camera config.
#
# Safety contract:
#   - Export is read-only (no side effects on current data).
#   - Import validates JSON, schema_version and unique seat IDs before touching disk.
#   - Import backs up the current layout before overwriting.
#   - Import never touches seat_names.json, config.yaml or any other file.
#
# No Qt, no network I/O.

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.atomic_write import write_bytes_atomic
from domain.room_layout import SCHEMA_VERSION


@dataclass
class ImportResult:
    imported: bool
    pre_import_backup: Optional[Path]
    layout_path: Path
    reason: Optional[str] = None

    def summary(self) -> str:
        if not self.imported:
            return f"Layout import failed: {self.reason}"
        return (
            f"Layout imported to {self.layout_path}"
            + (f" (backup: {self.pre_import_backup})" if self.pre_import_backup else "")
        )


class LayoutExportImportService:
    """
    Layout-only export and import.

    Export: copies the current room_layout.json to a chosen destination.
    Import: validates a layout file, backs up the current layout, then replaces it.

    Parameters
    ----------
    layout_path:
        Path to room_layout.json.  Defaults to the data_paths constant.
    """

    def __init__(self, layout_path: Path | None = None) -> None:
        if layout_path is None:
            from runtime.path_resolver import RuntimePathResolver
            layout_path = RuntimePathResolver().room_layout_file
        self._path = Path(layout_path)

    # ── Public API ────────────────────────────────────────────────────────────

    def export_layout(self, dest: Path) -> bool:
        """
        Copy the current layout file to *dest*.

        Returns True on success.
        Raises FileNotFoundError if no current layout exists.
        """
        dest = Path(dest)
        if not self._path.exists():
            raise FileNotFoundError(
                f"No layout file to export at {self._path}. "
                "Run LayoutService.load() first to generate the default layout."
            )
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._path, dest)
        return True

    def import_layout(self, src: Path) -> ImportResult:
        """
        Validate and import a layout file.

        Validation steps (in order):
          1. File must exist and be readable.
          2. Content must be valid JSON.
          3. ``schema_version`` must not exceed the current maximum.
          4. Each seat must have a non-empty, unique ``id``.

        If validation passes:
          - Backs up the current layout (if it exists).
          - Atomically writes the new layout.

        Returns ImportResult with outcome details.
        """
        src = Path(src)
        if not src.exists():
            return ImportResult(
                imported=False,
                pre_import_backup=None,
                layout_path=self._path,
                reason=f"Source file not found: {src}",
            )

        try:
            raw_bytes = src.read_bytes()
            raw = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            return ImportResult(
                imported=False,
                pre_import_backup=None,
                layout_path=self._path,
                reason=f"Invalid layout file: {exc}",
            )

        error = self._validate_raw(raw)
        if error:
            return ImportResult(
                imported=False,
                pre_import_backup=None,
                layout_path=self._path,
                reason=error,
            )

        pre_backup = self._backup_current()
        self._atomic_write(raw_bytes, self._path)

        return ImportResult(
            imported=True,
            pre_import_backup=pre_backup,
            layout_path=self._path,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_raw(raw) -> str | None:
        if not isinstance(raw, dict):
            return "Layout file must be a JSON object"

        version = raw.get("schema_version")
        if version is None:
            return "Missing 'schema_version' in layout file"
        try:
            version = int(version)
        except (TypeError, ValueError):
            return f"Invalid 'schema_version': {version!r}"
        if version > SCHEMA_VERSION:
            return (
                f"Layout uses schema version {version} but this version of HALLPTZ "
                f"only supports up to version {SCHEMA_VERSION}. "
                "Upgrade Hall PTZ Control to import this layout."
            )

        seats = raw.get("seats", [])
        if not isinstance(seats, list):
            return "'seats' must be a JSON array"

        seen_ids: set[str] = set()
        for i, seat in enumerate(seats):
            if not isinstance(seat, dict):
                return f"seats[{i}] must be a JSON object"
            seat_id = str(seat.get("id", ""))
            if not seat_id:
                return f"seats[{i}]: 'id' must be a non-empty string"
            if seat_id in seen_ids:
                return f"Duplicate seat id: {seat_id!r}"
            seen_ids.add(seat_id)

        return None

    def _backup_current(self) -> Path | None:
        if not self._path.exists():
            return None
        bak = self._path.with_suffix(".import.bak")
        try:
            shutil.copy2(self._path, bak)
            return bak
        except OSError:
            return None

    @staticmethod
    def _atomic_write(data: bytes, dest: Path) -> None:
        write_bytes_atomic(dest, data)
