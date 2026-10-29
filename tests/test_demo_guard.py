# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application/demo_guard.py and domain/runtime_mode.py (#295)."""
from __future__ import annotations

import os

import pytest

from application.demo_guard import DemoGuard, DemoModeViolation, _ALL_PROTECTED_NAMES
from domain.runtime_mode import RuntimeMode, parse_mode


# ── RuntimeMode tests ─────────────────────────────────────────────────────────

class TestRuntimeMode:
    def test_all_modes_defined(self):
        assert RuntimeMode.PRODUCTION.value == "production"
        assert RuntimeMode.DEMO.value == "demo"
        assert RuntimeMode.SIMULATION.value == "simulation"

    def test_parse_mode_production(self):
        assert parse_mode("production") is RuntimeMode.PRODUCTION

    def test_parse_mode_demo(self):
        assert parse_mode("demo") is RuntimeMode.DEMO

    def test_parse_mode_simulation(self):
        assert parse_mode("simulation") is RuntimeMode.SIMULATION

    def test_parse_mode_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown runtime mode"):
            parse_mode("test")

    def test_runtime_mode_is_str(self):
        assert RuntimeMode.DEMO == "demo"


# ── DemoGuard.active ──────────────────────────────────────────────────────────

class TestDemoGuardActive:
    def test_production_not_active(self, tmp_path):
        guard = DemoGuard(mode=RuntimeMode.PRODUCTION, demo_data_dir=tmp_path / "demo",
                          production_data_dir=tmp_path / "prod")
        assert guard.active is False

    def test_demo_active(self, tmp_path):
        guard = DemoGuard(mode=RuntimeMode.DEMO, demo_data_dir=tmp_path / "demo",
                          production_data_dir=tmp_path / "prod")
        assert guard.active is True

    def test_simulation_active(self, tmp_path):
        guard = DemoGuard(mode=RuntimeMode.SIMULATION, demo_data_dir=tmp_path / "demo",
                          production_data_dir=tmp_path / "prod")
        assert guard.active is True


# ── DemoGuard.apply ───────────────────────────────────────────────────────────

class TestDemoGuardApply:
    def test_apply_creates_demo_dir(self, tmp_path):
        demo_dir = tmp_path / "demo"
        guard = DemoGuard(mode=RuntimeMode.DEMO, demo_data_dir=demo_dir,
                          production_data_dir=tmp_path / "prod")
        guard.apply()
        assert demo_dir.exists()

    def test_apply_sets_env_var(self, tmp_path):
        demo_dir = tmp_path / "demo"
        guard = DemoGuard(mode=RuntimeMode.DEMO, demo_data_dir=demo_dir,
                          production_data_dir=tmp_path / "prod")
        guard.apply()
        assert os.environ.get("HALLPTZ_DATA_DIR") == str(demo_dir)

    def test_apply_overrides_hallptz_data_dir_when_present(self, tmp_path, monkeypatch):
        demo_dir = tmp_path / "demo"
        monkeypatch.setenv("HALLPTZ_DATA_DIR", str(tmp_path / "prod"))
        guard = DemoGuard(mode=RuntimeMode.DEMO, demo_data_dir=demo_dir,
                          production_data_dir=tmp_path / "prod")
        guard.apply()
        assert os.environ.get("HALLPTZ_DATA_DIR") == str(demo_dir)

    def test_apply_production_mode_does_nothing(self, tmp_path):
        demo_dir = tmp_path / "demo"
        prod_dir = tmp_path / "prod"
        guard = DemoGuard(mode=RuntimeMode.PRODUCTION, demo_data_dir=demo_dir,
                          production_data_dir=prod_dir)
        result = guard.apply()
        assert not demo_dir.exists()
        assert result == prod_dir.resolve()

    def test_apply_idempotent(self, tmp_path):
        demo_dir = tmp_path / "demo"
        guard = DemoGuard(mode=RuntimeMode.DEMO, demo_data_dir=demo_dir,
                          production_data_dir=tmp_path / "prod")
        guard.apply()
        guard.apply()  # second call must not raise
        assert demo_dir.exists()

    def test_apply_returns_demo_dir(self, tmp_path):
        demo_dir = tmp_path / "demo"
        guard = DemoGuard(mode=RuntimeMode.DEMO, demo_data_dir=demo_dir,
                          production_data_dir=tmp_path / "prod")
        result = guard.apply()
        assert result == demo_dir.resolve()


# ── DemoGuard.assert_safe ─────────────────────────────────────────────────────

class TestDemoGuardAssertSafe:
    def _guard(self, tmp_path):
        demo_dir = tmp_path / "demo"
        prod_dir = tmp_path / "prod"
        prod_dir.mkdir(parents=True)
        demo_dir.mkdir(parents=True)
        return DemoGuard(
            mode=RuntimeMode.DEMO,
            demo_data_dir=demo_dir,
            production_data_dir=prod_dir,
        )

    def test_production_mode_always_safe(self, tmp_path):
        prod_dir = tmp_path / "prod"
        prod_dir.mkdir()
        guard = DemoGuard(mode=RuntimeMode.PRODUCTION,
                          demo_data_dir=tmp_path / "demo",
                          production_data_dir=prod_dir)
        # Should not raise even for protected names
        guard.assert_safe(prod_dir / "config.yaml")

    def test_unknown_filename_safe_in_demo(self, tmp_path):
        guard = self._guard(tmp_path)
        guard.assert_safe(tmp_path / "prod" / "my_custom_file.txt")

    def test_protected_in_prod_dir_raises(self, tmp_path):
        guard = self._guard(tmp_path)
        with pytest.raises(DemoModeViolation):
            guard.assert_safe(tmp_path / "prod" / "config.yaml")

    def test_protected_json_in_prod_dir_raises(self, tmp_path):
        guard = self._guard(tmp_path)
        for name in ["room_layout.json", "chairman_presets.json",
                     "seat_names.json", "schedule.json"]:
            with pytest.raises(DemoModeViolation):
                guard.assert_safe(tmp_path / "prod" / name)

    def test_protected_txt_in_prod_dir_raises(self, tmp_path):
        guard = self._guard(tmp_path)
        for name in ["PTZ1IP.txt", "PTZ2IP.txt", "Cam1ID.txt",
                     "Cam2ID.txt", "ATEMIP.txt", "Contact.txt"]:
            with pytest.raises(DemoModeViolation):
                guard.assert_safe(tmp_path / "prod" / name)

    def test_protected_in_demo_dir_allowed(self, tmp_path):
        guard = self._guard(tmp_path)
        # Writing config.yaml inside the demo dir is allowed
        guard.assert_safe(tmp_path / "demo" / "config.yaml")

    def test_protected_name_in_unrelated_dir_is_safe(self, tmp_path):
        """A protected filename outside prod/app dirs must NOT be blocked (#599)."""
        guard = self._guard(tmp_path)
        unrelated = tmp_path / "sandbox" / "schedule.json"
        unrelated.parent.mkdir()
        # Must not raise — unrelated directory, not under prod or app dir
        guard.assert_safe(unrelated)

    def test_protected_txt_in_unrelated_dir_is_safe(self, tmp_path):
        guard = self._guard(tmp_path)
        unrelated = tmp_path / "sandbox" / "PTZ1IP.txt"
        unrelated.parent.mkdir()
        guard.assert_safe(unrelated)

    def test_protected_names_set_completeness(self):
        expected = {
            "PTZ1IP.txt", "PTZ2IP.txt", "Cam1ID.txt", "Cam2ID.txt",
            "ATEMIP.txt", "Contact.txt", "password.enc",
            "room_layout.json", "chairman_presets.json",
            "seat_names.json", "schedule.json", "config.yaml",
        }
        assert expected == _ALL_PROTECTED_NAMES


# ── Production config not written in demo ────────────────────────────────────

class TestProductionIsolation:
    """Prove production config files are not written during demo startup."""

    def test_demo_apply_does_not_create_production_dir(self, tmp_path):
        prod_dir = tmp_path / "prod"
        demo_dir = tmp_path / "demo"
        guard = DemoGuard(mode=RuntimeMode.DEMO, demo_data_dir=demo_dir,
                          production_data_dir=prod_dir)
        guard.apply()
        assert not prod_dir.exists(), "apply() must not touch the production directory"

    def test_demo_apply_does_not_write_protected_files(self, tmp_path):
        prod_dir = tmp_path / "prod"
        demo_dir = tmp_path / "demo"
        guard = DemoGuard(mode=RuntimeMode.DEMO, demo_data_dir=demo_dir,
                          production_data_dir=prod_dir)
        guard.apply()
        for name in _ALL_PROTECTED_NAMES:
            assert not (prod_dir / name).exists(), \
                f"apply() must not create {name} in production dir"
