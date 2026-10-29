#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/access_mode_service.py — Servicio de rol de acceso persistido (#718 #719)
#
# Gestiona el rol de acceso actual del producto.
# El rol se persiste en ACCESS_MODE_FILE entre reinicios de la aplicación.
#
# Rol por defecto: CAMERA_OPERATOR (operador de sala — #718 #719).
#
# Precedencia al determinar el rol inicial:
#   1. Variable de entorno KHPTZ_ACCESS_ROLE (o KHPTZ_ACCESS_MODE como alias legacy).
#   2. Archivo persistido ACCESS_MODE_FILE (si existe y contiene un valor válido).
#   3. Defecto del producto: CAMERA_OPERATOR.
#
# Migración de valores antiguos persistidos:
#   "operator"        → BASIC_OPERATOR
#   "admin_installer" → TECHNICIAN

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable

from domain.call_set_policy import OperatingMode

logger = logging.getLogger(__name__)

_DEFAULT: OperatingMode = OperatingMode.CAMERA_OPERATOR

# Roles que pueden guardarse en disco y seleccionarse en la UI de configuración.
_VALID_PERSISTENT_MODES: frozenset[OperatingMode] = frozenset({
    OperatingMode.BASIC_OPERATOR,
    OperatingMode.CAMERA_OPERATOR,
    OperatingMode.TECHNICIAN,
    OperatingMode.SYSTEM_ADMIN,
})

# Mapa de migración: valor antiguo → nuevo rol canónico.
_LEGACY_MAP: dict[str, OperatingMode] = {
    "operator":        OperatingMode.BASIC_OPERATOR,
    "admin_installer": OperatingMode.TECHNICIAN,
}


def _resolve_env_override() -> OperatingMode | None:
    """Lee KHPTZ_ACCESS_ROLE (o el alias legacy KHPTZ_ACCESS_MODE) del entorno."""
    raw = os.environ.get("KHPTZ_ACCESS_ROLE") or os.environ.get("KHPTZ_ACCESS_MODE")
    if not raw:
        return None
    # Intenta migración de valores legacy primero.
    if raw in _LEGACY_MAP:
        resolved = _LEGACY_MAP[raw]
        logger.info("access_mode: variable de entorno legacy %r → %s", raw, resolved.value)
        return resolved
    try:
        mode = OperatingMode(raw)
        if mode in _VALID_PERSISTENT_MODES:
            return mode
        logger.warning("access_mode: variable de entorno %r no es un rol válido — ignorada", raw)
    except ValueError:
        logger.warning("access_mode: variable de entorno %r desconocida — ignorada", raw)
    return None


class AccessModeService:
    """
    Servicio de rol de acceso: carga, persiste y cambia el rol activo.

    Precedencia: override de entorno > archivo persistido > CAMERA_OPERATOR.
    Falla de forma segura (vuelve al defecto) si el archivo es inválido o corrupto.
    """

    def __init__(self, path: Path | None = None):
        if path is None:
            from runtime.path_resolver import RuntimePathResolver
            path = RuntimePathResolver().access_mode_file
        self._path = path
        self._mode: OperatingMode = _DEFAULT
        self._observers: list[Callable[[OperatingMode], None]] = []
        self._load()

    # ── API pública ───────────────────────────────────────────────────────────

    @property
    def mode(self) -> OperatingMode:
        return self._mode

    def subscribe(self, cb: Callable[[OperatingMode], None]) -> None:
        """Registra un callback invocado con el nuevo OperatingMode tras cada set_mode()."""
        if cb not in self._observers:
            self._observers.append(cb)

    def unsubscribe(self, cb: Callable[[OperatingMode], None]) -> None:
        self._observers = [o for o in self._observers if o != cb]

    def set_mode(self, mode: OperatingMode) -> None:
        if mode not in _VALID_PERSISTENT_MODES:
            raise ValueError(f"AccessModeService: rol no válido para persistir: {mode!r}")
        self._mode = mode
        self._save()
        logger.info("access_mode cambiado a %s", mode.value)
        for cb in list(self._observers):
            try:
                cb(mode)
            except Exception:
                logger.exception("access_mode: error en observer %r", cb)

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        # 1. Override de entorno tiene máxima prioridad.
        env_mode = _resolve_env_override()
        if env_mode is not None:
            self._mode = env_mode
            logger.info("access_mode: override de entorno → %s", env_mode.value)
            return

        # 2. Leer archivo persistido.
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8-sig"))
            value = raw.get("access_mode", "")

            # Migrar valores legacy.
            if value in _LEGACY_MAP:
                self._mode = _LEGACY_MAP[value]
                logger.info("access_mode: migrado %r → %s", value, self._mode.value)
                return

            candidate = OperatingMode(value)
            if candidate not in _VALID_PERSISTENT_MODES:
                raise ValueError(f"valor no es rol persistente válido: {value!r}")
            self._mode = candidate
            logger.debug("access_mode cargado: %s", self._mode.value)

        except FileNotFoundError:
            self._mode = _DEFAULT
        except Exception as exc:
            logger.warning("access_mode: no se pudo leer %s (%s) — usando defecto %s",
                           self._path, exc, _DEFAULT.value)
            self._mode = _DEFAULT

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"access_mode": self._mode.value}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.exception("access_mode: no se pudo guardar en %s: %s", self._path, exc)
