#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# runtime/build_info.py — Runtime identity metadata for Hall PTZ Control.
#
# BuildInfo provides consistent version/profile/installation identity
# for use in hallptz status, hallptz version, support bundles and doctor output.
#
# No I/O at module import — build_info() reads files lazily.

from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app_version import read_version
from domain.runtime_mode import parse_mode


def _read_git_commit(source_root: Path) -> str:
    """Return the short git commit hash, or 'unknown' if not available."""
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip() or "unknown"
    except Exception:
        pass
    return "unknown"


def _read_installation_id(data_dir: Path) -> str:
    """Read installation_id from data_dir/installation_id.txt, or return 'unknown'."""
    candidate = data_dir / "installation_id.txt"
    try:
        val = candidate.read_text(encoding="utf-8").strip()
        return val or "unknown"
    except OSError:
        pass
    # Fallback: read site.installation_id from canonical config.yaml
    try:
        import yaml
        from runtime.path_resolver import RuntimePathResolver
        config_path = RuntimePathResolver().config_dir / "config.yaml"
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                site = data.get("site", {})
                if isinstance(site, dict):
                    iid = str(site.get("installation_id", "")).strip()
                    if iid:
                        return iid
    except Exception:
        pass
    return "unknown"


@dataclass(frozen=True)
class BuildInfo:
    """
    Runtime identity snapshot — captured once at startup or on demand.

    All fields default to 'unknown' rather than None so they are always
    safe to log and serialize without None-checks.
    """

    app_version: str = "unknown"
    git_commit: str = "unknown"
    build_date: str = "unknown"
    runtime_profile: str = "production"
    installation_id: str = "unknown"
    connectivity_mode: str = "unknown"
    running_from_source: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["running_from_source"] = str(self.running_from_source)
        return d

    def version_line(self) -> str:
        """Single-line human-readable identity string."""
        commit = f" ({self.git_commit})" if self.git_commit != "unknown" else ""
        profile = (
            f" [{self.runtime_profile.upper()}]"
            if self.runtime_profile != "production"
            else ""
        )
        return f"Hall PTZ Control {self.app_version}{commit}{profile}"


def build_info(
    *,
    data_dir: Path | None = None,
    version_file: Path | None = None,
) -> BuildInfo:
    """
    Assemble a BuildInfo snapshot.

    data_dir:    where to look for installation_id.txt (defaults to data_paths.CONFIG_DIR)
    version_file: override for the VERSION file path (defaults to app_version.VERSION_FILE)
    """
    source_root = Path(__file__).resolve().parent.parent

    # Runtime profile from env or default
    raw_profile = os.environ.get("HALLPTZ_PROFILE", "production")
    try:
        mode = parse_mode(raw_profile)
        profile_str = mode.value
    except ValueError:
        profile_str = "unknown"

    # Version
    app_ver = read_version(version_file)

    # Git commit (best-effort)
    git_commit = _read_git_commit(source_root)

    # Installation ID
    if data_dir is None:
        try:
            from runtime.path_resolver import RuntimePathResolver
            data_dir = RuntimePathResolver().data_dir
        except Exception:
            data_dir = Path.home() / ".config" / "hallptz"
    installation_id = _read_installation_id(data_dir)

    # Running from source detection
    running_from_source = (source_root / ".git").is_dir()

    return BuildInfo(
        app_version=app_ver,
        git_commit=git_commit,
        build_date="unknown",     # populated by CI/release tooling if available
        runtime_profile=profile_str,
        installation_id=installation_id,
        connectivity_mode="unknown",  # populated by diagnostics at runtime
        running_from_source=running_from_source,
    )
