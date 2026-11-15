#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# scripts/check_release_readiness.py — release-decision gate for the readiness
# checklist (#520/#452: NOT_TESTED must never count as a pass)
#
# Usage:
#   python3 scripts/check_release_readiness.py [docs/RELEASE_READINESS_CHECKLIST.md]
#
# Contract:
#   The checklist's "Evidence record" table carries a **Decision** cell.
#   - Decision claiming CUSTOMER/pilot readiness: every checklist row must be
#     PASS, WARN or N/A. Any FAIL or NOT_TESTED row blocks (exit 1), because
#     the status key defines both as blocking a customer release.
#   - Decision DEMO ONLY: FAIL/NOT_TESTED rows are reported but do not block.
#   - No readable Decision cell: exit 2 (fail safe — a gate that cannot tell
#     what was decided must not wave a release through).
#
# This gate reads the recorded decision; it never sets it. Hardware sections
# stay NOT_TESTED until real Pi acceptance is recorded (#381) — this script
# does not, and cannot, turn software checks into hardware acceptance.

from __future__ import annotations

import re
import sys
from pathlib import Path

_BLOCKING_STATUSES = ("FAIL", "NOT_TESTED")


def _decision(text: str) -> str | None:
    m = re.search(r"\|\s*\*\*Decision\*\*\s*\|\s*(.+?)\s*\|", text)
    return m.group(1) if m else None


def _blocking_rows(text: str) -> list[tuple[str, str]]:
    """(row label, status) for table rows whose status cell is FAIL/NOT_TESTED."""
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.split("|")]
        # data rows look like: ['', '1.1', 'check text', '✅ PASS', 'notes', '']
        if len(cells) < 5 or not re.fullmatch(r"\d+\.\d+", cells[1]):
            continue
        status_cell = cells[3].upper()
        for status in _BLOCKING_STATUSES:
            if status in status_cell:
                rows.append((f"{cells[1]} {cells[2]}", status))
                break
    return rows


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path("docs/RELEASE_READINESS_CHECKLIST.md")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: cannot read checklist {path}: {exc}")
        return 2

    decision = _decision(text)
    if decision is None:
        print("ERROR: no **Decision** cell found in the evidence record - fail safe")
        return 2
    print(f"Recorded decision: {decision}")

    rows = _blocking_rows(text)
    claims_customer = "CUSTOMER" in decision.upper() or "PILOT" in decision.upper()

    if not rows:
        print("No FAIL or NOT_TESTED rows.")
        return 0

    print(f"Rows with blocking status ({len(rows)}):")
    for label, status in rows:
        print(f"  [{status}] {label}")

    if claims_customer:
        print("ERROR: decision claims customer/pilot readiness but blocking rows exist")
        return 1
    print("Decision is demo-only: blocking rows reported, not blocking this gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
