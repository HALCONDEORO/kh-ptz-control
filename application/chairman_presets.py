#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# chairman_presets.py — Persistencia de presets de cámara por persona para Chairman
from __future__ import annotations
#
# Responsabilidad única: cargar y guardar el archivo chairman_presets.json,
# que mapea nombre de asistente → número de preset VISCA en Cam1 (Platform).
#
# ESTRUCTURA DEL ARCHIVO:
#   {
#     "Marco": 10,
#     "PersonC": 11,
#     "Gary":  12
#   }
#
# MOTIVO DE ARCHIVO SEPARADO:
#   seat_names.json gestiona asignaciones de asientos (quién está sentado dónde).
#   Los presets de Chairman son datos de cámara, no de sala — separarlo evita
#   mezclar dos responsabilidades distintas en el mismo archivo y facilita
#   exportar/importar configuraciones de cámara independientemente.
#
# RANGO DE PRESETS RESERVADOS PARA CHAIRMAN:
#   Presets 1-3 están ocupados por Chairman/Left/Right genéricos.
#   Los presets personales se asignan desde CHAIRMAN_PRESET_START (10)
#   hacia arriba, uno por persona, hasta CHAIRMAN_PRESET_MAX (89).
#   MOTIVO del 10: deja margen para otros presets de sistema en 4-9.
#   MOTIVO del 89: límite antes del bloque reservado VISCA (0x5A en adelante
#   según algunas cámaras; 89 = 0x59 es el último seguro del rango directo).

import logging
from core.json_io import load_json, save_json

from runtime.path_resolver import RuntimePathResolver as _R
CHAIRMAN_PRESETS_FILE = _R().chairman_presets_file
from domain.preset import PRESET_SLOT_MIN, PRESET_SLOT_MAX, PRESET_CHAIRMAN_GENERIC

logger = logging.getLogger(__name__)
# Aliases exported for backward compatibility with external code and tests.
# CHAIRMAN_GENERIC_PRESET re-exports the domain constant so there is a single
# source of truth for the fallback value (domain/preset.py).
CHAIRMAN_PRESET_START   = PRESET_SLOT_MIN
CHAIRMAN_PRESET_MAX     = PRESET_SLOT_MAX
CHAIRMAN_GENERIC_PRESET = PRESET_CHAIRMAN_GENERIC


def load_chairman_presets() -> dict[str, int]:
    """
    Carga el mapa nombre→número_de_preset desde chairman_presets.json.
    Devuelve dict vacío si el archivo no existe o está corrupto.

    Si el JSON contiene dos personas con el mismo número de preset (duplicado),
    se mantiene la primera aparición y se descarta la segunda, registrando
    un warning para que el administrador pueda corregirlo manualmente.
    """
    data = load_json(CHAIRMAN_PRESETS_FILE, default={})
    if not isinstance(data, dict):
        logger.warning("%s: formato inesperado — iniciando sin presets personales", CHAIRMAN_PRESETS_FILE)
        return {}

    result: dict[str, int] = {}
    seen: dict[int, str] = {}  # preset_num → primer nombre que lo reclamó

    for name, preset in data.items():
        if not isinstance(preset, int):
            logger.warning("Preset de '%s' ignorado: valor no entero (%r)", name, preset)
            continue
        if not (CHAIRMAN_PRESET_START <= preset <= CHAIRMAN_PRESET_MAX):
            logger.warning(
                "Preset de '%s' ignorado: %d fuera de rango [%d, %d]",
                name, preset, CHAIRMAN_PRESET_START, CHAIRMAN_PRESET_MAX,
            )
            continue
        if preset in seen:
            logger.warning(
                "Preset %d duplicado en chairman_presets.json: "
                "'%s' y '%s' comparten el mismo número. "
                "Se mantiene '%s', se descarta '%s'. "
                "Guarda de nuevo la posición de '%s' para resolverlo.",
                preset, seen[preset], name, seen[preset], name, name,
            )
            continue
        seen[preset] = name
        result[name] = preset

    return result


def save_chairman_presets(presets: dict[str, int]) -> bool:
    """Persiste el mapa nombre→preset en chairman_presets.json. Devuelve True si tiene éxito."""
    result = save_json(CHAIRMAN_PRESETS_FILE, presets)
    if not result:
        logger.error("Error guardando %s", CHAIRMAN_PRESETS_FILE)
    return result


def next_available_preset(presets: dict[str, int]) -> int | None:
    """
    Devuelve el siguiente número de preset libre en el rango reservado.
    Devuelve None si el rango está agotado (más de 79 personas con preset).
    MOTIVO: asignar automáticamente evita que el operador tenga que
    conocer los números internos de preset VISCA.
    """
    used = set(presets.values())
    for n in range(CHAIRMAN_PRESET_START, CHAIRMAN_PRESET_MAX + 1):
        if n not in used:
            return n
    return None  # rango agotado — situación muy improbable (80 personas: slots 10–89)


def get_preset_for_name(presets: dict[str, int], name: str) -> int:
    """
    Devuelve el número de preset asociado a name, o el genérico si no existe.
    Centraliza la lógica de fallback para no repetirla en MainWindow y en
    ChairmanButton.
    """
    return presets.get(name, CHAIRMAN_GENERIC_PRESET)
