#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/fingerprint_service.py — InstallationFingerprint and FingerprintService.
#
# Generates a stable, safe fingerprint of the current installation state.
# Same state → same fingerprint. Secrets are excluded from all hashes and output.
#
# See docs/RUNTIME_PATH_CONTRACT.md and docs/SUPPORT_BUNDLE_CONTRACT.md.

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from domain.redaction import RedactionGuard
from runtime.build_info import build_info
from runtime.path_resolver import RuntimePathResolver

logger = logging.getLogger(__name__)

_guard = RedactionGuard()


def _file_sha256(path: Path) -> str:
    """Return lowercase hex SHA-256 of a file, or 'missing' if not found."""
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return digest
    except OSError:
        return "missing"


def _safe_json_hash(path: Path) -> str:
    """
    Return a stable SHA-256 of a JSON file after redaction.

    - If the file does not exist: 'missing'.
    - If the file is not valid JSON: 'invalid'.
    - If redaction fails: 'redaction_error'.
    - Otherwise: hex SHA-256 of the redacted JSON (sorted keys, no whitespace).
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return "missing"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "invalid"
    try:
        redacted = _guard.redact_mapping(data) if isinstance(data, dict) else data
    except Exception:
        return "redaction_error"
    canonical = json.dumps(redacted, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _camera_summary(paths: RuntimePathResolver) -> list[dict[str, str]]:
    """Return a redacted summary of camera config (roles only, no raw IPs)."""
    summary: list[dict[str, str]] = []
    try:
        _data_dir = paths.data_dir
        for txt in ("PTZ1IP.txt", "PTZ2IP.txt"):
            ip_path = Path(__file__).parent.parent / txt
            if not ip_path.exists():
                ip_path = _data_dir / txt
            if ip_path.exists():
                summary.append({
                    "role": "cam1" if "PTZ1" in txt else "cam2",
                    "configured": "yes",
                })
            else:
                summary.append({
                    "role": "cam1" if "PTZ1" in txt else "cam2",
                    "configured": "no",
                })
    except Exception as exc:  # noqa: BLE001
        logger.debug("_camera_summary: could not read camera config: %s", exc)
    return summary


# ── InstallationFingerprint ───────────────────────────────────────────────────

@dataclass
class InstallationFingerprint:
    """
    Safe fingerprint of the current installation state.

    All fields default to 'unknown' rather than None — safe to log without
    None-checks. Secrets are excluded from all hash and summary fields.
    """

    installation_id: str = "unknown"
    app_version: str = "unknown"
    git_commit: str = "unknown"
    profile: str = "unknown"
    config_hash: str = "unknown"
    layout_hash: str = "unknown"
    cameras: list = field(default_factory=list)
    atem_enabled: str = "unknown"
    atem_configured: str = "unknown"
    runtime_paths: dict = field(default_factory=dict)
    known_good_state_version: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def fingerprint_hash(self) -> str:
        """
        Return a stable SHA-256 of the fingerprint itself.

        Same installation state → same hash.
        Changes to config, layout, cameras or versions change this hash.
        """
        stable = json.dumps(
            {
                "installation_id": self.installation_id,
                "app_version": self.app_version,
                "config_hash": self.config_hash,
                "layout_hash": self.layout_hash,
                "cameras": sorted(
                    [f"{c.get('role','?')}:{c.get('configured','?')}" for c in self.cameras]
                ),
                "atem_enabled": self.atem_enabled,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()

    def human_summary(self) -> list[str]:
        """Return human-readable lines for hallptz fingerprint output."""
        lines = [
            f"  Installation ID:   {self.installation_id}",
            f"  App version:       {self.app_version}",
            f"  Git commit:        {self.git_commit}",
            f"  Profile:           {self.profile}",
            f"  Config hash:       {self.config_hash[:16]}…" if len(self.config_hash) > 16
                else f"  Config hash:       {self.config_hash}",
            f"  Layout hash:       {self.layout_hash[:16]}…" if len(self.layout_hash) > 16
                else f"  Layout hash:       {self.layout_hash}",
            f"  Fingerprint hash:  {self.fingerprint_hash()[:16]}…",
            f"  ATEM enabled:      {self.atem_enabled}",
        ]
        for cam in self.cameras:
            lines.append(
                f"  Camera {cam.get('role','?')}:         {cam.get('configured','?')}"
            )
        if self.known_good_state_version != "unknown":
            lines.append(f"  Known-good at:     {self.known_good_state_version}")
        return lines


# ── FingerprintService ────────────────────────────────────────────────────────

class FingerprintService:
    """Generate a safe installation fingerprint from the current runtime state."""

    def __init__(
        self,
        paths: RuntimePathResolver | None = None,
    ) -> None:
        self._paths = paths or RuntimePathResolver()

    def generate(self) -> InstallationFingerprint:
        """
        Generate a fingerprint for the current installation state.

        All hashes exclude secrets. Missing files are represented as 'missing'.
        """
        info = build_info(data_dir=self._paths.data_dir)

        # Config hash (redacted JSON)
        config_hash = self._hash_config()

        # Layout hash
        layout_hash = _safe_json_hash(self._paths.room_layout_file)

        # Camera summary (no raw IPs)
        cameras = _camera_summary(self._paths)

        # ATEM summary
        atem_enabled, atem_configured = self._atem_summary()

        # Known-good state version (if any)
        kgs_version = self._known_good_state_version()

        return InstallationFingerprint(
            installation_id=info.installation_id,
            app_version=info.app_version,
            git_commit=info.git_commit,
            profile=info.runtime_profile,
            config_hash=config_hash,
            layout_hash=layout_hash,
            cameras=cameras,
            atem_enabled=atem_enabled,
            atem_configured=atem_configured,
            runtime_paths=self._paths.to_dict(),
            known_good_state_version=kgs_version,
        )

    def _hash_config(self) -> str:
        """Hash config.yaml after redacting secrets. Returns 'missing' if absent."""
        # Try config.yaml in the install root first, then config_dir.
        install_root = Path(__file__).parent.parent
        candidates = [
            install_root / "config.yaml",
            self._paths.config_dir / "config.yaml",
        ]
        for path in candidates:
            if path.exists():
                try:
                    raw = path.read_text(encoding="utf-8")
                    # YAML parsed as text: apply text-level redaction, then hash
                    redacted = _guard.redact_text(raw)
                    return hashlib.sha256(redacted.encode("utf-8")).hexdigest()
                except OSError:
                    return "missing"
        return "missing"

    def _atem_summary(self) -> tuple[str, str]:
        """Return (atem_enabled, atem_configured) without raw IPs."""
        try:
            from runtime.path_resolver import RuntimePathResolver
            atem_ip_path = Path(__file__).parent.parent / "ATEMIP.txt"
            if not atem_ip_path.exists():
                atem_ip_path = RuntimePathResolver().data_dir / "ATEMIP.txt"
            if atem_ip_path.exists():
                content = atem_ip_path.read_text(encoding="utf-8").strip()
                configured = "yes" if content else "no"
            else:
                configured = "no"
        except Exception:
            configured = "unknown"
        return "unknown", configured   # enabled state requires config.yaml

    def _known_good_state_version(self) -> str:
        """Read the known-good state version tag if the file exists."""
        try:
            path = self._paths.known_good_state_file
            if not path.exists():
                return "unknown"
            data = json.loads(path.read_text(encoding="utf-8"))
            return str(data.get("marked_at", "unknown"))
        except Exception:
            return "unknown"
