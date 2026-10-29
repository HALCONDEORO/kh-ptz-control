#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_supervisor_health_loop.py — Tests for Supervisor health-check loop, worker
registration and start() idempotency.

Stop/idempotency tests live in test_clean_shutdown.py.  These tests cover the
_bucle loop behaviour that was previously untested.
"""
from __future__ import annotations

import threading
import time


from core.supervisor import Supervisor


# ── registrar() ───────────────────────────────────────────────────────────────

class TestSupervisorRegistrar:
    def test_register_one_worker(self):
        sup = Supervisor(intervalo=60.0)
        sup.registrar("cam", lambda: True, lambda: None)
        assert len(sup._workers) == 1

    def test_register_multiple_workers(self):
        sup = Supervisor(intervalo=60.0)
        for i in range(3):
            sup.registrar(f"w{i}", lambda: True, lambda: None)
        assert len(sup._workers) == 3

    def test_registered_tuple_stores_name_and_callables(self):
        sup = Supervisor(intervalo=60.0)
        def alive_fn(): return True
        def restart_fn(): return None
        sup.registrar("cam", alive_fn, restart_fn)
        name, fn_a, fn_r = sup._workers[0]
        assert name == "cam"
        assert fn_a is alive_fn
        assert fn_r is restart_fn


# ── start() ───────────────────────────────────────────────────────────────────

class TestSupervisorStart:
    def test_start_creates_alive_thread(self):
        sup = Supervisor(intervalo=60.0)
        sup.start()
        try:
            assert sup._hilo is not None
            assert sup._hilo.is_alive()
        finally:
            sup.stop()

    def test_start_twice_keeps_same_thread(self):
        sup = Supervisor(intervalo=60.0)
        sup.start()
        try:
            first = sup._hilo
            sup.start()
            assert sup._hilo is first
        finally:
            sup.stop()

    def test_stop_then_start_creates_new_thread(self):
        sup = Supervisor(intervalo=60.0)
        sup.start()
        first = sup._hilo
        sup.stop()
        sup.start()
        try:
            assert sup._hilo is not first
            assert sup._hilo.is_alive()
        finally:
            sup.stop()


# ── _bucle() — health-check loop ──────────────────────────────────────────────

class TestSupervisorHealthLoop:
    _TICK = 0.025   # short interval so tests run fast

    def test_restart_called_when_worker_dead(self):
        restarted = threading.Event()

        def is_alive():
            return False

        def restart():
            restarted.set()

        sup = Supervisor(intervalo=self._TICK)
        sup.registrar("cam", is_alive, restart)
        sup.start()
        triggered = restarted.wait(timeout=2.0)
        sup.stop()

        assert triggered, "reiniciar() was not called within 2 s"

    def test_restart_not_called_when_worker_alive(self):
        restart_called = threading.Event()

        def is_alive():
            return True

        def restart():
            restart_called.set()

        sup = Supervisor(intervalo=self._TICK)
        sup.registrar("cam", is_alive, restart)
        sup.start()
        time.sleep(self._TICK * 4)   # enough for several ticks
        sup.stop()

        assert not restart_called.is_set(), "reiniciar() was called for a healthy worker"

    def test_exception_in_reiniciar_does_not_kill_thread(self):
        first_check = threading.Event()

        def is_alive():
            first_check.set()
            return False

        def bad_restart():
            raise RuntimeError("restart failed")

        sup = Supervisor(intervalo=self._TICK)
        sup.registrar("cam", is_alive, bad_restart)
        sup.start()
        first_check.wait(timeout=2.0)
        time.sleep(self._TICK * 3)
        still_alive = sup._hilo.is_alive()
        sup.stop()

        assert still_alive, "Supervisor thread died after exception in reiniciar()"

    def test_exception_in_alive_check_does_not_kill_thread(self):
        first_call = threading.Event()

        def bad_alive():
            first_call.set()
            raise RuntimeError("check failed")

        sup = Supervisor(intervalo=self._TICK)
        sup.registrar("cam", bad_alive, lambda: None)
        sup.start()
        first_call.wait(timeout=2.0)
        time.sleep(self._TICK * 3)
        still_alive = sup._hilo.is_alive()
        sup.stop()

        assert still_alive, "Supervisor thread died after exception in esta_vivo()"

    def test_all_registered_workers_are_checked(self):
        events = [threading.Event() for _ in range(3)]

        def make_alive(ev):
            def fn():
                ev.set()
                return True
            return fn

        sup = Supervisor(intervalo=self._TICK)
        for i, ev in enumerate(events):
            sup.registrar(f"w{i}", make_alive(ev), lambda: None)

        sup.start()
        all_triggered = all(ev.wait(timeout=2.0) for ev in events)
        sup.stop()

        assert all_triggered, "Not all workers were checked by the health loop"

    def test_dead_worker_restarted_multiple_times(self):
        restart_count = [0]
        enough = threading.Event()

        def is_alive():
            return False

        def restart():
            restart_count[0] += 1
            if restart_count[0] >= 3:
                enough.set()

        sup = Supervisor(intervalo=self._TICK)
        sup.registrar("cam", is_alive, restart)
        sup.start()
        triggered = enough.wait(timeout=3.0)
        sup.stop()

        assert triggered, f"Worker only restarted {restart_count[0]} times, expected ≥ 3"

