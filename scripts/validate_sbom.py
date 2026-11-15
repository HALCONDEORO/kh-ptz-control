#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# scripts/validate_sbom.py — validate a generated SBOM (#513)
#
# Usage:
#   python3 scripts/validate_sbom.py release/sbom.json
#
# The release gate must fail when the SBOM is missing or malformed. Generation
# (scripts/generate_sbom.py) proves the file exists; this validator runs a
# PARTIAL structural check (it is not the full CycloneDX schema): right
# format, a known specVersion, typed fields, and components pinned to exact
# versions - ranges, wildcards and placeholders like "unknown" are rejected.
# Dependency completeness and the CVE gate (checklist 4.3/4.4) stay pending.

from __future__ import annotations

import json
import re
import sys
from pathlib import Path



_KNOWN_SPEC_VERSIONS = {"1.2", "1.3", "1.4", "1.5", "1.6"}
_PIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]*$")
_NOT_A_PIN = {"unknown", "latest", "n/a", "none", "tbd", "*"}


def _version_problems(i: int, name, version) -> list[str]:
    label = name if isinstance(name, str) and name else f"components[{i}]"
    if not isinstance(version, str) or not version.strip():
        return [f"{label} has no usable version: {version!r}"]
    v = version.strip()
    if v.lower() in _NOT_A_PIN or any(t in v for t in (">", "<", "~", "^", "*", "|", " ")):
        return [f"{label} version {version!r} is not an exact pin (range/wildcard/placeholder)"]
    if not _PIN_RE.match(v):
        return [f"{label} version {version!r} is not a plausible pinned version string"]
    return []


def validate(path: Path) -> list[str]:
    """Return a list of problems; empty means the SBOM is valid."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"cannot read {path}: {exc}"]
    except json.JSONDecodeError as exc:
        return [f"{path} is not valid JSON: {exc}"]

    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["top level is not a JSON object"]
    if doc.get("bomFormat") != "CycloneDX":
        problems.append(f"bomFormat is {doc.get('bomFormat')!r}, expected 'CycloneDX'")
    spec = doc.get("specVersion")
    if not isinstance(spec, str) or spec not in _KNOWN_SPEC_VERSIONS:
        problems.append(f"specVersion {spec!r} is not a known CycloneDX version {sorted(_KNOWN_SPEC_VERSIONS)}")

    components = doc.get("components")
    if not isinstance(components, list) or not components:
        problems.append("components is missing or empty")
        return problems
    for i, comp in enumerate(components):
        if not isinstance(comp, dict):
            problems.append(f"components[{i}] is not an object")
            continue
        name = comp.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"components[{i}] has no usable name: {name!r}")
        problems.extend(_version_problems(i, name, comp.get("version")))
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_sbom.py SBOM.json")
        return 2
    problems = validate(Path(argv[1]))
    if problems:
        for p in problems:
            print(f"ERROR: {p}")
        return 1
    print("SBOM valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
