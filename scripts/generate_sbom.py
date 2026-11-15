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
import re
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


_REQ_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def _declared_runtime_requirements() -> list[str]:
    """Return the requirement names declared in requirements.txt.

    The SBOM describes the project's runtime dependencies, so it must be built
    from the declared requirements — not from whatever happens to be installed
    in the environment where the script runs. Reading the ambient environment
    both makes the artifact inaccurate (dev tools and unrelated packages leak
    into a release artifact) and makes tests over it non-deterministic.
    """
    req_file = Path(__file__).resolve().parent.parent / "requirements.txt"
    names = []
    for raw_line in req_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _REQ_NAME_RE.match(line)
        if match:
            names.append(match.group(1))
    return names


def _normalize(name: str) -> str:
    """PEP 503 normalisation for distribution name lookups."""
    return re.sub(r"[-_.]+", "-", name).lower()


UNKNOWN_VERSIONS: list[str] = []


def _collect_packages() -> list[dict]:
    """Return sorted list of the declared runtime dependencies.

    Versions and descriptions come from the installed distributions (run
    this in the release environment for accurate versions). A declared
    dependency whose exact version cannot be determined makes generation
    FAIL: an SBOM with "unknown" pins is not a valid release artifact and
    the gate validator rejects it, so failing here keeps the error at the
    source.
    """
    installed = {
        _normalize(dist.metadata["Name"] or "unknown"): dist
        for dist in importlib.metadata.distributions()
    }
    packages = []
    for req_name in _declared_runtime_requirements():
        dist = installed.get(_normalize(req_name))
        if dist is not None:
            meta = dist.metadata
            name = meta["Name"] or req_name
            version = meta["Version"] or "unknown"
            if version == "unknown":
                UNKNOWN_VERSIONS.append(req_name)
            description = (meta["Summary"] or "").strip()
        else:
            name = req_name
            version = "unknown"
            description = ""
            UNKNOWN_VERSIONS.append(req_name)
        packages.append({
            "type": "library",
            "name": name,
            "version": version,
            "description": description,
            "purl": f"pkg:pypi/{_normalize(name)}@{version}",
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
    if UNKNOWN_VERSIONS:
        print(
            "ERROR: exact versions could not be determined for: "
            + ", ".join(sorted(UNKNOWN_VERSIONS))
            + " - run in the release environment with requirements.txt installed",
            file=sys.stderr,
        )
        return 1
    sbom = _build_cyclonedx(app_version, git_commit, components)

    out_path.write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
    print(f"Written: {out_path}")
    print(f"SBOM — {app_version} ({git_commit}) — {len(components)} component(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
