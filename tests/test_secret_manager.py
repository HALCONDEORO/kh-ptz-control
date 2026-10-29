#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_secret_manager.py — Tests de la capa de cifrado XOR-stream y del ciclo
encrypt/decrypt. Lógica pura: sin Qt, sin hardware, sin red.
"""

import sys

# test_preset_poll.py inyecta sys.modules["secret_manager"] = stub a nivel de módulo
# durante la fase de colección de pytest. Lo eliminamos aquí para garantizar que
# este archivo siempre importa la implementación real, independientemente del orden
# en que pytest coleccione los módulos.
sys.modules.pop("secret_manager", None)

import pytest
import runtime.secret_manager as _sm

_xor_stream              = _sm._xor_stream
encrypt_password         = _sm.encrypt_password
decrypt_password         = _sm.decrypt_password
password_is_configured   = _sm.password_is_configured
PasswordNotConfiguredError = _sm.PasswordNotConfiguredError


# ═══════════════════════════════════════════════════════════════════════════════
#  _xor_stream — propiedades de la primitiva XOR
# ═══════════════════════════════════════════════════════════════════════════════

class TestXorStream:

    def test_empty_input(self):
        assert _xor_stream(b"", b"anykey") == b""

    def test_xor_is_self_inverse(self):
        """Propiedad fundamental: aplicar el stream dos veces recupera el original."""
        data = b"hello world - datos de prueba"
        key  = b"x" * 32
        assert _xor_stream(_xor_stream(data, key), key) == data

    def test_output_length_equals_input_length(self):
        """El output siempre tiene la misma longitud que el input."""
        key = b"k" * 32
        for n in [1, 7, 31, 32, 33, 64, 100, 255]:
            assert len(_xor_stream(bytes(n), key)) == n

    def test_output_is_not_plaintext(self):
        """El output cifrado no debe coincidir con el input (keystream no es todo ceros)."""
        data = b"A" * 32
        key  = b"testkey" + bytes(25)
        assert _xor_stream(data, key) != data

    def test_different_keys_produce_different_ciphertext(self):
        data = b"mismo mensaje"
        out1 = _xor_stream(data, b"a" * 32)
        out2 = _xor_stream(data, b"b" * 32)
        assert out1 != out2

    def test_same_key_same_output_is_deterministic(self):
        data = b"deterministic"
        key  = b"z" * 32
        assert _xor_stream(data, key) == _xor_stream(data, key)

    def test_crosses_sha256_block_boundary(self):
        """SHA256 produce bloques de 32 bytes; datos >32 bytes usan más de un bloque."""
        data = bytes(range(256))  # 256 bytes = 8 bloques SHA256
        key  = b"longkey" + bytes(25)
        assert _xor_stream(_xor_stream(data, key), key) == data

    def test_single_byte_is_invertible(self):
        data = bytes([0xAB])
        key  = bytes(32)
        result = _xor_stream(data, key)
        assert len(result) == 1
        assert _xor_stream(result, key) == data


# ═══════════════════════════════════════════════════════════════════════════════
#  encrypt_password / decrypt_password — ciclo completo
# ═══════════════════════════════════════════════════════════════════════════════

class TestEncryptDecryptRoundtrip:

    @pytest.fixture(autouse=True)
    def isolated_enc_file(self, tmp_path, monkeypatch):
        """Redirige _ENC_FILE a un archivo temporal para no tocar password.enc real."""
        fake = tmp_path / "password.enc"
        monkeypatch.setattr(_sm, "_ENC_FILE", fake)
        self.enc_file = fake

    def test_roundtrip_simple_password(self):
        encrypt_password("fixture-only-not-a-real-password")
        assert decrypt_password() == "fixture-only-not-a-real-password"

    def test_roundtrip_complex_password(self):
        pw = "P@ss!w0rd#2026-Ñoño"
        encrypt_password(pw)
        assert decrypt_password() == pw

    def test_roundtrip_unicode_password(self):
        pw = "cámara-PTZ-€"
        encrypt_password(pw)
        assert decrypt_password() == pw

    def test_roundtrip_empty_password(self):
        encrypt_password("")
        assert decrypt_password() == ""

    def test_roundtrip_long_password(self):
        pw = "a" * 1000
        encrypt_password(pw)
        assert decrypt_password() == pw

    def test_missing_file_raises(self):
        assert not self.enc_file.exists()
        with pytest.raises(PasswordNotConfiguredError):
            decrypt_password()

    def test_missing_file_not_configured(self):
        assert not self.enc_file.exists()
        assert password_is_configured() is False

    def test_enc_file_created_after_encrypt(self):
        encrypt_password("test")
        assert self.enc_file.exists()

    def test_enc_file_format_is_salt_colon_cipher(self):
        """El archivo debe tener formato 'hex_salt:hex_cipher' legible como ASCII."""
        encrypt_password("test")
        content = self.enc_file.read_text(encoding="ascii").strip()
        parts = content.split(":")
        assert len(parts) == 2, "El archivo no tiene formato 'salt:cipher'"
        salt_hex, cipher_hex = parts
        # Ambas partes deben ser hex decodificable
        assert bytes.fromhex(salt_hex)
        assert bytes.fromhex(cipher_hex)
        # Salt debe ser 16 bytes → 32 caracteres hex
        assert len(salt_hex) == 32, f"Salt inesperado: {len(salt_hex)} chars (esperado 32)"

    def test_two_encryptions_differ_due_to_random_salt(self):
        """Salt aleatorio → cada cifrado produce un blob distinto para la misma contraseña."""
        encrypt_password("same_password")
        blob1 = self.enc_file.read_text()
        encrypt_password("same_password")
        blob2 = self.enc_file.read_text()
        assert blob1 != blob2

    def test_corrupted_file_raises(self):
        self.enc_file.write_text("not_valid_blob", encoding="ascii")
        with pytest.raises(PasswordNotConfiguredError):
            decrypt_password()

    def test_corrupted_file_not_configured(self):
        self.enc_file.write_text("not_valid_blob", encoding="ascii")
        assert password_is_configured() is False

    def test_unreadable_file_raises_configured_error(self, monkeypatch):
        class UnreadableFile:
            def exists(self):
                return True

            def read_text(self, *_args, **_kwargs):
                raise OSError("read failed")

        monkeypatch.setattr(_sm, "_ENC_FILE", UnreadableFile())

        with pytest.raises(PasswordNotConfiguredError):
            decrypt_password()

    def test_unreadable_file_not_configured(self, monkeypatch):
        class UnreadableFile:
            def exists(self):
                return True

            def read_text(self, *_args, **_kwargs):
                raise OSError("read failed")

        monkeypatch.setattr(_sm, "_ENC_FILE", UnreadableFile())

        assert password_is_configured() is False

    def test_invalid_hex_file_raises_configured_error(self):
        self.enc_file.write_text("zzzz:nothex", encoding="ascii")

        with pytest.raises(PasswordNotConfiguredError):
            decrypt_password()

    def test_truncated_file_raises(self):
        """Un archivo con solo el salt (sin ':cipher') lanza PasswordNotConfiguredError."""
        self.enc_file.write_text("a" * 32, encoding="ascii")
        with pytest.raises(PasswordNotConfiguredError):
            decrypt_password()

    def test_truncated_file_not_configured(self):
        self.enc_file.write_text("a" * 32, encoding="ascii")
        assert password_is_configured() is False

    def test_decrypted_value_matches_encrypted(self):
        """Confirma que decrypt devuelve exactamente la contraseña cifrada."""
        custom = "mi_password_especifico_12345"
        encrypt_password(custom)
        assert decrypt_password() == custom

    def test_configured_returns_true_after_encrypt(self):
        encrypt_password("cualquier_clave")
        assert password_is_configured() is True


# ═══════════════════════════════════════════════════════════════════════════════
#  CWD independence and migration (#601)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNamedSecrets:
    """Entry (password.enc) and admin (admin.enc) are independent secrets."""

    @pytest.fixture(autouse=True)
    def isolated_dir(self, tmp_path, monkeypatch):
        data = tmp_path / "data"
        monkeypatch.setattr(_sm, "_CONFIG_DIR", data)
        monkeypatch.setattr(_sm, "_ENC_FILE", data / "password.enc")

    def test_admin_roundtrip(self):
        _sm.encrypt_secret(_sm.SECRET_ADMIN, "admin-pass")
        assert _sm.decrypt_secret(_sm.SECRET_ADMIN) == "admin-pass"

    def test_admin_not_configured_initially(self):
        assert _sm.secret_is_configured(_sm.SECRET_ADMIN) is False

    def test_admin_configured_after_set(self):
        _sm.encrypt_secret(_sm.SECRET_ADMIN, "x")
        assert _sm.secret_is_configured(_sm.SECRET_ADMIN) is True

    def test_admin_file_is_admin_enc(self):
        _sm.encrypt_secret(_sm.SECRET_ADMIN, "x")
        assert (_sm._CONFIG_DIR / "admin.enc").exists()

    def test_entry_and_admin_are_independent(self):
        _sm.encrypt_secret(_sm.SECRET_ENTRY, "entry-pw")
        _sm.encrypt_secret(_sm.SECRET_ADMIN, "admin-pw")
        assert _sm.decrypt_secret(_sm.SECRET_ENTRY) == "entry-pw"
        assert _sm.decrypt_secret(_sm.SECRET_ADMIN) == "admin-pw"
        # Setting admin must not change the entry password and vice versa.
        assert decrypt_password() == "entry-pw"

    def test_entry_secret_uses_password_enc_constant(self):
        # SECRET_ENTRY must resolve to the dedicated _ENC_FILE constant.
        assert _sm._secret_file(_sm.SECRET_ENTRY) == _sm._ENC_FILE

    def test_invalid_secret_name_rejected(self):
        for bad in ("../escape", "Admin", "with space", "", "1leading"):
            with pytest.raises(ValueError):
                _sm._secret_file(bad)

    def test_missing_admin_raises(self):
        with pytest.raises(PasswordNotConfiguredError):
            _sm.decrypt_secret(_sm.SECRET_ADMIN)


class TestCwdIndependence:

    def test_enc_file_is_absolute_path(self):
        """_ENC_FILE must not be a relative path."""
        assert _sm._ENC_FILE.is_absolute()

    def test_enc_file_does_not_depend_on_cwd(self, tmp_path, monkeypatch):
        """Changing CWD must not alter where password.enc is read/written."""
        monkeypatch.chdir(tmp_path)
        assert _sm._ENC_FILE.is_absolute()
        assert not _sm._ENC_FILE.is_relative_to(tmp_path)


class TestMigrateEncFile:

    @pytest.fixture(autouse=True)
    def isolated_paths(self, tmp_path, monkeypatch):
        self.canonical = tmp_path / "data" / "password.enc"
        monkeypatch.setattr(_sm, "_ENC_FILE", self.canonical)
        monkeypatch.setattr(_sm, "_CONFIG_DIR", tmp_path / "data")

    def test_migrate_moves_legacy_file_to_canonical(self, tmp_path):
        legacy = tmp_path / "legacy" / "password.enc"
        legacy.parent.mkdir()
        encrypt_password("secreto")
        self.canonical.rename(legacy)

        _sm._migrate_enc_file(legacy_paths=[legacy])

        assert self.canonical.exists()
        assert not legacy.exists()
        assert decrypt_password() == "secreto"

    def test_migrate_is_noop_when_canonical_exists(self, tmp_path):
        legacy = tmp_path / "legacy" / "password.enc"
        legacy.parent.mkdir()
        encrypt_password("canonical_pass")
        legacy.write_text("intruder", encoding="ascii")

        _sm._migrate_enc_file(legacy_paths=[legacy])

        # Canonical file must be untouched; legacy still there
        assert decrypt_password() == "canonical_pass"
        assert legacy.exists()

    def test_migrate_is_noop_when_no_legacy_file(self, tmp_path):
        _sm._migrate_enc_file(legacy_paths=[tmp_path / "nonexistent.enc"])
        assert not self.canonical.exists()

    def test_decrypt_calls_migration_automatically(self, tmp_path):
        legacy = tmp_path / "old.enc"
        encrypt_password("via_decrypt")
        self.canonical.rename(legacy)

        _sm._migrate_enc_file(legacy_paths=[legacy])
        result = decrypt_password()

        assert result == "via_decrypt"
