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
#                        WARN row must carry written acceptance
#
# Strict contracts (fail closed, exit 2, never inferred):
#   - The decision must be recorded as "**Current decision:** DEMO ONLY" or
#     "**Current decision:** CUSTOMER READY" - exact equality after stripping
#     markdown asterisks and extra whitespace. No prefix or substring match:
#     "DEMONSTRATION ..." or "CUSTOMER READY NOT APPROVED" are schema errors.
#   - Row ids must be numbered X.Y ("9" alone is a schema error).
#   - Statuses must equal exactly one of PASS / WARN / FAIL / N/A / NOT_TESTED
#     after removing an optional published emoji and normalising case/whitespace.
#     "NOT_PASS" or "PENDING" are schema errors, never silently bucketed.
#   - Coverage: the current record must contain at least one row for every
#     published section 1-12. Zero rows or missing sections are schema
#     errors - absent coverage never counts as PASS.
#   - Written acceptance is a structured field: a WARN counts as accepted
#     only when its Notes cell begins with the exact token "ACCEPTED: "
#     followed by who/when. Prose such as "not accepted by reviewer" never
#     counts.
#
# Exit codes: 0 = recorded decision consistent with recorded rows;
# 1 = decision not backed by the rows (named findings);
# 2 = schema violation / unreadable checklist (fail closed).
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
_REQUIRED_SECTIONS = {str(n) for n in range(1, 13)}
_DEMO_CLEAN_SECTIONS = {"1", "2", "3", "5", "6"}
_DECISIONS = {"DEMO ONLY": "demo", "CUSTOMER READY": "customer"}
_ACCEPTANCE_RE = re.compile(r"^ACCEPTED:\s*\S")


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
    value = re.sub(r"\s+", " ", m.group(1).replace("*", "").strip()).upper()
    return _DECISIONS.get(value)


def _normalise_status(status_cell: str) -> str | None:
    """Exact status after removing emoji/symbols; None when not in the enum."""
    # Strip only an optional published display icon, never arbitrary data.
    # Removing arbitrary symbols/digits turns PASS123 / !PASS into PASS.
    token = re.sub(r"^(?:✅|⚠️?|❌|🔲)\s*", "", status_cell.strip())
    token = re.sub(r"\s+", " ", token).strip().upper()
    return token if token in _ALLOWED_STATUSES else None


def _rows(
    region: str,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]], list[str]]:
    """(fail_rows, not_tested_rows, unaccepted_warns, malformed)."""
    fails: list[tuple[str, str]] = []
    not_tested: list[tuple[str, str]] = []
    unaccepted_warns: list[tuple[str, str]] = []
    malformed: list[str] = []
    sections_seen: set[str] = set()
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
        section = m.group(1)
        sections_seen.add(section)
        status = _normalise_status(status_cell)
        if status is None:
            malformed.append(
                f"row {row_id} status {status_cell!r} is not exactly one of "
                f"{'/'.join(_ALLOWED_STATUSES)}"
            )
            continue
        label = f"{row_id} {cells[2]}"
        if status == "FAIL":
            fails.append((label, "FAIL"))
        elif status == "NOT_TESTED":
            not_tested.append((label, section))
        elif status == "WARN" and not _ACCEPTANCE_RE.match(notes):
            unaccepted_warns.append((label, "WARN without written acceptance ('ACCEPTED: ...)"))
    if not sections_seen:
        malformed.append("no checklist rows in the current record - coverage cannot be proven")
    else:
        missing = sorted(_REQUIRED_SECTIONS - sections_seen, key=int)
        if missing:
            malformed.append(
                "current record is missing rows for section(s) "
                + ", ".join(missing)
                + " - all 12 published sections must be covered"
            )
    return fails, not_tested, unaccepted_warns, malformed


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
        print(
            "ERROR: '**Current decision:**' missing or not exactly 'DEMO ONLY' / "
            "'CUSTOMER READY' - fail closed"
        )
        return 2

    fails, not_tested, unaccepted_warns, malformed = _rows(region)
    if malformed:
        print("ERROR: checklist schema violations:")
        for item in malformed:
            print(f"  {item}")
        return 2

    print(f"Recorded decision: {'DEMO ONLY' if decision == 'demo' else 'CUSTOMER READY'}")

    problems: list[tuple[str, str]] = list(fails)
    for label, section in not_tested:
        if section in _DEMO_CLEAN_SECTIONS or decision == "customer":
            problems.append((label, "NOT_TESTED"))
    if decision == "customer":
        problems += unaccepted_warns

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
