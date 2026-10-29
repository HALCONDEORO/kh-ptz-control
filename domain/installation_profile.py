#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/installation_profile.py — Perfiles de instalación y reglas de validación
#
# Sin I/O. Solo constantes y lógica pura de dominio.

from __future__ import annotations

from enum import Enum
from typing import Optional


class InstallationProfile(str, Enum):
    """Tipos de instalación soportados."""
    STARTER_1_CAMERA            = "starter_1_camera"
    STANDARD_2_CAMERA           = "standard_2_camera"
    DEMO                        = "demo"
    # Reservados para versiones futuras — aceptados pero sin validación de cámaras
    PROFESSIONAL_MULTI_CAMERA   = "professional_multi_camera"
    CUSTOM                      = "custom"


# Perfiles activamente soportados (con validación completa)
ACTIVE_PROFILES = {
    InstallationProfile.STARTER_1_CAMERA,
    InstallationProfile.STANDARD_2_CAMERA,
    InstallationProfile.DEMO,
}

# Número exacto de cámaras esperado por perfil (None = sin restricción)
_EXPECTED_CAMERA_COUNT: dict[InstallationProfile, Optional[int]] = {
    InstallationProfile.STARTER_1_CAMERA:           1,
    InstallationProfile.STANDARD_2_CAMERA:          2,
    InstallationProfile.DEMO:                       None,
    InstallationProfile.PROFESSIONAL_MULTI_CAMERA:  None,
    InstallationProfile.CUSTOM:                     None,
}

KNOWN_PROFILE_VALUES = {p.value for p in InstallationProfile}


def parse_profile(value: str) -> Optional[InstallationProfile]:
    """Return the InstallationProfile for *value*, or None if unrecognised."""
    try:
        return InstallationProfile(value)
    except ValueError:
        return None


def expected_camera_count(profile: InstallationProfile) -> Optional[int]:
    """Return the required camera count for *profile*, or None if unrestricted."""
    return _EXPECTED_CAMERA_COUNT.get(profile)


# Perfiles cuya identidad la define el número de cámaras. El resto (demo,
# professional, custom) son elecciones explícitas del operador y se respetan.
_COUNT_DERIVED_PROFILES: dict[int, InstallationProfile] = {
    1: InstallationProfile.STARTER_1_CAMERA,
    2: InstallationProfile.STANDARD_2_CAMERA,
}

EXPLICIT_PROFILES = {
    InstallationProfile.DEMO,
    InstallationProfile.PROFESSIONAL_MULTI_CAMERA,
    InstallationProfile.CUSTOM,
}


def derive_installation_profile(
    camera_count: int,
    current: Optional[str] = None,
) -> InstallationProfile:
    """Devuelve el perfil que corresponde a *camera_count*.

    El instalador siembra config.yaml con `starter_1_camera` antes de que el
    asistente se ejecute. Si el operador configura dos cámaras y el perfil
    sembrado se conserva, `khptz doctor` avisa de una contradicción que el
    usuario no puede resolver desde el asistente (#886). Derivar el perfil del
    número real de cámaras elimina ese estado inconsistente.

    Un perfil explícito (demo, professional_multi_camera, custom) se conserva:
    esos son una decisión deliberada y no están atados a un recuento concreto.
    """
    parsed = parse_profile(current) if current else None
    if parsed in EXPLICIT_PROFILES:
        return parsed

    derived = _COUNT_DERIVED_PROFILES.get(camera_count)
    if derived is not None:
        return derived
    if camera_count > 2:
        return InstallationProfile.PROFESSIONAL_MULTI_CAMERA
    # Sin cámaras todavía: conserva lo que hubiera, o cae al perfil base.
    return parsed or InstallationProfile.STARTER_1_CAMERA
