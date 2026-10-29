#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_startup_errors.py — Tests for startup error classification (#103).

Verifies that StartupError correctly classifies recoverable vs fatal failures,
and that the helper constructors produce the expected objects.
"""
from __future__ import annotations

from domain.startup_errors import (
    StartupErrorKind,
    recoverable, fatal,
)


class TestStartupErrorKind:

    def test_recoverable_is_not_fatal(self):
        err = recoverable("camera", "connection timeout")
        assert not err.is_fatal
        assert err.kind is StartupErrorKind.RECOVERABLE

    def test_fatal_is_fatal(self):
        err = fatal("pyqt5", "module not found")
        assert err.is_fatal
        assert err.kind is StartupErrorKind.FATAL

    def test_recoverable_str_includes_component_and_detail(self):
        err = recoverable("atem", "not reachable")
        s = str(err)
        assert "atem" in s
        assert "not reachable" in s
        assert "recoverable" in s.lower()

    def test_fatal_str_includes_fatal(self):
        err = fatal("data_dir", "not writable")
        assert "fatal" in str(err).lower()

    def test_component_stored(self):
        err = recoverable("schedule", "corrupt json")
        assert err.component == "schedule"

    def test_detail_stored(self):
        err = fatal("qt", "PyQt5 not installed")
        assert err.detail == "PyQt5 not installed"

    def test_repr_is_informative(self):
        err = recoverable("camera", "timeout")
        assert "recoverable" in repr(err)
        assert "camera" in repr(err)


class TestKnownClassifications:
    """Document expected classification for well-known failure modes."""

    def test_camera_timeout_is_recoverable(self):
        err = recoverable("camera", "startup timeout")
        assert not err.is_fatal

    def test_atem_unavailable_is_recoverable(self):
        err = recoverable("atem", "not reachable")
        assert not err.is_fatal

    def test_pyatemmax_missing_is_recoverable(self):
        err = recoverable("atem", "PyATEMMax not installed")
        assert not err.is_fatal

    def test_pyqt5_missing_is_fatal(self):
        err = fatal("pyqt5", "module not found")
        assert err.is_fatal

    def test_data_dir_not_writable_is_fatal(self):
        err = fatal("data_dir", "directory not writable")
        assert err.is_fatal
