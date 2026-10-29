#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_dangerous_api_guard.py — the appliance stays free of the classic RCE vectors
#
# The security review found these clean. This pins them, because each is a
# one-line mistake away from returning and none is caught by ruff:
#
#   * yaml.load without SafeLoader executes arbitrary Python from a config file
#     — and config.yaml is operator-editable on the appliance;
#   * pickle deserialises to arbitrary objects, so it must never touch a file
#     or a socket payload;
#   * eval/exec turn any parsed value into code;
#   * subprocess with shell=True or a string command turns a camera name, an IP
#     or a path into a shell injection.
#
# Scoped to the shipped application: tests may legitimately use eval-like
# helpers, and the vendored dependencies under venv/ are not ours.

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Directories rsynced to /opt/khptz and executed on the appliance.
SHIPPED_DIRS = (
    "adapters", "application", "config", "core", "domain",
    "ports", "ptz", "runtime", "simulation", "ui",
)


def _shipped_sources() -> list[Path]:
    files: list[Path] = []
    for name in SHIPPED_DIRS:
        directory = REPO_ROOT / name
        if directory.is_dir():
            files.extend(
                p for p in directory.rglob("*.py")
                if "__pycache__" not in p.parts
            )
    for extra in ("main.py", "bootstrap.py"):
        path = REPO_ROOT / extra
        if path.is_file():
            files.append(path)
    assert files, "no shipped sources found — the scan would pass vacuously"
    return files


@pytest.fixture(scope="module")
def trees() -> list[tuple[Path, ast.AST]]:
    parsed = []
    for path in _shipped_sources():
        try:
            parsed.append((path, ast.parse(path.read_text(encoding="utf-8"))))
        except SyntaxError as exc:  # pragma: no cover - would fail the build anyway
            pytest.fail(f"{path} does not parse: {exc}")
    return parsed


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _calls(tree: ast.AST):
    return (n for n in ast.walk(tree) if isinstance(n, ast.Call))


def _dotted(func: ast.AST) -> str:
    """Best-effort dotted name for a call target."""
    parts: list[str] = []
    node = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


class TestNoUnsafeDeserialisation:
    def test_yaml_is_always_loaded_safely(self, trees):
        offenders = []
        for path, tree in trees:
            for call in _calls(tree):
                name = _dotted(call.func)
                if name in ("yaml.load", "yaml.full_load", "yaml.unsafe_load"):
                    # yaml.load is only safe with an explicit SafeLoader.
                    kwargs = {k.arg for k in call.keywords}
                    if name != "yaml.load" or "Loader" not in kwargs:
                        offenders.append(f"{_rel(path)}:{call.lineno} {name}")
        assert not offenders, f"unsafe YAML loading: {offenders}"

    def test_pickle_is_not_used(self, trees):
        offenders = []
        for path, tree in trees:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    offenders += [
                        f"{_rel(path)}:{node.lineno}" for a in node.names
                        if a.name.split(".")[0] in ("pickle", "cPickle", "dill", "shelve")
                    ]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.split(".")[0] in ("pickle", "cPickle", "dill", "shelve"):
                        offenders.append(f"{_rel(path)}:{node.lineno}")
        assert not offenders, f"pickle-family import in shipped code: {offenders}"


class TestNoDynamicCodeExecution:
    @pytest.mark.parametrize("builtin", ["eval", "exec", "compile"])
    def test_builtin_is_not_called(self, trees, builtin):
        offenders = [
            f"{_rel(path)}:{call.lineno}"
            for path, tree in trees
            for call in _calls(tree)
            if isinstance(call.func, ast.Name) and call.func.id == builtin
        ]
        assert not offenders, f"{builtin}() in shipped code: {offenders}"

    def test_os_system_is_not_used(self, trees):
        offenders = [
            f"{_rel(path)}:{call.lineno}"
            for path, tree in trees
            for call in _calls(tree)
            if _dotted(call.func) in ("os.system", "os.popen")
        ]
        assert not offenders, f"os.system/os.popen in shipped code: {offenders}"


class TestSubprocessCannotBeInjected:
    """Every command must be an argument list, never a shell string."""

    _SUBPROCESS_FUNCS = {
        "subprocess.run", "subprocess.Popen", "subprocess.call",
        "subprocess.check_call", "subprocess.check_output", "subprocess.getoutput",
    }

    def test_shell_true_is_never_passed(self, trees):
        offenders = []
        for path, tree in trees:
            for call in _calls(tree):
                if _dotted(call.func) not in self._SUBPROCESS_FUNCS:
                    continue
                for kw in call.keywords:
                    if kw.arg == "shell" and not (
                        isinstance(kw.value, ast.Constant) and kw.value.value is False
                    ):
                        offenders.append(f"{_rel(path)}:{call.lineno}")
        assert not offenders, f"subprocess with shell=True: {offenders}"

    def test_command_is_never_a_bare_string(self, trees):
        """A string command is shell-interpreted on some platforms and hides
        argument boundaries on all of them."""
        offenders = []
        for path, tree in trees:
            for call in _calls(tree):
                if _dotted(call.func) not in self._SUBPROCESS_FUNCS:
                    continue
                if not call.args:
                    continue
                first = call.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    offenders.append(f"{_rel(path)}:{call.lineno} (literal)")
                elif isinstance(first, ast.JoinedStr):
                    offenders.append(f"{_rel(path)}:{call.lineno} (f-string)")
                elif isinstance(first, ast.BinOp):
                    # "cmd " + user_value, or "cmd %s" % value — the most
                    # dangerous form, since building a command by concatenation
                    # is what interpolates untrusted input into it.
                    offenders.append(f"{_rel(path)}:{call.lineno} (built by operator)")
                elif (
                    isinstance(first, ast.Call)
                    and isinstance(first.func, ast.Attribute)
                    and first.func.attr in ("format", "join")
                ):
                    # Checked on the attribute itself: a dotted-name helper
                    # returns just "format" when the base is a literal
                    # ("cmd {}".format(x)), so matching ".format" misses it.
                    offenders.append(f"{_rel(path)}:{call.lineno} (str.{first.func.attr})")
        assert not offenders, f"subprocess called with a string command: {offenders}"
