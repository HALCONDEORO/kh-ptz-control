#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Contract tests for the release-decision gate and SBOM validator
(#520/#452: NOT_TESTED must never count as pass; #513: SBOM missing fails)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


readiness = _load("check_release_readiness", REPO_ROOT / "scripts" / "check_release_readiness.py")
sbom = _load("validate_sbom", REPO_ROOT / "scripts" / "validate_sbom.py")

CHECKLIST = """# Checklist

| Field | Value |
|-------|-------|
| **Decision** | {decision} |

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1.1 | VERSION present | ✅ PASS | ok |
{rows}
"""


def _write_checklist(tmp_path: Path, decision: str, rows: str) -> Path:
    p = tmp_path / "CHECKLIST.md"
    p.write_text(CHECKLIST.format(decision=decision, rows=rows), encoding="utf-8")
    return p


NOT_TESTED_ROW = "| 9.1 | App starts on Pi hardware | 🔲 NOT_TESTED | needs Pi |"
FAIL_ROW = "| 1.2 | git tag matches VERSION | ❌ FAIL | no tag |"


class TestDecisionGate:
    def test_demo_decision_allows_not_tested(self, tmp_path):
        p = _write_checklist(tmp_path, "**DEMO ONLY** — hardware NOT_TESTED", NOT_TESTED_ROW)
        assert readiness.main(["prog", str(p)]) == 0

    def test_customer_decision_fails_on_not_tested(self, tmp_path, capsys):
        p = _write_checklist(tmp_path, "**CUSTOMER READY**", NOT_TESTED_ROW)
        assert readiness.main(["prog", str(p)]) == 1
        out = capsys.readouterr().out
        assert "9.1" in out and "NOT_TESTED" in out

    def test_customer_decision_fails_on_fail_row(self, tmp_path):
        p = _write_checklist(tmp_path, "**CUSTOMER READY**", FAIL_ROW)
        assert readiness.main(["prog", str(p)]) == 1

    def test_customer_decision_all_pass_is_green(self, tmp_path):
        p = _write_checklist(tmp_path, "**CUSTOMER READY**", "| 1.2 | tag | ✅ PASS | ok |")
        assert readiness.main(["prog", str(p)]) == 0

    def test_missing_decision_fails_safe(self, tmp_path):
        p = tmp_path / "CHECKLIST.md"
        p.write_text("# no decision here\n", encoding="utf-8")
        assert readiness.main(["prog", str(p)]) == 2

    def test_missing_file_fails_safe(self, tmp_path):
        assert readiness.main(["prog", str(tmp_path / "nope.md")]) == 2

    def test_real_checklist_is_parseable_and_demo(self):
        # The shipped checklist records DEMO ONLY today; the gate must agree.
        assert readiness.main(["prog", str(REPO_ROOT / "docs" / "RELEASE_READINESS_CHECKLIST.md")]) == 0


def _sbom_doc(**over):
    doc = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "components": [{"name": "pyqt6", "version": "6.5.0"}],
    }
    doc.update(over)
    return doc


class TestSbomValidator:
    def test_valid_document_passes(self, tmp_path):
        p = tmp_path / "sbom.json"
        p.write_text(json.dumps(_sbom_doc()), encoding="utf-8")
        assert sbom.validate(p) == []

    def test_missing_file_fails(self, tmp_path):
        problems = sbom.validate(tmp_path / "missing.json")
        assert problems and "cannot read" in problems[0]

    def test_invalid_json_fails(self, tmp_path):
        p = tmp_path / "sbom.json"
        p.write_text("{not json", encoding="utf-8")
        assert sbom.validate(p)

    def test_wrong_format_fails(self, tmp_path):
        p = tmp_path / "sbom.json"
        p.write_text(json.dumps(_sbom_doc(bomFormat="SPDX")), encoding="utf-8")
        assert any("bomFormat" in pr for pr in sbom.validate(p))

    def test_empty_components_fail(self, tmp_path):
        p = tmp_path / "sbom.json"
        p.write_text(json.dumps(_sbom_doc(components=[])), encoding="utf-8")
        assert any("components" in pr for pr in sbom.validate(p))

    def test_unpinned_component_fails(self, tmp_path):
        p = tmp_path / "sbom.json"
        p.write_text(json.dumps(_sbom_doc(components=[{"name": "pyqt6"}])), encoding="utf-8")
        assert any("version" in pr for pr in sbom.validate(p))

    def test_generated_sbom_is_valid(self, tmp_path):
        """The repo's own generator must produce a document the gate accepts."""
        import subprocess
        out = tmp_path / "sbom.json"
        subprocess.run(
            ["python3", str(REPO_ROOT / "scripts" / "generate_sbom.py"), "--out", str(out)],
            check=True, capture_output=True,
        )
        assert sbom.validate(out) == []
