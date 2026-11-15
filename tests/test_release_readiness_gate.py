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


def _row(section: int, status: str = "✅ PASS", notes: str = "verified") -> str:
    return f"| {section}.1 | section {section} check | {status} | {notes} |"


def _full_coverage(overrides: dict[int, str] | None = None) -> str:
    """One row per published section 1-12 - the minimum valid coverage."""
    overrides = overrides or {}
    return "\n".join(overrides.get(n, _row(n)) for n in range(1, 13))


def _write(tmp_path: Path, decision: str, rows: str) -> Path:
    p = tmp_path / "CHECKLIST.md"
    p.write_text(CHECKLIST.format(decision=decision, rows=rows), encoding="utf-8")
    return p


def _run(tmp_path: Path, decision: str, rows: str) -> int:
    return readiness.main(["prog", str(_write(tmp_path, decision, rows))])


class TestDecisionEnum:
    def test_demo_passes_when_consistent(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", _full_coverage()) == 0

    def test_decision_match_is_exact_not_prefix(self, tmp_path):
        assert _run(tmp_path, "DEMONSTRATION BANANA", _full_coverage()) == 2
        assert _run(tmp_path, "CUSTOMER READY NOT APPROVED", _full_coverage()) == 2

    def test_unknown_decision_fails_closed(self, tmp_path):
        assert _run(tmp_path, "BANANA", _full_coverage()) == 2

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
        rows = _full_coverage({2: _row(2, "🔲 NOT_TESTED", "not run")})
        assert _run(tmp_path, "DEMO ONLY", rows) == 1

    def test_not_tested_in_hardware_section_ok_for_demo(self, tmp_path):
        rows = _full_coverage({9: _row(9, "🔲 NOT_TESTED", "awaits Pi")})
        assert _run(tmp_path, "DEMO ONLY", rows) == 0

    def test_fail_anywhere_blocks_demo(self, tmp_path):
        rows = _full_coverage({8: _row(8, "❌ FAIL", "broken")})
        assert _run(tmp_path, "DEMO ONLY", rows) == 1


class TestCustomerPolicy:
    def test_customer_blocks_any_not_tested(self, tmp_path):
        rows = _full_coverage({9: _row(9, "🔲 NOT_TESTED", "awaits Pi")})
        assert _run(tmp_path, "CUSTOMER READY", rows) == 1

    def test_customer_warn_requires_written_acceptance(self, tmp_path):
        rows = _full_coverage({3: _row(3, "⚠️ WARN", "caveat")})
        assert _run(tmp_path, "CUSTOMER READY", rows) == 1

    def test_negative_prose_is_not_acceptance(self, tmp_path):
        rows = _full_coverage({3: _row(3, "⚠️ WARN", "not accepted by reviewer")})
        assert _run(tmp_path, "CUSTOMER READY", rows) == 1

    def test_lowercase_prose_is_not_acceptance(self, tmp_path):
        rows = _full_coverage({3: _row(3, "⚠️ WARN", "accepted: documented exception")})
        assert _run(tmp_path, "CUSTOMER READY", rows) == 1

    def test_structured_acceptance_field_passes(self, tmp_path):
        rows = _full_coverage({3: _row(3, "⚠️ WARN", "ACCEPTED: reviewer Jane, 2026-11-15")})
        assert _run(tmp_path, "CUSTOMER READY", rows) == 0

    def test_demo_warn_needs_no_acceptance(self, tmp_path):
        rows = _full_coverage({3: _row(3, "⚠️ WARN", "caveat")})
        assert _run(tmp_path, "DEMO ONLY", rows) == 0


class TestSchemaCoverage:
    def test_zero_rows_fails_closed(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", "| --- | --- | --- | --- |") == 2

    def test_single_row_is_incomplete_coverage(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", _row(1)) == 2

    def test_missing_one_section_fails_closed(self, tmp_path):
        rows = "\n".join(_row(n) for n in range(1, 13) if n != 7)
        assert _run(tmp_path, "DEMO ONLY", rows) == 2

    def test_unknown_status_fails_closed(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", _full_coverage({1: _row(1, "PENDING", "later")})) == 2

    def test_status_match_is_exact_not_substring(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", _full_coverage({1: _row(1, "NOT_PASS", "x")})) == 2
        assert _run(tmp_path, "DEMO ONLY", _full_coverage({1: _row(1, "PASSING", "x")})) == 2

    @pytest.mark.parametrize("bad", ["PASS123", "!PASS", "PASS!", "P.A.S.S", "N/A0", "NOT TESTED", "✅ PASS123"])
    def test_status_never_discards_non_emoji_data(self, tmp_path, bad):
        assert _run(tmp_path, "DEMO ONLY", _full_coverage({1: _row(1, bad, "x")})) == 2

    def test_published_na_icon_is_supported(self, tmp_path):
        assert readiness._normalise_status("➖ N/A") == "N/A"
        assert _run(tmp_path, "DEMO ONLY", _full_coverage({9: _row(9, "➖ N/A", "not applicable")})) == 0

    def test_bare_section_number_fails_closed(self, tmp_path):
        assert _run(tmp_path, "DEMO ONLY", "| 9 | x | ✅ PASS | ok |") == 2

    def test_archived_rows_are_ignored(self, tmp_path):
        # The template's archived block contains FAIL and NOT_TESTED rows.
        assert _run(tmp_path, "DEMO ONLY", _full_coverage()) == 0

    def test_missing_file_fails_closed(self, tmp_path):
        assert readiness.main(["prog", str(tmp_path / "nope.md")]) == 2


class TestRealChecklist:
    def test_shipped_checklist_records_real_gaps(self, capsys):
        """The shipped checklist is the real record: sections 3 (git-history
        scrub, limitation 2), 5 (doctor never gated in CI) and 6 (network
        never validated on target hardware) are open gaps, so the recorded
        DEMO ONLY decision is NOT yet backed. The gate must report those
        findings (exit 1) - the record may fail; rows must never be edited
        to make the gate pass without re-verification evidence."""
        rc = readiness.main(
            ["prog", str(REPO_ROOT / "docs" / "RELEASE_READINESS_CHECKLIST.md")]
        )
        out = capsys.readouterr().out
        assert rc == 1
        assert "3.1" in out
        assert "5.2" in out
        assert "6.1" in out


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
        gen = _load("generate_sbom", REPO_ROOT / "scripts" / "generate_sbom.py")
        reqs = gen._declared_runtime_requirements()
        assert reqs, "requirements.txt declares nothing - test premise broken"
        # In this environment every declared dependency resolves (CI installs
        # requirements-dev); the fail path is exercised via the collector:
        gen.UNKNOWN_VERSIONS.clear()
        packages = gen._collect_packages()
        assert gen.UNKNOWN_VERSIONS == [], f"unresolved in this env: {gen.UNKNOWN_VERSIONS}"
        assert all(p["version"] != "unknown" for p in packages)
