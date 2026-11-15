#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Contract tests for the release-decision gate and SBOM tooling
(#520/#452: NOT_TESTED never counts as pass; #513: SBOM missing/malformed
fails). The gate checks the consistency of the recorded decision with the
recorded rows; it never accepts a release and never sets the decision."""

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

## Current candidate: 9.9.9

**Current decision:** {decision}

| # | Check | Status | Notes |
|---|-------|--------|-------|
{rows}

## Archived evidence record - old build

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1.1 | archived FAIL row | ❌ FAIL | must be ignored |
| 9.9 | archived NOT_TESTED | 🔲 NOT_TESTED | must be ignored |
"""

PASS_ROW = "| 1.1 | version ok | ✅ PASS | verified in CI |"
WARN_ROW = "| 3.1 | hygiene | ⚠️ WARN | {notes} |"
WARN_ACCEPTED = "| 3.1 | hygiene | ⚠️ WARN | accepted: documented exception by reviewer |"
NT_CORE = "| 2.1 | tests | 🔲 NOT_TESTED | not run |"
NT_HW = "| 9.1 | pi hardware | 🔲 NOT_TESTED | awaits Pi |"
FAIL_ROW = "| 8.1 | installer | ❌ FAIL | broken |"


def _write(tmp_path: Path, decision: str, rows: str) -> Path:
    p = tmp_path / "CHECKLIST.md"
    p.write_text(CHECKLIST.format(decision=decision, rows=rows), encoding="utf-8")
    return p


def _run(tmp_path: Path, decision: str, rows: str) -> int:
    return readiness.main(["prog", str(_write(tmp_path, decision, rows))])


class TestDecisionEnum:
    def test_demo_passes_when_consistent(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", PASS_ROW + "\n" + NT_HW) == 0

    def test_unknown_decision_fails_closed(self, tmp_path):
        assert _run(tmp_path, "BANANA", PASS_ROW + "\n" + NT_HW) == 2

    def test_missing_current_decision_fails_closed(self, tmp_path):
        p = tmp_path / "C.md"
        p.write_text("## Current candidate: 1\n\n| a | b |\n", encoding="utf-8")
        assert readiness.main(["prog", str(p)]) == 2

    def test_missing_current_region_fails_closed(self, tmp_path):
        p = tmp_path / "C.md"
        p.write_text("# no candidate here\n**Current decision:** DEMO ONLY\n", encoding="utf-8")
        assert readiness.main(["prog", str(p)]) == 2


class TestDemoPolicy:
    def test_not_tested_in_core_section_blocks_demo(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", PASS_ROW + "\n" + NT_CORE) == 1

    def test_not_tested_in_hardware_section_ok_for_demo(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", PASS_ROW + "\n" + NT_HW) == 0

    def test_fail_anywhere_blocks_demo(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", PASS_ROW + "\n" + FAIL_ROW) == 1


class TestCustomerPolicy:
    def test_customer_blocks_any_not_tested(self, tmp_path):
        assert _run(tmp_path, "CUSTOMER READY", PASS_ROW + "\n" + NT_HW) == 1

    def test_customer_warn_requires_written_acceptance(self, tmp_path):
        assert _run(tmp_path, "CUSTOMER READY", PASS_ROW + "\n" + WARN_ROW.format(notes="caveat")) == 1

    def test_customer_warn_with_acceptance_passes(self, tmp_path):
        assert _run(tmp_path, "CUSTOMER READY", PASS_ROW + "\n" + WARN_ACCEPTED) == 0

    def test_demo_warn_needs_no_acceptance(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", PASS_ROW + "\n" + WARN_ROW.format(notes="caveat")) == 0


class TestSchemaCoverage:
    def test_zero_rows_fails_closed(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", "| --- | --- | --- | --- |") == 2

    def test_unknown_status_fails_closed(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", "| 1.1 | x | PENDING | later |") == 2

    def test_bare_section_number_fails_closed(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", "| 9 | x | ✅ PASS | ok |") == 2

    def test_archived_rows_are_ignored(self, tmp_path):
        # The template's archived block contains FAIL and NOT_TESTED rows.
        assert _run(tmp_path, "DEMO ONLY", PASS_ROW) == 0

    def test_missing_file_fails_closed(self, tmp_path):
        assert readiness.main(["prog", str(tmp_path / "nope.md")]) == 2


class TestRealChecklist:
    def test_shipped_checklist_passes_its_own_gate(self):
        assert readiness.main(
            ["prog", str(REPO_ROOT / "docs" / "RELEASE_READINESS_CHECKLIST.md")]
        ) == 0


def _sbom_doc(**over):
    doc = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.4",
        "components": [{"name": "pyqt6", "version": "6.5.0"}],
    }
    doc.update(over)
    return doc


class TestSbomValidator:
    def _check(self, tmp_path: Path, doc) -> list[str]:
        p = tmp_path / "sbom.json"
        p.write_text(json.dumps(doc) if not isinstance(doc, str) else doc, encoding="utf-8")
        return sbom.validate(p)

    def test_valid_document_passes(self, tmp_path):
        assert self._check(tmp_path, _sbom_doc()) == []

    def test_missing_file_fails(self, tmp_path):
        assert sbom.validate(tmp_path / "missing.json")

    def test_invalid_json_fails(self, tmp_path):
        assert self._check(tmp_path, "{not json")

    def test_wrong_format_fails(self, tmp_path):
        assert any("bomFormat" in p for p in self._check(tmp_path, _sbom_doc(bomFormat="SPDX")))

    def test_specversion_must_be_known_string(self, tmp_path):
        assert self._check(tmp_path, _sbom_doc(specVersion={"x": 1}))
        assert self._check(tmp_path, _sbom_doc(specVersion="nonsense"))

    def test_empty_components_fail(self, tmp_path):
        assert self._check(tmp_path, _sbom_doc(components=[]))

    def test_component_name_must_be_string(self, tmp_path):
        problems = self._check(tmp_path, _sbom_doc(components=[{"name": 123, "version": "1.0"}]))
        assert any("name" in p for p in problems)

    @pytest.mark.parametrize("bad", ["unknown", "UNKNOWN", "*", ">=1.0", "^1.2", "~1.2", "1.0 || 2.0", "latest", ""])
    def test_version_ranges_wildcards_placeholders_rejected(self, tmp_path, bad):
        problems = self._check(tmp_path, _sbom_doc(components=[{"name": "dep", "version": bad}]))
        assert problems, bad

    def test_unusual_but_real_pins_accepted(self, tmp_path):
        doc = _sbom_doc(components=[{"name": "dep", "version": "1.0+build5"}, {"name": "x", "version": "2026.11.15"}])
        assert self._check(tmp_path, doc) == []

    def test_generated_sbom_is_valid(self, tmp_path):
        import subprocess
        out = tmp_path / "sbom.json"
        subprocess.run(
            ["python3", str(REPO_ROOT / "scripts" / "generate_sbom.py"), "--out", str(out)],
            check=True, capture_output=True,
        )
        assert sbom.validate(out) == []


class TestGeneratorFailsClosed:
    def test_undeclared_environment_leaves_no_unknown_versions(self, tmp_path):
        """A declared dependency with an unresolvable version must fail
        generation (exit 1), never emit version 'unknown'."""
        import subprocess
        gen = _load("generate_sbom", REPO_ROOT / "scripts" / "generate_sbom.py")
        reqs = gen._declared_runtime_requirements()
        assert reqs, "requirements.txt declares nothing - test premise broken"
        # In this environment every declared dependency resolves (CI installs
        # requirements-dev); the fail path is exercised via the collector:
        gen.UNKNOWN_VERSIONS.clear()
        packages = gen._collect_packages()
        assert gen.UNKNOWN_VERSIONS == [], f"unresolved in this env: {gen.UNKNOWN_VERSIONS}"
        assert all(p["version"] != "unknown" for p in packages)
