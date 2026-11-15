# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Offline report fixtures, not real vulnerability database evidence."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("check_sbom_audit", Path(__file__).resolve().parents[1] / "scripts/check_sbom_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

SBOM = {"bomFormat": "CycloneDX", "components": [
    {"type": "library", "name": "A", "version": "1.0", "purl": "pkg:pypi/a@1.0"},
    {"type": "library", "name": "Some_Name", "version": "2.0", "purl": "pkg:pypi/some-name@2.0"}]}
REPORT = {"dependencies": [{"name": "a", "version": "1.0", "vulns": []},
                           {"name": "some-name", "version": "2.0", "vulns": []}], "fixes": []}


def write(tmp_path, doc, name):
    p = tmp_path / name
    p.write_text(json.dumps(doc))
    return p


def test_matching_exact_pins_and_normalized_names(tmp_path):
    assert audit.check(write(tmp_path, SBOM, "sbom"), write(tmp_path, REPORT, "report")) == 2


def test_export_exact_sorted_pins_and_refuse_overwrite(tmp_path):
    source = write(tmp_path, SBOM, "sbom")
    dest = tmp_path / "pins"
    assert audit.main([str(source), "--write-requirements", str(dest)]) == 0
    assert dest.read_text() == "a==1.0\nsome-name==2.0\n"
    dest.write_text("preserve")
    assert audit.main([str(source), "--write-requirements", str(dest)]) == 1
    assert dest.read_text() == "preserve"


@pytest.mark.parametrize("change", [
    lambda d: d.update(dependencies=[]),
    lambda d: d["dependencies"].pop(),
    lambda d: d["dependencies"].append(d["dependencies"][0].copy()),
    lambda d: d["dependencies"][0].update(version="1.1"),
    lambda d: d["dependencies"][0].update(name="other"),
    lambda d: d["dependencies"][0].update(skip_reason="not found"),
    lambda d: d["dependencies"][0].pop("vulns"),
    lambda d: d["dependencies"][0].update(vulns=None),
    lambda d: d["dependencies"][0].update(vulns=[{"id": "FIXTURE-low", "severity": "LOW"}]),
    lambda d: d.update(fixes=[{"name": "a", "new_version": "2"}]),
    lambda d: d.pop("fixes"),
    lambda d: d.update(dependencies={}),
])
def test_incomplete_mismatched_or_vulnerable_report_rejected(tmp_path, change):
    report = copy.deepcopy(REPORT)
    change(report)
    assert audit.main([str(write(tmp_path, SBOM, "sbom")), "--audit-report",
                       str(write(tmp_path, report, "report"))]) == 1


@pytest.mark.parametrize("change", [
    lambda d: d.update(components=[]),
    lambda d: d.update(bomFormat="other"),
    lambda d: d["components"].append(d["components"][0].copy()),
    lambda d: d["components"][0].update(name="a\n--index-url=https://example.invalid"),
    lambda d: d["components"][0].update(version=">=1"),
    lambda d: d["components"][0].update(purl="pkg:pypi/other@1.0"),
    lambda d: d["components"][0].update(type="application"),
])
def test_unsafe_or_ambiguous_sbom_fails_without_export(tmp_path, change):
    sbom = copy.deepcopy(SBOM)
    change(sbom)
    dest = tmp_path / "pins"
    assert audit.main([str(write(tmp_path, sbom, "sbom")), "--write-requirements", str(dest)]) == 1
    assert not dest.exists()


@pytest.mark.parametrize("raw", ['{"dependencies":[],"dependencies":[],"fixes":[]}', '[]', 'not json'])
def test_malformed_or_duplicate_json_rejected(tmp_path, raw):
    report = tmp_path / "report"
    report.write_text(raw)
    assert audit.main([str(write(tmp_path, SBOM, "sbom")), "--audit-report", str(report)]) == 1


def test_missing_report_is_not_clean(tmp_path):
    assert audit.main([str(write(tmp_path, SBOM, "sbom")), "--audit-report", str(tmp_path / "missing")]) == 1
