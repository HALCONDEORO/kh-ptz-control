#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_support_bundle_secrets.py — a bundle never carries a secret
#
# The support bundle is the one artefact that deliberately LEAVES the appliance
# and reaches the vendor, so it is the highest-consequence place for a secret to
# appear. Two separate properties matter and are tested separately, because
# confusing them is how deny-list bundles leak:
#
#   1. Construction: content is assembled from an explicit allow-list. Nothing
#      walks the data directory, so a new secret file added in future cannot be
#      swept in by accident.
#   2. Declaration: the manifest tells the recipient what was withheld. It must
#      name every secret the product actually has — admin.enc arrived with the
#      operator/administrator password split and was missing from that list.

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICE = REPO_ROOT / "application" / "support_bundle_service.py"
SECRET_MANAGER = REPO_ROOT / "runtime" / "secret_manager.py"


@pytest.fixture(scope="module")
def source() -> str:
    return SERVICE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def excluded_entries(source) -> list[str]:
    """The manifest's excluded list, parsed from the assignment itself.

    Searching the whole file would be satisfied by the surrounding comment,
    which names admin.enc while explaining why it must be listed — a test that
    passes whether or not the entry is actually there.
    """
    match = re.search(
        r"excluded:\s*list\[str\]\s*=\s*\[(.*?)\]", source, re.DOTALL
    )
    assert match, "could not locate the excluded list"
    return re.findall(r'"([^"]+)"', match.group(1))


class TestManifestDeclaresEverySecret:
    @pytest.mark.parametrize("secret", ["password.enc", "admin.enc"])
    def test_secret_is_declared_excluded(self, excluded_entries, secret):
        assert secret in excluded_entries, (
            f"{secret} is not in the manifest's excluded list: {excluded_entries}"
        )

    def test_declaration_covers_the_products_real_secret_names(self, excluded_entries):
        """Derived from secret_manager rather than hardcoded here, so adding a
        third secret makes this fail instead of silently under-reporting."""
        sm = SECRET_MANAGER.read_text(encoding="utf-8")
        names = set(re.findall(r'^SECRET_\w+\s*=\s*"([^"]+)"', sm, re.MULTILINE))
        assert names, "could not read the secret names from secret_manager"
        for name in names:
            assert f"{name}.enc" in excluded_entries, (
                f"secret '{name}' has no entry in the bundle's excluded list"
            )


class TestConstructionIsAnAllowList:
    """A deny-list would leak the first secret someone forgets to add."""

    def test_no_unrestricted_directory_sweep(self, source):
        """Recursive or unfiltered enumeration is what sweeps in a secret."""
        for sweeper in (".rglob(", "os.walk", ".iterdir("):
            assert sweeper not in source, (
                f"bundle content is gathered with {sweeper} — a new secret file "
                "would be collected automatically"
            )

    def test_every_glob_pattern_is_specific(self, source):
        """glob() itself is fine; the pattern is what decides whether a secret
        can match. The service legitimately globs incident reports and old
        bundles, and neither pattern can ever select a .enc file."""
        patterns = re.findall(r'\.glob\(\s*"([^"]+)"', source)
        assert patterns, "expected the incident/prune globs to still exist"
        for pattern in patterns:
            assert not pattern.startswith("*"), (
                f"glob pattern {pattern!r} has no fixed prefix — it could match "
                "files it was never meant to collect"
            )
            assert pattern.endswith((".json", ".zip")), (
                f"glob pattern {pattern!r} is not restricted to a safe extension"
            )

    def test_entries_are_named_individually(self, source):
        appended = re.findall(r'entries\.append\(\("([^"]+)"', source)
        assert appended, "no explicitly named bundle entries found"
        for name in appended:
            assert not name.endswith(".enc"), f"bundle adds a secret file: {name}"

    def test_only_named_entries_are_written(self, source):
        """Everything written to the ZIP comes from the manifest or entries."""
        writes = re.findall(r'zf\.writestr\(\s*([^,]+),', source)
        assert writes, "no ZIP writes found"
        for target in writes:
            target = target.strip()
            assert target in ('"manifest.json"', "arc"), (
                f"unexpected ZIP write target: {target}"
            )
