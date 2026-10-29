#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# camera_discovery.py — Descubrimiento de IPs de cámaras en la red local
#
# Expone tres funciones independientes del framework UI:
#   get_camera_subnet()  — Prefijo /24 derivado de CAM1.ip
#   tcp_scan()           — Escaneo TCP paralelo (50 workers) en VISCA_PORT
#   arp_scan()           — Lectura de la tabla ARP del sistema operativo
#   discover_cameras()   — Unión de ambos métodos, IPs únicas y ordenadas
#
# Importado desde:
#   splash_screen.py  — tests de inicialización
#   config_dialog.py  — botón "Scan Network" en ajustes

from __future__ import annotations

import logging
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import List

from config import CAM1, VISCA_PORT

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  SUBRED
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_SUBNET = '172.16.1'


def get_camera_subnet() -> str:
    """Return the /24 prefix of CAM1.ip (e.g. '172.16.1').

    Falls back to _DEFAULT_SUBNET when CAM1.ip is not a valid IPv4 address
    so that an unconfigured or invalid IP never produces a malformed subnet.
    """
    from config import is_valid_ip
    ip = CAM1.ip
    if not is_valid_ip(ip):
        return _DEFAULT_SUBNET
    return '.'.join(ip.split('.')[:3])


# ─────────────────────────────────────────────────────────────────────────────
#  TCP SCAN
# ─────────────────────────────────────────────────────────────────────────────

def _tcp_connect(host: str, timeout: float = 0.3, port: int = VISCA_PORT) -> bool:
    """Return True if *host* accepts a TCP connection on *port* (VISCA by default)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def tcp_scan(subnet: str = '', workers: int = 50, timeout: float = 0.3,
             port: int = VISCA_PORT) -> List[str]:
    """
    Escanea las 254 IPs de la subred /24 en *port* con 'workers' threads
    paralelos. Devuelve lista ordenada de IPs que aceptan conexión TCP.

    Parámetros:
        subnet   — Prefijo /24 (p.ej. '172.16.1'). Si vacío, usa get_camera_subnet().
        workers  — Número de threads simultáneos (defecto 50).
        timeout  — Timeout por host en segundos (defecto 0.3 s).
        port     — Puerto TCP a sondear (defecto VISCA_PORT).
    """
    if not subnet:
        subnet = get_camera_subnet()

    hosts = [f"{subnet}.{i}" for i in range(1, 255)]
    found: List[str] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for host, ok in zip(hosts, ex.map(lambda h: _tcp_connect(h, timeout, port), hosts)):
            if ok:
                found.append(host)
    return sorted(found)


# ─────────────────────────────────────────────────────────────────────────────
#  ARP TABLE
# ─────────────────────────────────────────────────────────────────────────────

def arp_scan(subnet: str = '') -> List[str]:
    """
    Ejecuta 'arp -a' y devuelve las IPs de la subred de las cámaras,
    sin broadcasts (.255) y sin duplicados.

    Parámetros:
        subnet — Prefijo /24. Si vacío, usa get_camera_subnet().
    """
    if not subnet:
        subnet = get_camera_subnet()
    try:
        proc = subprocess.run(
            ['arp', '-a'],
            capture_output=True, text=True, timeout=5
        )
        found: List[str] = []
        seen: set = set()
        for line in proc.stdout.splitlines():
            if line.strip().lower().startswith('interface'):
                continue
            m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
            if m:
                ip = m.group(1)
                if (ip.startswith(subnet + '.')
                        and not ip.endswith('.255')
                        and ip not in seen):
                    found.append(ip)
                    seen.add(ip)
        return found
    except Exception as exc:  # noqa: BLE001
        logger.warning("scan_arp: unexpected error (returning empty): %s", exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
#  DESCUBRIMIENTO COMBINADO
# ─────────────────────────────────────────────────────────────────────────────

def discover_cameras(subnet: str = '') -> List[str]:
    """
    Combina TCP scan y ARP table.
    TCP results are already VISCA_PORT-validated. ARP-only candidates are
    verified with a TCP probe before inclusion — prevents routers, printers
    and PCs from appearing as assignable cameras (#190).
    """
    if not subnet:
        subnet = get_camera_subnet()
    tcp = set(tcp_scan(subnet))
    arp_only = set(arp_scan(subnet)) - tcp
    confirmed_arp = {ip for ip in arp_only if _tcp_connect(ip)}
    return sorted(tcp | confirmed_arp)


# ─────────────────────────────────────────────────────────────────────────────
#  DESCUBRIMIENTO DE SWITCHERS ATEM
# ─────────────────────────────────────────────────────────────────────────────

# Blackmagic ATEM switchers escuchan en el puerto 9910 (mismo puerto que sondea
# el diagnóstico de red y el botón "Scan"). Descubrirlos permite al técnico
# encontrar la IP sin conocerla de antemano.
ATEM_PORT = 9910


def discover_atem_switchers(subnet: str = '') -> List[str]:
    """
    Escanea la subred /24 en el puerto de control ATEM (9910) y devuelve las
    IPs que responden, ordenadas.

    Reutiliza la subred de las cámaras (get_camera_subnet) porque en la mayoría
    de instalaciones el switcher está en la misma red que las cámaras.
    """
    if not subnet:
        subnet = get_camera_subnet()
    return tcp_scan(subnet, port=ATEM_PORT)
