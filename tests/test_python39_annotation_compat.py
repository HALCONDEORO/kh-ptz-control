#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Guardrail: the codebase must import on Python 3.9.2 (Raspberry Pi OS Bullseye).

The supported runtime target is Python 3.9.2 (see docs/RPI_RUNTIME_BASELINE.md).
PEP 604 union annotations (``X | None``) are valid syntax on 3.9 but are
*evaluated at import time* unless the module declares postponed annotation
evaluation. On Python 3.9 that evaluation raises::

    TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'

This was observed importing ``ui/config_dialog.py`` on a real Pi (3.9.2).

The clean fix is a single ``from __future__ import annotations`` at the top of
any module using PEP 604 unions — not a runtime import shim. This test fails if
a module slips through, so the 3.9 target stays real instead of relying on CI
happening to run a newer interpreter.

This is a precise AST check (annotations only); it does not false-positive on
comments, docstrings or string literals that merely contain ``| None``.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "venv",
    ".venv",
    "build",
    "dist",
    "worktrees",
    ".claude",
}
_FUTURE_IMPORT = "from __future__ import annotations"


def _iter_project_py_files():
    for path in _REPO_ROOT.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.relative_to(_REPO_ROOT).parts):
            continue
        yield path


def _annotation_nodes(tree: ast.AST):
    """Yield every annotation expression that Python evaluates at import time."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            yield node.annotation
        elif isinstance(node, ast.arg) and node.annotation is not None:
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
            yield node.returns


def _uses_pep604_union(annotation: ast.AST) -> bool:
    return any(
        isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr)
        for sub in ast.walk(annotation)
    )


def test_no_pep604_union_annotations_without_future_import():
    offenders: list[str] = []

    for path in _iter_project_py_files():
        source = path.read_text(encoding="utf-8")
        if _FUTURE_IMPORT in source:
            continue
        tree = ast.parse(source)
        bad_lines = sorted(
            {
                ann.lineno
                for ann in _annotation_nodes(tree)
                if _uses_pep604_union(ann)
            }
        )
        if bad_lines:
            rel = path.relative_to(_REPO_ROOT).as_posix()
            offenders.append(f"{rel}: lines {bad_lines}")

    assert not offenders, (
        "These modules use PEP 604 `X | Y` annotations evaluated at import time "
        "but lack `from __future__ import annotations`. They will raise TypeError "
        "on Python 3.9.2 (the supported target). Add the future import as the "
        "first statement:\n  " + "\n  ".join(offenders)
    )

