#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for PiPNudgeService and _load_pip_nudge."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, call

import pytest

from application.pip_nudge_service import PiPNudgeService
from config.loader import ConfigError, _load_pip_nudge
from config.settings import PiPNudgeSettings


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_port():
    return MagicMock()


def _make_cfg(**kwargs) -> PiPNudgeSettings:
    defaults = dict(camera_role="platform", pan_speed=5, direction="right", duration_ms=100)
    defaults.update(kwargs)
    return PiPNudgeSettings(**defaults)


def _svc(session_active=True, **cfg_kwargs) -> tuple[PiPNudgeService, MagicMock]:
    port = _make_port()
    svc = PiPNudgeService(
        port, "cam1", _make_cfg(**cfg_kwargs),
        session_provider=lambda: session_active,
    )
    return svc, port


# ── PiPNudgeService ───────────────────────────────────────────────────────────

class TestPiPNudgeService:

    def test_no_movement_when_pan_speed_zero(self):
        svc, port = _svc(pan_speed=0, duration_ms=200)
        svc.on_pip_on()
        port.move.assert_not_called()

    def test_no_movement_when_duration_zero(self):
        svc, port = _svc(pan_speed=5, duration_ms=0)
        svc.on_pip_on()
        port.move.assert_not_called()

    def test_pip_on_moves_right(self):
        svc, port = _svc(pan_speed=7, direction="right", duration_ms=50)
        svc.on_pip_on()
        port.move.assert_called_once_with("cam1", 7, 0)

    def test_pip_on_moves_left(self):
        svc, port = _svc(pan_speed=7, direction="left", duration_ms=50)
        svc.on_pip_on()
        port.move.assert_called_once_with("cam1", -7, 0)

    def test_pip_off_reverses_right_nudge(self):
        svc, port = _svc(pan_speed=5, direction="right", duration_ms=50)
        svc.on_pip_on()
        svc.on_pip_off()
        assert port.move.call_args_list == [call("cam1", 5, 0), call("cam1", -5, 0)]

    def test_pip_off_reverses_left_nudge(self):
        svc, port = _svc(pan_speed=5, direction="left", duration_ms=50)
        svc.on_pip_on()
        svc.on_pip_off()
        assert port.move.call_args_list == [call("cam1", -5, 0), call("cam1", 5, 0)]

    def test_pip_off_noop_without_prior_pip_on(self):
        svc, port = _svc()
        svc.on_pip_off()
        port.move.assert_not_called()

    def test_pip_off_noop_after_cancel(self):
        svc, port = _svc()
        svc.on_pip_on()
        svc.cancel()
        svc.on_pip_off()
        port.move.assert_called_once()  # solo el on_pip_on

    def test_cancel_prevents_second_pip_off(self):
        svc, port = _svc()
        svc.on_pip_on()
        svc.on_pip_off()
        port.reset_mock()
        svc.cancel()
        svc.on_pip_off()
        port.move.assert_not_called()

    def test_double_pip_on_does_not_double_move(self):
        """Segundo pip_on sin pip_off intermedio: sigue siendo un solo estado activo."""
        svc, port = _svc(duration_ms=50)
        svc.on_pip_on()
        svc.on_pip_on()  # segundo on — reaplica el nudge
        # pip_off debe revertir exactamente una vez
        svc.on_pip_off()
        assert port.move.call_count == 3  # on, on, off

    def test_stop_move_called_after_duration(self):
        """stop_move se llama al expirar el timer."""
        svc, port = _svc(pan_speed=5, duration_ms=80)
        svc.on_pip_on()
        time.sleep(0.2)   # espera 200ms > 80ms
        port.stop_move.assert_called_with("cam1")

    def test_stop_move_not_called_if_cancelled_before_timer(self):
        """Si el timer se cancela antes de disparar, stop_move no se llama."""
        svc, port = _svc(pan_speed=5, duration_ms=500)
        svc.on_pip_on()
        svc.cancel()
        time.sleep(0.1)   # espera para dar tiempo al timer (si no fue cancelado)
        port.stop_move.assert_not_called()

    def test_generation_counter_prevents_stale_stop(self):
        """Un stop tardío de pip_on no interrumpe el movimiento de pip_off."""
        svc, port = _svc(pan_speed=5, duration_ms=50)
        svc.on_pip_on()
        svc.on_pip_off()   # nuevo _apply → incrementa generación
        time.sleep(0.15)
        # Solo debe haber un stop_move (del pip_off), no dos
        assert port.stop_move.call_count == 1


# ── on_pip_changed (con session_provider) ────────────────────────────────────

class TestOnPipChanged:
    def _pip(self, enabled: bool):
        class _State:
            pass
        s = _State()
        s.enabled = enabled
        return s

    def test_fires_on_pip_on_when_session_active(self):
        svc, port = _svc(session_active=True)
        svc.on_pip_changed(self._pip(True))
        port.move.assert_called_once()

    def test_blocked_when_session_inactive(self):
        svc, port = _svc(session_active=False)
        svc.on_pip_changed(self._pip(True))
        port.move.assert_not_called()

    def test_fires_off_when_session_active(self):
        svc, port = _svc(session_active=True)
        svc.on_pip_changed(self._pip(True))
        svc.on_pip_changed(self._pip(False))
        assert port.move.call_count == 2  # on + off


# ── Thread safety ─────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_stop_camera_clears_pending_stop(self):
        # Tras completarse el timer, _pending_stop debe quedar limpio.
        svc, port = _svc(pan_speed=5, duration_ms=10)
        svc.on_pip_on()
        assert svc._pending_stop is not None
        time.sleep(0.05)
        assert svc._pending_stop is None
        port.stop_move.assert_called_once_with("cam1")

    def test_concurrent_entry_points_do_not_raise_or_corrupt(self):
        # on_pip_on/off (hilo monitor), cancel (hilo bus) y los timers
        # (_stop_camera) se ejecutan en paralelo; el lock debe evitar fallos.
        svc, port = _svc(pan_speed=5, duration_ms=5)
        errors: list[BaseException] = []

        def hammer(fn):
            try:
                for _ in range(200):
                    fn()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=hammer, args=(svc.on_pip_on,)),
            threading.Thread(target=hammer, args=(svc.on_pip_off,)),
            threading.Thread(target=hammer, args=(svc.cancel,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        time.sleep(0.05)  # deja completar los timers pendientes
        assert errors == []


# ── update() ─────────────────────────────────────────────────────────────────

class TestUpdate:
    def test_update_changes_speed_for_next_nudge(self):
        svc, port = _svc(pan_speed=5, duration_ms=100)
        svc.update(pan_speed=12, direction="right", duration_ms=200)
        svc.on_pip_on()
        port.move.assert_called_once_with("cam1", 12, 0)

    def test_update_changes_direction(self):
        svc, port = _svc(pan_speed=5, direction="right", duration_ms=100)
        svc.update(pan_speed=5, direction="left", duration_ms=100)
        svc.on_pip_on()
        port.move.assert_called_once_with("cam1", -5, 0)

    def test_update_to_zero_disables_nudge(self):
        svc, port = _svc(pan_speed=5, duration_ms=100)
        svc.update(pan_speed=0, direction="right", duration_ms=100)
        svc.on_pip_on()
        port.move.assert_not_called()

    def test_describe_reflects_update(self):
        svc, _ = _svc(pan_speed=0, duration_ms=0)
        assert "0" in svc.describe()
        svc.update(pan_speed=7, direction="left", duration_ms=350)
        desc = svc.describe()
        assert "left" in desc
        assert "7" in desc
        assert "350" in desc


# ── _load_pip_nudge ───────────────────────────────────────────────────────────

class TestLoadPipNudge:

    def test_empty_dict_returns_defaults(self):
        cfg = _load_pip_nudge({})
        assert cfg.pan_speed == 0
        assert cfg.duration_ms == 0
        assert cfg.direction == "right"
        assert cfg.camera_role == "platform"

    def test_non_dict_returns_defaults(self):
        cfg = _load_pip_nudge(None)
        assert cfg.pan_speed == 0

    def test_full_config_parsed(self):
        cfg = _load_pip_nudge({
            "camera_role": "comments",
            "pan_speed": 10,
            "direction": "left",
            "duration_ms": 350,
        })
        assert cfg.camera_role == "comments"
        assert cfg.pan_speed == 10
        assert cfg.direction == "left"
        assert cfg.duration_ms == 350

    def test_direction_invalid_raises(self):
        with pytest.raises(ConfigError, match="direction"):
            _load_pip_nudge({"direction": "up"})

    def test_pan_speed_out_of_range_raises(self):
        with pytest.raises(ConfigError, match="pan_speed"):
            _load_pip_nudge({"pan_speed": 25})

    def test_pan_speed_negative_raises(self):
        with pytest.raises(ConfigError, match="pan_speed"):
            _load_pip_nudge({"pan_speed": -1})

    def test_pan_speed_non_numeric_raises(self):
        with pytest.raises(ConfigError, match="pan_speed"):
            _load_pip_nudge({"pan_speed": "fast"})

    def test_duration_ms_out_of_range_raises(self):
        with pytest.raises(ConfigError, match="duration_ms"):
            _load_pip_nudge({"duration_ms": 9999})

    def test_duration_ms_non_numeric_raises(self):
        with pytest.raises(ConfigError, match="duration_ms"):
            _load_pip_nudge({"duration_ms": "slow"})

    def test_zero_values_accepted(self):
        cfg = _load_pip_nudge({"pan_speed": 0, "duration_ms": 0})
        assert cfg.pan_speed == 0
        assert cfg.duration_ms == 0

    def test_direction_case_insensitive(self):
        cfg = _load_pip_nudge({"direction": "RIGHT"})
        assert cfg.direction == "right"

    def test_camera_role_stripped(self):
        cfg = _load_pip_nudge({"camera_role": "  platform  "})
        assert cfg.camera_role == "platform"
