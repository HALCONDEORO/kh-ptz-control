#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# scripts/generate_sbom.py — Generate a Software Bill of Materials for release builds (#513)
#
# Usage:
#   python3 scripts/generate_sbom.py
#   python3 scripts/generate_sbom.py --out release/sbom.json
#
# Outputs:
#   release/sbom.json       — CycloneDX 1.4-compatible JSON SBOM
#
# Regeneration:
#   Run this script in the release environment (or from the pinned venv) to get
#   accurate installed package versions. The output is a release artifact, not
#   committed for every dev run.
#
# Safety rules:
#   - No secrets, tokens, credentials or customer data are included.
#   - This SBOM describes runtime dependencies — it is not a security certificate.

from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _app_version() -> str:
    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def _collect_packages() -> list[dict]:
    """Return sorted list of installed packages with name, version and description."""
    packages = []
    for dist in importlib.metadata.distributions():
        meta = dist.metadata
        name = meta["Name"] or "unknown"
        version = meta["Version"] or "unknown"
        description = (meta["Summary"] or "").strip()
        packages.append({
            "type": "library",
            "name": name,
            "version": version,
            "description": description,
            "purl": f"pkg:pypi/{name.lower()}@{version}",
        })
    return sorted(packages, key=lambda p: p["name"].lower())


def _build_cyclonedx(app_version: str, git_commit: str, components: list[dict]) -> dict:
    """Build a CycloneDX 1.4-compatible JSON SBOM."""
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {
                "type": "application",
                "name": "khptz-adaptive-control",
                "version": app_version,
                "description": "KH PTZ Control — VISCA-over-IP PTZ camera control for Raspberry Pi",
                "properties": [
                    {"name": "git:commit", "value": git_commit},
                ],
            },
        },
        "components": components,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate SBOM for KH PTZ Control")
    parser.add_argument("--out", default="release/sbom.json", help="Output path")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    app_version = _app_version()
    git_commit = _git_commit()
    components = _collect_packages()
    sbom = _build_cyclonedx(app_version, git_commit, components)

    out_path.write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
    print(f"Written: {out_path}")
    print(f"SBOM — {app_version} ({git_commit}) — {len(components)} component(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
