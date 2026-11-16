#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Check consistency of doctor evidence, not physical hardware acceptance.

Reads doctor JSON from stdin; emits only a fixed diagnostic, not report values.
Sequential human/JSON runs can observe different state. A mismatch needs review,
never automatic repair or promotion to an accepted result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from domain.doctor_outcome import CheckCategory, DoctorOutcome, derive_outcome, exit_code_for  # noqa: E402


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("non-JSON numeric constant")


def validate(raw: str, human_rc: int, json_rc: int, human_outcome: str) -> None:
    doc = json.loads(raw, object_pairs_hook=_unique, parse_constant=_invalid_constant)
    if not isinstance(doc, dict):
        raise ValueError("doctor JSON is not an object")
    outcome = DoctorOutcome(doc.get("outcome"))
    if type(doc.get("exit_code")) is not int:
        raise ValueError("doctor JSON exit_code is not an integer")
    if not (human_rc == json_rc == doc["exit_code"] == exit_code_for(outcome)):
        raise ValueError("doctor process codes and JSON outcome disagree")
    if human_outcome != outcome.value:
        raise ValueError("human and JSON doctor outcomes disagree")
    checks = doc.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("doctor JSON checks are missing or empty")
    keys = set()
    normalized = []
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError("doctor check is not an object")
        key, severity, blocking = check.get("key"), check.get("severity"), check.get("blocking")
        if not isinstance(key, str) or not key.strip() or key in keys:
            raise ValueError("doctor check key is missing or repeated")
        if severity not in ("OK", "WARNING", "ERROR") or type(blocking) is not bool:
            raise ValueError("doctor check severity or blocking flag is invalid")
        category = CheckCategory(check.get("category"))
        keys.add(key)
        normalized.append((severity, blocking, category))
    unhealthy = [row for row in normalized if row[0] != "OK"]
    derived = derive_outcome(
        has_blocking_failure=any(severity == "ERROR" or blocking for severity, blocking, _ in unhealthy),
        has_actionable_issue=any(category in (CheckCategory.CONFIGURATION, CheckCategory.OPERATIONAL)
                                 for _, _, category in unhealthy),
        has_advisory=any(category == CheckCategory.ADVISORY for _, _, category in unhealthy),
    )
    overall = ("FAIL" if any(row[0] == "ERROR" for row in normalized) else
               "WARNING" if unhealthy else "OK")
    if derived != outcome or doc.get("overall") != overall:
        raise ValueError("doctor JSON summary disagrees with its checks")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--human-rc", type=int, required=True)
    parser.add_argument("--json-rc", type=int, required=True)
    parser.add_argument("--human-outcome", required=True)
    args = parser.parse_args(argv)
    try:
        validate(sys.stdin.read(), args.human_rc, args.json_rc, args.human_outcome)
    except (ValueError, TypeError, RecursionError):
        # Never echo user-controlled report fields or exception text.
        print("Doctor evidence is malformed or inconsistent; acceptance needs review", file=sys.stderr)
        return 1
    print("Doctor JSON structure, summaries and human/process outcomes agree; not hardware acceptance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
