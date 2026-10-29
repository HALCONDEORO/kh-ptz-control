#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# config/__init__.py — Configuración legacy de la aplicación (migrado desde config.py)
#
# Exporta las mismas constantes y funciones que el antiguo config.py para que
# todo el código existente siga funcionando con `from config import ...`.
# La nueva configuración tipada está en config/settings.py + config/loader.py.

from __future__ import annotations

import logging
import re
import socket
import binascii
import threading
from dataclasses import dataclass, field
from pathlib import Path

from runtime.path_resolver import RuntimePathResolver as _RuntimePathResolver
from core.json_io import load_json, save_json

NAMES_FILE = _RuntimePathResolver().seat_names_file

logger = logging.getLogger(__name__)

# Raíz del proyecto: un nivel arriba de este paquete config/
_PROJECT_ROOT = Path(__file__).parent.parent


# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTES DE VELOCIDAD Y RED
# ═══════════════════════════════════════════════════════════════════════════════

SPEED_MIN = 1
PAN_SPEED_MAX  = 24
TILT_SPEED_MAX = 20
ZOOM_DRIVE_MAX = 7
SPEED_MAX = TILT_SPEED_MAX
SPEED_DEFAULT = 8

CAMERA_CONNECT_TIMEOUT = 1
VISCA_READ_TIMEOUT     = 1
ATEM_CONNECT_TIMEOUT   = 5
SOCKET_TIMEOUT         = CAMERA_CONNECT_TIMEOUT
VISCA_PORT = 5678
CAMERA_QUEUE_MAXSIZE = 20
HEARTBEAT_TIMEOUT = 5.0
VISCA_SLOW_CMD_MS = 300
BUTTON_COLOR = "black"

PRESET_ZOOM_SETTLE_BASE   = 4.0
PRESET_ZOOM_SETTLE_MARGIN = 1.5
PRESET_ZOOM_SETTLE_MAX    = 12.0
PRESET_ZOOM_POLL_INTERVAL = 0.3


# ═══════════════════════════════════════════════════════════════════════════════
#  DATACLASS DE CONFIGURACIÓN DE CÁMARA
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CameraConfig:
    """Configuración de una cámara PTZ: dirección IP, VISCA ID y estado de conectividad."""
    ip: str
    cam_id: str
    check: str = field(default="Red")


@dataclass
class ATEMConfig:
    """Configuración del switcher ATEM: dirección IP."""
    ip: str


# ═══════════════════════════════════════════════════════════════════════════════
#  CARGAR CONFIGURACIÓN DESDE ARCHIVOS
# ═══════════════════════════════════════════════════════════════════════════════

# DEPRECATED globals — use AppSettings from config.yaml (injected via bootstrap).
# Defaults are empty; simulation mode patches these at startup via main_window.py.
# Warn if stale .txt files are found alongside a config.yaml that supersedes them.
CAM1 = CameraConfig(ip='', cam_id='81')
CAM2 = CameraConfig(ip='', cam_id='82')
ATEM = ATEMConfig(ip='')
Contact = 'No contact information available.'


def _warn_stale_txt_files() -> None:
    _config_yaml_present = False
    try:
        from runtime.path_resolver import RuntimePathResolver
        _config_yaml_present = (RuntimePathResolver().config_dir / 'config.yaml').exists()
    except Exception as exc:  # noqa: BLE001
        logger.debug("_warn_stale_txt_files: could not resolve config dir: %s", exc)
    if not _config_yaml_present:
        return
    for fname in ('PTZ1IP.txt', 'PTZ2IP.txt', 'Cam1ID.txt', 'Cam2ID.txt', 'ATEMIP.txt'):
        if (_PROJECT_ROOT / fname).exists():
            logger.warning(
                "Stale legacy config file found: %s — migrate to config.yaml and remove this file.",
                fname,
            )


_warn_stale_txt_files()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAPA DE PRESETS VISCA
# ═══════════════════════════════════════════════════════════════════════════════

PRESET_MAP: dict[int, str] = {}
for i in range(1, 90):
    PRESET_MAP[i] = f"{i:02X}"
for i in range(90, 100):
    PRESET_MAP[i] = f"{0x8C + (i - 90):02X}"
for i in range(100, 132):
    PRESET_MAP[i] = f"{i:02X}"
# 132 = segunda plataforma opcional (domain.preset.PRESET_PLATFORM_2 → hex 0x84)
PRESET_MAP[132] = f"{132:02X}"


# ═══════════════════════════════════════════════════════════════════════════════
#  POSICIONES DE ASIENTOS (COORDENADAS EN PÍXELES)
# ═══════════════════════════════════════════════════════════════════════════════

# DEPRECATED: Use LayoutService from AppContext. Will be removed when all
# installations have room_layout.json or LayoutService is always available.
SEAT_POSITIONS: dict[int, tuple[int, int]] = {
    4: (96, 211), 5: (159, 211), 6: (222, 211), 7: (285, 211),
    8: (500, 211), 9: (563, 211), 10: (626, 211), 11: (689, 211),
    12: (752, 211), 13: (815, 211), 14: (878, 211),
    15: (1094, 211), 16: (1157, 211), 17: (1220, 211), 18: (1283, 211),
    19: (96, 296), 20: (159, 296), 21: (222, 296), 22: (285, 296),
    23: (500, 296), 24: (563, 296), 25: (626, 296), 26: (689, 296),
    27: (752, 296), 28: (815, 296), 29: (878, 296),
    30: (1094, 296), 31: (1157, 296), 32: (1220, 296), 33: (1283, 296),
    34: (96, 383), 35: (159, 383), 36: (222, 383), 37: (285, 383),
    38: (500, 383), 39: (563, 383), 40: (626, 383), 41: (689, 383),
    42: (752, 383), 43: (815, 383), 44: (878, 383),
    45: (1094, 383), 46: (1157, 383), 47: (1220, 383), 48: (1283, 383),
    49: (96, 466), 50: (159, 466), 51: (222, 466), 52: (285, 466),
    53: (500, 466), 54: (563, 466), 55: (626, 466), 56: (689, 466),
    57: (752, 466), 58: (815, 466), 59: (878, 466),
    60: (1094, 466), 61: (1157, 466), 62: (1220, 466), 63: (1283, 466),
    64: (96, 551), 65: (159, 551), 66: (222, 551), 67: (285, 551),
    68: (500, 551), 69: (563, 551), 70: (626, 551), 71: (689, 551),
    72: (752, 551), 73: (815, 551), 74: (878, 551),
    75: (1094, 551), 76: (1157, 551), 77: (1220, 551), 78: (1283, 551),
    79: (96, 636), 80: (159, 636), 81: (222, 636), 82: (285, 636),
    83: (500, 636), 84: (563, 636), 85: (626, 636), 86: (689, 636),
    87: (752, 636), 88: (815, 636), 89: (878, 636),
    90: (1094, 636), 91: (1157, 636), 92: (1220, 636), 93: (1283, 636),
    94: (96, 721), 95: (159, 721), 96: (222, 721), 97: (285, 721),
    98: (500, 721), 99: (563, 721), 100: (626, 721), 101: (689, 721),
    102: (752, 721), 103: (815, 721), 104: (878, 721),
    105: (1094, 721), 106: (1157, 721), 107: (1220, 721), 108: (1283, 721),
    109: (96, 806), 110: (159, 806), 111: (222, 806), 112: (285, 806),
    113: (500, 806), 114: (563, 806), 115: (626, 806), 116: (689, 806),
    117: (752, 806), 118: (815, 806), 119: (878, 806),
    120: (1094, 806), 121: (1157, 806), 122: (1220, 806), 123: (1283, 806),
    124: (140, 960), 125: (230, 960), 126: (530, 960), 127: (620, 960),
    128: (150, 121),
    129: (380, 961),
    130: (1220, 121),
    131: (1157, 961),
}


# ═══════════════════════════════════════════════════════════════════════════════
#  VALIDADORES
# ═══════════════════════════════════════════════════════════════════════════════

def is_valid_ip(text: str) -> bool:
    """Validar dirección IPv4 (4 octetos 0-255)."""
    if not isinstance(text, str):
        return False
    text = text.strip()
    match = re.match(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$', text)
    if not match:
        return False
    try:
        return all(0 <= int(octet) <= 255 for octet in match.groups())
    except (ValueError, TypeError):
        return False


def is_valid_cam_id(text: str) -> bool:
    """Validar ID de cámara VISCA (formato hexadecimal, longitud par)."""
    if not isinstance(text, str):
        return False
    text = text.strip()
    if not text or len(text) % 2 != 0:
        return False
    try:
        binascii.unhexlify(text)
        return True
    except (binascii.Error, ValueError, TypeError):
        return False


# ═══════════════════════════════════════════════════════════════════════════════
#  PERSISTENCIA DE NOMBRES DE ASISTENTES
# ═══════════════════════════════════════════════════════════════════════════════

def load_names_data() -> dict:
    """Cargar nombres de asistentes y asignaciones de asientos desde JSON."""
    data = load_json(NAMES_FILE)
    if not isinstance(data, dict):
        return {"names": [], "seats": {}}
    names = data.get("names", [])
    seats = data.get("seats", {})
    if not isinstance(names, list):
        names = []
    if not isinstance(seats, dict):
        seats = {}
    return {"names": names, "seats": seats}


def save_names_data(names_list: list, seat_assignments: dict) -> bool:
    """Guardar nombres de asistentes y asignaciones en JSON (escritura atómica con backup)."""
    if not isinstance(names_list, list) or not isinstance(seat_assignments, dict):
        logger.warning("save_names_data: names must be list, seats must be dict")
        return False
    result = save_json(NAMES_FILE, {"names": names_list, "seats": seat_assignments})
    if not result:
        logger.error("Error saving %s", NAMES_FILE)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  VERIFICACIÓN DE CONECTIVIDAD DE CÁMARAS (PARALELA)
# ═══════════════════════════════════════════════════════════════════════════════

def check_camera(ip: str, cam_id: str, timeout: int = SOCKET_TIMEOUT) -> bool:
    """Verificar disponibilidad de cámara mediante conexión TCP."""
    if not is_valid_ip(ip) or not is_valid_cam_id(cam_id):
        logger.warning("check_camera: parámetros inválidos ip=%s cam_id=%s", ip, cam_id)
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((ip, VISCA_PORT))
            sock.sendall(binascii.unhexlify(cam_id + "090400FF"))
            sock.recv(1024)
        return True
    except (socket.timeout, socket.error, OSError, binascii.Error) as exc:
        logger.warning("check_camera %s: %s", ip, exc)
        return False


def check_all_cameras() -> None:
    """Verificar conectividad de todas las cámaras en paralelo y actualizar su campo .check."""
    from adapters.sim_mode import BACKUP as _SIM_BACKUP
    if _SIM_BACKUP.exists():
        CAM1.check = "Green"
        CAM2.check = "Green"
        return

    cam1_result = [False]
    cam2_result = [False]
    try:
        def _run_cam1(): cam1_result[0] = check_camera(CAM1.ip, CAM1.cam_id)
        def _run_cam2(): cam2_result[0] = check_camera(CAM2.ip, CAM2.cam_id)
        t1 = threading.Thread(target=_run_cam1, daemon=True)
        t2 = threading.Thread(target=_run_cam2, daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=3)
        t2.join(timeout=3)
    except Exception as exc:
        logger.exception("Error en threads de verificacion de camaras: %s", exc)
    CAM1.check = "Green" if cam1_result[0] else "Red"
    CAM2.check = "Green" if cam2_result[0] else "Red"
