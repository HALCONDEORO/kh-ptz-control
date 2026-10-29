#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/diagnostics_presenter.py — Pure display formatter for DiagnosticsReport
#
# Turns a DiagnosticsReport (from DiagnosticsService.run()) into display-ready
# rows and an overall summary, with NO PyQt / I/O. This keeps the "how do we
# show doctor results" logic testable without a running Qt stack, so the admin
# in-app diagnostics panel and any other surface render the same way.

from __future__ import annotations

from dataclasses import dataclass

from application.diagnostics_service import DiagnosticsReport, Status

# Short fixed-width labels so rows align in a monospace view.
_STATUS_LABEL = {Status.OK: "OK", Status.WARNING: "WARN", Status.FAIL: "FAIL"}


def _label(status: Status) -> str:
    return _STATUS_LABEL.get(status, "?")


@dataclass(frozen=True)
class DiagnosticsRow:
    """One rendered check line."""

    status: str  # "OK" | "WARN" | "FAIL" | "?"
    name: str
    message: str
    suggested_action: str | None = None

    @property
    def text(self) -> str:
        line = f"[{self.status:4}] {self.name}: {self.message}"
        if self.suggested_action:
            line += f"  → {self.suggested_action}"
        return line


@dataclass(frozen=True)
class DiagnosticsView:
    """Display-ready view of a whole diagnostics run."""

    overall: str  # "OK" | "WARN" | "FAIL" | "?"
    rows: list[DiagnosticsRow]

    @property
    def counts(self) -> dict[str, int]:
        out = {"OK": 0, "WARN": 0, "FAIL": 0}
        for r in self.rows:
            if r.status in out:
                out[r.status] += 1
        return out

    @property
    def summary(self) -> str:
        c = self.counts
        return f"{c['OK']} ok · {c['WARN']} warning · {c['FAIL']} failed"

    @property
    def text_lines(self) -> list[str]:
        return [r.text for r in self.rows]


def build_view(report: DiagnosticsReport) -> DiagnosticsView:
    """Build a pure, display-ready view from a diagnostics report."""
    rows = [
        DiagnosticsRow(
            status=_label(c.status),
            name=c.name,
            message=c.message,
            suggested_action=c.suggested_action,
        )
        for c in report.checks
    ]
    return DiagnosticsView(overall=_label(report.overall), rows=rows)
