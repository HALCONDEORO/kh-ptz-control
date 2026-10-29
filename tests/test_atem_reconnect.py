#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_atem_reconnect.py — Tests para issue #173: reintentos y reconexión ATEM

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QCoreApplication, Qt

if not QCoreApplication.instance():
    _app = QCoreApplication(sys.argv)

from domain.atem_state import ATEMState
from domain.retry_policy import ATEM_RETRY_POLICY
from application.runtime_state_store import RuntimeStateStore


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_mock_pyatemmax(*, connect_ok: bool = False, wait_ok: bool = False):
    """Construye un mock de PyATEMMax que falla o tiene éxito según los parámetros."""
    instance = MagicMock()
    instance.waitForConnection.return_value = wait_ok
    if not connect_ok:
        instance.connect.side_effect = OSError("Connection refused") if not connect_ok else None
    mock_module = MagicMock()
    mock_module.ATEMMax.return_value = instance
    return mock_module, instance


class _ProgramInputSequence:
    def __init__(self, monitor, sources):
        self._monitor = monitor
        self._sources = list(sources)
        self._index = 0

    def __getitem__(self, index):
        if self._index >= len(self._sources):
            self._monitor.requestInterruption()
            source = self._sources[-1]
        else:
            source = self._sources[self._index]
        self._index += 1
        item = MagicMock()
        item.videoSource = source
        return item


def _collect_states(monitor, timeout_ms: int = 5000) -> list[ATEMState]:
    """Ejecuta el monitor con DirectConnection y recoge estados emitidos."""
    from unittest.mock import patch

    states: list[ATEMState] = []
    monitor.state_changed.connect(states.append, Qt.DirectConnection)

    with patch("adapters.atem_monitor._sim_is_active", return_value=False):
        try:
            monitor.start()
            monitor.wait(timeout_ms)
        finally:
            if monitor.isRunning():
                monitor.requestInterruption()
                monitor.wait(2000)
    return states


# ─── Política de reintentos ───────────────────────────────────────────────────

class TestRetryPolicy:
    def test_retry_count_bounded(self):
        """El monitor no debe reintentar más de len(_BACKOFFS) veces."""
        import adapters.atem_monitor as _am
        from adapters.atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None  # connect no lanza; waitForConnection False

        expected_attempts = ATEM_RETRY_POLICY.max_attempts

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            _collect_states(monitor, timeout_ms=5000)

        assert mock_module.ATEMMax.call_count == expected_attempts, (
            f"Esperados {expected_attempts} intentos, got {mock_module.ATEMMax.call_count}"
        )

    def test_failed_attempts_close_atem_client(self):
        """Cada intento fallido debe cerrar el cliente ATEM creado."""
        import adapters.atem_monitor as _am
        from adapters.atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None
        expected_attempts = ATEM_RETRY_POLICY.max_attempts

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            _collect_states(monitor, timeout_ms=5000)

        assert instance.disconnect.call_count == expected_attempts

    def test_emits_disconnected_after_all_retries(self):
        """Tras agotar todos los reintentos el estado final debe ser DISCONNECTED."""
        import adapters.atem_monitor as _am
        from adapters.atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=5000)

        assert ATEMState.DISCONNECTED in states, f"Estados: {states}"
        assert states[-1] == ATEMState.DISCONNECTED, f"Último estado debe ser DISCONNECTED: {states}"

    def test_failed_retry_state_sequence_is_stable(self):
        """El flujo de estados en fallo total debe mantener el orden esperado."""
        import adapters.atem_monitor as _am
        from adapters.atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=5000)

        expected = []
        for attempt in range(1, ATEM_RETRY_POLICY.max_attempts + 1):
            expected.append(ATEMState.CONNECTING)
            if attempt <= len(ATEM_RETRY_POLICY.backoffs):
                expected.append(ATEMState.RECONNECTING)
        expected.append(ATEMState.DISCONNECTED)

        assert states == expected

    def test_emits_reconnecting_between_attempts(self):
        """Entre intentos fallidos debe emitirse RECONNECTING."""
        import adapters.atem_monitor as _am
        from adapters.atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=5000)

        assert ATEMState.RECONNECTING in states, f"Estados: {states}"
        # Exactamente len(_BACKOFFS) emisiones de RECONNECTING
        reconnecting_count = states.count(ATEMState.RECONNECTING)
        assert reconnecting_count == len(ATEM_RETRY_POLICY.backoffs), (
            f"Esperados {len(ATEM_RETRY_POLICY.backoffs)} RECONNECTING, got {reconnecting_count}"
        )

    def test_emits_connecting_on_each_attempt(self):
        """Cada intento (inicial + reintentos) debe emitir CONNECTING primero."""
        import adapters.atem_monitor as _am
        from adapters.atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None
        expected_attempts = ATEM_RETRY_POLICY.max_attempts

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=5000)

        connecting_count = states.count(ATEMState.CONNECTING)
        assert connecting_count == expected_attempts, (
            f"Esperados {expected_attempts} CONNECTING, got {connecting_count}"
        )

    def test_no_retry_on_success(self):
        """Si el primer intento tiene éxito no debe haber RECONNECTING."""
        from adapters.atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=True)
        instance.connect.side_effect = None

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}):
            monitor = ATEMMonitor("192.168.1.1")
            instance.programInput = _ProgramInputSequence(monitor, [3])
            states = _collect_states(monitor, timeout_ms=3000)

        assert mock_module.ATEMMax.call_count == 1
        assert ATEMState.CONNECTED in states
        assert ATEMState.RECONNECTING not in states
        instance.disconnect.assert_called_once_with()

    def test_poll_recovery_restores_connected_after_error(self):
        """Un poll correcto después de ERROR debe restaurar CONNECTED."""
        from adapters.atem_monitor import ATEMMonitor

        class _ProgramInput:
            def __init__(self):
                self.calls = 0

            def __getitem__(self, index):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("temporary")
                if self.calls == 3:
                    monitor.requestInterruption()
                item = MagicMock()
                item.videoSource = 3
                return item

        monitor = ATEMMonitor("192.168.1.1")
        atem = MagicMock()
        atem.programInput = _ProgramInput()
        states = []
        monitor.state_changed.connect(states.append, Qt.DirectConnection)
        monitor._emit_state(ATEMState.CONNECTED)

        with patch.object(monitor, "isInterruptionRequested",
                          side_effect=[False, False, True]):
            monitor._poll_loop(atem)

        assert states == [
            ATEMState.CONNECTED,
            ATEMState.ERROR,
            ATEMState.CONNECTED,
        ]

    def test_poll_repeated_failures_emit_error_once(self):
        """Errores consecutivos de polling no deben spamear state_changed(ERROR)."""
        from adapters.atem_monitor import ATEMMonitor

        atem = MagicMock()
        atem.programInput.__getitem__.side_effect = RuntimeError("still failing")
        monitor = ATEMMonitor("192.168.1.1")
        states = []
        monitor.state_changed.connect(states.append, Qt.DirectConnection)
        monitor._emit_state(ATEMState.CONNECTED)

        with patch.object(monitor, "isInterruptionRequested",
                          side_effect=[False, False, False, True]):
            monitor._poll_loop(atem)

        assert states == [ATEMState.CONNECTED, ATEMState.ERROR]

    def test_program_changed_emits_only_when_input_changes(self):
        from adapters.atem_monitor import ATEMMonitor

        monitor = ATEMMonitor("192.168.1.1")
        atem = MagicMock()
        atem.programInput = _ProgramInputSequence(monitor, [3, 3, 2, 2, 1])
        programs = []
        monitor.program_changed.connect(programs.append, Qt.DirectConnection)

        with patch.object(monitor, "isInterruptionRequested",
                          side_effect=([False] * 5) + [True]):
            monitor._poll_loop(atem)

        assert programs == [3, 2, 1]

    def test_poll_loop_mirrors_program_input_to_runtime_state_store(self):
        from adapters.atem_monitor import ATEMMonitor

        store = RuntimeStateStore()
        monitor = ATEMMonitor("192.168.1.1", runtime_state_store=store)
        atem = MagicMock()
        atem.programInput = _ProgramInputSequence(monitor, [3, 2])

        with patch.object(monitor, "isInterruptionRequested",
                          side_effect=[False, False, True]):
            monitor._poll_loop(atem)

        assert store.snapshot().atem.program_input == 2

    def test_poll_loop_does_not_rewrite_program_input_when_unchanged(self):
        from adapters.atem_monitor import ATEMMonitor

        store = RuntimeStateStore()
        received = []
        store.subscribe(received.append)
        monitor = ATEMMonitor("192.168.1.1", runtime_state_store=store)
        atem = MagicMock()
        atem.programInput = _ProgramInputSequence(monitor, [3, 3, 3])

        with patch.object(monitor, "isInterruptionRequested",
                          side_effect=[False, False, False, True]):
            monitor._poll_loop(atem)

        assert store.snapshot().atem.program_input == 3
        assert len(received) == 1

    def test_interruption_before_first_attempt_does_not_create_client(self):
        from adapters.atem_monitor import ATEMMonitor

        mock_module = MagicMock()
        monitor = ATEMMonitor("192.168.1.1")

        with patch.object(monitor, "isInterruptionRequested", return_value=True):
            monitor._run_with_retry(mock_module)

        mock_module.ATEMMax.assert_not_called()
        assert monitor.state is None

    def test_interruption_during_backoff_stops_retries(self):
        """Interrumpir durante el backoff debe detener los reintentos limpiamente."""
        import adapters.atem_monitor as _am
        from adapters.atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None
        # _wait_interruptible devuelve True = fue interrumpido
        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=True):
            monitor = ATEMMonitor("192.168.1.1")
            _collect_states(monitor, timeout_ms=3000)

        # Solo debe haber un intento (el primero) + ningún RECONNECTING procesado
        assert mock_module.ATEMMax.call_count == 1, (
            f"Interrumpido en el primer backoff: esperado 1 intento, got {mock_module.ATEMMax.call_count}"
        )
        instance.disconnect.assert_called_once_with()


# ─── Espera interrumpible ─────────────────────────────────────────────────────

class TestWaitInterruptible:
    def test_returns_false_when_wait_completes(self):
        """Espera corta sin interrupción → devuelve False."""
        from adapters.atem_monitor import ATEMMonitor
        monitor = ATEMMonitor("")
        result = monitor._wait_interruptible(0.05)
        assert result is False

    def test_interruption_exits_retry_loop_early(self):
        """Interrupción durante backoff causa salida anticipada del bucle de reintentos.

        Verifica que el monitor se detiene antes de completar todos los reintentos cuando
        se interrumpe dentro del QThread (comportamiento real de producción).
        """
        import adapters.atem_monitor as _am
        from adapters.atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None

        interrupted_at = []

        def _fake_wait(self, seconds):
            interrupted_at.append(seconds)
            return True  # simula interrupción en el primer backoff

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", _fake_wait):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=3000)

        # Solo el primer backoff debe haberse ejecutado antes de la interrupción
        assert len(interrupted_at) == 1, f"Solo debe haber un backoff antes de la interrupción: {interrupted_at}"
        # El hilo no debe emitir DISCONNECTED (salió limpiamente por interrupción)
        assert ATEMState.DISCONNECTED not in states, f"No debe emitirse DISCONNECTED por interrupción: {states}"

    def test_close_atem_ignores_close_errors(self):
        from adapters.atem_monitor import ATEMMonitor

        atem = MagicMock()
        atem.disconnect.side_effect = RuntimeError("already closed")

        ATEMMonitor("")._close_atem(atem)

        atem.disconnect.assert_called_once_with()

    def test_close_atem_uses_close_when_disconnect_missing(self):
        from adapters.atem_monitor import ATEMMonitor

        class _Atem:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        atem = _Atem()

        ATEMMonitor("")._close_atem(atem)

        assert atem.closed is True

    def test_close_atem_accepts_client_without_close_method(self):
        from adapters.atem_monitor import ATEMMonitor

        ATEMMonitor("")._close_atem(object())


# ─── Escenario de reconexión manual ──────────────────────────────────────────

class TestIndependentMonitorRuns:
    def test_new_monitor_can_connect_after_previous_instance_disconnected(self):
        """Una nueva instancia puede conectar después de que otra terminara en DISCONNECTED."""
        import adapters.atem_monitor as _am
        from adapters.atem_monitor import ATEMMonitor

        # Primera ronda: siempre falla
        mock_fail, instance_fail = _make_mock_pyatemmax(wait_ok=False)
        instance_fail.connect.side_effect = None

        with patch.dict(sys.modules, {"PyATEMMax": mock_fail}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            mon1 = ATEMMonitor("192.168.1.1")
            states1 = _collect_states(mon1, timeout_ms=5000)

        assert ATEMState.DISCONNECTED in states1
        assert not mon1.isRunning()

        # Segunda ronda: tiene éxito con otra instancia independiente.
        mock_ok, instance_ok = _make_mock_pyatemmax(wait_ok=True)
        instance_ok.connect.side_effect = None
        instance_ok.programInput = MagicMock(side_effect=Exception("exit poll"))

        with patch.dict(sys.modules, {"PyATEMMax": mock_ok}):
            mon2 = ATEMMonitor("192.168.1.1")
            states2 = _collect_states(mon2, timeout_ms=3000)

        assert ATEMState.CONNECTED in states2

    def test_reconnect_does_not_emit_connected_when_still_failing(self):
        """Tras reconexión que también falla, el nuevo monitor emite DISCONNECTED (no CONNECTED)."""
        import adapters.atem_monitor as _am
        from adapters.atem_monitor import ATEMMonitor

        mock_module, instance = _make_mock_pyatemmax(wait_ok=False)
        instance.connect.side_effect = None

        with patch.dict(sys.modules, {"PyATEMMax": mock_module}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor, timeout_ms=5000)

        assert ATEMState.CONNECTED not in states
        assert ATEMState.DISCONNECTED in states


# ─── Backoffs configurados son razonables ────────────────────────────────────

class TestATEMSupervisorHealth:
    def test_running_or_pending_restart_is_healthy(self):
        from domain.atem_state import is_atem_supervisor_healthy

        assert is_atem_supervisor_healthy(
            is_running=True,
            restart_pending=False,
            state=None,
        ) is True
        assert is_atem_supervisor_healthy(
            is_running=False,
            restart_pending=True,
            state=ATEMState.ERROR,
        ) is True

    def test_terminal_expected_states_are_healthy(self):
        from domain.atem_state import is_atem_supervisor_healthy

        for state in (
            ATEMState.NOT_CONFIGURED,
            ATEMState.DEPENDENCY_MISSING,
            ATEMState.DISCONNECTED,
        ):
            assert is_atem_supervisor_healthy(
                is_running=False,
                restart_pending=False,
                state=state,
            ) is True

    def test_stopped_error_state_is_unhealthy(self):
        from domain.atem_state import is_atem_supervisor_healthy

        assert is_atem_supervisor_healthy(
            is_running=False,
            restart_pending=False,
            state=ATEMState.ERROR,
        ) is False

    def test_unknown_stopped_state_is_unhealthy(self):
        from domain.atem_state import is_atem_supervisor_healthy

        assert is_atem_supervisor_healthy(
            is_running=False,
            restart_pending=False,
            state=None,
        ) is False


class TestBackoffConstants:
    def test_backoffs_are_positive_and_increasing(self):
        backoffs = ATEM_RETRY_POLICY.backoffs
        assert all(b > 0 for b in backoffs), "Todos los backoffs deben ser positivos"
        assert list(backoffs) == sorted(backoffs), "Los backoffs deben ser crecientes"

    def test_at_least_two_retries(self):
        assert len(ATEM_RETRY_POLICY.backoffs) >= 2, "Debe haber al menos 2 reintentos (3 intentos totales)"
