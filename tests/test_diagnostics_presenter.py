#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_diagnostics_presenter.py — Pure DiagnosticsReport → display view (#diag-panel)

from __future__ import annotations

from application.diagnostics_presenter import build_view
from application.diagnostics_service import CheckResult, DiagnosticsReport, Status


def _report() -> DiagnosticsReport:
    report = DiagnosticsReport()
    report.add(CheckResult("version", Status.OK, "3.38.3"))
    report.add(CheckResult("disk", Status.WARNING, "low space",
                           suggested_action="free up space"))
    report.add(CheckResult("config", Status.FAIL, "missing config.yaml"))
    return report


def test_overall_is_worst_status():
    view = build_view(_report())
    assert view.overall == "FAIL"


def test_rows_preserve_order_and_fields():
    view = build_view(_report())
    assert [r.name for r in view.rows] == ["version", "disk", "config"]
    assert view.rows[0].status == "OK"
    assert view.rows[1].status == "WARN"
    assert view.rows[2].status == "FAIL"


def test_suggested_action_appears_in_text():
    view = build_view(_report())
    assert "→ free up space" in view.rows[1].text
    # A check without a suggestion has no arrow.
    assert "→" not in view.rows[0].text


def test_summary_counts():
    view = build_view(_report())
    assert view.counts == {"OK": 1, "WARN": 1, "FAIL": 1}
    assert view.summary == "1 ok · 1 warning · 1 failed"


def test_all_ok_report_is_ok():
    report = DiagnosticsReport()
    report.add(CheckResult("a", Status.OK, "fine"))
    report.add(CheckResult("b", Status.OK, "fine"))
    view = build_view(report)
    assert view.overall == "OK"
    assert view.text_lines == ["[OK  ] a: fine", "[OK  ] b: fine"]

