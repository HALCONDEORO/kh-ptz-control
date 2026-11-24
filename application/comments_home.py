#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/comments_home.py — Posición editable de Comments → Home
#
# Comments → Home envía Cam2 a su home mecánico VISCA por defecto. El operador
# puede redefinir esa posición: una pulsación larga (5 s) sobre el botón guarda
# el encuadre actual en un slot VISCA dedicado de la memoria de Cam2
# (domain.preset.PRESET_COMMENTS_HOME), y este servicio recuerda que existe una
# posición personalizada.
#
# ESTRUCTURA DEL ARCHIVO (comments_home.json):
#   {"slot": 3}
#
# La posición en sí vive en la memoria de la cámara (sobrevive reinstalaciones
# de la app); el archivo solo registra qué slot la contiene. Si el archivo
# falta o es inválido, el botón vuelve al home mecánico aunque la cámara aún
# conserve el slot — basta otra pulsación larga para reactivarlo.
#
# Sin Qt. Sin I/O de red. Solo lógica de negocio + persistencia JSON.

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

from core.json_io import load_json, save_json
from config import PRESET_MAP

from runtime.path_resolver import RuntimePathResolver as _R
# Resuelto en importación, no por instancia (mismo patrón que
# chairman_presets.py): los tests parchean RuntimePathResolver después del
# import y una resolución tardía rompería build_app_context.
COMMENTS_HOME_FILE = _R().comments_home_file

logger = logging.getLogger(__name__)


class CommentsHomeService:
    """
    Dueño único del slot de la posición personalizada de Comments → Home.

    Thread-safety: el lock protege solo lecturas/escrituras del slot en
    memoria. La I/O de disco se realiza fuera del lock para no bloquear
    hilos de worker.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else COMMENTS_HOME_FILE
        self._lock = threading.Lock()
        self._slot: Optional[int] = self._load()

    def _load(self) -> Optional[int]:
        data = load_json(self._path, default=None)
        if data is None:
            return None
        if isinstance(data, dict):
            slot = data.get("slot")
            if isinstance(slot, int) and not isinstance(slot, bool) and slot in PRESET_MAP:
                return slot
        logger.warning("comments_home: entrada inválida en %s — ignorando", self._path)
        return None

    def saved_slot(self) -> Optional[int]:
        """Slot VISCA de la posición personalizada, o None si nunca se guardó."""
        with self._lock:
            return self._slot

    def set_slot(self, slot: int) -> bool:
        """Persiste el slot tras un save_preset confirmado. True si quedó guardado."""
        if slot not in PRESET_MAP:
            logger.error("comments_home: slot %r fuera de PRESET_MAP", slot)
            return False
        if not save_json(self._path, {"slot": slot}):
            logger.error("comments_home: no se pudo persistir %s", self._path)
            return False
        with self._lock:
            self._slot = slot
        return True
