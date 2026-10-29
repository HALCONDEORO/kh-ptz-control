#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# secret_manager.py — Cifrado de contraseña ligado a la máquina (sin dependencias externas)
#
# Esquema: PBKDF2-HMAC-SHA256(machine_guid, salt, 200_000) → clave 32 bytes
#          XOR-stream con SHA256 en modo contador → cifrado simétrico
#          Almacenamiento: 16 bytes salt (hex) + ':' + datos cifrados (hex) en password.enc
#
# El archivo password.enc es inútil fuera de esta máquina porque la clave
# se deriva del MachineGuid de Windows (o del hostname como fallback).

from __future__ import annotations

import hashlib
import logging
import os
import re
import socket
from pathlib import Path

from core.atomic_write import write_text_atomic

_logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(
    os.environ.get("HALLPTZ_DATA_DIR")
    or os.environ.get("HALLPTZ_DATA_DIR")
    or (Path.home() / ".config" / "hallptz")
)
_ENC_FILE = _CONFIG_DIR / "password.enc"

# Canonical secret names. The entry (operator) password keeps the historical
# password.enc filename for backward compatibility; the administrator password
# is a separate secret so the two logins are truly independent.
SECRET_ENTRY = "password"   # operator entry password  → password.enc
SECRET_ADMIN = "admin"      # administrator password   → admin.enc

_SECRET_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _secret_file(name: str) -> Path:
    """Resolve ``<name>.enc`` inside the secrets dir, rejecting unsafe names.

    ``SECRET_ENTRY`` resolves to the dedicated ``_ENC_FILE`` constant so the
    legacy filename and existing test isolation (which monkeypatches it) keep
    working; every other name lands at ``_CONFIG_DIR / "<name>.enc"``.
    """
    if not _SECRET_NAME_RE.match(name):
        raise ValueError(f"Invalid secret name: {name!r}")
    if name == SECRET_ENTRY:
        return _ENC_FILE
    return _CONFIG_DIR / f"{name}.enc"


class PasswordNotConfiguredError(Exception):
    """Raised when password.enc is missing, corrupt, or unreadable."""


# ─────────────────────────────────────────────────────────────────
#  IDENTIFICADOR DE MÁQUINA
# ─────────────────────────────────────────────────────────────────

def _machine_id() -> str:
    """Obtener identificador único de la máquina."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography"
        )
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return guid
    except Exception:
        pass
    try:
        return Path("/etc/machine-id").read_text(encoding="ascii").strip()
    except OSError:
        return socket.gethostname()


# ─────────────────────────────────────────────────────────────────
#  DERIVACIÓN DE CLAVE
# ─────────────────────────────────────────────────────────────────

def _derive_key(salt: bytes) -> bytes:
    """Derivar clave de 32 bytes a partir del ID de máquina y sal aleatoria."""
    machine = _machine_id().encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", machine, salt, 200_000, dklen=32)


# ─────────────────────────────────────────────────────────────────
#  CIFRADO / DESCIFRADO  (XOR-stream con SHA256 en modo contador)
# ─────────────────────────────────────────────────────────────────

def _xor_stream(data: bytes, key: bytes) -> bytes:
    """Aplicar cifrado XOR-stream: genera keystream con SHA256 por bloques de 32 bytes."""
    out = bytearray(len(data))
    block = 0
    offset = 0
    while offset < len(data):
        ks_block = hashlib.sha256(key + block.to_bytes(4, "big")).digest()
        for byte in ks_block:
            if offset >= len(data):
                break
            out[offset] = data[offset] ^ byte
            offset += 1
        block += 1
    return bytes(out)


def _migrate_enc_file(legacy_paths: list[Path] | None = None) -> None:
    """Move password.enc from legacy CWD/app-dir location to canonical _CONFIG_DIR."""
    if _ENC_FILE.exists():
        return
    if legacy_paths is None:
        legacy_paths = [Path("password.enc"), Path(__file__).parent / "password.enc"]
    for src in legacy_paths:
        try:
            if src.exists() and src.resolve() != _ENC_FILE.resolve():
                _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                _ENC_FILE.write_bytes(src.read_bytes())
                src.unlink(missing_ok=True)
                _logger.info("password.enc migrado de %s -> %s", src, _ENC_FILE)
                return
        except OSError as exc:
            _logger.warning("No se pudo migrar password.enc desde %s: %s", src, exc)


# ─────────────────────────────────────────────────────────────────
#  SECRETOS CON NOMBRE  (entrada + admin, mismo cifrado)
# ─────────────────────────────────────────────────────────────────

def encrypt_secret(name: str, plaintext: str) -> None:
    """Cifrar *plaintext* y guardarlo en ``<name>.enc`` (atómico, modo 0600)."""
    path = _secret_file(name)
    salt = os.urandom(16)
    key = _derive_key(salt)
    encrypted = _xor_stream(plaintext.encode("utf-8"), key)
    blob = salt.hex() + ":" + encrypted.hex()
    write_text_atomic(path, blob, encoding="ascii", mode=0o600)


def decrypt_secret(name: str) -> str:
    """Descifrar ``<name>.enc``.

    Raises PasswordNotConfiguredError if the file is missing, corrupt, or
    unreadable — never falls back to a hardcoded default.
    """
    path = _secret_file(name)
    if not path.exists():
        raise PasswordNotConfiguredError(f"{name}.enc not found.")
    try:
        blob = path.read_text(encoding="ascii").strip()
        salt_hex, enc_hex = blob.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        encrypted = bytes.fromhex(enc_hex)
        key = _derive_key(salt)
        return _xor_stream(encrypted, key).decode("utf-8")
    except Exception as exc:
        raise PasswordNotConfiguredError(
            f"{name}.enc is corrupt or unreadable: {exc}."
        ) from exc


def secret_is_configured(name: str) -> bool:
    """Return True only if ``<name>.enc`` exists and decrypts successfully."""
    try:
        decrypt_secret(name)
        return True
    except PasswordNotConfiguredError:
        return False


def secret_file_exists(name: str) -> bool:
    """Return True if ``<name>.enc`` is present, whether or not it decrypts.

    Deliberately distinct from :func:`secret_is_configured`, which conflates
    "no secret was ever set" with "a secret exists but could not be read".
    Callers that gate on privilege need to tell those apart: an unreadable
    admin secret must deny access, never silently fall back to a lower-privilege
    password. Existence alone must not raise, so a permissions problem cannot
    turn into an authentication decision.
    """
    try:
        return _secret_file(name).exists()
    except (OSError, ValueError):
        # An invalid name or an unstattable path: treat the secret as present so
        # callers fail closed rather than opening a fallback path.
        return True


# ─────────────────────────────────────────────────────────────────
#  CONTRASEÑA DE ENTRADA (operador)  — back-compat password.enc
# ─────────────────────────────────────────────────────────────────

def encrypt_password(plaintext: str) -> None:
    """Cifrar la contraseña de entrada y guardarla en password.enc."""
    encrypt_secret(SECRET_ENTRY, plaintext)


def password_is_configured() -> bool:
    """Return True only if password.enc exists and can be decrypted successfully."""
    return secret_is_configured(SECRET_ENTRY)


def decrypt_password() -> str:
    """Descifrar la contraseña de entrada desde password.enc.

    Migra primero desde una ubicación legacy si procede, luego delega en
    decrypt_secret. Raises PasswordNotConfiguredError si falta o está corrupto.
    """
    _migrate_enc_file()
    try:
        return decrypt_secret(SECRET_ENTRY)
    except PasswordNotConfiguredError as exc:
        # Keep the historical, terminal-friendly remediation for the entry
        # password (the admin secret is set via the wizard, not this command).
        raise PasswordNotConfiguredError(
            f"{exc} Run: python3 -m runtime.setup_password"
        ) from exc
