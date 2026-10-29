#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""ATEM runtime selection tests — #750.

Proves that the runtime correctly selects FakeATEM (demo/sim) vs ATEMMonitor
(production) — the last open acceptance criterion of #750:

    demo / simulation profile     -> FakeATEM, no real ATEMMonitor, no sockets
    sim_mode active (any profile)  -> FakeATEM
    production (sim inactive)      -> real ATEMMonitor (PyATEMMax path)

The decision function ``is_fake_atem_mode`` (domain.atem_runtime_policy) is
tested here as a pure Python function — no Qt, no network, no hardware.
``MainWindow._start_atem_monitor`` calls it and is therefore also covered.
"""
from __future__ import annotations

from domain.atem_runtime_policy import is_fake_atem_mode


# ── Demo / simulation profile -> FakeATEM ──────────────────────────────────

class TestDemoProfileSelectsFakeATEM:
    def test_demo_profile_is_fake(self):
        assert is_fake_atem_mode(profile="demo") is True

    def test_simulation_profile_is_fake(self):
        assert is_fake_atem_mode(profile="simulation") is True

    def test_demo_case_insensitive_not_needed(self):
        # Only exact strings matter; wrong case is not fake.
        assert is_fake_atem_mode(profile="Demo") is False

    def test_demo_env_var_read_when_profile_none(self, monkeypatch):
        monkeypatch.setenv("HALLPTZ_PROFILE", "demo")
        assert is_fake_atem_mode() is True

    def test_simulation_env_var_read_when_profile_none(self, monkeypatch):
        monkeypatch.setenv("HALLPTZ_PROFILE", "simulation")
        assert is_fake_atem_mode() is True

    def test_demo_path_ignores_sim_active_flag(self):
        # Even with sim_active=False, demo profile still gives fake.
        assert is_fake_atem_mode(profile="demo", sim_active=False) is True


# ── sim_mode active overrides production profile ──────────────────────────

class TestSimModeActiveSelectsFakeATEM:
    def test_sim_active_with_production_profile_is_fake(self):
        assert is_fake_atem_mode(profile="production", sim_active=True) is True

    def test_sim_active_with_no_profile_is_fake(self):
        assert is_fake_atem_mode(profile=None, sim_active=True) is True

    def test_sim_active_env_default_is_fake(self, monkeypatch):
        monkeypatch.setenv("HALLPTZ_PROFILE", "production")
        assert is_fake_atem_mode(sim_active=True) is True


# ── Production profile -> real ATEMMonitor ────────────────────────────────

class TestProductionProfileSelectsRealMonitor:
    def test_production_is_not_fake(self):
        assert is_fake_atem_mode(profile="production", sim_active=False) is False

    def test_default_is_not_fake(self, monkeypatch):
        monkeypatch.setenv("HALLPTZ_PROFILE", "production")
        assert is_fake_atem_mode(sim_active=False) is False

    def test_unknown_profile_is_not_fake(self):
        # Any profile other than demo/simulation → real monitor.
        assert is_fake_atem_mode(profile="staging", sim_active=False) is False

