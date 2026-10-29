#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_atem_optional.py — Tests para issue #172: ATEM opcional y no crítico

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QCoreApplication

# Asegura que existe una app para QThread.
if not QCoreApplication.instance():
    _app = QCoreApplication(sys.argv)

from PyQt5.QtCore import Qt
from application.runtime_state_store import RuntimeStateStore
from domain.atem_state import ATEMState


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _collect_states(monitor, timeout_ms: int = 3000) -> list[ATEMState]:
    """Ejecuta el monitor en un hilo y recoge todos los estados emitidos.

    Usa DirectConnection para que los signals se entreguen sin event loop.
    Parchea _SIM_FLAG para que los tests no entren en modo simulación aunque
    sim_ip_backup.json exista en el directorio de trabajo.
    """
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
                monitor.wait(1000)
    return states


# ─── config.py ────────────────────────────────────────────────────────────────

class TestATEMConfig:
    def test_atem_ip_default_is_empty(self):
        """ATEM.ip default must be '' — no hardcoded fallback IP."""
        import config as cfg
        assert cfg.ATEM.ip == "", "ATEM.ip fallback must be empty string, not a fake IP"

    def test_no_fake_fallback_ip(self):
        """CAM1/CAM2 IPs must default to empty string, not hardcoded addresses."""
        import config as cfg
        assert cfg.CAM1.ip == "", "CAM1 fallback must be empty (use config.yaml)"
        assert cfg.CAM2.ip == "", "CAM2 fallback must be empty (use config.yaml)"

    def test_invalid_ip_rejected(self):
        from config import is_valid_ip
        assert not is_valid_ip("999.0.0.1")
        assert not is_valid_ip("not-an-ip")
        assert not is_valid_ip("176.16.1")
        assert not is_valid_ip("")


# ─── ATEMMonitor con IP vacía → NOT_CONFIGURED ────────────────────────────────

class TestATEMMonitorNotConfigured:
    def test_empty_ip_emits_not_configured(self):
        from adapters.atem_monitor import ATEMMonitor
        monitor = ATEMMonitor("")
        states = _collect_states(monitor)
        assert ATEMState.NOT_CONFIGURED in states, f"Estados recibidos: {states}"

    def test_whitespace_ip_emits_not_configured(self):
        from adapters.atem_monitor import ATEMMonitor
        monitor = ATEMMonitor("   ")
        states = _collect_states(monitor)
        assert ATEMState.NOT_CONFIGURED in states, f"Estados recibidos: {states}"

    def test_invalid_ip_emits_not_configured(self):
        from adapters.atem_monitor import ATEMMonitor
        monitor = ATEMMonitor("999.0.0.1")
        states = _collect_states(monitor)
        assert ATEMState.NOT_CONFIGURED in states, f"Estados recibidos: {states}"

    def test_not_configured_does_not_crash(self):
        """El monitor debe terminar limpiamente sin IP configurada."""
        from adapters.atem_monitor import ATEMMonitor
        monitor = ATEMMonitor("")
        _collect_states(monitor, timeout_ms=2000)
        assert not monitor.isRunning(), "El hilo debe terminar solo cuando no hay IP"

    def test_not_configured_is_mirrored_to_runtime_state_store(self):
        from adapters.atem_monitor import ATEMMonitor
        store = RuntimeStateStore()
        monitor = ATEMMonitor("", runtime_state_store=store)

        states = _collect_states(monitor, timeout_ms=2000)

        assert ATEMState.NOT_CONFIGURED in states
        assert store.snapshot().atem.connection_state == "not_configured"


# ─── ATEMMonitor sin PyATEMMax → DEPENDENCY_MISSING ──────────────────────────

class TestATEMMonitorDependencyMissing:
    def test_missing_pyatemmax_emits_dependency_missing(self):
        from adapters.atem_monitor import ATEMMonitor
        with patch.dict(sys.modules, {"PyATEMMax": None}):
            monitor = ATEMMonitor("192.168.1.1")
            states = _collect_states(monitor)
        assert ATEMState.DEPENDENCY_MISSING in states, f"Estados recibidos: {states}"

    def test_missing_pyatemmax_does_not_crash(self):
        from adapters.atem_monitor import ATEMMonitor
        with patch.dict(sys.modules, {"PyATEMMax": None}):
            monitor = ATEMMonitor("192.168.1.1")
            _collect_states(monitor, timeout_ms=2000)
        assert not monitor.isRunning(), "El hilo debe terminar solo cuando falta la dependencia"


# ─── ATEMMonitor sin hardware → DISCONNECTED ──────────────────────────────────

class TestATEMMonitorDisconnected:
    def test_unreachable_host_emits_disconnected(self):
        """ATEM no alcanzable → estado DISCONNECTED (no crash)."""
        import adapters.atem_monitor as _am
        mock_atem_instance = MagicMock()
        mock_atem_instance.waitForConnection.return_value = False
        mock_pyatemmax = MagicMock()
        mock_pyatemmax.ATEMMax.return_value = mock_atem_instance

        from adapters.atem_monitor import ATEMMonitor
        with patch.dict(sys.modules, {"PyATEMMax": mock_pyatemmax}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("10.0.0.99")
            states = _collect_states(monitor)

        assert ATEMState.DISCONNECTED in states, f"Estados recibidos: {states}"
        assert ATEMState.CONNECTED not in states

    def test_connection_exception_emits_disconnected(self):
        """Excepción al conectar → DISCONNECTED (no crash)."""
        import adapters.atem_monitor as _am
        mock_atem_instance = MagicMock()
        mock_atem_instance.connect.side_effect = OSError("Network unreachable")
        mock_pyatemmax = MagicMock()
        mock_pyatemmax.ATEMMax.return_value = mock_atem_instance

        from adapters.atem_monitor import ATEMMonitor
        with patch.dict(sys.modules, {"PyATEMMax": mock_pyatemmax}), \
             patch.object(_am.ATEMMonitor, "_wait_interruptible", return_value=False):
            monitor = ATEMMonitor("10.0.0.99")
            states = _collect_states(monitor)

        assert ATEMState.DISCONNECTED in states, f"Estados recibidos: {states}"


class TestATEMRuntimeStateStore:
    def test_connected_state_clears_previous_runtime_error(self):
        from adapters.atem_monitor import ATEMMonitor
        store = RuntimeStateStore()
        store.update_atem(connection_state="error", last_error="previous")
        monitor = ATEMMonitor("192.168.1.1", runtime_state_store=store)

        monitor._emit_state(ATEMState.CONNECTED)

        snapshot = store.snapshot()
        assert snapshot.atem.connection_state == "connected"
        assert snapshot.atem.last_error is None

    def test_error_state_keeps_runtime_error_message(self):
        from adapters.atem_monitor import ATEMMonitor
        store = RuntimeStateStore()
        monitor = ATEMMonitor("192.168.1.1", runtime_state_store=store)

        monitor._emit_state(ATEMState.ERROR, last_error="poll failed")

        snapshot = store.snapshot()
        assert snapshot.atem.connection_state == "error"
        assert snapshot.atem.last_error == "poll failed"

    def test_store_failure_does_not_block_state_signal(self):
        from adapters.atem_monitor import ATEMMonitor

        class BrokenStore:
            def update_atem(self, **kwargs):
                raise RuntimeError("store unavailable")

        monitor = ATEMMonitor("192.168.1.1", runtime_state_store=BrokenStore())
        states = []
        monitor.state_changed.connect(states.append, Qt.DirectConnection)

        monitor._emit_state(ATEMState.CONNECTED)

        assert monitor.state == ATEMState.CONNECTED
        assert states == [ATEMState.CONNECTED]


# ─── ATEMState enum ────────────────────────────────────────────────────────────

class TestATEMStateEnum:
    def test_all_states_defined(self):
        expected = {
            "NOT_CONFIGURED", "DEPENDENCY_MISSING",
            "CONNECTING", "CONNECTED", "DISCONNECTED", "ERROR", "RECONNECTING",
        }
        actual = {s.name for s in ATEMState}
        assert actual == expected

    def test_states_are_distinct(self):
        values = [s.value for s in ATEMState]
        assert len(values) == len(set(values))
