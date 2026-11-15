#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Export exact Python SBOM pins or check a pip-audit 2.9 JSON report.

Offline structural/coverage check, not report authenticity or freshness proof.
Any reported vulnerability blocks, regardless of severity. No exceptions/fixes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from packaging.utils import canonicalize_name
from packaging.version import Version


def _json(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def pins(sbom: Path) -> dict[str, str]:
    doc = _json(sbom)
    if not isinstance(doc, dict) or doc.get("bomFormat") != "CycloneDX":
        raise ValueError("expected CycloneDX object")
    components = doc.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("expected nonempty SBOM components")
    result = {}
    for component in components:
        if not isinstance(component, dict) or component.get("type") != "library":
            raise ValueError("only Python library components are supported")
        name, version = component.get("name"), component.get("version")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", name):
            raise ValueError("invalid Python distribution name")
        if not isinstance(version, str) or str(Version(version)) != version:
            raise ValueError("version must be an exact canonical PEP440 pin")
        normalized = canonicalize_name(name)
        if normalized in result or component.get("purl") != f"pkg:pypi/{normalized}@{version}":
            raise ValueError("duplicate component or inconsistent Python purl")
        result[normalized] = version
    return result


def check(sbom: Path, report: Path) -> int:
    expected = pins(sbom)
    doc = _json(report)
    if not isinstance(doc, dict) or not isinstance(doc.get("dependencies"), list) or doc.get("fixes") != []:
        raise ValueError("expected pip-audit JSON object with dependencies and empty fixes")
    actual = {}
    for dep in doc["dependencies"]:
        if not isinstance(dep, dict) or "skip_reason" in dep:
            raise ValueError("skipped or malformed audit dependency")
        name, version, vulns = dep.get("name"), dep.get("version"), dep.get("vulns")
        if not isinstance(name, str) or canonicalize_name(name) not in expected:
            raise ValueError("unexpected audit dependency")
        name = canonicalize_name(name)
        if name in actual or version != expected[name] or not isinstance(vulns, list):
            raise ValueError("duplicate, mismatched pin or missing vulnerability results")
        if vulns:
            raise ValueError(f"known vulnerability reported for {name} (all severities block)")
        actual[name] = version
    if actual != expected:
        raise ValueError("audit coverage differs from SBOM exact pins")
    return len(actual)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sbom", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write-requirements", type=Path)
    mode.add_argument("--audit-report", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.write_requirements:
            requirements = pins(args.sbom)
            # A fresh path prevents accidentally replacing evidence or inputs.
            with args.write_requirements.open("x", encoding="utf-8") as out:
                out.write("".join(f"{name}=={version}\n" for name, version in sorted(requirements.items())))
            print(f"Exported {len(requirements)} exact Python pins; not an audit result")
        else:
            count = check(args.sbom, args.audit_report)
            print(f"Audit report covers {count} exact SBOM pins with no reported vulnerabilities; "
                  "not proof of vulnerability absence or release approval")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
