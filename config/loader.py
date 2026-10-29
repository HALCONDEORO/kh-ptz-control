#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# config/loader.py — Cargador y validador de config.yaml
#
# load_config(path) → AppSettings
#   - Valida los campos obligatorios de cada cámara.
#   - Rechaza IDs de cámara duplicados.
#   - Informa con mensajes claros sobre cualquier campo faltante.
# Sin Qt. Sin I/O de red.

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

import yaml

from config.settings import (
    AppSettings,
    ATEMSettings,
    CameraSettings,
    FeaturesSettings,
    NetworkSettings,
    PiPNudgeSettings,
    RuntimeSettings,
    SiteSettings,
)


class ConfigError(ValueError):
    """Structured config.yaml validation error.

    Attributes
    ----------
    field_path:
        Dot-path of the offending field, e.g. ``cameras[0].ip``.
    severity:
        ``"error"`` (blocks startup), ``"warning"`` (degraded), or ``"info"``.
    remediation:
        Short installer-facing instruction for fixing the problem.
    """

    def __init__(
        self,
        message: str,
        *,
        field_path: str = "",
        severity: str = "error",
        remediation: str = "",
    ) -> None:
        super().__init__(message)
        self.field_path = field_path
        self.severity = severity
        self.remediation = remediation


def load_config(path: Path) -> AppSettings:
    """
    Carga y valida un archivo config.yaml.

    Raises
    ------
    ConfigError
        Si faltan campos obligatorios o hay IDs de cámara duplicados.
    FileNotFoundError
        Si el archivo no existe.
    yaml.YAMLError
        Si el YAML no es válido.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return build_settings(raw)


def build_settings(raw: Dict[str, Any]) -> AppSettings:
    """Validate an already-parsed config mapping into an AppSettings tree.

    Same validation as load_config, without file I/O — used by the provisioning
    engine to validate wizard answers in memory. Raises ConfigError on any
    invalid or missing required field.
    """
    if not isinstance(raw, dict):
        raise ConfigError(
            "config root must be a mapping",
            field_path="",
            remediation="The top level of config.yaml must be a YAML mapping",
        )

    site = _load_site(raw.get("site") or {})
    cameras = _load_cameras(raw.get("cameras") or [])
    atem = _load_atem(raw.get("atem") or {})
    runtime = _load_runtime(raw.get("runtime") or {})
    features = _load_features(raw.get("features") or {})
    network = _load_network(raw.get("network") or {})

    return AppSettings(
        site=site,
        cameras=cameras,
        atem=atem,
        runtime=runtime,
        features=features,
        network=network,
    )


# ── Secciones ────────────────────────────────────────────────────────────────

def _load_site(data: Dict[str, Any]) -> SiteSettings:
    return SiteSettings(
        name=str(data.get("name", "")),
        contact=str(data.get("contact", "")),
        installation_profile=str(data.get("installation_profile", "")),
        installation_id=str(data.get("installation_id", "")),
    )


_IPV4_RE = re.compile(
    r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
)
_VISCA_HEX_RE = re.compile(r"^[0-9A-Fa-f]{2}$")

# Etiquetas legibles por defecto para los roles conocidos. Se usan cuando
# config.yaml no trae el campo opcional `name`, de modo que las instalaciones
# antiguas (escritas antes de existir `name`) sigan cargando sin cambios.
_ROLE_DISPLAY_NAMES = {"platform": "Platform", "comments": "Comments"}


def _default_camera_name(role: str) -> str:
    """Nombre de cámara legible derivado de su rol.

    Para roles conocidos usa una etiqueta fija; para cualquier otro, convierte
    el rol en un texto presentable. Nunca devuelve cadena vacía.
    """
    key = role.strip().lower()
    if key in _ROLE_DISPLAY_NAMES:
        return _ROLE_DISPLAY_NAMES[key]
    return role.strip().replace("_", " ").title() or "Camera"


def _is_valid_ipv4(value: str) -> bool:
    m = _IPV4_RE.match(value)
    if not m:
        return False
    return all(0 <= int(g) <= 255 for g in m.groups())


def _is_valid_visca_id(value: str) -> bool:
    """VISCA camera address byte: one hex byte, e.g. '81', '82'."""
    return bool(_VISCA_HEX_RE.match(value))


def _load_cameras(items: Any) -> list[CameraSettings]:
    if not isinstance(items, list):
        raise ConfigError(
            "'cameras' debe ser una lista",
            field_path="cameras",
            remediation="cameras debe ser una lista YAML de entradas de cámara",
        )

    if not items:
        raise ConfigError(
            "'cameras' no puede estar vacío — se requiere al menos una cámara",
            field_path="cameras",
            remediation="Añade al menos una entrada de cámara bajo la sección cameras",
        )

    cameras = []
    seen_ids:   set[str] = set()
    seen_ips:   set[str] = set()
    seen_visca: set[str] = set()

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ConfigError(
                f"cameras[{idx}]: se esperaba un objeto, se obtuvo {type(item).__name__}",
                field_path=f"cameras[{idx}]",
                remediation="Cada entrada de cámara debe ser un objeto YAML con los campos id, role, ip y visca_id",
            )

        cam_id   = _require_str(item, "id",       f"cameras[{idx}]")
        role     = _require_str(item, "role",     f"cameras[{idx}]")
        ip       = _require_str(item, "ip",       f"cameras[{idx}]")
        visca_id = _require_str(item, "visca_id", f"cameras[{idx}]")

        if cam_id in seen_ids:
            raise ConfigError(
                f"ID de cámara duplicado: '{cam_id}'",
                field_path=f"cameras[{idx}].id",
                remediation="Cada cámara debe tener un id único; elige un identificador distinto",
            )
        seen_ids.add(cam_id)

        if not _is_valid_ipv4(ip):
            raise ConfigError(
                f"cameras[{idx}].ip: dirección IPv4 no válida: '{ip}'",
                field_path=f"cameras[{idx}].ip",
                remediation="Usa una dirección IPv4 válida, p.ej. 192.168.30.20",
            )
        if ip in seen_ips:
            raise ConfigError(
                f"cameras[{idx}].ip: dirección IP duplicada: '{ip}'",
                field_path=f"cameras[{idx}].ip",
                remediation="Cada cámara debe tener una dirección IP distinta",
            )
        seen_ips.add(ip)

        if not _is_valid_visca_id(visca_id):
            raise ConfigError(
                f"cameras[{idx}].visca_id: ID VISCA no válido: '{visca_id}' — "
                "se espera un byte hexadecimal, p.ej. '81'",
                field_path=f"cameras[{idx}].visca_id",
                remediation="visca_id debe ser un byte hexadecimal de dos dígitos, p.ej. '81' para la primera cámara, '82' para la segunda",
            )
        if visca_id in seen_visca:
            raise ConfigError(
                f"cameras[{idx}].visca_id: ID VISCA duplicado: '{visca_id}'",
                field_path=f"cameras[{idx}].visca_id",
                remediation="Cada cámara debe tener un visca_id distinto",
            )
        seen_visca.add(visca_id)

        # `name` es opcional: etiqueta editable y visible, separada del rol.
        # Si falta o está vacío, se deriva del rol (retro-compatible).
        name = str(item.get("name", "")).strip() or _default_camera_name(role)

        cameras.append(
            CameraSettings(id=cam_id, role=role, ip=ip, visca_id=visca_id, name=name)
        )

    return cameras


def _load_atem(data: Dict[str, Any]) -> ATEMSettings:
    installed = _parse_bool(data.get("installed", False), "atem.installed")
    enabled = _parse_bool(data.get("enabled", False), "atem.enabled")

    if enabled and not installed:
        raise ConfigError(
            "atem.enabled=true requires atem.installed=true",
            field_path="atem.enabled",
            severity="error",
            remediation="Set atem.installed=true or set atem.enabled=false",
        )

    raw_labels = data.get("input_labels", {})
    if not isinstance(raw_labels, dict):
        raise ConfigError(
            "atem.input_labels must be a mapping of input_id to label string",
            field_path="atem.input_labels",
            remediation="Use a YAML mapping: input_labels: {1: Platform, 2: Comments}",
        )
    input_labels = {str(k): str(v) for k, v in raw_labels.items()}

    try:
        me_index = int(data.get("me_index", 0))
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"atem.me_index: debe ser un entero, se obtuvo {data.get('me_index')!r}",
            field_path="atem.me_index",
        ) from exc
    try:
        connect_timeout_secs = int(data.get("connect_timeout_secs", 10))
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"atem.connect_timeout_secs: debe ser un entero, se obtuvo {data.get('connect_timeout_secs')!r}",
            field_path="atem.connect_timeout_secs",
        ) from exc
    try:
        reconnect_timeout_secs = int(data.get("reconnect_timeout_secs", 30))
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"atem.reconnect_timeout_secs: debe ser un entero, se obtuvo {data.get('reconnect_timeout_secs')!r}",
            field_path="atem.reconnect_timeout_secs",
        ) from exc

    return ATEMSettings(
        ip=str(data.get("ip", "")),
        installed=installed,
        enabled=enabled,
        disabled_reason=str(data.get("disabled_reason", "")),
        me_index=me_index,
        input_labels=input_labels,
        connect_timeout_secs=connect_timeout_secs,
        reconnect_timeout_secs=reconnect_timeout_secs,
        automation_disabled=_parse_bool(data.get("automation_disabled", True), "atem.automation_disabled"),
        pip_nudge=_load_pip_nudge(data.get("pip_nudge") or {}),
    )


def _load_pip_nudge(raw: Any) -> PiPNudgeSettings:
    """Parse the atem.pip_nudge subsection — all fields optional, safe defaults."""
    if not isinstance(raw, dict):
        if raw is not None:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "atem.pip_nudge: se esperaba un dict, se obtuvo %s — usando valores por defecto",
                type(raw).__name__,
            )
        return PiPNudgeSettings()

    direction = str(raw.get("direction", "right")).strip().lower()
    if direction not in ("right", "left"):
        raise ConfigError(
            f"atem.pip_nudge.direction: debe ser 'right' o 'left', se obtuvo {direction!r}",
            field_path="atem.pip_nudge.direction",
            remediation="Usa 'right' o 'left'",
        )

    try:
        pan_speed = int(raw.get("pan_speed", 0))
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"atem.pip_nudge.pan_speed: debe ser un entero, se obtuvo {raw.get('pan_speed')!r}",
            field_path="atem.pip_nudge.pan_speed",
            remediation="Usa un número entero entre 0 y 24",
        ) from exc
    if not 0 <= pan_speed <= 24:
        raise ConfigError(
            f"atem.pip_nudge.pan_speed: debe estar entre 0 y 24, se obtuvo {pan_speed}",
            field_path="atem.pip_nudge.pan_speed",
            remediation="Usa 0 para desactivar o un valor entre 1 (lento) y 24 (rápido)",
        )

    try:
        duration_ms = int(raw.get("duration_ms", 0))
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"atem.pip_nudge.duration_ms: debe ser un entero, se obtuvo {raw.get('duration_ms')!r}",
            field_path="atem.pip_nudge.duration_ms",
            remediation="Usa un número entero en milisegundos entre 0 y 5000",
        ) from exc
    if not 0 <= duration_ms <= 5000:
        raise ConfigError(
            f"atem.pip_nudge.duration_ms: debe estar entre 0 y 5000, se obtuvo {duration_ms}",
            field_path="atem.pip_nudge.duration_ms",
            remediation="Usa 0 para desactivar o un valor en milisegundos entre 1 y 5000",
        )

    return PiPNudgeSettings(
        camera_role=str(raw.get("camera_role", "platform")).strip(),
        pan_speed=pan_speed,
        direction=direction,
        duration_ms=duration_ms,
    )


def _load_runtime(data: Dict[str, Any]) -> RuntimeSettings:
    return RuntimeSettings(
        data_dir=str(data.get("data_dir", "")),
        connectivity_mode=str(data.get("connectivity_mode", "offline")),
        mode=str(data.get("mode", "production")),
    )


def _load_network(data: Dict[str, Any]) -> NetworkSettings:
    """Load network profile section — all fields optional, safe defaults for existing installs."""
    return NetworkSettings(
        profile=str(data.get("profile", "unknown")).strip().lower(),
        av_subnet=str(data.get("av_subnet", "")).strip(),
        av_vlan_id=str(data.get("av_vlan_id", "")).strip(),
        guest_access_allowed=_optional_bool(data.get("guest_access_allowed"), "network.guest_access_allowed"),
        internet_required=_parse_bool(data.get("internet_required", False), "network.internet_required"),
        static_ips=_optional_bool(data.get("static_ips"), "network.static_ips"),
        notes=str(data.get("notes", "")),
    )


def _load_features(data: Dict[str, Any]) -> FeaturesSettings:
    return FeaturesSettings(
        atem_enabled=_parse_bool(data.get("atem_enabled", False), "features.atem_enabled"),
        simulation=_parse_bool(data.get("simulation", False), "features.simulation"),
        allow_real_hardware_in_demo=_parse_bool(
            data.get("allow_real_hardware_in_demo", False),
            "features.allow_real_hardware_in_demo",
        ),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

_TRUE_STRINGS  = frozenset({"true", "yes", "1"})
_FALSE_STRINGS = frozenset({"false", "no", "0"})


def _parse_bool(value: Any, context: str) -> bool:
    """Parse a config boolean value strictly.

    Accepts Python bool, or strings 'true'/'false'/'yes'/'no'/'1'/'0' (case-insensitive).
    Raises ConfigError for anything else so that quoted 'false' never becomes True.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in _TRUE_STRINGS:
            return True
        if lower in _FALSE_STRINGS:
            return False
    raise ConfigError(
        f"{context}: valor booleano no válido {value!r} — "
        "usa true/false, yes/no o 1/0",
        field_path=context,
        remediation="Usa true o false (sin comillas) para este campo booleano",
    )


def _optional_bool(value: Any, context: str) -> bool | None:
    """Like _parse_bool but returns None when value is None."""
    if value is None:
        return None
    return _parse_bool(value, context)


def _require_str(data: Dict[str, Any], key: str, context: str) -> str:
    if key not in data:
        raise ConfigError(
            f"{context}: falta el campo obligatorio '{key}'",
            field_path=f"{context}.{key}",
            remediation=f"Añade el campo '{key}' a {context}",
        )
    value = data[key]
    if value is None or str(value).strip() == "":
        raise ConfigError(
            f"{context}.{key}: no puede estar vacío",
            field_path=f"{context}.{key}",
            remediation=f"El campo '{key}' no puede estar vacío en {context}",
        )
    return str(value).strip()
