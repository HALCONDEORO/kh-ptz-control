# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Synthetic installed metadata tests: no pip installs, network or CVE claims."""
from email.message import Message
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("sbom_closure", Path(__file__).resolve().parents[1] / "scripts/sbom_closure.py")
closure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(closure)


class Dist:
    def __init__(self, name, version="1.0", requires=(), extras=()):
        self.version, self.requires = version, requires
        self.metadata = Message()
        self.metadata["Name"] = name
        for extra in extras:
            self.metadata["Provides-Extra"] = extra


def run(tmp_path, monkeypatch, requirements, distributions):
    (tmp_path / "requirements.txt").write_text(requirements)
    monkeypatch.setattr(closure.importlib.metadata, "distributions", lambda: distributions)
    return closure.collect(tmp_path)


def test_closure_graph_excludes_ambient_and_inactive_marker(tmp_path, monkeypatch):
    components, graph, roots = run(tmp_path, monkeypatch, "Root>=1\n", [
        Dist("Root", requires=["Child==1.0", "Ignored; python_version<'2'"]),
        Dist("Child", requires=["Leaf"]), Dist("Leaf"), Dist("Unrelated")])
    assert [c["name"] for c in components] == ["Child", "Leaf", "Root"]
    assert roots == ["pkg:pypi/root@1.0"]
    assert graph == [{"ref": "pkg:pypi/child@1.0", "dependsOn": ["pkg:pypi/leaf@1.0"]},
                     {"ref": "pkg:pypi/leaf@1.0", "dependsOn": []},
                     {"ref": "pkg:pypi/root@1.0", "dependsOn": ["pkg:pypi/child@1.0"]}]


def test_extras_propagate_when_discovered_late_and_cycles_terminate(tmp_path, monkeypatch):
    components, _, _ = run(tmp_path, monkeypatch, "A\nB\n", [
        Dist("A", requires=["C; extra=='fast'", "B"], extras=["fast"]),
        Dist("B", requires=["A[fast]"]), Dist("C")])
    assert {c["name"] for c in components} == {"A", "B", "C"}


@pytest.mark.parametrize("requirements,distributions", [
    ("Missing", []), ("A", [Dist("A"), Dist("a")]),
    ("A>=2", [Dist("A")]), ("A", [Dist("A", requires=["Missing"])]),
    ("A", [Dist("A", requires=["B>=2"]), Dist("B")]),
    ("A[unknown]", [Dist("A")]), ("A @ https://example.invalid/a.whl", [Dist("A")]),
    ("-r other.txt", []), ("", []), ("A", [Dist("A", "invalid version")]),
    ("A", [Dist("A", requires=["???"])]),
    ("A\nB", [Dist("A", requires=["C<2"]), Dist("B", requires=["C>=2"]), Dist("C")]),
])
def test_unresolved_or_unsupported_input_fails(tmp_path, monkeypatch, requirements, distributions):
    with pytest.raises(ValueError):
        run(tmp_path, monkeypatch, requirements, distributions)


def test_normalized_names_and_prerelease_pins(tmp_path, monkeypatch):
    components, _, _ = run(tmp_path, monkeypatch, "Some_Name==1.0b9", [Dist("Some-Name", "1.0b9")])
    assert components[0]["purl"] == "pkg:pypi/some-name@1.0b9"
