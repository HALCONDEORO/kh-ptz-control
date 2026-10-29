#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# atem_dispatcher.py — Capa de despacho entre ATEMMonitor y acciones de cámara
#
# El monitor ATEM emite eventos limpios (program_changed, state_changed).
# Este dispatcher decide si esos eventos producen acciones de cámara,
# aplicando todas las capas de seguridad antes de emitir action_triggered.
#
# CAPAS DE SEGURIDAD (en orden de evaluación):
#   1. armed      — si False, solo monitoriza (no emite acciones)
#   2. session    — si sesión inactiva, ignora
#   3. cooldown   — N segundos de espera tras control manual
#   4. reconnect  — pausa hasta confirmación explícita tras reconexión
#   5. log_only   — registra la acción pero no la emite (modo ensayo)
#
# MAPEO DE ENTRADAS:
#   Cargado desde atem_mapping.json; formato {"<from>-><to>": "<action>"}.
#   También acepta {"<input_id>": "<action>"} para actuar al entrar en un input.
#   Claves PiP reservadas: "pip:on" y "pip:off" para reaccionar al estado PiP.
#   Acciones reconocidas: "none", "comments_home", "platform_home",
#                         "pip_on", "pip_off".
#   Transiciones/entradas sin mapeo → "none".

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from core.atomic_write import write_bytes_atomic, write_text_atomic
from domain.atem_state import ATEMPiPState, ATEMState

if TYPE_CHECKING:
    from domain.atem_state import AtemAutomationState

logger = logging.getLogger(__name__)

_MAPPING_FILENAME = "atem_mapping.json"


def _mapping_file() -> Path:
    """Where the ATEM action mapping lives: data_dir, not config_dir.

    This file is rewritten at RUNTIME, by the operator, from the running app —
    `set_pip_automation_enabled` and `update_mapping` both save it. It used to
    resolve to /etc/hallptz/atem_mapping.json, which on a product install is
    root:hallptz 2751: the service runs as User=hallptz and has no write permission
    there, so every save failed with EACCES and was swallowed as a warning.
    The operator toggled PiP automation, saw no error, and lost the change on
    the next restart.

    docs/RUNTIME_PATH_CONTRACT.md already says which directory this belongs to:
    config_dir is admin-write only, data_dir is where the service persists
    customer/runtime data. Moving it also puts it inside `hallptz backup`, which
    only ever collects config.yaml out of config_dir.
    """
    try:
        from runtime.path_resolver import RuntimePathResolver
        return RuntimePathResolver().data_dir / _MAPPING_FILENAME
    except Exception:
        return Path(_MAPPING_FILENAME)  # fallback for tests / offline runs


def _legacy_mapping_file() -> Optional[Path]:
    """Pre-move location under config_dir — a read-migrate source only.

    Never written and never deleted: an install that predates the move keeps
    its mapping readable by hand, and a rollback to an older release still
    finds the file it expects.
    """
    try:
        from runtime.path_resolver import RuntimePathResolver
        return RuntimePathResolver().config_dir / _MAPPING_FILENAME
    except Exception:
        return None


def _migrate_legacy_mapping() -> None:
    """Copy a pre-move mapping into data_dir, once, best-effort.

    Done on read rather than left to the next save, because a site that never
    touches the ATEM settings again would otherwise keep its mapping in a
    directory `hallptz backup` does not collect — the file would survive until the
    first restore quietly dropped it.
    """
    legacy = _legacy_mapping_file()
    target = _mapping_file()
    if legacy is None or legacy == target:
        return
    try:
        if target.exists() or not legacy.is_file():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        # Copied as BYTES, deliberately. Decoding here would raise
        # UnicodeDecodeError - which is a ValueError, not an OSError - on a
        # mapping written under a non-UTF-8 locale, and it would escape both
        # this function and _load_mapping, whose own reader explicitly handles
        # that case and falls back to the defaults. A migration that cannot
        # start the application is worse than the file it was migrating.
        # Copying the bytes verbatim also preserves the original exactly, so
        # the tolerant loader below makes the same decision it would have made
        # about the legacy file.
        write_bytes_atomic(target, legacy.read_bytes())
        logger.info("[ATEM] mapping migrado de %s a %s", legacy, target)
    except (OSError, ValueError) as exc:
        # A failed migration is not fatal: _load_mapping falls back to reading
        # the legacy file in place on this and every later run.
        logger.warning("[ATEM] no se pudo migrar el mapping desde %s: %s", legacy, exc)

from domain.atem_constants import ATEM_DEFAULT_MAPPING as _DEFAULT_MAPPING
_MANUAL_COOLDOWN_SECS = 30
_PIP_AUTOMATION_KEY = "pip_automation_enabled"  # meta-key in atem_mapping.json

KNOWN_ACTIONS = frozenset({"none", "comments_home", "platform_home", "pip_on", "pip_off"})

# Claves de mapeo reservadas para eventos PiP
_PIP_KEY_ON  = "pip:on"
_PIP_KEY_OFF = "pip:off"
_PIP_KEYS    = frozenset({_PIP_KEY_ON, _PIP_KEY_OFF})


def _is_valid_mapping_key(key: str) -> bool:
    if key in _PIP_KEYS:
        return True
    if key.isdigit():
        return True
    parts = key.split("->")
    return len(parts) == 2 and all(part.isdigit() for part in parts)


def _load_mapping() -> tuple[dict[str, str], bool]:
    """Load action mapping and pip_automation_enabled from atem_mapping.json.

    Returns (mapping_dict, pip_automation_enabled).
    pip_automation_enabled defaults to True when the key is absent.
    """
    _migrate_legacy_mapping()
    path = _mapping_file()
    if not path.exists():
        # Migration could not write data_dir (read-only mount, wrong owner):
        # read the pre-move file where it stands rather than silently reverting
        # this install to the default mapping.
        legacy = _legacy_mapping_file()
        if legacy is not None and legacy != path and legacy.is_file():
            path = legacy
    try:
        if not path.exists():
            return dict(_DEFAULT_MAPPING), True
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        logger.warning("[ATEM] mapping: no se pudo cargar %s: %s — usando defaults", path, exc)
        return dict(_DEFAULT_MAPPING), True

    if not isinstance(raw, dict):
        logger.warning("[ATEM] mapping: expected JSON object — using defaults")
        return dict(_DEFAULT_MAPPING), True

    pip_enabled = bool(raw.get(_PIP_AUTOMATION_KEY, True))

    result: dict[str, str] = {}
    for k, v in raw.items():
        if k == _PIP_AUTOMATION_KEY:
            continue  # meta-key — not an action mapping
        key = str(k)
        if not _is_valid_mapping_key(key):
            logger.warning(
                "[ATEM] mapping: clave inválida %r (debe ser dígito o transición A->B) — omitida",
                k,
            )
            continue
        if v not in KNOWN_ACTIONS:
            logger.warning("[ATEM] mapping: acción desconocida %r para input %s — usando 'none'", v, k)
            v = "none"
        result[key] = v
    return result, pip_enabled


def _save_mapping(mapping: dict[str, str], pip_automation_enabled: bool = True) -> None:
    """Persist action mapping and pip_automation_enabled to atem_mapping.json.

    Written through core.atomic_write so the file picks up the runtime
    directory's own access policy: 0600 when only the service uses it, 0660
    when the directory is group-shared with a session-owned GUI (#885). The
    previous hand-rolled tmp+replace always left it at the caller's umask, so
    under --gui-mode user the GUI and the service could each write a mapping
    the other could not read back.
    """
    path = _mapping_file()
    data: dict = {}
    if not pip_automation_enabled:
        # Only write the key when disabled (True is default; omitting saves space)
        data[_PIP_AUTOMATION_KEY] = False
    data.update(mapping)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=2))
    except OSError as exc:
        logger.warning("[ATEM] no se pudo guardar mapping en %s: %s", path, exc)


class ATEMDispatcher:
    """
    Recibe eventos de programa del ATEMMonitor y decide si disparar acciones de cámara.

    Nunca mueve cámaras directamente; llama on_action(str) para que
    la capa superior (MainWindow) ejecute la acción correspondiente.
    """

    def __init__(
        self,
        session_provider: Callable[[], bool],
        on_action: Callable[[str], None] | None = None,
    ):
        """
        session_provider — callable sin argumentos que devuelve bool:
                           True si hay una sesión activa.
        on_action — callback invocado cuando una acción supera todas las capas de seguridad.
        """
        self._session_provider = session_provider
        self._on_action = on_action
        self._mapping, self._pip_automation_enabled = _load_mapping()
        self._armed = False
        self._log_only = False
        self._manual_cooldown_until = 0.0
        self._reconnect_guard = False
        self._atem_connected = False   # updated by on_atem_state_changed
        self._last_input: int | None = None
        self._last_pip_enabled: bool | None = None  # None = estado aún desconocido

    # ── Propiedades de estado ─────────────────────────────────────────────────

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def log_only(self) -> bool:
        return self._log_only

    @property
    def reconnect_guard(self) -> bool:
        return self._reconnect_guard

    @property
    def mapping(self) -> dict[str, str]:
        return dict(self._mapping)

    @property
    def pip_automation_enabled(self) -> bool:
        """True cuando la automatización PiP está activa (responde a pip:on / pip:off)."""
        return self._pip_automation_enabled

    # ── API pública ───────────────────────────────────────────────────────────

    def set_armed(self, armed: bool) -> None:
        if self._armed == armed:
            return
        self._armed = armed
        logger.info("[ATEM] Automatización %s", "ARMADA" if armed else "DESARMADA")

    def set_log_only(self, log_only: bool) -> None:
        self._log_only = log_only
        logger.info("[ATEM] Modo solo-registro %s", "ACTIVADO" if log_only else "DESACTIVADO")

    def set_pip_automation_enabled(self, enabled: bool) -> None:
        """Activa o desactiva la respuesta automática a cambios de PiP.

        El monitor sigue detectando PiP; solo se suprime la ejecución de acciones.
        El estado se persiste en atem_mapping.json.
        """
        if self._pip_automation_enabled == enabled:
            return
        self._pip_automation_enabled = enabled
        if enabled:
            # Reset dedup state so the first real PiP event after re-enabling
            # always fires, even if the physical PiP state hasn't changed.
            self._last_pip_enabled = None
        _save_mapping(self._mapping, pip_automation_enabled=enabled)
        logger.info("[ATEM] PiP automation %s", "ACTIVADA" if enabled else "DESACTIVADA")

    def update_mapping(self, mapping: dict[str, str]) -> None:
        """Actualiza el mapeo en memoria y lo persiste a disco."""
        self._mapping = dict(mapping)
        _save_mapping(self._mapping, pip_automation_enabled=self._pip_automation_enabled)
        logger.info("[ATEM] Mapeo actualizado: %s", self._mapping)

    def notify_manual_control(self) -> None:
        """Registra un control manual; suprime ATEM durante _MANUAL_COOLDOWN_SECS."""
        self._manual_cooldown_until = time.monotonic() + _MANUAL_COOLDOWN_SECS

    def on_atem_state_changed(self, state: ATEMState) -> None:
        """Rastrea estado de conexión y activa reconnect guard al reconectar."""
        was_connected = self._atem_connected
        self._atem_connected = (state == ATEMState.CONNECTED)
        if self._atem_connected and not was_connected and self._last_input is not None:
            self._reconnect_guard = True
            logger.info("[ATEM] Reconnect guard activado — confirmar para reanudar automatización")

    def mark_reconnecting(self) -> None:
        """Activa el guard al reiniciar el monitor si la automatización está armada."""
        if self._armed:
            self._reconnect_guard = True
            logger.info("[ATEM] Reconnect guard activado por reinicio del monitor")

    def clear_reconnect_guard(self) -> None:
        self._reconnect_guard = False
        logger.info("[ATEM] Reconnect guard desactivado")

    def get_blocked_reason(self) -> str:
        """Return the human-readable reason automation is blocked, or '' if unblocked."""
        return self._blocked_reason()

    def reset_input_tracking(self) -> None:
        """Limpia el input previo y el estado PiP conocido.

        Llamar tras reconexión para que el próximo evento de programa y el
        próximo cambio de PiP sean tratados como transiciones frescas,
        evitando que la deduplicación descarte el primer evento post-reconexión.
        """
        self._last_input = None
        self._last_pip_enabled = None

    # ── Receptor de eventos del monitor ──────────────────────────────────────

    def on_pip_changed(self, pip_state: ATEMPiPState) -> None:
        """Recibe el nuevo estado PiP y dispara la acción mapeada si procede.

        La clave de mapeo "pip:on" se usa cuando PiP se activa,
        "pip:off" cuando se desactiva. Las mismas capas de seguridad
        (armed, session, cooldown, reconnect, log_only) se aplican aquí.
        Si pip_automation_enabled es False, solo rastrea el estado sin disparar.
        """
        enabled = pip_state.enabled
        if enabled == self._last_pip_enabled:
            return  # deduplicación
        self._last_pip_enabled = enabled

        if not self._pip_automation_enabled:
            logger.debug("[ATEM] PiP %s → ignorado (pip_automation desactivada)", "ON" if enabled else "OFF")
            return

        key = _PIP_KEY_ON if enabled else _PIP_KEY_OFF
        action = self._mapping.get(key, "none")
        self._dispatch_action(action, f"PiP {'ON' if enabled else 'OFF'}")

    def on_program_changed(self, input_id: int) -> None:
        """Recibe el input de programa actual y decide la acción."""
        if input_id == self._last_input:
            return  # deduplicación: mismo input repetido → ignorar
        prev_input = self._last_input
        self._last_input = input_id
        action = self._action_for(prev_input, input_id)
        self._dispatch_action(action, f"Input {input_id}")

    # ── Dry-run ───────────────────────────────────────────────────────────────

    def get_automation_state(self) -> "AtemAutomationState":
        """Devuelve un snapshot del estado de automatización para UI/diagnósticos."""
        from domain.atem_state import AtemAutomationState
        return AtemAutomationState(
            armed=self._armed,
            log_only=self._log_only,
            reconnect_guard=self._reconnect_guard,
            manual_cooldown_active=time.monotonic() < self._manual_cooldown_until,
            blocked_reason=self._blocked_reason(),
            last_input=self._last_input,
            pip_automation_enabled=self._pip_automation_enabled,
            last_pip_enabled=self._last_pip_enabled,
        )

    def dry_run(self, input_id: int) -> str:
        """Simula qué pasaría con input_id sin mover cámaras."""
        if input_id == self._last_input:
            return f"Input {input_id}: same as current program input — no transition event"
        action = self._action_for(self._last_input, input_id)
        if action == "none":
            return f"Input {input_id}: no action (not mapped)"
        reason = self._blocked_reason()
        if reason:
            return f"Would trigger: {action} | Blocked because: {reason}"
        if self._log_only:
            return f"Would trigger: {action} | Mode: log-only (not executed)"
        return f"Would trigger: {action}"

    # ── Dry-run PiP ───────────────────────────────────────────────────────────

    def dry_run_pip(self, enabled: bool) -> str:
        """Simula qué pasaría al recibir un evento PiP sin ejecutar acciones.

        Replica fielmente la lógica de on_pip_changed(), incluyendo
        deduplicación y el check de pip_automation_enabled, para que el
        resultado sea siempre consistente con lo que haría el evento real.
        """
        label = "PiP ON" if enabled else "PiP OFF"

        # Deduplication — same check as on_pip_changed line 236
        if enabled == self._last_pip_enabled:
            return f"{label}: no change (state already {'ON' if enabled else 'OFF'})"

        if not self._pip_automation_enabled:
            return f"{label}: no action (pip automation disabled)"

        key = _PIP_KEY_ON if enabled else _PIP_KEY_OFF
        action = self._mapping.get(key, "none")
        if action == "none":
            return f"{label}: no action (not mapped)"
        reason = self._blocked_reason()
        if reason:
            return f"Would trigger: {action} | Blocked because: {reason}"
        if self._log_only:
            return f"Would trigger: {action} | Mode: log-only (not executed)"
        return f"Would trigger: {action}"

    # ── Internos ──────────────────────────────────────────────────────────────

    def _dispatch_action(self, action: str, log_prefix: str) -> None:
        """Aplica todas las capas de seguridad y emite action_triggered si pasa."""
        if action == "none":
            logger.debug("[ATEM] %s → sin acción mapeada", log_prefix)
            return
        reason = self._blocked_reason()
        if reason:
            logger.info("[ATEM] %s → %s | Bloqueado: %s", log_prefix, action, reason)
            return
        if self._log_only:
            logger.info("[ATEM] %s → %s (solo-registro — no ejecutado)", log_prefix, action)
            return
        logger.info("[ATEM] %s → %s", log_prefix, action)
        if self._on_action is not None:
            self._on_action(action)

    def _action_for(self, prev_input: int | None, input_id: int) -> str:
        if prev_input is not None:
            transition_key = f"{prev_input}->{input_id}"
            if transition_key in self._mapping:
                return self._mapping[transition_key]
        return self._mapping.get(str(input_id), "none")

    def _blocked_reason(self) -> str:
        if not self._armed:
            return "automation disarmed"
        if not self._atem_connected:
            return "ATEM not connected"
        if not self._session_provider():
            return "session inactive"
        if time.monotonic() < self._manual_cooldown_until:
            return "manual override cooldown"
        if self._reconnect_guard:
            return "reconnect guard active"
        return ""
