#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# atem_monitor.py — Monitor de programa del switcher BlackMagic ATEM
#
# Corre en un hilo daemon y emite program_changed(int) con el input de programa
# activo cada vez que cambia. Emite state_changed(ATEMState) en cada transición.
# Emite pip_changed(ATEMPiPState) cuando el estado de Picture-in-Picture cambia.
# La lógica de qué acción tomar con cada input vive en ATEMDispatcher.
#
# POLÍTICA DE REINTENTOS:
#   Usa ATEM_RETRY_POLICY de domain.retry_policy (backoffs: 2, 5, 15 s).
#   Si todos los intentos fallan emite DISCONNECTED y termina.
#   El hilo puede interrumpirse en cualquier momento (requestInterruption).
#
# MODO SIMULACIÓN (LEGACY — shim, ver #750):
#   Cola legacy hardware_simulator.atem_event_queue / pip_event_queue.
#   Este path está SUPERSEDIDO por FakeATEM (adapters/fake_atem.py).
#   MainWindow._start_atem_monitor selecciona FakeATEM directamente en perfil
#   demo/simulación y NO construye este ATEMMonitor, por lo que _run_simulated()
#   ya no está en la ruta de runtime y NO es la fuente de verdad del ATEM.
#   Se conserva sólo como shim de compatibilidad para construcción directa en
#   tests; no añadir aquí nueva lógica de simulación — usar FakeATEM.

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from PyQt5.QtCore import QThread, pyqtSignal

from domain.atem_state import ATEMPiPState, ATEMState
from config import is_valid_ip
from domain.retry_policy import ATEM_RETRY_POLICY
from adapters.sim_mode import is_active as _sim_is_active

if TYPE_CHECKING:
    from application.runtime_state_store import RuntimeStateStore

logger = logging.getLogger(__name__)


class ATEMMonitor(QThread):
    """
    Hilo daemon que monitoriza el programa del ATEM vía Ethernet (TCP 9910).
    Emite program_changed(int) con el input activo cada vez que cambia.
    Emite state_changed(ATEMState) en cada transición de estado relevante.

    Tras fallo de conexión reintenta con backoff creciente (ATEM_RETRY_POLICY).
    El hilo puede interrumpirse limpiamente en cualquier punto de espera.

    En modo simulación (sim_ip_backup.json presente) escucha la cola de
    hardware_simulator en lugar de conectar al hardware real.
    """

    program_changed    = pyqtSignal(int)     # input de programa actual al cambiar
    state_changed      = pyqtSignal(object)  # ATEMState
    input_names_ready  = pyqtSignal(dict)    # {input_id: name} tras conectar al ATEM real
    pip_changed        = pyqtSignal(object)  # ATEMPiPState — PiP activado/desactivado

    def __init__(
        self,
        ip: str,
        parent=None,
        runtime_state_store: 'RuntimeStateStore | None' = None,
    ):
        super().__init__(parent)
        self._ip = ip.strip() if ip else ""
        self._state: ATEMState | None = None
        self.last_error: str = ""
        self._store = runtime_state_store  # #793 — fuente unica de verdad
        self._pip_enabled: bool | None = None  # None = estado aún desconocido

    @property
    def state(self) -> ATEMState | None:
        return self._state

    def _safe_store_update(self, **kwargs) -> None:
        """Update RuntimeStateStore without raising — store errors must not crash the monitor."""
        if self._store is not None:
            try:
                self._store.update_atem(**kwargs)
            except Exception:  # noqa: BLE001
                pass

    def _emit_state(self, state: ATEMState, last_error: str = "") -> None:
        self._state = state
        self.state_changed.emit(state)
        self._safe_store_update(
            connection_state=state.name.lower(),
            last_error=last_error if last_error else None,
            clear_error=(not last_error),
        )

    # ── Punto de entrada del hilo ─────────────────────────────────────────────

    def run(self):
        if _sim_is_active():
            self._run_simulated()
            return

        if not self._ip:
            logger.info("ATEM: IP no configurada — monitorización desactivada")
            self._emit_state(ATEMState.NOT_CONFIGURED)
            return

        if not is_valid_ip(self._ip):
            logger.info("ATEM: IP inválida '%s' — monitorización desactivada", self._ip)
            self._emit_state(ATEMState.NOT_CONFIGURED)
            return

        try:
            import PyATEMMax
        except ImportError:
            logger.warning("PyATEMMax no instalado — monitorización ATEM desactivada")
            self._emit_state(ATEMState.DEPENDENCY_MISSING)
            return

        self._run_with_retry(PyATEMMax)

    # ── Ciclo de conexión con reintentos ──────────────────────────────────────

    def _run_with_retry(self, PyATEMMax) -> None:
        policy = ATEM_RETRY_POLICY
        max_attempts = policy.max_attempts

        for attempt in range(1, max_attempts + 1):
            if self.isInterruptionRequested():
                return

            self._emit_state(ATEMState.CONNECTING)
            atem = PyATEMMax.ATEMMax()
            connected = False

            try:
                atem.connect(self._ip)
                if atem.waitForConnection(timeout=10):
                    connected = True
                else:
                    msg = f"No response from {self._ip} (attempt {attempt}/{max_attempts})"
                    logger.warning("ATEM no responde en %s (intento %d/%d)", self._ip, attempt, max_attempts)
                    self.last_error = msg
            except Exception as exc:
                msg = f"{exc} (attempt {attempt}/{max_attempts})"
                logger.warning("Error conectando al ATEM %s (intento %d/%d): %s", self._ip, attempt, max_attempts, exc)
                self.last_error = msg

            if connected:
                logger.info("ATEM conectado en %s (intento %d)", self._ip, attempt)
                self.last_error = ""
                self._emit_state(ATEMState.CONNECTED)
                names = self._read_input_names(atem, PyATEMMax)
                if names:
                    logger.info("[ATEM] Nombres de inputs leídos: %s", names)
                    self.input_names_ready.emit(names)
                try:
                    self._poll_loop(atem)
                finally:
                    self._close_atem(atem)
                return

            self._close_atem(atem)

            if self.isInterruptionRequested():
                return

            # Última tentativa fallida → DISCONNECTED
            if attempt == max_attempts:
                logger.warning(
                    "ATEM: todos los intentos agotados (%d/%d) — marcando DISCONNECTED",
                    attempt, max_attempts,
                )
                self._emit_state(ATEMState.DISCONNECTED)
                return

            # Espera con backoff antes del siguiente intento
            backoff = policy.backoffs[attempt - 1]
            logger.info(
                "ATEM: reintentando en %ds (intento %d/%d completado)",
                backoff, attempt, max_attempts,
            )
            self._emit_state(ATEMState.RECONNECTING)
            if self._wait_interruptible(backoff):
                return  # hilo interrumpido durante la espera

    def _close_atem(self, atem) -> None:
        """Cierra recursos del cliente ATEM probando los métodos disponibles en orden."""
        for method_name in ("disconnect", "close", "stop"):
            method = getattr(atem, method_name, None)
            if not callable(method):
                continue
            try:
                method()
                return
            except Exception as exc:
                logger.debug("ATEM: error cerrando cliente con %s(): %s", method_name, exc)

    # ── Lectura de nombres de inputs ──────────────────────────────────────────

    def _read_input_names(self, atem, PyATEMMax) -> dict:
        """Lee los nombres de TODAS las fuentes de vídeo disponibles en el ATEM.

        Itera sobre todos los miembros de ATEMVideoSources (inputs físicos, Black,
        Color Bars, Color 1/2, Media Players, SuperSource, etc.) y devuelve las
        que el hardware reporta con nombre en inputProperties.

        El ATEM solo incluye en inputProperties las fuentes que ese modelo soporta,
        así que el resultado varía por modelo sin necesitar ningún rango hardcodeado.
        Devuelve {source_id: name} solo con fuentes que tienen nombre no vacío.
        """
        names: dict = {}
        try:
            all_sources = list(PyATEMMax.ATEMVideoSources)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ATEM] no se pudo iterar ATEMVideoSources: %s", exc)
            return names

        for source in all_sources:
            try:
                source_id = int(source)
                prop = atem.inputProperties[source]
                name = (getattr(prop, "longName", None) or
                        getattr(prop, "shortName", None) or "").strip()
                if name:
                    names[source_id] = name
            except Exception:  # noqa: BLE001
                pass  # fuente no disponible en este modelo — ignorar

        logger.info("[ATEM] %d fuentes leídas del switcher: %s", len(names), sorted(names.keys()))
        return names

    # ── Bucle de polling del programa + PiP ──────────────────────────────────

    def _poll_loop(self, atem) -> None:
        prev_input = None
        while not self.isInterruptionRequested():
            try:
                cur = int(atem.programInput[0].videoSource)
                if self._state == ATEMState.ERROR:
                    logger.info("ATEM: poll recovered from ERROR — marking CONNECTED")
                    self._emit_state(ATEMState.CONNECTED)
                if cur != prev_input:
                    self.program_changed.emit(cur)
                    self._safe_store_update(program_input=cur)
                prev_input = cur
            except Exception:
                logger.exception("ATEM poll cycle failed")
                if self._state != ATEMState.ERROR:
                    self._emit_state(ATEMState.ERROR, last_error="poll cycle failed")
            self._poll_pip(atem)
            time.sleep(0.1)

    def _poll_pip(self, atem) -> None:
        """Comprueba el estado PiP del ATEM y emite pip_changed si ha cambiado.

        PyATEMMax expone el estado PiP en ``atem.pictureInPicture[0]``.
        Los atributos relevantes son ``enabled`` (bool) y ``source`` (int-like).
        No lanza — cualquier fallo del API se ignora para no interrumpir el hilo.
        """
        try:
            pip_block = atem.pictureInPicture[0]
            enabled = bool(getattr(pip_block, "enabled", False))
            source_raw = getattr(pip_block, "source", None)
            try:
                source = int(source_raw) if source_raw is not None else None
            except (ValueError, TypeError):
                source = None
        except Exception:  # noqa: BLE001
            return  # hardware sin soporte PiP o API no disponible — silencio

        if self._pip_enabled is None:
            # Primera lectura tras conectar — inicializa silenciosamente.
            # Solo emite si PiP ya está activo al conectar; descarta el "off" inicial
            # para evitar un evento espurio en cada arranque.
            self._pip_enabled = enabled
            if not enabled:
                return
        elif enabled == self._pip_enabled:
            return  # sin cambio

        self._pip_enabled = enabled
        pip_state = ATEMPiPState(enabled=enabled, source=source if enabled else None)
        logger.info(
            "ATEM PiP: %s (source=%s)",
            "ON" if enabled else "OFF",
            source if enabled else "-",
        )
        self.pip_changed.emit(pip_state)

    # ── Espera interrumpible ──────────────────────────────────────────────────

    def _wait_interruptible(self, seconds: float) -> bool:
        """Espera hasta `seconds` comprobando interrupción cada 0.2s.

        Devuelve True si el hilo fue interrumpido antes de que terminara la espera.
        """
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.isInterruptionRequested():
                return True
            time.sleep(0.2)
        return False

    # ── Modo simulación ───────────────────────────────────────────────────────

    def _run_simulated(self):
        """LEGACY shim (#750): escucha atem_event_queue / pip_event_queue.

        Supersedido por FakeATEM. Fuera de la ruta de runtime demo/simulación
        (MainWindow selecciona FakeATEM y no construye ATEMMonitor). Conservado
        sólo para construcción directa en tests; no es fuente de verdad del ATEM.
        """
        import queue as _queue
        import adapters.hardware_simulator as _hw

        logger.info("ATEMMonitor: modo simulacion activo")
        self._emit_state(ATEMState.CONNECTED)

        while not self.isInterruptionRequested():
            # ── Eventos de programa ───────────────────────────────────────────
            try:
                event = _hw.atem_event_queue.get_nowait()
                if event == "switch_to_input2":
                    logger.info("ATEM sim: evento Input 3->2 recibido")
                    self.program_changed.emit(2)
                    self._safe_store_update(program_input=2)
                elif event == "switch_to_input3":
                    logger.info("ATEM sim: evento Input 2->3 recibido")
                    self.program_changed.emit(3)
                    self._safe_store_update(program_input=3)
            except _queue.Empty:
                pass

            # ── Eventos PiP ───────────────────────────────────────────────────
            # Formato: "pip_on" | "pip_on:<source>" | "pip_off"
            try:
                pip_event = _hw.pip_event_queue.get_nowait()
                self._handle_sim_pip_event(pip_event)
            except _queue.Empty:
                pass

            time.sleep(0.05)

    def _handle_sim_pip_event(self, event: str) -> None:
        """Procesa un evento PiP del simulador y emite pip_changed si procede."""
        if event.startswith("pip_on"):
            source: int | None = None
            if ":" in event:
                try:
                    source = int(event.split(":", 1)[1])
                except ValueError:
                    pass
            pip_state = ATEMPiPState(enabled=True, source=source)
        elif event == "pip_off":
            pip_state = ATEMPiPState(enabled=False, source=None)
        else:
            logger.warning("ATEM sim: evento PiP desconocido %r — ignorado", event)
            return

        if pip_state.enabled == self._pip_enabled:
            return  # sin cambio, no emitir

        self._pip_enabled = pip_state.enabled
        logger.info(
            "ATEM sim PiP: %s (source=%s)",
            "ON" if pip_state.enabled else "OFF",
            pip_state.source if pip_state.enabled else "-",
        )
        self.pip_changed.emit(pip_state)
