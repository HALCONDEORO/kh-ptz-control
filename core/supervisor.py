#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# core/supervisor.py — Supervisor de workers: detecta y reinicia threads caídos

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Intervalo de sondeo entre comprobaciones de salud (segundos).
_INTERVALO_SONDEO = 10.0


class Supervisor:
    """
    Comprueba periódicamente los workers registrados y los reinicia si fallan.

    Cada worker se describe con tres argumentos en register():
      nombre    — etiqueta usada en los mensajes de log
      esta_vivo — () -> bool: devuelve True si el worker funciona correctamente
      reiniciar — () -> None: recrea o reinicia el worker; debe ser idempotente

    Ambas funciones se invocan desde el hilo daemon del supervisor.
    Si reiniciar() toca objetos Qt, envuélvela con QTimer.singleShot(0, fn)
    para que el trabajo real ocurra en el hilo principal de Qt.
    """

    def __init__(self, intervalo: float = _INTERVALO_SONDEO) -> None:
        self._intervalo = intervalo
        self._workers: list[tuple[str, Callable[[], bool], Callable[[], None]]] = []
        self._parar = threading.Event()
        self._hilo: Optional[threading.Thread] = None  # creado en start()

    def registrar(
        self,
        nombre: str,
        esta_vivo: Callable[[], bool],
        reiniciar: Callable[[], None],
    ) -> None:
        """Registra un worker para monitorizar. Llamar antes de start()."""
        self._workers.append((nombre, esta_vivo, reiniciar))

    def start(self) -> None:
        """Inicia el hilo daemon del supervisor. Idempotente: no hace nada si ya corre."""
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._parar.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="Supervisor")
        self._hilo.start()
        logger.info("Supervisor iniciado — monitorizando %d worker(s)", len(self._workers))

    def stop(self) -> None:
        """Detiene el supervisor y espera a que su hilo termine. Idempotente."""
        self._parar.set()
        if self._hilo is not None and self._hilo.is_alive():
            self._hilo.join(timeout=self._intervalo + 2)

    def _bucle(self) -> None:
        while not self._parar.wait(self._intervalo):
            for nombre, esta_vivo, reiniciar in self._workers:
                try:
                    if not esta_vivo():
                        logger.warning("Supervisor: %s caído — reiniciando", nombre)
                        reiniciar()
                        logger.info("Supervisor: %s reiniciado", nombre)
                except Exception:
                    logger.exception("Supervisor: error inesperado gestionando %s", nombre)
