#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Installed Python dependency closure for one interpreter and declared profile.

No installation, network access, vulnerability lookup or release approval.
"""
from __future__ import annotations

from collections import deque
import importlib.metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


def collect(root: Path) -> tuple[list[dict], list[dict], list[str]]:
    """Fail on unsupported input, missing/duplicate metadata or violated pins."""
    requirements = []
    for raw in (root / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            requirements.append(Requirement(line))
    if not requirements:
        raise ValueError("runtime requirements are empty")
    installed = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            installed.setdefault(canonicalize_name(name), []).append(dist)
    environment = default_environment()
    pending = deque((None, requirement, {""}) for requirement in requirements)
    active_extras: dict[str, set[str]] = {}
    edges: dict[str | None, set[str]] = {None: set()}
    records = {}
    while pending:
        parent, requirement, parent_extras = pending.popleft()
        if requirement.url:
            raise ValueError(f"direct URL requirement is unsupported: {requirement.name}")
        if requirement.marker and not any(
            requirement.marker.evaluate({**environment, "extra": extra}) for extra in parent_extras
        ):
            continue
        name = canonicalize_name(requirement.name)
        matches = installed.get(name, [])
        if len(matches) != 1:
            raise ValueError(f"{name}: expected one installed distribution, found {len(matches)}")
        dist = matches[0]
        version = Version(dist.version)
        if not requirement.specifier.contains(version, prereleases=True):
            raise ValueError(f"{name} {version} violates requirement {requirement}")
        edges.setdefault(parent, set()).add(name)
        edges.setdefault(name, set())
        extras = {"", *requirement.extras}
        provided = {canonicalize_name(x) for x in dist.metadata.get_all("Provides-Extra", [])}
        if any(canonicalize_name(x) not in provided for x in requirement.extras):
            raise ValueError(f"{name}: requested extra is not declared by installed metadata")
        new_extras = extras - active_extras.get(name, set())
        if not new_extras:
            continue
        active_extras.setdefault(name, set()).update(new_extras)
        ref = f"pkg:pypi/{name}@{dist.version}"
        records[name] = {"type": "library", "name": dist.metadata["Name"],
                         "version": dist.version, "purl": ref, "bom-ref": ref,
                         "description": (dist.metadata.get("Summary") or "").strip()}
        for child in dist.requires or []:
            pending.append((name, Requirement(child), active_extras[name].copy()))
    refs = {name: record["bom-ref"] for name, record in records.items()}
    graph = [{"ref": refs[name], "dependsOn": sorted(refs[child] for child in children)}
             for name, children in sorted(edges.items(), key=lambda item: item[0] or "") if name is not None]
    return [records[name] for name in sorted(records)], graph, sorted(refs[name] for name in edges[None])
