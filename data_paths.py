#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# data_paths.py — Directorio persistente de datos de usuario
#
# Centraliza la ubicación de todos los archivos JSON que deben sobrevivir
# una reinstalación del software (git pull, rm -rf + clone, etc.).
#
# Directorio de datos: ~/.config/khptz/  (por defecto)
#   Override: variable de entorno KHPTZ_DATA_DIR
#   Ejemplo:  KHPTZ_DATA_DIR=/mnt/usb/backup python3 main.py
#
#   - Vive en el home del usuario, fuera del árbol de la app.
#   - Se crea automáticamente al arrancar la aplicación.
#   - En reinstalaciones solo se toca el directorio de la app; ~/.config queda intacto.
#
# Migración automática:
#   Si los archivos existen en el directorio antiguo (directorio de la app)
#   y NO en el nuevo, se copian automáticamente la primera vez que arranque
#   la app con esta versión. Esto evita perder datos en instalaciones existentes.
#
# Backup ZIP:
#   export_backup() crea un ZIP con TODOS los archivos necesarios para
#   reproducir una instalación en otro equipo:
#     - Datos JSON (chairman_presets, seat_names, schedule) → ~/.config/khptz/
#     - Config TXT (PTZ1IP, PTZ2IP, Cam1ID, Cam2ID, ATEMIP, Contact) → app dir
#   import_backup() restaura ambos grupos al directorio correcto.

from __future__ import annotations

import json
import logging
import os
import shutil
import warnings
import zipfile
from pathlib import Path

warnings.warn(
    "data_paths is deprecated and will be removed in a future release. "
    "Use runtime.path_resolver.RuntimePathResolver instead.",
    DeprecationWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_DIR = Path.home() / '.config' / 'khptz'

# KHPTZ_DATA_DIR permite al administrador apuntar los datos a cualquier ruta
# (NAS, USB, directorio de pruebas) sin tocar el código.
_data_dir_env = os.environ.get('KHPTZ_DATA_DIR') or ''
CONFIG_DIR = Path(_data_dir_env) if _data_dir_env else _DEFAULT_CONFIG_DIR
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Rutas de archivos de datos JSON
CHAIRMAN_PRESETS_FILE  = CONFIG_DIR / 'chairman_presets.json'
SEAT_NAMES_FILE        = CONFIG_DIR / 'seat_names.json'
SCHEDULE_FILE          = CONFIG_DIR / 'schedule.json'
ROOM_LAYOUT_FILE       = CONFIG_DIR / 'room_layout.json'
CHANGE_HISTORY_FILE    = CONFIG_DIR / 'change_history.json'
PRESET_BRIGHTNESS_FILE = CONFIG_DIR / 'preset_brightness.json'
SESSION_MARKER_FILE    = CONFIG_DIR / 'session.active'
ACCESS_MODE_FILE       = CONFIG_DIR / 'access_mode.json'
ADMIN_LOGIN_FLAG       = CONFIG_DIR / 'admin_login.flag'

_DATA_FILES   = (CHAIRMAN_PRESETS_FILE, SEAT_NAMES_FILE, SCHEDULE_FILE, ROOM_LAYOUT_FILE, PRESET_BRIGHTNESS_FILE)
_LEGACY_FILES = ('chairman_presets.json', 'seat_names.json', 'schedule.json')

# Contenido por defecto para resetear los archivos legacy del directorio de la app
_LEGACY_DEFAULTS = {
    'chairman_presets.json': '{}',
    'seat_names.json':       '{"names": [], "seats": {}}',
    'schedule.json':         '{}',
}

# Archivos de configuración de red — viven en el directorio de la app
_CONFIG_TXT_FILES = (
    'PTZ1IP.txt',
    'PTZ2IP.txt',
    'Cam1ID.txt',
    'Cam2ID.txt',
    'ATEMIP.txt',
    'Contact.txt',
)


def _app_dir() -> Path:
    """Directorio de la aplicación (donde viven los .txt de configuración de red)."""
    return Path(__file__).parent


def migrate_legacy_files(app_dir: Path | None = None) -> None:
    """
    Migra archivos desde el directorio de la app al CONFIG_DIR si no existen ya.
    Una vez migrados (ambos lados existen), resetea el del directorio de la app
    a valores por defecto para evitar confusión: el archivo activo es siempre
    el de CONFIG_DIR.

    Llamar una vez al arrancar la aplicación (desde main.py), antes de que
    cualquier módulo intente leer los archivos de datos.
    app_dir se puede pasar explícitamente en tests para aislar la llamada.
    """
    if app_dir is None:
        app_dir = _app_dir()
    for filename in _LEGACY_FILES:
        src = app_dir / filename
        dst = CONFIG_DIR / filename
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(src, dst)
                logger.info("Migrado %s → %s", src, dst)
            except OSError as exc:
                logger.warning("No se pudo migrar %s: %s", src, exc)
                continue
        # Si el archivo ya existe en CONFIG_DIR y también en el directorio de la
        # app, resetear el de la app a contenido vacío/por defecto para evitar
        # confusión: el archivo activo es siempre el de CONFIG_DIR.
        if src.exists() and dst.exists():
            default = _LEGACY_DEFAULTS.get(filename, '{}')
            try:
                src.write_text(default, encoding='utf-8')
                logger.info("Archivo legacy reseteado a valores por defecto: %s", src.name)
            except OSError as exc:
                logger.warning("No se pudo resetear legacy %s: %s", src, exc)


def export_backup(dest_zip: Path, app_dir: Path | None = None) -> list[str]:
    """
    Crea un ZIP con todos los archivos necesarios para restaurar la instalación.

    Incluye:
      - Archivos JSON de datos (desde CONFIG_DIR):
          chairman_presets.json, seat_names.json, schedule.json
      - Archivos TXT de configuración de red (desde el directorio de la app):
          PTZ1IP.txt, PTZ2IP.txt, Cam1ID.txt, Cam2ID.txt, ATEMIP.txt, Contact.txt

    Los archivos TXT se almacenan en el ZIP bajo la carpeta 'config/' para
    distinguirlos de los JSON y poder restaurarlos al directorio correcto.

    Devuelve la lista de nombres incluidos (sin prefijo de carpeta).
    Lanza OSError si la escritura falla.
    """
    if app_dir is None:
        app_dir = _app_dir()

    included: list[str] = []
    with zipfile.ZipFile(dest_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in _DATA_FILES:
            if f.exists():
                zf.write(f, f.name)
                included.append(f.name)

        for name in _CONFIG_TXT_FILES:
            f = app_dir / name
            if f.exists():
                zf.write(f, f'config/{name}')
                included.append(name)

    logger.info("Backup exportado a %s (%d archivos)", dest_zip, len(included))
    return included


def import_backup(zip_path: Path, app_dir: Path | None = None) -> list[str]:
    """
    Restaura archivos de datos y configuración desde un ZIP de backup.

    - Archivos JSON (raíz del ZIP): se validan como JSON y se restauran a CONFIG_DIR.
    - Archivos TXT (carpeta 'config/' del ZIP): se restauran al directorio de la app.
    - Crea .bak del archivo existente antes de sobreescribir.
    - Usa escritura atómica (.tmp → os.replace) para evitar corrupción parcial.
    - Devuelve la lista de nombres restaurados (sin prefijo de carpeta).
    - Lanza ValueError si el ZIP no contiene ningún archivo reconocido.
    - Lanza json.JSONDecodeError si algún JSON del ZIP está corrupto.
    - Lanza zipfile.BadZipFile si el ZIP está corrupto.
    """
    if app_dir is None:
        app_dir = _app_dir()

    valid_json = {f.name for f in _DATA_FILES}
    valid_txt  = set(_CONFIG_TXT_FILES)
    restored: list[str] = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        namelist = zf.namelist()

        # Identificar qué archivos reconocidos hay en el ZIP
        json_found = [n for n in namelist if n in valid_json]
        txt_found  = [n for n in namelist if n.startswith('config/') and
                      n[len('config/'):] in valid_txt]

        if not json_found and not txt_found:
            raise ValueError(
                "El ZIP no contiene archivos reconocidos. "
                f"JSON esperados: {', '.join(sorted(valid_json))}. "
                f"TXT esperados (en carpeta config/): {', '.join(sorted(valid_txt))}."
            )

        # Restaurar JSON de datos → CONFIG_DIR
        for name in json_found:
            raw = zf.read(name).decode('utf-8')
            decoded = json.loads(raw)  # valida JSON antes de tocar disco
            if not isinstance(decoded, dict):
                raise ValueError(f"{name} debe contener un objeto JSON")

            dst = CONFIG_DIR / name
            if dst.exists():
                shutil.copy2(dst, dst.with_suffix('.bak'))

            tmp = dst.with_suffix('.tmp')
            try:
                tmp.write_text(raw, encoding='utf-8')
                os.replace(tmp, dst)
            except OSError as exc:
                tmp.unlink(missing_ok=True)
                logger.exception("No se pudo restaurar %s: %s", name, exc)
                continue

            restored.append(name)
            logger.info("Restaurado %s → %s", name, dst)

        # Restaurar TXT de configuración → directorio de la app
        for zip_name in txt_found:
            name = zip_name[len('config/'):]  # quitar prefijo de carpeta
            raw = zf.read(zip_name).decode('utf-8').strip()

            dst = app_dir / name
            if dst.exists():
                shutil.copy2(dst, dst.with_suffix('.bak'))

            tmp = dst.with_suffix('.tmp')
            try:
                tmp.write_text(raw, encoding='utf-8')
                os.replace(tmp, dst)
            except OSError as exc:
                tmp.unlink(missing_ok=True)
                logger.exception("No se pudo restaurar %s: %s", name, exc)
                continue

            restored.append(name)
            logger.info("Restaurado %s → %s", name, dst)

    return restored
