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

Migration: legacy administrator credentials require an explicit privileged reset.
A missing administrator secret never accepts the operator password.
Session-owned GUI administrator access is disabled until a privileged
verification broker exists.
"""

from __future__ import annotations

import hmac
import os

from runtime import secret_manager

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
    """Verify a dedicated administrator credential, failing closed on absence."""
    if os.environ.get("KHPTZ_GUI_MODE") == "user":
        return False
    try:
        actual = secret_manager.decrypt_secret(secret_manager.SECRET_ADMIN)
    except (secret_manager.PasswordNotConfiguredError, OSError):
        return False
    return _matches(candidate, actual)
