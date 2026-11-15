#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# scripts/validate_sbom.py — validate a generated SBOM (#513)
#
# Usage:
#   python3 scripts/validate_sbom.py release/sbom.json
#
# The release gate must fail when the SBOM is missing or malformed. Generation
# (scripts/generate_sbom.py) proves the file exists; this validator proves it
# is a usable CycloneDX document: every component pinned to an exact version.

from __future__ import annotations

import json
import sys
from pathlib import Path


def validate(path: Path) -> list[str]:
    """Return a list of problems; empty means the SBOM is valid."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"cannot read {path}: {exc}"]
    except json.JSONDecodeError as exc:
        return [f"{path} is not valid JSON: {exc}"]

    problems: list[str] = []
    if doc.get("bomFormat") != "CycloneDX":
        problems.append(f"bomFormat is {doc.get('bomFormat')!r}, expected 'CycloneDX'")
    if not doc.get("specVersion"):
        problems.append("missing specVersion")

    components = doc.get("components")
    if not isinstance(components, list) or not components:
        problems.append("components is missing or empty")
        return problems
    for i, comp in enumerate(components):
        if not isinstance(comp, dict):
            problems.append(f"components[{i}] is not an object")
            continue
        if not comp.get("name"):
            problems.append(f"components[{i}] has no name")
        if not comp.get("version"):
            problems.append(f"components[{i}] ({comp.get('name', '?')}) has no pinned version")
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
