#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_migrations.py — Tests for versioned runtime data migration framework (#155).
"""
from __future__ import annotations

import pytest
from domain.migrations import MigrationPlan, migrate


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_plan_v2():
    """A plan with one step: v0 → v1 adds 'migrated': True."""
    plan = MigrationPlan("test_v1")

    @plan.step(from_version=0, to_version=1)
    def _add_flag(data):
        data["migrated"] = True
        return data

    return plan


def _make_plan_v3():
    """A plan with two steps: v0→v1 adds 'a', v1→v2 adds 'b'."""
    plan = MigrationPlan("test_v2")

    @plan.step(from_version=0, to_version=1)
    def _step_a(data):
        data["a"] = 1
        return data

    @plan.step(from_version=1, to_version=2)
    def _step_b(data):
        data["b"] = 2
        return data

    return plan


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestMigrationPlan:

    def test_no_migration_needed_returns_unchanged(self):
        plan = _make_plan_v2()
        data = {"schema_version": 1, "x": 42}
        result, changed = plan.migrate(data, target_version=1)
        assert not changed
        assert result is data or result == data

    def test_missing_schema_version_treated_as_zero(self):
        plan = _make_plan_v2()
        data = {"x": 1}
        result, changed = plan.migrate(data, target_version=1)
        assert changed
        assert result["schema_version"] == 1

    def test_single_step_applied(self):
        plan = _make_plan_v2()
        data = {}
        result, changed = plan.migrate(data, target_version=1)
        assert changed
        assert result["migrated"] is True
        assert result["schema_version"] == 1

    def test_schema_version_updated_after_migration(self):
        plan = _make_plan_v2()
        data = {"schema_version": 0}
        result, _ = plan.migrate(data, target_version=1)
        assert result["schema_version"] == 1

    def test_two_steps_applied_in_order(self):
        plan = _make_plan_v3()
        data = {}
        result, changed = plan.migrate(data, target_version=2)
        assert changed
        assert result["a"] == 1
        assert result["b"] == 2
        assert result["schema_version"] == 2

    def test_partial_migration_when_step_raises(self):
        plan = MigrationPlan("failing")

        @plan.step(from_version=0, to_version=1)
        def _good(data):
            data["step1"] = True
            return data

        @plan.step(from_version=1, to_version=2)
        def _bad(data):
            raise RuntimeError("simulated failure")

        data = {}
        result, changed = plan.migrate(data, target_version=2)
        assert changed
        assert result["step1"] is True
        assert result["schema_version"] == 1  # stopped after step 1

    def test_original_data_not_mutated(self):
        plan = _make_plan_v2()
        original = {"schema_version": 0, "key": "value"}
        orig_copy = dict(original)
        plan.migrate(original, target_version=1)
        assert original == orig_copy  # original untouched

    def test_gap_in_version_numbers_skipped(self):
        plan = MigrationPlan("gapped")

        @plan.step(from_version=0, to_version=1)
        def _step(data):
            data["done"] = True
            return data

        # Step from 1→2 does not exist; target is 3
        data = {}
        result, _ = plan.migrate(data, target_version=3)
        assert result["done"] is True  # step 0→1 ran

    def test_step_must_increment_by_one(self):
        plan = MigrationPlan("bad")
        with pytest.raises(ValueError):
            @plan.step(from_version=0, to_version=2)
            def _bad(data):
                return data


class TestMigrateConvenienceWrapper:

    def test_non_dict_data_returned_unchanged(self):
        plan = _make_plan_v2()
        result, changed = migrate(plan, None, current_target_version=1)
        assert not changed
        assert result is None

    def test_list_returned_unchanged(self):
        plan = _make_plan_v2()
        lst = [1, 2, 3]
        result, changed = migrate(plan, lst, current_target_version=1)
        assert not changed
        assert result is lst

    def test_dict_migrated_normally(self):
        plan = _make_plan_v2()
        result, changed = migrate(plan, {}, current_target_version=1)
        assert changed
        assert result["migrated"] is True


class TestBackupIntegration:
    """Verify that saving migrated data uses json_io (which creates .bak)."""

    def test_save_after_migration_creates_bak(self, tmp_path):
        from core.json_io import save_json, load_json
        from domain.migrations import MigrationPlan, migrate

        f = tmp_path / "data.json"
        save_json(f, {"schema_version": 0, "value": "original"})

        plan = MigrationPlan("backup_test")

        @plan.step(from_version=0, to_version=1)
        def _step(data):
            data["value"] = "migrated"
            return data

        raw = load_json(f)
        result, changed = migrate(plan, raw, current_target_version=1)
        assert changed
        save_json(f, result)  # json_io creates .bak before overwrite

        assert f.with_suffix(".bak").exists(), ".bak should be created by save_json"
        saved = load_json(f)
        assert saved["value"] == "migrated"
