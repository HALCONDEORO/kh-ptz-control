#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# schedule_config.py — Persistencia y consulta del calendario semanal de bypass de contraseña

from __future__ import annotations

import logging
from datetime import datetime
from core.json_io import load_json, save_json

from runtime.path_resolver import RuntimePathResolver as _R
SCHEDULE_FILE = _R().schedule_file

logger = logging.getLogger(__name__)

# Rango de años plausible para confiar en el bypass por calendario.
# Una Raspberry Pi sin NTP sincronizado puede arrancar en 1970 o en la época Unix.
_CLOCK_MIN_YEAR = 2024
_CLOCK_MAX_YEAR = 2100


def is_clock_plausible() -> bool:
    """Devuelve True si el reloj del sistema está dentro de un rango plausible.

    Una Raspberry Pi sin RTC puede arrancar con año 1970 o una fecha antigua
    hasta que NTP sincronice. Confiar en ese reloj para el auto-login por
    calendario sería un riesgo de seguridad: el calendario podría estar activo
    en un periodo no previsto.

    Devuelve False cuando el año queda fuera de
    [_CLOCK_MIN_YEAR, _CLOCK_MAX_YEAR].
    """
    year = datetime.now().year
    plausible = _CLOCK_MIN_YEAR <= year <= _CLOCK_MAX_YEAR
    if not plausible:
        logger.warning(
            "System clock year %d is outside plausible range [%d, %d] — "
            "schedule bypass disabled. Sync NTP or set the correct date.",
            year, _CLOCK_MIN_YEAR, _CLOCK_MAX_YEAR,
        )
    return plausible

DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

_BOOL_TRUE  = {"true",  "yes", "1"}
_BOOL_FALSE = {"false", "no",  "0"}


def _parse_bool_strict(value: object, context: str) -> bool:
    """Parse a schedule enabled flag strictly.

    Accepts real booleans and a fixed set of string aliases.
    Any unrecognised value is treated as False and logged so the operator
    can correct the file — the schedule must never be accidentally enabled.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in _BOOL_TRUE:
            return True
        if lower in _BOOL_FALSE:
            return False
        logger.warning(
            "schedule.json: unrecognised 'enabled' value %r in %s — "
            "treating as disabled (fail-closed). Use true or false.",
            value, context,
        )
        return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    logger.warning(
        "schedule.json: unexpected 'enabled' type %s in %s — treating as disabled.",
        type(value).__name__, context,
    )
    return False

DEFAULT_SCHEDULE: dict = {
    day: {"enabled": False, "start": "09:00", "end": "17:00"}
    for day in DAYS
}


def load_schedule() -> dict:
    """Leer schedule.json. Devuelve DEFAULT_SCHEDULE si no existe o hay error.

    El dict devuelto incluye la clave especial ``'always_bypass'`` (bool)
    junto a las entradas de días. Esto permite leer y guardar todo desde
    un único punto.
    """
    data = load_json(SCHEDULE_FILE)
    if not isinstance(data, dict):
        result = {day: dict(DEFAULT_SCHEDULE[day]) for day in DAYS}
        result['always_bypass'] = False
        return result
    try:
        result = {}
        result['always_bypass'] = _parse_bool_strict(
            data.get('always_bypass', False), 'always_bypass'
        )
        for day in DAYS:
            entry = data.get(day, DEFAULT_SCHEDULE[day])
            result[day] = {
                "enabled": _parse_bool_strict(entry.get("enabled", False), day),
                "start":   str(entry.get("start", "09:00")),
                "end":     str(entry.get("end",   "17:00")),
            }
        return result
    except (TypeError, AttributeError):
        result = {day: dict(DEFAULT_SCHEDULE[day]) for day in DAYS}
        result['always_bypass'] = False
        return result


def save_schedule(data: dict) -> bool:
    """Guardar calendario en schedule.json. Devuelve True si tiene éxito.

    ``data`` puede incluir la clave ``'always_bypass'`` junto a las entradas
    de días; se persiste todo en el mismo archivo.
    """
    return save_json(SCHEDULE_FILE, data)


def _parse_minutes(entry: dict, key: str) -> int | None:
    """Parsea "HH:MM" de entry[key] a minutos desde medianoche; None si falla."""
    try:
        h, m = map(int, entry[key].split(":"))
    except (ValueError, KeyError, AttributeError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def _entry_active_at(entry: dict, current_minutes: int) -> bool:
    """Devuelve True si *entry* cubre *current_minutes* desde medianoche."""
    if not entry.get("enabled", False):
        return False
    start = _parse_minutes(entry, "start")
    end   = _parse_minutes(entry, "end")
    if start is None or end is None:
        return False
    if end <= start:
        # Intervalo nocturno (p. ej. 22:00 → 06:00): cubre ambos lados de medianoche.
        return current_minutes >= start or current_minutes < end
    return start <= current_minutes < end


def is_within_schedule() -> bool:
    """
    Comprobar si el auto-login de operador está permitido ahora mismo.
    Devuelve True → auto-login permitido (no se pide contraseña).
    Devuelve False → pedir contraseña normalmente.

    Dos vías de bypass:

    1. ``always_bypass = true`` en schedule.json → siempre True, sin importar
       el reloj ni el día. El admin configuró acceso sin contraseña permanente.

    2. Horario semanal → True solo si la hora actual cae en un intervalo activo.
       Requiere reloj plausible (año en [_CLOCK_MIN_YEAR, _CLOCK_MAX_YEAR]) para
       evitar bypass accidental en una Raspberry Pi sin NTP sincronizado.

    También comprueba el intervalo nocturno del día anterior, así una ventana
    lunes 22:00→06:00 sigue activa el martes a las 02:00.
    """
    schedule = load_schedule()

    # ── 1. Always bypass: acceso permanente sin contraseña ────────────────────
    if schedule.get('always_bypass', False):
        return True

    # ── 2. Horario semanal: requiere reloj plausible ──────────────────────────
    if not is_clock_plausible():
        return False

    now = datetime.now()
    weekday = now.weekday()  # 0=lunes … 6=domingo
    current_minutes = now.hour * 60 + now.minute

    # Comprobar la entrada de hoy.
    today_name = DAYS[weekday]
    if _entry_active_at(schedule.get(today_name, {}), current_minutes):
        return True

    # Comprobar el intervalo nocturno del día anterior: solo importa en la
    # parte de madrugada (current_minutes < fin de la ventana anterior).
    prev_weekday = (weekday - 1) % 7
    prev_name = DAYS[prev_weekday]
    prev_entry = schedule.get(prev_name, {})
    if prev_entry.get("enabled", False):
        start = _parse_minutes(prev_entry, "start")
        end   = _parse_minutes(prev_entry, "end")
        if start is not None and end is not None and end <= start:
            if current_minutes < end:
                return True

    return False
