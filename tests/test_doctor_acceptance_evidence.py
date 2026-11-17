# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Offline evidence consistency, never a physical Pi acceptance claim."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/check_doctor_acceptance.py"
spec = importlib.util.spec_from_file_location("check_doctor_acceptance", HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def report(severity="OK", category="configuration", blocking=False):
    from domain.doctor_outcome import CheckCategory, derive_outcome, exit_code_for
    outcome = derive_outcome(
        has_blocking_failure=severity == "ERROR" or (severity != "OK" and blocking),
        has_actionable_issue=severity != "OK" and CheckCategory(category) in (
            CheckCategory.CONFIGURATION, CheckCategory.OPERATIONAL),
        has_advisory=severity != "OK" and category == "advisory",
    )
    return {"overall": {"OK": "OK", "WARNING": "WARNING", "ERROR": "FAIL"}[severity],
            "outcome": outcome.value, "exit_code": exit_code_for(outcome),
            "checks": [{"key": "fixture", "severity": severity, "category": category,
                        "blocking": blocking}]}


def valid(doc):
    module.validate(json.dumps(doc), doc["exit_code"], doc["exit_code"], doc["outcome"])


@pytest.mark.parametrize("severity", ["OK", "WARNING", "ERROR"])
@pytest.mark.parametrize("category", ["configuration", "operational", "advisory"])
@pytest.mark.parametrize("blocking", [False, True])
def test_domain_matrix(severity, category, blocking):
    valid(report(severity, category, blocking))


@pytest.mark.parametrize("raw", ["garbage", "", "[]", "null", "{}", "true", "1", "NaN", "Infinity",
                                  '{"outcome":"PASS","outcome":"FAIL"}'])
def test_malformed(raw):
    with pytest.raises((ValueError, TypeError)):
        module.validate(raw, 0, 0, "PASS")


@pytest.mark.parametrize("path,value", [
    (("exit_code",), False), (("exit_code",), "0"), (("exit_code",), 10),
    (("outcome",), "FAIL"), (("overall",), "FAIL"), (("checks",), []),
    (("checks",), None), (("checks",), [None]),
    (("checks", 0, "severity"), "UNKNOWN"), (("checks", 0, "severity"), "NOT_APPLICABLE"),
    (("checks", 0, "severity"), "ERROR"), (("checks", 0, "category"), "unknown"),
    (("checks", 0, "blocking"), "false"), (("checks", 0, "blocking"), 0),
    (("checks", 0, "key"), ""), (("checks", 0, "key"), None),
])
def test_invalid_or_dishonest_summary(path, value):
    doc = report()
    parent = doc
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises((ValueError, TypeError)):
        valid(doc)


def test_duplicate_check_rejected():
    doc = report()
    doc["checks"].append(copy.deepcopy(doc["checks"][0]))
    with pytest.raises(ValueError):
        valid(doc)


@pytest.mark.parametrize("human_rc,json_rc,human", [
    (10, 0, "PASS"), (0, 10, "PASS"), (0, 0, "FAIL"),
    (0, 0, ""), (0, 0, "PASS\nPASS"), (127, 127, "PASS"),
])
def test_process_or_human_mismatch(human_rc, json_rc, human):
    with pytest.raises(ValueError):
        module.validate(json.dumps(report()), human_rc, json_rc, human)


def run_section(script, tmp_path, raw, rc=0, human="PASS"):
    """Run the actual diagnostics shell section with all appliance CLI stubbed."""
    text = Path(script).read_text()
    start = text.index('head2 "Diagnostics (')
    end = text.index('# ── Service / GUI wiring', start)
    stubbin = tmp_path / "bin"
    stubbin.mkdir(exist_ok=True)
    cli = stubbin / "khptz"
    cli.write_text('#!/bin/bash\nexit 99\n')
    cli.chmod(0o755)
    payload = tmp_path / "payload.json"
    payload.write_text(raw)
    body = '''
head2() { :; }
pass() { printf 'PASS %s\\n' "$*"; }
fail() { printf 'FAIL %s\\n' "$*"; }
say() { :; }
cli_as_service() {
    if [[ "$2" == doctor ]]; then
        if [[ "$3" == --json ]]; then cat "$PAYLOAD";
        else printf '  Outcome: %s\\n' "$HUMAN"; fi
        return "$DOCTOR_RC"
    fi
    return 0
}
'''
    import os
    return subprocess.run(["bash", "-c", body + text[start:end]], text=True,
        capture_output=True, check=True, env={**os.environ,
        "PATH": f"{stubbin}:{os.environ['PATH']}", "REPORT": str(tmp_path / "report.txt"),
        "ACCEPTANCE_SCRIPT_DIR": str(HELPER.parent), "PAYLOAD": str(payload),
        "HUMAN": human, "DOCTOR_RC": str(rc)}).stdout


@pytest.mark.parametrize("doc", [report(), report("WARNING", "advisory"),
                                  report("WARNING"), report("ERROR")])
def test_shell_admits_consistent_evidence_but_keeps_config_and_fail_red(tmp_path, doc):
    out = run_section(ROOT / "scripts/validate_rpi_acceptance.sh", tmp_path,
                      json.dumps(doc), doc["exit_code"], doc["outcome"])
    assert "PASS khptz doctor JSON structure and outcomes agree" in out
    if doc["exit_code"] in (20, 30):
        assert "FAIL doctor outcome:" in out


@pytest.mark.parametrize("raw", ["not-json", json.dumps({**report(), "outcome": "FAIL"}),
                                  json.dumps({**report(), "checks": []})])
def test_shell_rejects_equal_process_codes_with_invalid_evidence(tmp_path, raw):
    out = run_section(ROOT / "scripts/validate_rpi_acceptance.sh", tmp_path, raw)
    assert "FAIL doctor JSON is malformed or disagrees" in out
    assert "PASS khptz doctor JSON" not in out


def test_helper_missing_fails_closed(tmp_path):
    text = (ROOT / "scripts/validate_rpi_acceptance.sh").read_text()
    replacement = tmp_path / "harness.sh"
    replacement.write_text(text.replace('"${ACCEPTANCE_SCRIPT_DIR}/check_doctor_acceptance.py"',
                                        '"/nonexistent/check_doctor_acceptance.py"'))
    out = run_section(replacement, tmp_path, json.dumps(report()))
    assert "FAIL doctor JSON is malformed or disagrees" in out


def test_cli_error_does_not_echo_report_contents():
    import sys
    result = subprocess.run([sys.executable, str(HELPER), "--human-rc", "0", "--json-rc", "0",
                             "--human-outcome", "PASS"], input='SENSITIVE_FIXTURE', text=True,
                            capture_output=True)
    assert result.returncode == 1
    assert "SENSITIVE_FIXTURE" not in result.stdout + result.stderr


@pytest.mark.parametrize("severity_name", ["OK", "WARNING", "FAIL"])
@pytest.mark.parametrize("category_name", ["CONFIGURATION", "OPERATIONAL", "ADVISORY"])
@pytest.mark.parametrize("blocking", [False, True])
def test_accepts_real_report_serialization(severity_name, category_name, blocking):
    from application.diagnostics_service import CheckResult, DiagnosticsReport, Status
    from domain.doctor_outcome import CheckCategory
    real = DiagnosticsReport([CheckResult("fixture", getattr(Status, severity_name), "fixture",
                                         blocking=blocking,
                                         category=getattr(CheckCategory, category_name))])
    doc = real.to_json_dict()
    module.validate(json.dumps(doc), real.exit_code, real.exit_code, real.outcome.value)
