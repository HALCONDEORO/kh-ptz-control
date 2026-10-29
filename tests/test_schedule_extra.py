#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_schedule_extra.py — Casos límite de is_within_schedule y next_available_preset
no cubiertos en test_persistence.py.
"""

import pytest
from datetime import datetime as dt
from unittest.mock import patch


# ═══════════════════════════════════════════════════════════════════════════════
#  Fixture compartida
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def sf(tmp_path, monkeypatch):
    """Apunta schedule_config.SCHEDULE_FILE al directorio temporal."""
    import application.schedule_config as sc
    f = tmp_path / "schedule.json"
    monkeypatch.setattr(sc, "SCHEDULE_FILE", f)
    return f


def _full_schedule(monday_kwargs=None, **day_overrides):
    """Construye un schedule completo con todos los días desactivados excepto los indicados."""
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    base = {d: {"enabled": False, "start": "09:00", "end": "17:00"} for d in days}
    if monday_kwargs:
        base["monday"].update(monday_kwargs)
    base.update(day_overrides)
    return base


# ═══════════════════════════════════════════════════════════════════════════════
#  is_within_schedule — día desactivado
# ═══════════════════════════════════════════════════════════════════════════════

class TestDisabledDay:

    def test_disabled_day_returns_false_even_if_in_time_range(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        save_schedule(_full_schedule(monday_kwargs={"enabled": False, "start": "09:00", "end": "17:00"}))
        fake = dt(2024, 1, 1, 12, 0)  # lunes a las 12:00 — dentro del rango horario
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is False

    def test_all_days_disabled_always_false(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        save_schedule(_full_schedule())  # todos desactivados
        fake = dt(2024, 1, 3, 12, 0)  # miércoles
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is False


# ═══════════════════════════════════════════════════════════════════════════════
#  is_within_schedule — límites exactos de intervalo
# ═══════════════════════════════════════════════════════════════════════════════

class TestBoundaryMinutes:
    """El intervalo es [start, end) — start incluido, end excluido."""

    def test_exactly_at_start_is_inside(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        save_schedule(_full_schedule(monday_kwargs={"enabled": True, "start": "10:00", "end": "12:00"}))
        fake = dt(2024, 1, 1, 10, 0)  # exactamente a las 10:00
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is True

    def test_exactly_at_end_is_outside(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        save_schedule(_full_schedule(monday_kwargs={"enabled": True, "start": "10:00", "end": "12:00"}))
        fake = dt(2024, 1, 1, 12, 0)  # exactamente a las 12:00
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is False

    def test_one_minute_before_start_is_outside(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        save_schedule(_full_schedule(monday_kwargs={"enabled": True, "start": "10:00", "end": "12:00"}))
        fake = dt(2024, 1, 1, 9, 59)
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is False

    def test_one_minute_before_end_is_inside(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        save_schedule(_full_schedule(monday_kwargs={"enabled": True, "start": "10:00", "end": "12:00"}))
        fake = dt(2024, 1, 1, 11, 59)
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is True


# ═══════════════════════════════════════════════════════════════════════════════
#  is_within_schedule — cruce de medianoche
# ═══════════════════════════════════════════════════════════════════════════════

class TestMidnightBoundary:

    def test_at_midnight_inside_overnight(self, sf):
        """Horario 22:00–06:00: las 00:00 deben estar dentro."""
        from application.schedule_config import is_within_schedule, save_schedule
        save_schedule(_full_schedule(monday_kwargs={"enabled": True, "start": "22:00", "end": "06:00"}))
        fake = dt(2024, 1, 1, 0, 0)  # lunes a las 00:00
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is True

    def test_exactly_at_overnight_end_is_outside(self, sf):
        """Horario 22:00–06:00: exactamente a las 06:00 ya está fuera."""
        from application.schedule_config import is_within_schedule, save_schedule
        save_schedule(_full_schedule(monday_kwargs={"enabled": True, "start": "22:00", "end": "06:00"}))
        fake = dt(2024, 1, 1, 6, 0)
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is False

    def test_one_minute_before_overnight_end_is_inside(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        save_schedule(_full_schedule(monday_kwargs={"enabled": True, "start": "22:00", "end": "06:00"}))
        fake = dt(2024, 1, 1, 5, 59)
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is True


# ═══════════════════════════════════════════════════════════════════════════════
#  is_within_schedule — previous day overnight (#188)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreviousDayOvernight:
    """Monday 22:00→06:00 must still be active on Tuesday at 02:00 (#188)."""

    def _build_schedule(self, monday_kwargs=None, tuesday_kwargs=None):
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        sched = {d: {"enabled": False, "start": "09:00", "end": "17:00"} for d in days}
        if monday_kwargs:
            sched["monday"].update(monday_kwargs)
        if tuesday_kwargs:
            sched["tuesday"].update(tuesday_kwargs)
        return sched

    def test_tuesday_2am_inside_monday_overnight_window(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        sched = self._build_schedule(
            monday_kwargs={"enabled": True, "start": "22:00", "end": "06:00"}
        )
        save_schedule(sched)
        # Tuesday 02:00 — within Monday's 22:00→06:00 window
        fake = dt(2024, 1, 2, 2, 0)  # Tuesday
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is True

    def test_tuesday_6am_outside_monday_overnight_window(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        sched = self._build_schedule(
            monday_kwargs={"enabled": True, "start": "22:00", "end": "06:00"}
        )
        save_schedule(sched)
        # Tuesday 06:00 — the window ends at 06:00 (exclusive)
        fake = dt(2024, 1, 2, 6, 0)
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is False

    def test_tuesday_5_59am_inside_monday_overnight_window(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        sched = self._build_schedule(
            monday_kwargs={"enabled": True, "start": "22:00", "end": "06:00"}
        )
        save_schedule(sched)
        fake = dt(2024, 1, 2, 5, 59)
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is True

    def test_tuesday_9am_not_inside_monday_daytime_window(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        # Monday daytime (not overnight) — should not bleed into Tuesday
        sched = self._build_schedule(
            monday_kwargs={"enabled": True, "start": "09:00", "end": "17:00"}
        )
        save_schedule(sched)
        fake = dt(2024, 1, 2, 9, 0)  # Tuesday 09:00
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is False

    def test_previous_day_disabled_overnight_does_not_bleed(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        sched = self._build_schedule(
            # Monday disabled but with overnight times
            monday_kwargs={"enabled": False, "start": "22:00", "end": "06:00"}
        )
        save_schedule(sched)
        fake = dt(2024, 1, 2, 2, 0)  # Tuesday 02:00
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is False

    def test_sunday_to_monday_overnight_crossover(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        sched = {d: {"enabled": False, "start": "09:00", "end": "17:00"} for d in days}
        sched["sunday"] = {"enabled": True, "start": "23:00", "end": "04:00"}
        save_schedule(sched)
        # Monday 01:00 — within Sunday's 23:00→04:00 window
        fake = dt(2024, 1, 1, 1, 0)  # Monday
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is True


# ═══════════════════════════════════════════════════════════════════════════════
#  is_within_schedule — claves extra desconocidas en JSON
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtraKeys:

    def test_extra_keys_in_json_do_not_crash(self, sf):
        """JSON con claves desconocidas debe ignorarlas y funcionar con normalidad."""
        from application.schedule_config import is_within_schedule
        import json
        sf.write_text(json.dumps({
            "monday": {"enabled": True, "start": "09:00", "end": "17:00", "unknown_key": "ignored"},
            "tuesday": {"enabled": False, "start": "09:00", "end": "17:00"},
            "wednesday": {"enabled": False, "start": "09:00", "end": "17:00"},
            "thursday": {"enabled": False, "start": "09:00", "end": "17:00"},
            "friday": {"enabled": False, "start": "09:00", "end": "17:00"},
            "saturday": {"enabled": False, "start": "09:00", "end": "17:00"},
            "sunday": {"enabled": False, "start": "09:00", "end": "17:00"},
            "extra_top_level": "ignored too",
        }), encoding="utf-8")

        fake = dt(2024, 1, 1, 12, 0)  # lunes a las 12:00
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            result = is_within_schedule()
        assert result is True  # lunes activo, dentro del rango


# ═══════════════════════════════════════════════════════════════════════════════
#  load_schedule — strict boolean parsing for enabled (#608)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrictBoolParsing:
    """String-encoded booleans must never accidentally enable bypass (#608)."""

    @pytest.fixture(autouse=True)
    def _sf(self, sf):
        self.sf = sf

    def _write(self, enabled_value):
        import json
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        data = {d: {"enabled": False, "start": "09:00", "end": "17:00"} for d in days}
        data["monday"]["enabled"] = enabled_value
        self.sf.write_text(json.dumps(data), encoding="utf-8")

    def _load_monday_enabled(self):
        from application.schedule_config import load_schedule
        return load_schedule()["monday"]["enabled"]

    def test_bool_true_is_enabled(self):
        self._write(True)
        assert self._load_monday_enabled() is True

    def test_bool_false_is_disabled(self):
        self._write(False)
        assert self._load_monday_enabled() is False

    def test_string_false_is_disabled(self):
        self._write("false")
        assert self._load_monday_enabled() is False

    def test_string_False_capitalised_is_disabled(self):
        self._write("False")
        assert self._load_monday_enabled() is False

    def test_string_zero_is_disabled(self):
        self._write("0")
        assert self._load_monday_enabled() is False

    def test_string_no_is_disabled(self):
        self._write("no")
        assert self._load_monday_enabled() is False

    def test_string_true_is_enabled(self):
        self._write("true")
        assert self._load_monday_enabled() is True

    def test_string_yes_is_enabled(self):
        self._write("yes")
        assert self._load_monday_enabled() is True

    def test_string_one_is_enabled(self):
        self._write("1")
        assert self._load_monday_enabled() is True

    def test_unrecognised_string_is_disabled(self):
        self._write("enabled")
        assert self._load_monday_enabled() is False

    def test_null_value_is_disabled(self):
        self._write(None)
        assert self._load_monday_enabled() is False

    def test_string_false_does_not_trigger_bypass(self, sf):
        """End-to-end: 'false' string in JSON must not allow schedule bypass."""
        from application.schedule_config import is_within_schedule, save_schedule
        sched = _full_schedule(monday_kwargs={"enabled": "false", "start": "09:00", "end": "17:00"})
        save_schedule(sched)
        fake = dt(2024, 1, 1, 12, 0)
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is False

    def test_string_zero_does_not_trigger_bypass(self, sf):
        from application.schedule_config import is_within_schedule, save_schedule
        sched = _full_schedule(monday_kwargs={"enabled": "0", "start": "09:00", "end": "17:00"})
        save_schedule(sched)
        fake = dt(2024, 1, 1, 12, 0)
        with patch("application.schedule_config.datetime") as mock_dt:
            mock_dt.now.return_value = fake
            assert is_within_schedule() is False


# ═══════════════════════════════════════════════════════════════════════════════
#  next_available_preset — huecos en el rango
# ═══════════════════════════════════════════════════════════════════════════════

class TestNextAvailablePresetGaps:

    @pytest.fixture()
    def preset_file(self, tmp_path, monkeypatch):
        import application.chairman_presets as cp
        f = tmp_path / "chairman_presets.json"
        monkeypatch.setattr(cp, "CHAIRMAN_PRESETS_FILE", f)
        return f

    def test_finds_gap_in_middle(self, preset_file):
        """Presets {10, 12, 13} → el hueco es el 11."""
        from application.chairman_presets import next_available_preset
        used = {"A": 10, "B": 12, "C": 13}
        assert next_available_preset(used) == 11

    def test_finds_first_gap_not_second(self, preset_file):
        """Presets {10, 11, 13} → primer hueco es el 12, no el 14."""
        from application.chairman_presets import next_available_preset
        used = {"A": 10, "B": 11, "C": 13}
        assert next_available_preset(used) == 12

    def test_single_slot_occupied_at_start(self, preset_file):
        """Solo {10} → siguiente es 11."""
        from application.chairman_presets import next_available_preset
        assert next_available_preset({"A": 10}) == 11

    def test_case_sensitive_name(self, preset_file):
        """'PersonA' y 'alice' son personas distintas — cada una puede tener su preset."""
        from application.chairman_presets import get_preset_for_name
        presets = {"PersonA": 10, "alice": 11}
        assert get_preset_for_name(presets, "PersonA") == 10
        assert get_preset_for_name(presets, "alice") == 11

    def test_get_preset_empty_string_name_uses_generic(self, preset_file):
        from application.chairman_presets import get_preset_for_name, CHAIRMAN_GENERIC_PRESET
        assert get_preset_for_name({}, "") == CHAIRMAN_GENERIC_PRESET
