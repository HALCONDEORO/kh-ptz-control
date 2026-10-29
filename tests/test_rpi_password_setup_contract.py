#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Regression tests for Raspberry Pi password setup robustness.

Two failure modes observed on real Raspberry Pi installs:

1. The password setup tool printed Unicode (accents, arrows, check marks). On a
   headless Pi terminal with a C / ISO-8859-* locale, writing those to stdout or
   the tty raises UnicodeEncodeError and aborts the setup.
2. Docs and the `password.enc` remediation message tell the technician to run
   `python3 setup_password.py`, but no such file existed at the repo root, so the
   documented command failed with "No such file or directory".
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_setup_password_source_is_ascii_safe():
    """Setup output must not require a Unicode-capable terminal."""
    source = (_REPO_ROOT / "runtime" / "setup_password.py").read_text(encoding="utf-8")
    # Raises UnicodeEncodeError (failing the test) if any non-ASCII char slips in.
    source.encode("ascii")


def test_root_setup_password_wrapper_exists_and_delegates():
    """The documented `python3 setup_password.py` command must keep working."""
    wrapper = _REPO_ROOT / "setup_password.py"
    assert wrapper.exists(), "root setup_password.py wrapper is missing"
    text = wrapper.read_text(encoding="utf-8")
    assert "from runtime.setup_password import main" in text


def test_secret_manager_remediation_command_resolves():
    """The remediation in secret_manager must point at a command that exists."""
    source = (_REPO_ROOT / "runtime" / "secret_manager.py").read_text(encoding="utf-8")
    assert "setup_password" in source
    # Whichever form the message uses, the corresponding entry point must exist.
    if "python3 setup_password.py" in source:
        assert (_REPO_ROOT / "setup_password.py").exists()
    if "runtime.setup_password" in source:
        assert (_REPO_ROOT / "runtime" / "setup_password.py").exists()


def test_setup_password_modules_parse_and_import_cleanly():
    """Static + real import sanity (modules must not run prompts at import time)."""
    for rel in ("runtime/setup_password.py", "setup_password.py"):
        ast.parse((_REPO_ROOT / rel).read_text(encoding="utf-8"))
    import importlib

    importlib.import_module("runtime.setup_password")

