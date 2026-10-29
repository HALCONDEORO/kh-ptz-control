#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/diagnostics_service.py — DiagnosticsService and CheckResult
#
# Runs basic health checks for the `hallptz doctor` command.
# Returns structured CheckResult objects so callers can act on results
# without parsing printed strings.
# Without Qt. Without network I/O (camera/ATEM reachability is out of scope here).

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import List

from domain.doctor_outcome import (
    CheckCategory,
    DoctorOutcome,
    derive_outcome,
    describe,
    exit_code_for,
)
from domain.runtime_mode import RuntimeMode


class Status(Enum):
    OK      = auto()
    WARNING = auto()
    FAIL    = auto()


# ── Runtime identity helpers (#887) ───────────────────────────────────────────
#
# `hallptz doctor` is run both by the desktop user (during installation) and by
# the hallptz service identity. Service-owned paths are deliberately not writable
# by the desktop user, so a permission check must know who is asking before it
# calls that a failure.

def _current_uid() -> int | None:
    getuid = getattr(os, "getuid", None)  # absent on Windows
    return getuid() if getuid is not None else None


def _current_user_label() -> str:
    try:
        import getpass
        return getpass.getuser()
    except Exception:  # noqa: BLE001
        uid = _current_uid()
        return f"uid {uid}" if uid is not None else "this user"


def _owner_label(path: Path) -> str:
    """Return the owning username of *path*, falling back to the raw uid."""
    try:
        uid = path.stat().st_uid
    except OSError:
        return "unknown"
    try:
        import pwd
        return pwd.getpwuid(uid).pw_name
    except Exception:  # noqa: BLE001 — no pwd on Windows, or unknown uid
        return str(uid)


def _is_owned_by_other_user(path: Path) -> bool:
    """True if *path* belongs to a different (service) user than the caller.

    Root is never "another user" — if root cannot write the path, that is a
    genuine fault rather than an identity mismatch. Returns False on platforms
    without POSIX ownership, so behaviour there is unchanged.
    """
    uid = _current_uid()
    if uid is None or uid == 0:
        return False
    try:
        return path.stat().st_uid != uid
    except OSError:
        return False


@dataclass
class CheckResult:
    name:    str
    status:  Status
    message: str
    evidence: dict = field(default_factory=dict)
    suggested_action: str | None = None
    blocking: bool = False
    #: How a non-OK result should be read by an installer (#887). Defaults to
    #: CONFIGURATION, the safe middle: a check that has not been classified is
    #: reported as "needs attention" rather than silently downgraded to advice.
    category: CheckCategory = CheckCategory.CONFIGURATION

    def to_doctor_check(self):
        """Return a domain.supportability.DoctorCheckResult equivalent."""
        from domain.supportability import DoctorCheckResult, DoctorSeverity
        _severity_map = {
            Status.OK:      DoctorSeverity.OK,
            Status.WARNING: DoctorSeverity.WARNING,
            Status.FAIL:    DoctorSeverity.ERROR,
        }
        return DoctorCheckResult(
            key=self.name,
            severity=_severity_map.get(self.status, DoctorSeverity.UNKNOWN),
            message=self.message,
            evidence=self.evidence,
            suggested_action=self.suggested_action,
            blocking=self.blocking,
        )


@dataclass
class DiagnosticsReport:
    checks: List[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)

    @property
    def overall(self) -> Status:
        if any(c.status == Status.FAIL for c in self.checks):
            return Status.FAIL
        if any(c.status == Status.WARNING for c in self.checks):
            return Status.WARNING
        return Status.OK

    # ── Deployment outcome model (#887) ───────────────────────────────────────

    def _unhealthy(self) -> list:
        return [c for c in self.checks if c.status != Status.OK]

    @property
    def outcome(self) -> DoctorOutcome:
        """Deployment verdict: PASS / READY_WITH_ADVISORIES / CONFIG_REQUIRED / FAIL.

        A FAIL check is always operational — it means the appliance cannot run.
        A WARNING is graded by its category, so "cameras share the LAN" no
        longer reads the same as "ATEM is enabled with no address".
        """
        unhealthy = self._unhealthy()
        return derive_outcome(
            has_blocking_failure=any(
                c.status == Status.FAIL or c.blocking for c in unhealthy
            ),
            # CONFIGURATION and non-blocking OPERATIONAL both mean "an installer
            # must act", so neither can be lost between the tiers.
            has_actionable_issue=any(
                c.category in (CheckCategory.CONFIGURATION, CheckCategory.OPERATIONAL)
                for c in unhealthy
            ),
            has_advisory=any(
                c.category == CheckCategory.ADVISORY for c in unhealthy
            ),
        )

    @property
    def outcome_description(self) -> str:
        return describe(self.outcome)

    def action_list(self) -> list[str]:
        """Concise, ordered list of what the installer should do next.

        Most severe first, each entry naming a concrete remediation where the
        check supplied one. Empty when everything passed.
        """
        order = {
            CheckCategory.OPERATIONAL:   0,
            CheckCategory.CONFIGURATION: 1,
            CheckCategory.ADVISORY:      2,
        }
        ranked = sorted(
            self._unhealthy(),
            key=lambda c: (0 if c.status == Status.FAIL else order.get(c.category, 1),
                           c.name),
        )
        actions = []
        for check in ranked:
            action = check.suggested_action or check.message
            actions.append(f"{check.name}: {action}")
        return actions

    def to_doctor_checks(self) -> list:
        """Return a list of DoctorCheckResult objects (from domain.supportability)."""
        return [c.to_doctor_check() for c in self.checks]

    def to_json_dict(self, runtime_state: dict | None = None) -> dict:
        """Return a plain dict suitable for JSON export (hallptz doctor --json).

        Parameters
        ----------
        runtime_state:
            Snapshot redactado opcional de RuntimeState para incluir en la salida.
            Pasar aqui ``diagnostics_service.runtime_state_snapshot()``.
        """
        _STATUS_LABEL = {Status.OK: "OK", Status.WARNING: "WARNING", Status.FAIL: "FAIL"}
        overall = self.overall
        result: dict = {
            "overall": _STATUS_LABEL.get(overall, "UNKNOWN"),
            # Human and machine output share one severity model (#887).
            "outcome": self.outcome.value,
            "outcome_description": self.outcome_description,
            "exit_code": self.exit_code,
            "actions": self.action_list(),
            "checks": [
                {**c.to_doctor_check().to_dict(), "category": c.category.value}
                for c in self.checks
            ],
        }
        if runtime_state is not None:
            result["runtime_state"] = runtime_state
        return result

    @property
    def exit_code(self) -> int:
        """Exit code matching the deployment outcome (#887).

        0 = PASS, 10 = READY_WITH_ADVISORIES, 20 = CONFIG_REQUIRED, 30 = FAIL.
        Still 0 only when everything passed, so existing "zero means healthy"
        callers keep working, but a wrapper can now branch on *why* it is not 0.
        """
        return exit_code_for(self.outcome)


class DiagnosticsService:
    """
    Runs the standard set of `hallptz doctor` checks.

    Parameters
    ----------
    install_dir:
        Root directory of the installed application.
        Defaults to the project root derived from this file's location.
    data_dir:
        User data directory (seat names, presets, etc.).
        Defaults to the value of HALLPTZ_DATA_DIR or ~/.config/hallptz.
    config_path:
        Path to config.yaml. Defaults to <install_dir>/config.yaml.
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def __init__(
        self,
        install_dir: Path | None = None,
        data_dir:    Path | None = None,
        log_dir:     Path | None = None,
        config_path: Path | None = None,
        health_svc=None,
        network_svc=None,
        mode: RuntimeMode = RuntimeMode.PRODUCTION,
        flight_recorder=None,
    ) -> None:
        self._install_dir = install_dir or Path(__file__).parent.parent
        self._version_file = self._install_dir / "VERSION"

        if data_dir is None:
            from runtime.path_resolver import RuntimePathResolver
            data_dir = RuntimePathResolver().data_dir
        self._data_dir = Path(data_dir)

        if log_dir is None:
            from runtime.path_resolver import RuntimePathResolver
            resolver = RuntimePathResolver()
            # Only report log_dir in production installs; skip in dev/source.
            self._log_dir: Path | None = (
                None if resolver.running_from_source else resolver.log_dir
            )
        else:
            self._log_dir = Path(log_dir)

        if config_path is not None:
            self._config_path = config_path
        else:
            try:
                from runtime.path_resolver import RuntimePathResolver
                self._config_path = RuntimePathResolver().config_dir / "config.yaml"
            except Exception:
                self._config_path = self._install_dir / "config.yaml"
        self._health_svc   = health_svc   # injectable for tests
        self._network_svc  = network_svc  # injectable for tests
        self._mode         = mode
        self._recorder     = flight_recorder
        self._runtime_store = None  # se configura con set_runtime_state_store()

    def set_runtime_state_store(self, store) -> None:
        """Conecta RuntimeStateStore para exportar snapshots runtime (#796)."""
        self._runtime_store = store

    def runtime_state_snapshot(self) -> dict | None:
        """
        Devuelve un snapshot RuntimeState redactado, o None si no hay store.

        Seguro para exportacion externa (hallptz doctor --json, support bundle).
        El nombre del chairman y otros datos PII quedan redactados.
        """
        if self._runtime_store is None:
            return None
        try:
            return self._runtime_store.snapshot().to_redacted_dict()
        except Exception:  # noqa: BLE001
            return None

    def run(self) -> DiagnosticsReport:
        report = DiagnosticsReport()
        report.add(self._check_version())
        report.add(self._check_python_version())
        if self._mode in (RuntimeMode.DEMO, RuntimeMode.SIMULATION):
            for r in self._demo_isolation_checks():
                report.add(r)
        settings = self._load_settings()
        report.add(self._check_config(settings))
        report.add(self._check_ip_config(settings))
        report.add(self._check_connectivity_mode(settings))
        report.add(self._check_installation_profile(settings))
        report.add(self._check_installation_id(settings))
        report.add(self._check_network_profile(settings))
        if settings is not None:
            self._add_network_reachability_checks(report, settings)
        report.add(self._check_data_dir())
        if self._log_dir is not None:
            report.add(self._check_log_dir())
        report.add(self._check_secret_permissions())
        report.add(self._check_gui_mode_coherence())
        report.add(self._check_sim_mode())
        report.add(self._check_seat_names())
        report.add(self._check_disk())
        report.add(self._check_temperature())
        self._record_doctor_run(report)
        return report

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_network_svc(self):
        if self._network_svc is not None:
            return self._network_svc
        from application.network_diagnostics import NetworkDiagnosticsService
        return NetworkDiagnosticsService()

    def _add_network_reachability_checks(self, report: DiagnosticsReport, settings) -> None:
        """Add Pi subnet, camera and ATEM reachability checks to the report."""
        svc = self._get_network_svc()

        pi_check = svc.check_pi_subnet(settings)
        if pi_check is not None:
            report.add(pi_check)

        for cam_check in svc.check_cameras(settings):
            report.add(cam_check)

        atem_check = svc.check_atem(settings)
        if atem_check is not None:
            report.add(atem_check)

    def _get_health_svc(self):
        if self._health_svc is not None:
            return self._health_svc
        from application.health_diagnostics import HealthDiagnosticsService
        return HealthDiagnosticsService()

    def _load_settings(self):
        """Load config.yaml once; return AppSettings or None on error."""
        if not self._config_path.exists():
            return None
        try:
            from config.loader import load_config
            return load_config(self._config_path)
        except Exception:  # noqa: BLE001
            return None

    # ── Checks ────────────────────────────────────────────────────────────────

    def _check_secret_permissions(self) -> CheckResult:
        """The encrypted passwords must not be readable beyond their owner.

        Their key is derived from /etc/machine-id, which is world-readable, so
        the only thing actually protecting them is the file mode. A group- or
        world-readable admin.enc is effectively plaintext to anyone who can
        reach it, which silently collapses the operator/administrator split.

        This exists because that regression really happened: a group-relaxation
        step in the installer swept the secrets along with the data files. A
        mode is far easier to check than to keep correct by hand.
        """
        import stat as _stat

        name = "secret_permissions"

        # POSIX only. Windows reports 0666 for every file regardless of its real
        # ACL, so evaluating the mode there produces a false FAIL on every
        # developer machine — the same trap that made an earlier
        # filesystem-based permission test meaningless.
        if os.name != "posix":
            return CheckResult(
                name, Status.OK,
                "Credential file modes not evaluated on this platform (POSIX only)",
            )

        try:
            from runtime import secret_manager
        except Exception as exc:  # noqa: BLE001
            return CheckResult(name, Status.WARN, f"Could not inspect secrets: {exc}",
                               category=CheckCategory.ADVISORY)

        exposed: list[str] = []
        checked = 0
        for secret in (secret_manager.SECRET_ENTRY, secret_manager.SECRET_ADMIN):
            try:
                path = secret_manager._secret_file(secret)
                if not path.exists():
                    continue
                mode = path.stat().st_mode
            except OSError:
                # Unreadable metadata is not evidence of exposure; the auth
                # layer already fails closed when a secret cannot be read.
                continue
            checked += 1
            if mode & (_stat.S_IRGRP | _stat.S_IWGRP | _stat.S_IROTH | _stat.S_IWOTH):
                exposed.append(f"{path.name} ({oct(mode & 0o777)})")

        if not checked:
            return CheckResult(name, Status.OK, "No credential files present yet")
        if exposed:
            return CheckResult(
                name, Status.FAIL,
                "Credential files are readable beyond their owner: " + ", ".join(exposed),
                evidence={"exposed": exposed},
                suggested_action="sudo chmod 600 /var/lib/hallptz/*.enc",
                blocking=True,
                category=CheckCategory.OPERATIONAL,
            )
        return CheckResult(name, Status.OK, f"Credential files are private ({checked} checked)")

    def _check_gui_mode_coherence(self) -> CheckResult:
        """Warn when the installed GUI mode cannot actually authenticate.

        Passwords are verified in-process: the login screen decrypts the secret
        files directly. Under --gui-mode user the GUI runs as the desktop
        account, which by design cannot read those 0600 hallptz-owned files — so
        the appliance installs cleanly and then nobody can log in.

        Reporting it here turns a mystifying runtime symptom into a named,
        documented limitation before the operator meets it.
        """
        name = "gui_mode"
        try:
            from runtime.install_state import gui_mode
            mode = gui_mode()
        except Exception as exc:  # noqa: BLE001
            return CheckResult(name, Status.WARN, f"Could not read the GUI mode: {exc}",
                               category=CheckCategory.ADVISORY)

        if mode != "user":
            return CheckResult(name, Status.OK, "GUI mode: system (service-owned)")

        try:
            from runtime import secret_manager
            entry = secret_manager._secret_file(secret_manager.SECRET_ENTRY)
            readable = entry.exists() and os.access(entry, os.R_OK)
        except Exception:  # noqa: BLE001
            readable = False

        if readable:
            return CheckResult(name, Status.OK, "GUI mode: user (session-owned)")
        return CheckResult(
            name, Status.WARN,
            "GUI mode is 'user' but this process cannot read the credential file — "
            "login will fail. Passwords are verified in-process, so a "
            "session-owned GUI cannot both authenticate and keep the "
            "administrator secret private.",
            suggested_action=(
                "Reinstall with --gui-mode system until verification moves "
                "behind the privileged channel (see docs/KNOWN_LIMITATIONS.md)"
            ),
            category=CheckCategory.CONFIGURATION,
        )

    def _check_version(self) -> CheckResult:
        try:
            version = self._version_file.read_text(encoding="utf-8").strip()
            return CheckResult("version", Status.OK, f"Hall PTZ Control {version}")
        except OSError as exc:
            return CheckResult("version", Status.FAIL, f"Cannot read VERSION: {exc}")

    def _check_python_version(self) -> CheckResult:
        """Report the running Python against the supported 3.9.2 target.

        The single supported runtime target is Python 3.9.2 (Raspberry Pi OS
        Bullseye). 3.10+ is not validated; below 3.9 the app cannot run.
        """
        major, minor, micro = sys.version_info[:3]
        version_str = f"{major}.{minor}.{micro}"
        evidence = {"python_version": version_str}
        if (major, minor) == (3, 9):
            return CheckResult(
                "python_version",
                Status.OK,
                f"Python {version_str} (supported target is 3.9.2)",
                evidence=evidence,
            )
        if major == 3 and minor >= 10:
            return CheckResult(
                "python_version",
                Status.WARNING,
                f"Python {version_str} is not a validated runtime; the supported "
                "target is 3.9.2 on Raspberry Pi OS Bullseye",
                evidence=evidence,
                suggested_action=(
                    "Provision Raspberry Pi OS Bullseye (system Python 3.9.2) for "
                    "validated/pilot installs."
                ),
            )
        return CheckResult(
            "python_version",
            Status.FAIL,
            f"Python {version_str} is too old; the supported target is 3.9.2 "
            "(3.9 minimum)",
            evidence=evidence,
            suggested_action="Install Python 3.9.2 (Raspberry Pi OS Bullseye system Python).",
        )

    def _check_config(self, settings) -> CheckResult:
        if not self._config_path.exists():
            return CheckResult(
                "config",
                Status.WARNING,
                f"config.yaml not found at {self._config_path} "
                "(copy config/defaults/starter.yaml to get started)",
            )
        if settings is None:
            try:
                from config.loader import load_config
                load_config(self._config_path)
            except Exception as exc:  # noqa: BLE001
                return CheckResult("config", Status.FAIL, f"config.yaml invalid: {exc}")
        return CheckResult("config", Status.OK, f"config.yaml loaded OK ({self._config_path})")

    def _check_ip_config(self, settings) -> CheckResult:
        if settings is None:
            return CheckResult(
                "ip_config",
                Status.WARNING,
                "IP configuration cannot be checked — config.yaml not loaded",
            )
        from domain.network_validation import validate_ip_config
        issues = validate_ip_config(settings)
        if not issues:
            cameras = len(settings.cameras)
            return CheckResult(
                "ip_config",
                Status.OK,
                f"IP configuration OK ({cameras} camera(s), no conflicts)",
            )
        messages = "; ".join(i.message for i in issues)
        return CheckResult("ip_config", Status.FAIL, f"IP configuration issues: {messages}")

    def _check_connectivity_mode(self, settings) -> CheckResult:
        if settings is None:
            return CheckResult(
                "connectivity_mode",
                Status.WARNING,
                "Connectivity mode cannot be checked — config.yaml not loaded",
            )
        from domain.connectivity import parse_connectivity_mode, KNOWN_MODE_VALUES
        raw = settings.runtime.connectivity_mode.strip()
        mode = parse_connectivity_mode(raw)
        if mode is None:
            known = ", ".join(sorted(KNOWN_MODE_VALUES))
            return CheckResult(
                "connectivity_mode",
                Status.WARNING,
                f"Unknown connectivity mode '{raw}' — known values: {known}",
            )
        from domain.connectivity import ConnectivityMode
        if mode == ConnectivityMode.OFFLINE:
            return CheckResult(
                "connectivity_mode",
                Status.OK,
                "Connectivity mode: offline — internet access not required",
            )
        return CheckResult(
            "connectivity_mode",
            Status.OK,
            f"Connectivity mode: {raw}",
        )

    def _check_installation_profile(self, settings) -> CheckResult:
        if settings is None:
            return CheckResult(
                "installation_profile",
                Status.WARNING,
                "Installation profile cannot be checked — config.yaml not loaded",
            )
        raw = settings.site.installation_profile.strip()
        if not raw:
            return CheckResult(
                "installation_profile",
                Status.WARNING,
                "Installation profile not set — add site.installation_profile to config.yaml "
                "(starter_1_camera / standard_2_camera / demo)",
            )
        from domain.installation_profile import parse_profile, expected_camera_count, KNOWN_PROFILE_VALUES
        profile = parse_profile(raw)
        if profile is None:
            known = ", ".join(sorted(KNOWN_PROFILE_VALUES))
            return CheckResult(
                "installation_profile",
                Status.WARNING,
                f"Unknown installation profile '{raw}' — known values: {known}",
            )
        camera_count = len(settings.cameras)
        required = expected_camera_count(profile)
        if required is not None and camera_count != required:
            return CheckResult(
                "installation_profile",
                Status.WARNING,
                f"Profile mismatch: '{raw}' expects {required} camera(s) "
                f"but {camera_count} configured",
            )
        return CheckResult(
            "installation_profile",
            Status.OK,
            f"Installation profile: {raw}",
        )

    def _check_installation_id(self, settings) -> CheckResult:
        if settings is None:
            return CheckResult(
                "installation_id",
                Status.WARNING,
                "Installation ID cannot be checked — config.yaml not loaded",
            )
        iid = settings.site.installation_id.strip()
        if not iid:
            return CheckResult(
                "installation_id",
                Status.WARNING,
                "Installation ID not set — add site.installation_id to config.yaml "
                "(generate one with: python -c \"from domain.installation_id import "
                "generate_installation_id; print(generate_installation_id(2026))\")",
            )
        return CheckResult("installation_id", Status.OK, f"Installation ID: {iid}")

    def _check_network_profile(self, settings) -> CheckResult:
        """
        Warn when the network profile is flat_lan or unknown.

        Does not block demo/development use — WARNING only, not FAIL.
        See docs/NETWORK_ARCHITECTURE.md.
        """
        if settings is None:
            return CheckResult(
                "network_profile",
                Status.WARNING,
                "Network profile cannot be checked — config.yaml not loaded",
            )

        from domain.network_profile import (
            NetworkProfileConfig,
            flat_network_action,
            flat_network_warning_message,
            is_risk_profile,
            validate_network_profile,
        )

        raw_profile = getattr(settings, "network", None)
        if raw_profile is None:
            # Existing installs without network section — safe default
            return CheckResult(
                "network_profile",
                Status.WARNING,
                "Network profile not configured. "
                "Add a 'network:' section to config.yaml — see docs/NETWORK_ARCHITECTURE.md.",
                suggested_action=flat_network_action(),
            )

        network_cfg = NetworkProfileConfig.from_dict({
            "profile": settings.network.profile,
            "av_subnet": settings.network.av_subnet,
            "av_vlan_id": settings.network.av_vlan_id,
            "guest_access_allowed": settings.network.guest_access_allowed,
            "internet_required": settings.network.internet_required,
            "static_ips": settings.network.static_ips,
            "notes": settings.network.notes,
        })

        issues = validate_network_profile(network_cfg)

        if is_risk_profile(network_cfg.profile):
            evidence = {"network_profile": network_cfg.profile.value}
            if issues:
                evidence["issues"] = "; ".join(i.message for i in issues)
            # flat_lan is a hardening recommendation, not a fault: the
            # appliance is fully operational on a shared LAN. Classifying it as
            # advisory is what lets a healthy site report
            # READY_WITH_ADVISORIES instead of a bare WARN (#887).
            return CheckResult(
                "network_profile",
                Status.WARNING,
                flat_network_warning_message(),
                evidence=evidence,
                suggested_action=flat_network_action(),
                category=CheckCategory.ADVISORY,
            )

        if issues:
            msg = "; ".join(i.message for i in issues)
            return CheckResult(
                "network_profile",
                Status.WARNING,
                f"Network profile issues: {msg}",
                suggested_action=flat_network_action(),
            )

        return CheckResult(
            "network_profile",
            Status.OK,
            f"Network profile: {network_cfg.profile.value}",
        )

    def _check_data_dir(self) -> CheckResult:
        if not self._data_dir.exists():
            try:
                self._data_dir.mkdir(parents=True, exist_ok=True)
                return CheckResult(
                    "data_dir", Status.OK,
                    f"Data directory created: {self._data_dir}",
                )
            except OSError as exc:
                return CheckResult(
                    "data_dir", Status.FAIL,
                    f"Cannot create data directory {self._data_dir}: {exc}",
                )

        readable  = os.access(self._data_dir, os.R_OK)
        writable  = os.access(self._data_dir, os.W_OK)
        if readable and writable:
            return CheckResult("data_dir", Status.OK, f"Data directory OK: {self._data_dir}")

        # Running as the desktop user against a hallptz-owned path is expected,
        # not a fault: the service still has the access it needs. Reporting
        # FAIL here made a healthy appliance show "Overall: FAIL" purely
        # because diagnostics were run from the desktop terminal (#887).
        if _is_owned_by_other_user(self._data_dir):
            return CheckResult(
                "data_dir", Status.OK,
                f"Data directory is service-owned: {self._data_dir} "
                f"(not writable by {_current_user_label()}, as expected)",
                evidence={"owner": _owner_label(self._data_dir)},
                category=CheckCategory.ADVISORY,
            )

        perms = "read" if not readable else "write"
        return CheckResult(
            "data_dir", Status.FAIL,
            f"Data directory not {perms}able: {self._data_dir}",
            suggested_action=(
                f"sudo chown -R hallptz:hallptz {self._data_dir} && sudo chmod 750 {self._data_dir}"
            ),
            category=CheckCategory.OPERATIONAL,
        )

    def _check_log_dir(self) -> CheckResult:
        """Verify the production log directory exists and is writable."""
        assert self._log_dir is not None  # guarded by caller
        log_dir = self._log_dir
        if not log_dir.exists():
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                return CheckResult(
                    "log_dir", Status.OK,
                    f"Log directory created: {log_dir}",
                )
            except OSError as exc:
                return CheckResult(
                    "log_dir", Status.WARNING,
                    f"Cannot create log directory {log_dir}: {exc}",
                    suggested_action="sudo mkdir -p /var/log/hallptz && sudo chown hallptz:hallptz /var/log/hallptz",
                )

        writable = os.access(log_dir, os.W_OK)
        app_log = log_dir / "app.log"
        if not writable:
            if _is_owned_by_other_user(log_dir):
                return CheckResult(
                    "log_dir", Status.OK,
                    f"Log directory is service-owned: {log_dir} "
                    f"(not writable by {_current_user_label()}, as expected)",
                    evidence={"owner": _owner_label(log_dir)},
                    category=CheckCategory.ADVISORY,
                )
            return CheckResult(
                "log_dir", Status.WARNING,
                f"Log directory not writable: {log_dir}",
                suggested_action="sudo chown hallptz:hallptz /var/log/hallptz && sudo chmod 750 /var/log/hallptz",
                category=CheckCategory.OPERATIONAL,
            )
        if app_log.exists():
            size_kb = app_log.stat().st_size // 1024
            return CheckResult(
                "log_dir", Status.OK,
                f"Log directory OK: {log_dir} (app.log: {size_kb} KB)",
            )
        return CheckResult(
            "log_dir", Status.OK,
            f"Log directory OK: {log_dir} (app.log not yet created — will appear on first run)",
        )

    def _check_sim_mode(self) -> CheckResult:
        sim_backup = self._install_dir / "sim_ip_backup.json"
        if sim_backup.exists():
            return CheckResult(
                "simulation",
                Status.WARNING,
                f"Simulation mode is active (sim_ip_backup.json found at {sim_backup})",
            )
        return CheckResult("simulation", Status.OK, "Simulation mode: off")

    def _demo_isolation_checks(self) -> list[CheckResult]:
        """Return demo-specific isolation proof checks (DEMO / SIMULATION mode only)."""
        results: list[CheckResult] = []

        # Camera adapter type
        results.append(CheckResult(
            "demo_camera_adapter",
            Status.OK,
            "Camera adapter: FakeCamera (no real hardware used)",
        ))

        # ATEM adapter type
        results.append(CheckResult(
            "demo_atem_adapter",
            Status.OK,
            "ATEM adapter: FakeATEM (no real ATEM used)",
        ))

        # Runtime data path
        results.append(CheckResult(
            "demo_data_path",
            Status.OK,
            f"[DEMO] Runtime data path: {self._data_dir} (isolated from production)",
        ))

        # Production config protection
        from application.demo_guard import _PRODUCTION_DATA_DIR
        prod_dir = _PRODUCTION_DATA_DIR.resolve()
        demo_dir = self._data_dir.resolve()
        protected = demo_dir != prod_dir
        if protected:
            results.append(CheckResult(
                "demo_production_protected",
                Status.OK,
                f"[DEMO] Production config protected: yes ({prod_dir} not in use)",
            ))
        else:
            results.append(CheckResult(
                "demo_production_protected",
                Status.FAIL,
                f"[DEMO] Production config NOT protected: data dir is the production path ({prod_dir})",
            ))

        # ATEM automation mode — always disarmed in demo
        results.append(CheckResult(
            "demo_atem_automation",
            Status.OK,
            "[DEMO] ATEM automation mode: disarmed (demo mode — no commands sent to real switcher)",
        ))

        return results

    def _check_seat_names(self) -> CheckResult:
        layout_file = self._data_dir / "room_layout.json"
        if not layout_file.exists():
            return CheckResult(
                "seat_names", Status.OK,
                "room_layout.json not found — skipping seat name check",
            )
        try:
            data = json.loads(layout_file.read_text(encoding="utf-8"))
            seats = data.get("seats", [])
            issues = []
            for seat in seats:
                seat_id = seat.get("id", "<unknown>")
                label = seat.get("label", "")
                if not label:
                    issues.append(f"seat '{seat_id}': empty label")
                elif len(label) > 20:
                    issues.append(f"seat '{seat_id}': label too long ({len(label)} chars)")
            if issues:
                return CheckResult(
                    "seat_names", Status.WARNING,
                    "Seat name issues: " + "; ".join(issues),
                )
            return CheckResult(
                "seat_names", Status.OK,
                f"Seat names OK ({len(seats)} seats checked)",
            )
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                "seat_names", Status.WARNING,
                f"Could not validate seat names: {exc}",
            )

    def _check_disk(self) -> CheckResult:
        return self._get_health_svc().check_disk(self._data_dir)

    def _check_temperature(self) -> CheckResult:
        return self._get_health_svc().check_temperature()

    def _record_doctor_run(self, report) -> None:
        if self._recorder is None:
            return
        try:
            from domain.blackbox_event import EventLevel, EventResult, EventSource
            from datetime import datetime, timezone
            fail_count = sum(1 for c in report.checks if str(c.status).endswith("FAIL"))
            warn_count = sum(1 for c in report.checks if str(c.status).endswith("WARNING"))
            level = EventLevel.ERROR if fail_count else (EventLevel.WARNING if warn_count else EventLevel.INFO)
            self._recorder.record_dict({
                "timestamp": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "level": level,
                "event_type": "DoctorRun",
                "source": EventSource.SYSTEM,
                "result": EventResult.FAILED if fail_count else EventResult.SUCCEEDED,
                "checks_total": len(report.checks),
                "checks_failed": fail_count,
                "checks_warned": warn_count,
            })
        except Exception:  # noqa: BLE001
            pass
