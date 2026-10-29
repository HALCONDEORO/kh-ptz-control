# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Presupuesto anti-crecimiento para los god-objects de la UI (ratchet).

La revisión de arquitectura identificó tres ficheros de UI grandes cuyo tamaño
concentra el riesgo de "tocar A y romper B" al añadir funciones nuevas:

    ui/config_dialog.py   (1 clase pública, ~120 métodos)
    ui/main_window.py
    ui/splash_screen.py

Este test NO importa PyQt: mide el fichero con `ast` y líneas físicas, así que
corre sin cámaras, hardware ni display. Es un *ratchet*: los presupuestos están
fijados en el tamaño actual, de modo que estos ficheros **no pueden crecer**.
Cuando se troceen (p. ej. dividir ConfigDialog en páginas por área), BAJA el
presupuesto correspondiente al nuevo tamaño. Nunca lo subas para "hacer sitio"
a más código: subirlo derrota el propósito de este test.

Ver la revisión de arquitectura y docs/ARCHITECTURE.md.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# fichero -> (máximo de líneas físicas, máximo de funciones/métodos).
# Fijados en el tamaño actual (2026-07-24). Solo se permiten valores MENORES.
BUDGETS: dict[str, tuple[int, int]] = {
    # config_dialog.py: 3102 -> 3058 when camera/ATEM writes moved to
    # CameraConfigService (#893), then 3058 -> 2273 when five section/strip
    # builders moved to ui/config_pages/sections.py (#894, phase 0). The ratchet
    # moves down as the god-object is decomposed — never up.
    "ui/config_dialog.py": (1159, 31),
    # main_window.py grew by 12 lines to own the CameraConfigService seam (#893);
    # baseline raised once for that reviewed wiring, not for feature bloat;
    # 1828 -> 1816 when the ATEM button-state policy moved to
    # ui/atem_button_state.py (#921); then down again when the thread-supervisor
    # wiring moved to core/supervisor_wiring.py and the amber-LED wiring to
    # ui/camera_led_wiring.py (VISCA robustness review). The ratchet moves
    # down, never up.
    "ui/main_window.py": (1792, 90),
    "ui/splash_screen.py": (1332, 53),
}


def _measure(relative_path: str) -> tuple[int, int]:
    """Devuelve (líneas físicas, nº de funciones/métodos) de un fichero fuente."""
    source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=relative_path)
    methods = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    )
    return len(source.splitlines()), methods


@pytest.mark.parametrize("relative_path", sorted(BUDGETS))
def test_ui_file_does_not_grow_beyond_budget(relative_path: str) -> None:
    max_loc, max_methods = BUDGETS[relative_path]
    loc, methods = _measure(relative_path)

    assert loc <= max_loc, (
        f"{relative_path} creció a {loc} líneas (presupuesto {max_loc}). "
        f"Este fichero es un god-object bajo vigilancia: no añadas más código; "
        f"trocéalo. Si de verdad lo redujiste, baja el presupuesto en BUDGETS."
    )
    assert methods <= max_methods, (
        f"{relative_path} tiene {methods} métodos (presupuesto {max_methods}). "
        f"No añadas más métodos a este god-object; extrae la responsabilidad a "
        f"un módulo/clase nuevo. Si lo redujiste, baja el presupuesto en BUDGETS."
    )


def test_budget_list_matches_the_files_on_disk() -> None:
    """Evita que un rename deje una entrada del presupuesto apuntando al vacío."""
    for relative_path in BUDGETS:
        assert (PROJECT_ROOT / relative_path).is_file(), (
            f"{relative_path} está en BUDGETS pero no existe. Actualiza el "
            f"presupuesto tras mover/renombrar el fichero."
        )
