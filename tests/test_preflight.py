#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application.preflight — setup wizard readiness checks (pure logic)."""

from __future__ import annotations

from application.preflight import (
    MIN_FREE_BYTES,
    check_disk_space,
    check_pyqt,
    check_python,
    has_blocking,
    run_preflight,
)


class TestPython:

    def test_supported_version_passes(self):
        c = check_python((3, 9, 2))
        assert c.ok and not c.blocking

    def test_newer_version_warns_not_blocks(self):
        c = check_python((3, 14, 0))
        assert not c.ok and c.warn_only and not c.blocking

    def test_older_version_blocks(self):
        c = check_python((3, 8, 0))
        assert c.blocking


class TestPyQt:

    def test_available_passes(self):
        assert check_pyqt(available=True).ok

    def test_missing_blocks(self):
        assert check_pyqt(available=False).blocking


class TestDisk:

    def test_enough_space_passes(self):
        assert check_disk_space(MIN_FREE_BYTES).ok

    def test_too_little_blocks(self):
        assert check_disk_space(1024).blocking


class TestAggregate:

    def test_all_good_not_blocking(self):
        checks = run_preflight(
            free_bytes=MIN_FREE_BYTES, pyqt_available=True, python_version=(3, 9, 2)
        )
        assert has_blocking(checks) is False

    def test_missing_pyqt_blocks(self):
        checks = run_preflight(
            free_bytes=MIN_FREE_BYTES, pyqt_available=False, python_version=(3, 9, 2)
        )
        assert has_blocking(checks) is True

    def test_newer_python_alone_does_not_block(self):
        checks = run_preflight(
            free_bytes=MIN_FREE_BYTES, pyqt_available=True, python_version=(3, 14, 0)
        )
        assert has_blocking(checks) is False
