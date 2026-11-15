#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_generate_sbom.py — Tests for scripts/generate_sbom.py (#513)
from __future__ import annotations

import json
import sys
from pathlib import Path


def _run_sbom(out_path: str) -> int:
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    import importlib
    gen = importlib.import_module("generate_sbom")
    old_argv = sys.argv[:]
    sys.argv = ["generate_sbom.py", "--out", out_path]
    try:
        return gen.main()
    finally:
        sys.argv = old_argv
        sys.path.pop(0)


def test_sbom_file_created(tmp_path):
    out = tmp_path / "sbom.json"
    rc = _run_sbom(str(out))
    assert rc == 0
    assert out.exists()


def test_sbom_is_cyclonedx(tmp_path):
    out = tmp_path / "sbom.json"
    _run_sbom(str(out))
    sbom = json.loads(out.read_text())
    assert sbom["bomFormat"] == "CycloneDX"
    assert "specVersion" in sbom
    assert "components" in sbom


def test_sbom_has_metadata(tmp_path):
    out = tmp_path / "sbom.json"
    _run_sbom(str(out))
    sbom = json.loads(out.read_text())
    meta = sbom.get("metadata", {})
    assert "timestamp" in meta
    comp = meta.get("component", {})
    assert comp.get("name") == "khptz-adaptive-control"
    assert comp.get("version") != ""


def test_sbom_has_no_secrets(tmp_path):
    out = tmp_path / "sbom.json"
    _run_sbom(str(out))
    text = out.read_text().lower()
    for pattern in ("password", "token", "secret", "credential"):
        assert pattern not in text, f"SBOM unexpectedly contains '{pattern}'"


def test_sbom_lists_declared_runtime_dependencies(tmp_path):
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    import importlib
    try:
        gen = importlib.import_module("generate_sbom")
    finally:
        sys.path.pop(0)
    declared = {gen._normalize(n) for n in gen._declared_runtime_requirements()}
    out = tmp_path / "sbom.json"
    _run_sbom(str(out))
    sbom = json.loads(out.read_text())
    names = {gen._normalize(comp["name"]) for comp in sbom["components"]}
    # The SBOM must describe exactly the declared runtime dependencies —
    # ambient environment packages (e.g. pytest, always installed here) must
    # not leak into a release artifact.
    assert names == declared
    assert "pytest" not in names


def test_sbom_components_have_purl(tmp_path):
    out = tmp_path / "sbom.json"
    _run_sbom(str(out))
    sbom = json.loads(out.read_text())
    for comp in sbom["components"]:
        assert comp.get("purl", "").startswith("pkg:pypi/"), \
            f"Component {comp.get('name')} missing valid purl"


def _generator():
    import importlib
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        return importlib.import_module("generate_sbom")
    finally:
        sys.path.pop(0)


def test_commit_uses_source_checkout_from_foreign_repo(tmp_path, monkeypatch):
    import subprocess
    gen = _generator()
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    subprocess.run(["git", "init", "-q", str(foreign)], check=True)
    subprocess.run(["git", "-C", str(foreign), "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-qm",
                    "foreign checkout", "--allow-empty"], check=True)
    foreign_sha = subprocess.check_output(["git", "-C", str(foreign), "rev-parse", "HEAD"]).decode().strip()
    expected = subprocess.check_output(["git", "-C", str(gen.ROOT), "rev-parse", "HEAD"]).decode().strip()
    monkeypatch.chdir(foreign)
    assert gen._git_commit() == expected
    assert expected != foreign_sha
    out = tmp_path / "sbom.json"
    assert _run_sbom(str(out)) == 0
    properties = json.loads(out.read_text())["metadata"]["component"]["properties"]
    assert properties == [{"name": "git:commit", "value": expected}]


def test_source_subdirectory_must_not_claim_parent_repository(tmp_path, monkeypatch):
    import subprocess
    gen = _generator()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-qm",
                    "parent checkout", "--allow-empty"], check=True)
    source_copy = tmp_path / "source-copy"
    source_copy.mkdir()
    monkeypatch.setattr(gen, "ROOT", source_copy)
    assert gen._git_commit() == "unknown"
    out = tmp_path / "untouched.json"
    out.write_text("original")
    assert _run_sbom(str(out)) == 1
    assert out.read_text() == "original"


def test_missing_git_identity_does_not_write_sbom(tmp_path, monkeypatch):
    gen = _generator()
    monkeypatch.setattr(gen, "_git_commit", lambda: "unknown")
    out = tmp_path / "sbom.json"
    assert _run_sbom(str(out)) == 1
    assert not out.exists()


def test_unresolved_packages_do_not_poison_next_collection(monkeypatch):
    gen = _generator()
    monkeypatch.setattr(gen, "_declared_runtime_requirements", lambda: ["Fixture"])
    monkeypatch.setattr(gen.importlib.metadata, "distributions", lambda: [])
    gen._collect_packages()
    assert gen.UNKNOWN_VERSIONS == ["Fixture"]

    class Distribution:
        metadata = {"Name": "Fixture", "Version": "1.2.3", "Summary": "local fixture"}

    monkeypatch.setattr(gen.importlib.metadata, "distributions", lambda: [Distribution()])
    components = gen._collect_packages()
    assert gen.UNKNOWN_VERSIONS == []
    assert components[0]["version"] == "1.2.3"


def test_unresolved_closure_does_not_overwrite_output(tmp_path, monkeypatch):
    gen = _generator()
    import importlib
    sys.path.insert(0, str(Path(gen.__file__).parent))
    try:
        closure = importlib.import_module("sbom_closure")
    finally:
        sys.path.pop(0)

    def unresolved(_root):
        raise ValueError("fixture dependency is missing")

    monkeypatch.setattr(closure, "collect", unresolved)
    monkeypatch.setattr(sys, "argv", ["generate_sbom.py", "--include-transitive",
                                   "--out", str(tmp_path / "sbom.json")])
    out = tmp_path / "sbom.json"
    out.write_text("existing")
    assert gen.main() == 1
    assert out.read_text() == "existing"
