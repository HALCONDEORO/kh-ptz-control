# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Pending product-contract tests from the release-candidate backlog.

These tests track behaviour that is NOT YET IMPLEMENTED.  When a feature
lands, move the relevant cases into the feature-specific test module and
remove the entry from the lists below.

Groups that have been fully promoted to real test files are no longer
listed here:

  CALL_SET           → tests/test_call_set_policy.py
  CAMERA_TARGET      → tests/test_camera_target_resolver.py
  LAYOUT_MIGRATION   → tests/test_legacy_migration.py
  SUPPORT_BUNDLE     → tests/test_support_bundle_service.py
  RUNTIME_PATH       → tests/test_runtime_path_resolver.py
  NO_HARDWARE        → tests/test_demo_mode_qa.py + test_demo_guard.py
  INSTALLER_SYSTEMD  → tests/test_installer_static.py
  ARCHITECTURE       → tests/test_architecture_boundaries.py
  RELEASE_GATE (partial) → tests/test_release_gate_contracts.py
"""

from __future__ import annotations

import pytest


def _pending(issue: str, requirement: str) -> None:
    """Mark a contract as pending without breaking the current suite."""
    pytest.xfail(f"{issue}: pending implementation for {requirement}")


# ── Backup / restore ──────────────────────────────────────────────────────────
# Remaining items: dry-run mode (RestoreService.restore has no dry_run param yet).
# Other backup/restore contracts are covered in test_backup_service.py and
# test_restore_service.py.

BACKUP_RESTORE_CONTRACTS = [
    ("#531", "restore dry-run writes no files"),
    ("#531", "restore dry-run lists affected files"),
]


@pytest.mark.parametrize(("issue", "requirement"), BACKUP_RESTORE_CONTRACTS)
def test_backup_restore_contract(issue: str, requirement: str) -> None:
    _pending(issue, requirement)


# ── Release gate ──────────────────────────────────────────────────────────────
# Remaining items: no implementation yet.
# Promoted to real tests: doctor data-dir write check and no-secrets output
# (see tests/test_release_gate_contracts.py).  Backup destination policy is
# covered by test_explicit_dest in test_backup_service.py.

RELEASE_GATE_CONTRACTS = [
    ("#520/#452", "doctor warns about legacy config data"),
    ("#520/#452", "restore supports dry-run option"),
    ("#520/#452", "release checklist does not treat NOT_TESTED as pass"),
    ("#520/#381", "validation report requires explicit hardware status"),
    ("#520/#452/#513", "release gate fails when SBOM is missing"),
    ("#520/#452/#514", "release gate fails when checksum manifest is missing"),
    ("#520/#452", "release gate fails when issue blocks map is stale"),
]


@pytest.mark.parametrize(("issue", "requirement"), RELEASE_GATE_CONTRACTS)
def test_release_gate_contract(issue: str, requirement: str) -> None:
    _pending(issue, requirement)
