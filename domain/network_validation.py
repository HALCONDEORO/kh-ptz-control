#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/network_validation.py — Reglas de validación de configuración de red
#
# Sin I/O de red. Solo lógica pura de dominio.
# Comprueba IPs duplicadas, IPs de loopback fuera de simulación, formato de IP y VISCA IDs.

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from config.settings import AppSettings

# Formato IPv4 básico: 4 grupos de 1-3 dígitos separados por puntos
_IPV4_RE = re.compile(
    r"^(25[0-5]|2[0-4]\d|[01]?\d\d?)\."
    r"(25[0-5]|2[0-4]\d|[01]?\d\d?)\."
    r"(25[0-5]|2[0-4]\d|[01]?\d\d?)\."
    r"(25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)


@dataclass(frozen=True)
class IpConfigIssue:
    """Un problema detectado en la configuración de red."""
    field: str    # p.ej. "cameras[0].ip"
    message: str  # descripción del problema


def is_valid_ipv4(value: str) -> bool:
    """Return True if *value* is a valid dotted-quad IPv4 address."""
    return bool(_IPV4_RE.match(value.strip()))


def is_loopback(value: str) -> bool:
    """Return True if *value* is a 127.x.x.x loopback address."""
    return value.strip().startswith("127.")


def validate_ip_config(settings: "AppSettings") -> List[IpConfigIssue]:
    """
    Validate the IP and VISCA configuration in *settings*.

    Returns a list of IpConfigIssue objects.  An empty list means no problems found.
    Pure function — no I/O.
    """
    issues: List[IpConfigIssue] = []
    is_simulation = settings.features.simulation

    camera_ips: List[str] = []
    seen_ips: set[str] = set()
    seen_visca_ids: set[str] = set()

    for idx, cam in enumerate(settings.cameras):
        ctx = f"cameras[{idx}] (id={cam.id!r})"
        ip = cam.ip.strip()

        if not ip:
            issues.append(IpConfigIssue(f"cameras[{idx}].ip", f"{ctx}: IP address is empty"))
            continue

        if not is_valid_ipv4(ip):
            issues.append(IpConfigIssue(f"cameras[{idx}].ip", f"{ctx}: invalid IP format '{ip}'"))
        else:
            if ip in seen_ips:
                issues.append(
                    IpConfigIssue(f"cameras[{idx}].ip", f"{ctx}: duplicate camera IP '{ip}'")
                )
            seen_ips.add(ip)
            camera_ips.append(ip)

            if is_loopback(ip) and not is_simulation:
                issues.append(
                    IpConfigIssue(
                        f"cameras[{idx}].ip",
                        f"{ctx}: loopback address '{ip}' only valid in simulation mode",
                    )
                )

        visca = cam.visca_id.strip()
        if visca in seen_visca_ids:
            issues.append(
                IpConfigIssue(
                    f"cameras[{idx}].visca_id",
                    f"{ctx}: duplicate VISCA ID '{visca}'",
                )
            )
        seen_visca_ids.add(visca)

    # Check ATEM IP against camera IPs
    atem_ip = settings.atem.ip.strip()
    if atem_ip and settings.features.atem_enabled:
        if not is_valid_ipv4(atem_ip):
            issues.append(IpConfigIssue("atem.ip", f"ATEM: invalid IP format '{atem_ip}'"))
        elif atem_ip in seen_ips:
            issues.append(
                IpConfigIssue("atem.ip", f"ATEM IP '{atem_ip}' conflicts with a camera IP")
            )

    return issues
