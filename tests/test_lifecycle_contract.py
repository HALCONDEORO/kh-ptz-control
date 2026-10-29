#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_lifecycle_contract.py — Lifecycle contract invariants (#691).

Covers:
- Session is not active immediately after build_app_context().
- Shutdown while a pending timer has been started does not raise.
- Supervisor.stop() called during its startup interval does not raise.
- AsyncEventBus.stop() before any events are dispatched does not raise.
"""
from __future__ import annotations



from bootstrap import build_app_context
from core.supervisor import Supervisor
from core.events import AsyncEventBus


class _FakeCamera:
    """Minimal stub — no sockets, no threads."""
    pass


# ── Invariant: session is inactive at boot ────────────────────────────────────

class TestSessionNotActiveAtBoot:

    def test_session_not_active_after_build_app_context(self):
        """SessionService.active must be False immediately after AppContext is built."""
        ctx = build_app_context(_FakeCamera())
        try:
            assert ctx.session_svc.active is False
        finally:
            ctx.bus.stop()

    def test_session_id_is_none_at_boot(self):
        """No session_id should exist before an explicit session start."""
        ctx = build_app_context(_FakeCamera())
        try:
            assert ctx.session_svc.session_id is None
        finally:
            ctx.bus.stop()


# ── Invariant: shutdown-during-pending-timer does not raise ───────────────────

class TestShutdownDuringPendingTimer:
    """
    Simulates stopping the Supervisor while its internal timer (threading.Event.wait)
    is still blocking.  This is the 'shutdown during startup timer' scenario from #691.

    The Supervisor's _parar event is set; the daemon thread wakes up and exits.
    No exception must propagate to the caller.
    """

    def test_supervisor_stop_during_wait_does_not_raise(self):
        """Stopping the Supervisor while it is waiting for its next poll must not raise."""
        # Use a long interval so the supervisor is definitely still in its wait.
        sup = Supervisor(intervalo=60.0)
        sup.start()
        assert sup._hilo is not None and sup._hilo.is_alive()
        # stop() signals the internal event and joins the thread.
        sup.stop()  # must not raise
        assert not sup._hilo.is_alive()

    def test_supervisor_stop_with_registered_worker_during_wait_does_not_raise(self):
        """Stopping with a registered (but never-fired) worker must not raise."""
        restarted = []
        sup = Supervisor(intervalo=60.0)
        sup.registrar("dummy", lambda: True, lambda: restarted.append(1))
        sup.start()
        sup.stop()  # must not raise, worker was never unhealthy
        assert restarted == []  # restart was never triggered

    def test_bus_stop_with_pending_emit_does_not_raise(self):
        """
        Stopping the AsyncEventBus immediately after start (with events possibly
        still enqueued) must not raise.
        """
        from core.events import EventType

        bus = AsyncEventBus()
        bus.start()
        # Emit a low-cost event and stop immediately — race is intentional.
        bus.emit(EventType.SESSION_START)
        bus.stop()  # must not raise

    def test_shutdown_sequence_does_not_raise_with_active_supervisor_and_bus(self):
        """
        Full sequence: build context, start supervisor, stop supervisor, stop bus.
        This mirrors the real teardown path and must complete without exceptions.
        """
        ctx = build_app_context(_FakeCamera())
        sup = Supervisor(intervalo=60.0)
        sup.start()

        # Teardown in shutdown order (steps 5-6 of LIFECYCLE_CONTRACT.md).
        sup.stop()       # step 5: stop Supervisor
        ctx.bus.stop()   # step 6: stop AsyncEventBus

