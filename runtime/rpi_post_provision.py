#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Normalize and validate Raspberry Pi configuration after wizard provisioning."""
from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from domain.installation_profile import derive_installation_profile


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def normalize_config(config_path: Path) -> List[str]:
    """Normalize wizard-managed fields and return non-blocking advisories."""
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise RuntimeError("config.yaml root must be a mapping")

    cameras = raw.get("cameras") or []
    if not isinstance(cameras, list) or not cameras:
        raise RuntimeError("At least one camera is required")

    site = raw.setdefault("site", {})
    if not isinstance(site, dict):
        raise RuntimeError("site must be a mapping")
    # Same rule the wizard applies, from the one domain implementation: two
    # copies disagreed above two cameras, so post-provision silently rewrote the
    # wizard's professional_multi_camera to custom.
    current_profile = str(site.get("installation_profile") or "")
    site["installation_profile"] = derive_installation_profile(
        len(cameras), current_profile
    ).value

    atem = raw.setdefault("atem", {})
    features = raw.setdefault("features", {})
    if not isinstance(atem, dict) or not isinstance(features, dict):
        raise RuntimeError("atem and features must be mappings")
    atem_enabled = _as_bool(atem.get("enabled", False)) or _as_bool(
        features.get("atem_enabled", False)
    )
    atem_ip = str(atem.get("ip") or "").strip()
    if atem_enabled and not atem_ip:
        raise RuntimeError(
            "ATEM is enabled but its IP address is empty. Go back to Optional "
            "hardware & network, enter the ATEM IP, and apply setup again."
        )
    atem["installed"] = atem_enabled
    atem["enabled"] = atem_enabled
    features["atem_enabled"] = atem_enabled

    advisories: List[str] = []
    network = raw.setdefault("network", {})
    if not isinstance(network, dict):
        raise RuntimeError("network must be a mapping")
    profile = str(network.get("profile") or "unknown").strip()
    if profile in {"", "unknown"}:
        advisories.append(
            "Network profile is not confirmed. Select Flat LAN or Isolated AV VLAN "
            "during setup before a production handover."
        )
    elif profile == "flat_lan":
        advisories.append(
            "Flat LAN is supported for testing, but an isolated AV VLAN is recommended "
            "for production installations."
        )

    _atomic_write_yaml(config_path, raw)
    return advisories


def _atomic_write_yaml(path: Path, data: Dict[str, Any]) -> None:
    st = path.stat()
    payload = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(temp_path, stat.S_IMODE(st.st_mode))
        try:
            os.chown(temp_path, st.st_uid, st.st_gid)
        except (AttributeError, PermissionError):
            pass
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def write_advisories(path: Path, advisories: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(
        json.dumps({"advisories": advisories}, indent=2), encoding="utf-8"
    )
    os.chmod(temp, 0o644)
    os.replace(temp, path)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("/etc/hallptz/config.yaml")
    )
    parser.add_argument(
        "--advisories",
        type=Path,
        default=Path("/run/hallptz/rpi-advisories.json"),
    )
    args = parser.parse_args(argv)
    advisories = normalize_config(args.config)
    write_advisories(args.advisories, advisories)
    for advisory in advisories:
        print(f"[WARN] {advisory}")
    print("[INFO] Raspberry Pi configuration normalized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
