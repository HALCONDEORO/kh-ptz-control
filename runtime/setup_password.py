#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# setup_password.py - Utilidad para establecer/cambiar la contrasena de acceso
#
# Uso:  python3 -m runtime.setup_password   (o:  python3 setup_password.py)
#
# Migra password.txt a password.enc y lo elimina si existe.
#
# NOTA ASCII: este script puede ejecutarse en una terminal de Raspberry Pi con
# locale C / ISO-8859-* (instalacion headless por serie/SSH). El texto se
# mantiene en ASCII puro a proposito: imprimir caracteres como "->" o acentos
# sobre stdout/tty en ASCII lanzaria UnicodeEncodeError y abortaria el setup.
# tests/test_rpi_password_setup_contract.py verifica que el fuente sea ASCII.

from __future__ import annotations

import getpass
import sys
from pathlib import Path

from runtime.secret_manager import encrypt_password, decrypt_password, _ENC_FILE, PasswordNotConfiguredError


def main() -> None:
    print("=" * 50)
    print("  KH PTZ Control - Configuracion de contrasena")
    print("=" * 50)

    # Migracion automatica desde password.txt (path canonico, no CWD-relativo)
    old_file = Path(__file__).parent / "password.txt"
    if old_file.exists() and not _ENC_FILE.exists():
        old_pwd = old_file.read_text(encoding="utf-8").strip()
        if old_pwd:
            try:
                encrypt_password(old_pwd)
                decrypt_password()  # verify write succeeded before deleting legacy file
                old_file.unlink()
                print("\n[OK] Contrasena migrada desde password.txt -> password.enc")
                print("  (password.txt eliminado)")
            except PasswordNotConfiguredError:
                print("[ERROR] La migracion no se pudo verificar. password.txt conservado.")
                sys.exit(1)
            return

    # Cambio manual de contrasena
    if _ENC_FILE.exists():
        try:
            current = decrypt_password()
        except PasswordNotConfiguredError:
            print("[AVISO] password.enc existe pero no se puede descifrar.")
            print("        Se establecera una contrasena nueva sin verificar la actual.")
            current = None
        if current is not None:
            confirm = getpass.getpass("\nContrasena actual: ")
            if confirm != current:
                print("[ERROR] Contrasena actual incorrecta.")
                sys.exit(1)

    while True:
        new_pwd = getpass.getpass("\nNueva contrasena: ")
        if not new_pwd:
            print("[ERROR] La contrasena no puede estar vacia.")
            continue
        confirm2 = getpass.getpass("Confirmar contrasena: ")
        if new_pwd != confirm2:
            print("[ERROR] Las contrasenas no coinciden.")
            continue
        break

    encrypt_password(new_pwd)
    print(f"\n[OK] Contrasena guardada en {_ENC_FILE}")


if __name__ == "__main__":
    main()
