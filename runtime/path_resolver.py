#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# runtime/path_resolver.py — Single source of truth for Hall PTZ Control runtime paths.
#
# Production paths (Raspberry Pi service install):
#   /opt/hallptz/          installed application code (read-only)
#   /etc/hallptz/          customer/site configuration
#   /var/lib/hallptz/      persistent customer/runtime data
#   /var/log/hallptz/      production logs
#   /var/backups/hallptz/  local backups
#
# Override variables (tests, demo, support):
#   HALLPTZ_CONFIG_DIR     overrides /etc/hallptz/
#   HALLPTZ_DATA_DIR  overrides /var/lib/hallptz/ (legacy compat variable)
#   HALLPTZ_LOG_DIR        overrides /var/log/hallptz/
#   HALLPTZ_BACKUP_DIR     overrides /var/backups/hallptz/
#
# See docs/RUNTIME_PATH_CONTRACT.md for ownership, permissions and migration rules.

from __future__ import annotations

import os
from pathlib import Path


# ── Production defaults ───────────────────────────────────────────────────────

_PROD_CONFIG_DIR  = Path("/etc/hallptz")
_PROD_DATA_DIR    = Path("/var/lib/hallptz")
_PROD_LOG_DIR     = Path("/var/log/hallptz")
_PROD_BACKUP_DIR  = Path("/var/backups/hallptz")
# Volatile provisioning channel (tmpfs). The unprivileged wizard drops a request
# here; the privileged hallptz-provision path-unit reacts and writes the result.
_PROD_RUN_DIR     = Path("/run/hallptz")

# Legacy location — read-migrate source only, never written by new code.
LEGACY_DATA_DIR = Path.home() / ".config" / "hallptz"


def _resolve(env_var: str, production_default: Path) -> Path:
    """Return the path from the env override, or the production default."""
    raw = os.environ.get(env_var, "")
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            raise ValueError(
                f"Environment override {env_var}={raw!r} must be an absolute path."
            )
        return p
    return production_default


class RuntimePathResolver:
    """
    One source of truth for all Hall PTZ Control runtime paths.

    Instantiate once at startup. Paths are resolved eagerly from environment
    variables or production defaults. No I/O is performed — callers are
    responsible for creating directories if needed.

    Environment variable overrides are intended for tests, demo and support use.
    They must not appear in production systemd unit files without explicit documentation.
    """

    def __init__(self) -> None:
        # Allow HALLPTZ_DATA_DIR as the legacy override for the data dir
        # (same variable honoured by data_paths.py for backward compat).
        data_env = os.environ.get("HALLPTZ_DATA_DIR") or ""

        self._config_dir  = _resolve("HALLPTZ_CONFIG_DIR",  _PROD_CONFIG_DIR)
        self._log_dir     = _resolve("HALLPTZ_LOG_DIR",    _PROD_LOG_DIR)
        self._backup_dir  = _resolve("HALLPTZ_BACKUP_DIR", _PROD_BACKUP_DIR)
        self._run_dir     = _resolve("HALLPTZ_RUN_DIR",    _PROD_RUN_DIR)

        # data_dir honours HALLPTZ_DATA_DIR / HALLPTZ_DATA_DIR (resolved into
        # data_env above); empty → production default, relative → error.
        self._data_dir = _PROD_DATA_DIR
        if data_env:
            p = Path(data_env)
            if not p.is_absolute():
                raise ValueError(
                    f"HALLPTZ_DATA_DIR / HALLPTZ_DATA_DIR={data_env!r} must be an absolute path."
                )
            self._data_dir = p

    # ── Directory accessors ───────────────────────────────────────────────────

    @property
    def config_dir(self) -> Path:
        """Site configuration directory (/etc/hallptz/ or override)."""
        return self._config_dir

    @property
    def data_dir(self) -> Path:
        """Persistent customer/runtime data directory (/var/lib/hallptz/ or override)."""
        return self._data_dir

    @property
    def log_dir(self) -> Path:
        """Production log directory (/var/log/hallptz/ or override)."""
        return self._log_dir

    @property
    def backup_dir(self) -> Path:
        """Local backup output directory (/var/backups/hallptz/ or override)."""
        return self._backup_dir

    @property
    def support_bundle_dir(self) -> Path:
        """Support bundle output directory (inside backup_dir)."""
        return self._backup_dir / "support"

    @property
    def run_dir(self) -> Path:
        """Volatile provisioning channel directory (/run/hallptz/ or override).

        tmpfs in production: created 0750 root:<desktop-user> by tmpfiles.d so
        only the wizard's session user can drop a request. Never holds data at
        rest — the privileged side shreds the request after applying it.
        """
        return self._run_dir

    @property
    def provision_request_file(self) -> Path:
        """Where the wizard writes the provisioning request the path-unit watches."""
        return self._run_dir / "request.json"

    @property
    def provision_result_file(self) -> Path:
        """Where the privileged side writes the result the wizard polls."""
        return self._run_dir / "result.json"

    # ── File accessors ────────────────────────────────────────────────────────

    @property
    def provisioned_marker_file(self) -> Path:
        """Sentinel written by the provisioner once install+verify succeeds.

        Lives in config_dir (e.g. /etc/hallptz/.provisioned). In production the dir
        is mode 2751 and this file 0644, so the unprivileged desktop session can
        stat it to decide whether to launch the setup wizard, without read access
        to config.yaml or the secrets.
        """
        return self._config_dir / ".provisioned"

    @property
    def known_good_state_file(self) -> Path:
        return self._data_dir / "known_good_state.json"

    @property
    def installation_fingerprint_file(self) -> Path:
        return self._data_dir / "installation_fingerprint.json"

    @property
    def maintenance_status_file(self) -> Path:
        return self._data_dir / "maintenance_status.json"

    @property
    def blackbox_dir(self) -> Path:
        """Black box / flight recorder directory (/var/log/hallptz/blackbox/ or override)."""
        return self._log_dir / "blackbox"

    @property
    def blackbox_events_file(self) -> Path:
        """Active flight recorder JSONL event log."""
        return self.blackbox_dir / "events.jsonl"

    @property
    def incidents_dir(self) -> Path:
        """Directory where IncidentService writes JSON incident snapshots."""
        return self._log_dir / "incidents"

    @property
    def incident_log_file(self) -> Path:
        return self._log_dir / "incidents.jsonl"

    @property
    def session_marker_file(self) -> Path:
        return self._data_dir / "session.active"

    @property
    def room_layout_file(self) -> Path:
        return self._data_dir / "room_layout.json"

    @property
    def chairman_presets_file(self) -> Path:
        return self._data_dir / "chairman_presets.json"

    @property
    def seat_names_file(self) -> Path:
        return self._data_dir / "seat_names.json"

    @property
    def schedule_file(self) -> Path:
        return self._data_dir / "schedule.json"

    @property
    def change_history_file(self) -> Path:
        return self._data_dir / "change_history.json"

    @property
    def access_mode_file(self) -> Path:
        return self._data_dir / "access_mode.json"

    @property
    def admin_login_flag(self) -> Path:
        return self._data_dir / "admin_login.flag"

    @property
    def preset_brightness_file(self) -> Path:
        return self._data_dir / "preset_brightness.json"

    # ── Source vs install detection ───────────────────────────────────────────

    @property
    def running_from_source(self) -> bool:
        """
        Return True if the process is running from a git checkout rather than
        a service install under /opt/hallptz/.

        Detection heuristic: check for a .git directory near the source root.
        This is intentionally conservative — false-negative (source reported as
        installed) is less dangerous than false-positive.
        """
        source_root = Path(__file__).resolve().parent.parent
        return (source_root / ".git").is_dir()

    # ── Override summary ──────────────────────────────────────────────────────

    def active_overrides(self) -> dict[str, str]:
        """Return a dict of env variables that are overriding the production defaults."""
        overrides: dict[str, str] = {}
        for var, default in (
            ("HALLPTZ_CONFIG_DIR",  str(_PROD_CONFIG_DIR)),
            ("HALLPTZ_LOG_DIR",     str(_PROD_LOG_DIR)),
            ("HALLPTZ_BACKUP_DIR",  str(_PROD_BACKUP_DIR)),
        ):
            val = os.environ.get(var, "")
            if val:
                overrides[var] = val
        for var in ("HALLPTZ_DATA_DIR", "HALLPTZ_DATA_DIR"):
            val = os.environ.get(var, "")
            if val:
                overrides[var] = val
                break
        return overrides

    def to_dict(self) -> dict[str, str]:
        """Return a plain dict summary suitable for hallptz doctor or support bundles."""
        return {
            "config_dir":                  str(self.config_dir),
            "data_dir":                    str(self.data_dir),
            "log_dir":                     str(self.log_dir),
            "backup_dir":                  str(self.backup_dir),
            "support_bundle_dir":          str(self.support_bundle_dir),
            "running_from_source":         str(self.running_from_source),
            "active_overrides":            ", ".join(self.active_overrides()) or "none",
        }
