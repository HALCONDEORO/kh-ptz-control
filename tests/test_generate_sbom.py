#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_generate_sbom.py — Tests for scripts/generate_sbom.py (#513)
from __future__ import annotations

import json
import sys
from pathlib import Path


def _run_sbom(out_path: str) -> int:
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    import importlib
    gen = importlib.import_module("generate_sbom")
    old_argv = sys.argv[:]
    sys.argv = ["generate_sbom.py", "--out", out_path]
    try:
        return gen.main()
    finally:
        sys.argv = old_argv
        sys.path.pop(0)


def test_sbom_file_created(tmp_path):
    out = tmp_path / "sbom.json"
    rc = _run_sbom(str(out))
    assert rc == 0
    assert out.exists()


def test_sbom_is_cyclonedx(tmp_path):
    out = tmp_path / "sbom.json"
    _run_sbom(str(out))
    sbom = json.loads(out.read_text())
    assert sbom["bomFormat"] == "CycloneDX"
    assert "specVersion" in sbom
    assert "components" in sbom


def test_sbom_has_metadata(tmp_path):
    out = tmp_path / "sbom.json"
    _run_sbom(str(out))
    sbom = json.loads(out.read_text())
    meta = sbom.get("metadata", {})
    assert "timestamp" in meta
    comp = meta.get("component", {})
    assert comp.get("name") == "khptz-adaptive-control"
    assert comp.get("version") != ""


def test_sbom_has_no_secrets(tmp_path):
    out = tmp_path / "sbom.json"
    _run_sbom(str(out))
    text = out.read_text().lower()
    for pattern in ("password", "token", "secret", "credential"):
        assert pattern not in text, f"SBOM unexpectedly contains '{pattern}'"


def test_sbom_components_have_purl(tmp_path):
    out = tmp_path / "sbom.json"
    _run_sbom(str(out))
    sbom = json.loads(out.read_text())
    for comp in sbom["components"]:
        assert comp.get("purl", "").startswith("pkg:pypi/"), \
            f"Component {comp.get('name')} missing valid purl"
