#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# preset_brightness.py — Persistencia de valor de brillo por slot de preset
#
# Responsabilidad única: guardar y cargar el mapa slot→{level, mode} en
# preset_brightness.json para que el operador pueda ver y restaurar
# el brillo asociado a cada preset (plataforma y personales).
#
# ESTRUCTURA DEL ARCHIVO:
#   {
#     "1":  {"level": 12, "mode": "bright"},
#     "2":  {"level": -3, "mode": "auto"},
#     "10": {"level":  8, "mode": "manual"}
#   }
#
# Claves: número de slot VISCA como string (para compatibilidad JSON).
# level: brillo 0–23 en modos manual/bright (CAM_BrightPos),
#        o -7..+7 en modo auto (CAM_ExpComp).
# mode:  'auto' | 'manual' | 'bright' — necesario para saber qué comando
#        usar al restaurar (bright_pos_set solo aplica a manual/bright).

from __future__ import annotations

import logging
import threading
from typing import Optional

from core.json_io import load_json, save_json

logger = logging.getLogger(__name__)

_lock   = threading.Lock()
_cache: dict[int, dict] = {}
_loaded = False


def _brightness_file():
    from runtime.path_resolver import RuntimePathResolver
    return RuntimePathResolver().preset_brightness_file


def _load_into_cache(data: dict) -> None:
    """Populate _cache from the raw JSON dict. Called with _lock held."""
    for k, v in data.items():
        try:
            slot = int(k)
            if isinstance(v, dict):
                _cache[slot] = {"level": int(v["level"]), "mode": str(v.get("mode", "auto"))}
            else:
                # Formato antiguo (solo entero): migrar a dict, modo desconocido
                _cache[slot] = {"level": int(v), "mode": "auto"}
        except (ValueError, TypeError, KeyError):
            logger.warning("preset_brightness: entrada inválida ignorada: %r=%r", k, v)


def _ensure_loaded_locked() -> None:
    """Must be called with _lock already held."""
    global _loaded
    if _loaded:
        return
    data = load_json(_brightness_file(), default={})
    if isinstance(data, dict):
        _load_into_cache(data)
    _loaded = True


def get_entry(slot: int) -> Optional[dict]:
    """Devuelve {'level': int, 'mode': str} para slot, o None si no existe."""
    with _lock:
        _ensure_loaded_locked()
        return _cache.get(slot)


def save_brightness(slot: int, level: int, mode: str) -> None:
    """Guarda el nivel y modo de exposición para slot y persiste en disco."""
    with _lock:
        _ensure_loaded_locked()
        _cache[slot] = {"level": level, "mode": mode}
        to_save = {str(k): v for k, v in sorted(_cache.items())}
    path = _brightness_file()
    ok = save_json(path, to_save)
    if not ok:
        logger.error("preset_brightness: error guardando %s", path)
