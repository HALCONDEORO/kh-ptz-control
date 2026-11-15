#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# scripts/check_release_readiness.py — release-decision gate for the readiness
# checklist (#520/#452: NOT_TESTED must never count as a pass)
#
# Usage:
#   python3 scripts/check_release_readiness.py [docs/RELEASE_READINESS_CHECKLIST.md]
#
# What it checks: the internal consistency of the CURRENT candidate record
# (the region between the "## Current candidate" heading and the archived
# evidence below it). It enforces the policy the document itself publishes:
#   - DEMO ONLY        - no FAIL anywhere; sections 1, 2, 3, 5, 6 all
#                        PASS/WARN/N/A (NOT_TESTED there blocks the demo claim)
#   - CUSTOMER READY   - PASS only; any FAIL or NOT_TESTED blocks, and every
#                        WARN row must carry written acceptance ("accepted")
#                        in its notes
# The decision must be recorded as "**Current decision:** DEMO ONLY" (or
# CUSTOMER READY). Missing or unrecognised decision, zero rows, mis-numbered
# rows (9 instead of 9.1) or statuses outside the published key are schema
# violations: exit 2, fail closed. Malformed or missing coverage never
# counts as PASS.
#
# This gate checks the consistency of the record. It does not accept a
# release, does not set the decision, and cannot turn software checks into
# hardware acceptance: hardware sections stay NOT_TESTED until real Pi
# acceptance is recorded (#381).

from __future__ import annotations

import re
import sys
from pathlib import Path

_ALLOWED_STATUSES = ("PASS", "WARN", "FAIL", "N/A", "NOT_TESTED")
_DEMO_CLEAN_SECTIONS = {"1", "2", "3", "5", "6"}


def _current_region(text: str) -> str | None:
    """The current-candidate record, excluding archived historical evidence."""
    m = re.search(r"^## Current candidate\b.*$", text, re.M)
    if not m:
        return None
    rest = text[m.start():]
    end = re.search(r"^## ", rest[len(m.group(0)):], re.M)
    return rest[: len(m.group(0)) + end.start()] if end else rest


def _decision(region: str) -> str | None:
    m = re.search(r"\*\*Current decision:\*\*\s*(.+?)\s*$", region, re.M)
    if not m:
        return None
    value = m.group(1).replace("*", "").strip().upper()
    if value.startswith("DEMO"):
        return "demo"
    if value.startswith("CUSTOMER READY") or value.startswith("PILOT READY"):
        return "customer"
    return None


def _rows(region: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[str]]:
    """(blocking, unaccepted_warns, malformed) for the current record."""
    blocking: list[tuple[str, str]] = []
    unaccepted_warns: list[tuple[str, str]] = []
    malformed: list[str] = []
    total = 0
    for line in region.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 5:
            continue
        row_id, status_cell, notes = cells[1], cells[3], cells[4]
        if re.fullmatch(r"\d+", row_id):
            malformed.append(f"row '{row_id}' has no sub-number (expected X.Y)")
            continue
        m = re.fullmatch(r"(\d+)\.\d+", row_id)
        if not m:
            continue
        total += 1
        section = m.group(1)
        status_upper = status_cell.upper()
        matched = [st for st in _ALLOWED_STATUSES if st in status_upper]
        if len(matched) != 1:
            malformed.append(
                f"row {row_id} status {status_cell!r} is not exactly one of "
                f"{'/'.join(_ALLOWED_STATUSES)}"
            )
            continue
        label = f"{row_id} {cells[2]}"
        if matched[0] == "FAIL":
            blocking.append((label, "FAIL"))
        elif matched[0] == "NOT_TESTED" and section in _DEMO_CLEAN_SECTIONS:
            blocking.append((label, "NOT_TESTED in demo-clean section"))
        elif matched[0] == "WARN" and "accept" not in notes.lower():
            unaccepted_warns.append((label, "WARN without written acceptance"))
    if total == 0 and not malformed:
        malformed.append("no checklist rows in the current record - coverage cannot be proven")
    return blocking, unaccepted_warns, malformed


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path("docs/RELEASE_READINESS_CHECKLIST.md")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read checklist {path}: {exc}")
        return 2

    region = _current_region(text)
    if region is None:
        print("ERROR: no '## Current candidate' record found - fail closed")
        return 2

    decision = _decision(region)
    if decision is None:
        print("ERROR: '**Current decision:**' missing or not DEMO ONLY / CUSTOMER READY - fail closed")
        return 2

    blocking, unaccepted_warns, malformed = _rows(region)
    if malformed:
        print("ERROR: checklist schema violations:")
        for item in malformed:
            print(f"  {item}")
        return 2

    print(f"Recorded decision: {'DEMO ONLY' if decision == 'demo' else 'CUSTOMER READY'}")

    problems = list(blocking)
    if decision == "customer":
        problems += unaccepted_warns
        # NOT_TESTED outside the demo-clean sections only blocks CUSTOMER.
        for line in region.splitlines():
            cells = [c.strip() for c in line.split("|")]
            if len(cells) >= 5 and re.fullmatch(r"\d+\.\d+", cells[1]) and "NOT_TESTED" in cells[3].upper():
                label = f"{cells[1]} {cells[2]}"
                if not any(label == b[0] for b in blocking):
                    problems.append((label, "NOT_TESTED"))
    if problems:
        print(f"Blocking findings ({len(problems)}):")
        for label, why in problems:
            print(f"  [{why}] {label}")
        print("ERROR: recorded decision is inconsistent with the recorded rows")
        return 1

    print("Recorded decision is consistent with the recorded rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
