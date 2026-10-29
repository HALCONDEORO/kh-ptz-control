#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/legacy_migration.py — migrate legacy .txt config files to config.yaml
#
# Safety rules:
#   - Never deletes legacy .txt files.
#   - Never overwrites an existing config.yaml unless --overwrite is explicit.
#   - When --overwrite is used on an existing config, creates a timestamped .bak first.
#   - Dry-run mode reports the planned changes without writing anything.
#   - Falls back silently if no legacy files are found (no-op for fresh installs).
#   - Atomic write (.tmp → os.replace) to prevent partial-write corruption.
#
# Legacy files (all in the install/app directory):
#   PTZ1IP.txt  — camera 1 IP address
#   Cam1ID.txt  — camera 1 VISCA ID (hex, e.g. "81")
#   PTZ2IP.txt  — camera 2 IP address (optional)
#   Cam2ID.txt  — camera 2 VISCA ID (optional)
#   ATEMIP.txt  — ATEM switcher IP (optional)
#   Contact.txt — site contact info (optional)
#
# Rollback:
#   If migration overwrites config.yaml and the result is wrong, restore from the
#   automatically-created backup (.bak file reported in MigrationResult.backup_path).
#   Run: cp <backup_path> config.yaml
#   Or use: hallptz restore to restore from a pre-migration backup created by BackupService.

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from core.atomic_write import write_text_atomic

logger = logging.getLogger(__name__)

_CAM1_FILES = ("PTZ1IP.txt", "Cam1ID.txt")
_CAM2_FILES = ("PTZ2IP.txt", "Cam2ID.txt")
_OPTIONAL_FILES = ("ATEMIP.txt", "Contact.txt")


@dataclass
class MigrationResult:
    config_written: bool
    config_path: Optional[Path]
    detected: List[str]
    skipped_reason: Optional[str] = None
    dry_run: bool = False
    backup_path: Optional[Path] = None

    def summary(self) -> str:
        if self.dry_run:
            return self._dry_run_summary()
        if self.skipped_reason:
            return f"Migration skipped: {self.skipped_reason}"
        if not self.config_written:
            return "Migration: no legacy files found — nothing to migrate"
        parts = [
            f"Migration: config.yaml written to {self.config_path}",
            f"(detected: {', '.join(self.detected)})",
        ]
        if self.backup_path:
            parts.append(f"\nPre-migration backup: {self.backup_path}")
        parts.append("\nRollback: if the result is incorrect, restore from the backup above")
        parts.append("  or run: hallptz restore <backup-zip> to recover from a full backup.")
        return " ".join(parts[:2]) + ("\n" + "\n".join(parts[2:]) if len(parts) > 2 else "")

    def _dry_run_summary(self) -> str:
        lines = ["Migration dry-run (no files written):"]
        if self.skipped_reason:
            lines.append(f"  Would skip: {self.skipped_reason}")
            return "\n".join(lines)
        if not self.detected:
            lines.append("  No legacy files found — nothing to migrate.")
            return "\n".join(lines)
        lines.append(f"  Legacy files detected: {', '.join(self.detected)}")
        if self.config_path and self.config_path.exists():
            lines.append("  Would back up existing config.yaml to a .bak file")
            lines.append(f"  Would overwrite: {self.config_path}")
        elif self.config_path:
            lines.append(f"  Would write: {self.config_path}")
        lines.append("  Run without --dry-run to apply.")
        return "\n".join(lines)


def detect_legacy_files(app_dir: Path) -> list[str]:
    """Return names of legacy .txt files that exist in *app_dir*."""
    all_legacy = list(_CAM1_FILES) + list(_CAM2_FILES) + list(_OPTIONAL_FILES)
    return [name for name in all_legacy if (app_dir / name).exists()]


def migrate(
    app_dir: Path,
    config_path: Path,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> MigrationResult:
    """
    Generate ``config.yaml`` from legacy .txt files if it does not already exist.

    Parameters
    ----------
    app_dir:
        Directory containing the legacy .txt files.
    config_path:
        Destination for the generated config.yaml.
    overwrite:
        If True, overwrite an existing config.yaml (after creating a .bak backup).
        Default is False.
    dry_run:
        If True, report what would happen without writing any files.
        Default is False.

    Returns
    -------
    MigrationResult
        Describes what happened.  ``config_written=False`` means nothing changed.
    """
    detected = detect_legacy_files(app_dir)

    if config_path.exists() and not overwrite:
        logger.debug("config.yaml already exists at %s — migration skipped", config_path)
        return MigrationResult(
            config_written=False,
            config_path=config_path,
            detected=detected,
            skipped_reason=f"config.yaml already exists at {config_path} — use --overwrite to replace it",
            dry_run=dry_run,
        )

    if not detected:
        logger.debug("No legacy .txt files found in %s — nothing to migrate", app_dir)
        return MigrationResult(
            config_written=False,
            config_path=None,
            detected=[],
            dry_run=dry_run,
        )

    cam1_ip = _read_txt(app_dir / "PTZ1IP.txt")
    cam1_id = _read_txt(app_dir / "Cam1ID.txt") or "81"
    cam2_ip = _read_txt(app_dir / "PTZ2IP.txt")
    cam2_id = _read_txt(app_dir / "Cam2ID.txt") or "82"
    atem_ip = _read_txt(app_dir / "ATEMIP.txt")
    contact = _read_txt(app_dir / "Contact.txt")

    if not cam1_ip:
        logger.debug("PTZ1IP.txt missing or empty — cannot migrate without a camera IP")
        return MigrationResult(
            config_written=False,
            config_path=None,
            detected=detected,
            skipped_reason="PTZ1IP.txt is missing or empty — at least one camera IP is required",
            dry_run=dry_run,
        )

    yaml_text = _build_yaml(
        cam1_ip=cam1_ip,
        cam1_id=cam1_id,
        cam2_ip=cam2_ip,
        cam2_id=cam2_id,
        atem_ip=atem_ip,
        contact=contact,
    )

    if dry_run:
        return MigrationResult(
            config_written=False,
            config_path=config_path,
            detected=detected,
            dry_run=True,
        )

    backup_path: Optional[Path] = None
    if config_path.exists() and overwrite:
        backup_path = _backup_existing_config(config_path)

    _atomic_write(config_path, yaml_text)
    logger.info("Legacy migration: config.yaml written to %s", config_path)
    if backup_path:
        logger.info("  Pre-migration backup: %s", backup_path)
    for name in detected:
        logger.info("  Legacy file preserved (not deleted): %s", app_dir / name)

    return MigrationResult(
        config_written=True,
        config_path=config_path,
        detected=detected,
        backup_path=backup_path,
    )


# ── YAML generation ───────────────────────────────────────────────────────────

def _build_yaml(
    cam1_ip: str,
    cam1_id: str,
    cam2_ip: str | None,
    cam2_id: str,
    atem_ip: str | None,
    contact: str | None,
) -> str:
    lines: list[str] = [
        "# Hall PTZ Control — migrated from legacy .txt configuration",
        "# Generated automatically — review and adjust before first run.",
        "",
        "site:",
        '  name: ""',
        f'  contact: {_yaml_str(contact or "")}',
        "",
        "cameras:",
        "  - id: platform",
        "    role: platform",
        f"    ip: {_yaml_str(cam1_ip)}",
        f"    visca_id: {_yaml_str(cam1_id)}",
    ]

    if cam2_ip:
        lines += [
            "  - id: comments",
            "    role: comments",
            f"    ip: {_yaml_str(cam2_ip)}",
            f"    visca_id: {_yaml_str(cam2_id)}",
        ]

    lines += [
        "",
        "atem:",
        f'  ip: {_yaml_str(atem_ip or "")}',
        "",
        "runtime:",
        '  data_dir: ""',
        '  connectivity_mode: offline',
        "",
        "features:",
        f"  atem_enabled: {str(bool(atem_ip)).lower()}",
        "  simulation: false",
    ]

    return "\n".join(lines) + "\n"


def _yaml_str(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_txt(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
        return text if text else None
    except OSError:
        return None


def _backup_existing_config(config_path: Path) -> Optional[Path]:
    """Create a timestamped .bak copy of config_path. Returns the backup path, or None on failure."""
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = config_path.with_name(f"{config_path.stem}_pre_migrate_{stamp}.bak")
    try:
        import shutil
        shutil.copy2(config_path, backup_path)
        return backup_path
    except OSError as exc:
        logger.warning("Could not create pre-migration backup of %s: %s", config_path, exc)
        return None


def _atomic_write(path: Path, text: str) -> None:
    write_text_atomic(path, text)
