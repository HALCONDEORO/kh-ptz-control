#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# sim_mode.py — Activa / desactiva el modo simulación
#
# Llamado desde config_dialog.py (_build_sim_section) y opcionalmente
# desde terminal:
#   python sim_mode.py on    -> guarda IPs reales y escribe IPs del simulador
#   python sim_mode.py off   -> restaura las IPs reales
#   python sim_mode.py show  -> muestra la configuracion actual

import json
import os
import sys
from pathlib import Path

_APP_DIR: Path = (
    Path(os.environ["KHPTZ_APP_DIR"]).resolve()
    if os.environ.get("KHPTZ_APP_DIR")
    else Path(__file__).resolve().parent.parent  # adapters/ -> project root
)

BACKUP = _APP_DIR / "sim_ip_backup.json"

# IPs que se escriben al activar el modo simulacion
SIM_VALUES = {
    "PTZ1IP.txt": "127.0.0.1",
    "PTZ2IP.txt": "127.0.0.2",
}

# Ficheros cuyo valor original se guarda en el backup
BACKUP_FILES = ["PTZ1IP.txt", "PTZ2IP.txt", "ATEMIP.txt"]


def _read(name: str) -> str:
    p = _APP_DIR / name
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def _write(name: str, value: str) -> None:
    (_APP_DIR / name).write_text(value, encoding="utf-8")


def _load_backup() -> dict:
    try:
        data = json.loads(BACKUP.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"No se pudo leer sim_ip_backup.json: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("sim_ip_backup.json no contiene un objeto JSON válido")
    return data


def activate() -> bool:
    """
    Guarda las IPs reales en sim_ip_backup.json y escribe las IPs del simulador.
    Devuelve True si se activó, False si ya estaba activo.
    Lanza RuntimeError si el backup no se puede escribir.
    """
    if BACKUP.exists():
        return False  # ya activo

    backup = {f: _read(f) for f in BACKUP_FILES}
    tmp = BACKUP.with_name(BACKUP.name + ".tmp")
    try:
        tmp.write_text(json.dumps(backup, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(BACKUP))
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"No se pudo escribir sim_ip_backup.json; activación cancelada: {exc}") from exc

    for filename, sim_val in SIM_VALUES.items():
        _write(filename, sim_val)

    return True


def deactivate() -> bool:
    """
    Restaura las IPs reales desde el backup y elimina sim_ip_backup.json.
    Devuelve True si se desactivó, False si no estaba activo.
    Lanza RuntimeError si el backup está corrupto.
    Unexpected keys and non-string values in the backup are ignored and logged.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    if not BACKUP.exists():
        return False  # ya inactivo

    backup = _load_backup()
    for filename in BACKUP_FILES:
        if filename not in backup:
            _log.warning("sim_mode: backup key %r missing — skipping restore", filename)
            continue
        value = backup[filename]
        if not isinstance(value, str):
            _log.warning(
                "sim_mode: backup value for %r is not a string (%r) — skipping restore",
                filename, type(value).__name__,
            )
            continue
        _write(filename, value)

    # Log unexpected keys so operators can diagnose manual edits
    unexpected = set(backup.keys()) - set(BACKUP_FILES)
    for key in unexpected:
        _log.warning("sim_mode: unexpected key %r in backup — ignored", key)

    BACKUP.unlink()
    return True


def is_active() -> bool:
    return BACKUP.exists()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "show"

    if cmd == "on":
        if activate():
            print("Modo simulacion ACTIVADO.")
            for f, v in SIM_VALUES.items():
                print(f"  {f}  ->  {v!r}")
        else:
            print("Ya estaba activo (sim_ip_backup.json existe).")

    elif cmd == "off":
        try:
            if deactivate():
                print("Modo simulacion DESACTIVADO. IPs reales restauradas.")
            else:
                print("No estaba activo.")
        except RuntimeError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    elif cmd == "show":
        active = is_active()
        print(f"Modo simulacion: {'ACTIVO' if active else 'INACTIVO'}")
        for f in ["PTZ1IP.txt", "PTZ2IP.txt", "ATEMIP.txt", "Cam1ID.txt", "Cam2ID.txt"]:
            print(f"  {f:<15}  {_read(f)!r}")
        if active:
            try:
                backup = _load_backup()
                print("\nIPs reales guardadas:")
                for f, v in backup.items():
                    print(f"  {f:<15}  {v!r}")
            except RuntimeError as e:
                print(f"  ERROR leyendo backup: {e}")

    else:
        print("Uso: python -m adapters.sim_mode [on|off|show]")
        sys.exit(1)
