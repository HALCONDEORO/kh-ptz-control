#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/installation_id.py — Reglas para el ID único de instalación
#
# Sin I/O. Solo generación y validación.
# Formato: khptz-YYYY-NNNN  (p.ej. khptz-2026-0042)
#   - Seguro para nombres de archivo, logs y archivos de backup.
#   - No depende de internet.

from __future__ import annotations

import random
import re

_ID_PATTERN = re.compile(r"^khptz-\d{4}-\d{4}$")

# Rango de sufijo numérico (0001–9999, evita el 0000 no significativo)
_SUFFIX_MIN = 1
_SUFFIX_MAX = 9999


def generate_installation_id(year: int) -> str:
    """
    Genera un ID de instalación en formato ``khptz-YYYY-NNNN``.

    El sufijo es un número aleatorio entre 0001 y 9999.
    Llamar a esta función dos veces en el mismo año puede producir el mismo ID;
    la unicidad real se garantiza al asignarlo manualmente o durante el setup.
    """
    suffix = random.randint(_SUFFIX_MIN, _SUFFIX_MAX)
    return f"khptz-{year:04d}-{suffix:04d}"


def is_valid_installation_id(value: str) -> bool:
    """Devuelve True si *value* tiene el formato khptz-YYYY-NNNN."""
    return bool(_ID_PATTERN.match(value))
