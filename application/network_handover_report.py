#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# application/network_handover_report.py — NetworkHandoverReport and service
#
# Generates a network handover record for customer installations.
# Summarises AV network profile, device IPs, isolation assumptions and
# preflight results in a format suitable for printed handover and support.
#
# Privacy rules:
#   - Never include passwords, SSH keys, WiFi credentials or support tokens.
#   - Unknown/unverified isolation is reported honestly (not silently as safe).
#   - Follow domain/redaction rules if/when they exist.

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# ── Verification state ────────────────────────────────────────────────────────

class VerificationStatus:
    VERIFIED              = "verified"
    CONFIGURED_NOT_VERIFIED = "configured_not_verified"
    NOT_CONFIGURED        = "not_configured"
    NOT_APPLICABLE        = "not_applicable"
    WARNING               = "warning"
    FAILED                = "failed"


# ── Device record ─────────────────────────────────────────────────────────────

@dataclass
class NetworkDeviceRecord:
    device_id: str
    role: str
    ip: str
    verification_status: str = VerificationStatus.CONFIGURED_NOT_VERIFIED
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── Report ─────────────────────────────────────────────────────────────────────

@dataclass
class NetworkHandoverReport:
    """
    Network handover record for one HALLPTZ installation.

    Fields are populated from config.yaml and optional preflight results.
    Unknown or unverified fields use honest status strings, not silently empty.
    """

    # Identity
    site_name: str = "unknown"
    installation_id: str = "unknown"
    generated_at: str = ""

    # Network profile
    network_profile: str = VerificationStatus.NOT_CONFIGURED
    vlan_id: str = ""
    av_subnet: str = ""
    guest_access_allowed: Optional[bool] = None
    internet_required: bool = False
    static_ips: Optional[bool] = None

    # Devices
    pi_ip: str = ""
    pi_subnet_verification: str = VerificationStatus.NOT_CONFIGURED
    cameras: list = field(default_factory=list)   # list[NetworkDeviceRecord]
    atem_ip: str = ""
    atem_enabled: bool = False
    atem_verification: str = VerificationStatus.NOT_APPLICABLE

    # Preflight
    preflight_summary: str = "NOT_RUN"
    flat_network_warning: bool = False

    # Notes
    notes: str = ""

    # Non-secret errors during report generation
    errors: list = field(default_factory=list)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = asdict(self)
        d["cameras"] = [c.to_dict() if hasattr(c, "to_dict") else c for c in self.cameras]
        return d

    # ── Human-readable output ─────────────────────────────────────────────────

    def human_summary(self) -> list[str]:
        """Return list of lines for hallptz network-report output (ASCII-safe)."""
        lines = [
            "HALLPTZ Network Handover Report",
            "=" * 44,
            f"Site:              {self.site_name}",
            f"Installation ID:   {self.installation_id}",
        ]
        if self.generated_at:
            lines.append(f"Generated:         {self.generated_at}")

        lines += [
            "",
            "-- Network profile --",
            f"Profile:           {self.network_profile}",
        ]
        if self.vlan_id:
            lines.append(f"VLAN ID:           {self.vlan_id}")
        if self.av_subnet:
            lines.append(f"Subnet:            {self.av_subnet}")
        if self.static_ips is not None:
            lines.append(f"Static IPs:        {'yes' if self.static_ips else 'no'}")
        if self.guest_access_allowed is not None:
            lines.append(
                f"Guest access to AV VLAN: {'yes (RISK)' if self.guest_access_allowed else 'blocked'}"
            )
        lines.append(
            f"Internet required: {'yes' if self.internet_required else 'no'}"
        )

        lines += [
            "",
            "-- Devices --",
        ]
        if self.pi_ip:
            lines.append(f"Raspberry Pi:      {self.pi_ip} ({self.pi_subnet_verification})")
        else:
            lines.append(f"Raspberry Pi IP:   not configured ({self.pi_subnet_verification})")

        for cam in self.cameras:
            if hasattr(cam, "ip"):
                ip, cam_id, role, vs = cam.ip, cam.device_id, cam.role, cam.verification_status
            else:
                ip = cam.get("ip", "")
                cam_id = cam.get("device_id", "")
                role = cam.get("role", "")
                vs = cam.get("verification_status", "")
            lines.append(f"Camera {cam_id} ({role}): {ip} ({vs})")

        if self.atem_enabled:
            atem_display = self.atem_ip or "not configured"
            lines.append(f"ATEM switcher:     {atem_display} ({self.atem_verification})")
        else:
            lines.append("ATEM switcher:     not enabled")

        lines += [
            "",
            "-- Preflight --",
            f"Preflight result:  {self.preflight_summary}",
        ]
        if self.flat_network_warning:
            lines.append(
                "WARNING: Flat/unknown network profile — AV isolation NOT verified. "
                "Review docs/NETWORK_ARCHITECTURE.md before customer handover."
            )

        if self.notes:
            lines += ["", "-- Notes --", self.notes]

        if self.errors:
            lines += ["", "-- Report generation warnings --"]
            lines += [f"  * {e}" for e in self.errors]

        return lines


# ── Report service ────────────────────────────────────────────────────────────

class NetworkHandoverReportService:
    """
    Generates a NetworkHandoverReport from config settings and optional
    preflight (doctor) results.

    Never raises — errors are captured in report.errors.
    """

    def __init__(self, config_path=None) -> None:
        from pathlib import Path
        self._config_path = config_path or (Path(__file__).parent.parent / "config.yaml")

    def generate(
        self,
        *,
        preflight_report=None,   # DiagnosticsReport | None
        notes: str = "",
    ) -> NetworkHandoverReport:
        """Generate and return a NetworkHandoverReport. Never raises."""
        import datetime
        report = NetworkHandoverReport(
            generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            notes=notes,
        )
        try:
            self._populate_from_config(report)
        except Exception as exc:  # noqa: BLE001
            report.errors.append(f"Config load error: {exc}")

        if preflight_report is not None:
            try:
                self._populate_from_preflight(report, preflight_report)
            except Exception as exc:  # noqa: BLE001
                report.errors.append(f"Preflight parse error: {exc}")

        return report

    # ── Private helpers ───────────────────────────────────────────────────────

    def _populate_from_config(self, report: NetworkHandoverReport) -> None:
        """Fill report fields from config.yaml. Raises on load failure."""
        from config.loader import load_config
        settings = load_config(self._config_path)

        report.site_name = getattr(settings.site, "name", "unknown") or "unknown"
        report.installation_id = getattr(settings.site, "installation_id", "unknown") or "unknown"

        # Network profile
        net = getattr(settings, "network", None)
        if net is not None:
            report.network_profile = getattr(net, "profile", "unknown") or "unknown"
            report.vlan_id = getattr(net, "av_vlan_id", "") or ""
            report.av_subnet = getattr(net, "av_subnet", "") or ""
            report.guest_access_allowed = getattr(net, "guest_access_allowed", None)
            report.internet_required = bool(getattr(net, "internet_required", False))
            report.static_ips = getattr(net, "static_ips", None)

            # Flat network flag
            from domain.network_profile import is_risk_profile, parse_network_profile
            profile_enum = parse_network_profile(report.network_profile)
            if profile_enum is None or is_risk_profile(profile_enum):
                report.flat_network_warning = True

        # Cameras
        for cam in settings.cameras:
            ip = getattr(cam, "ip", "").strip()
            rec = NetworkDeviceRecord(
                device_id=getattr(cam, "id", ""),
                role=getattr(cam, "role", ""),
                ip=ip,
                verification_status=(
                    VerificationStatus.CONFIGURED_NOT_VERIFIED if ip
                    else VerificationStatus.NOT_CONFIGURED
                ),
            )
            report.cameras.append(rec)

        # ATEM
        report.atem_enabled = bool(getattr(settings.features, "atem_enabled", False))
        if report.atem_enabled:
            report.atem_ip = getattr(settings.atem, "ip", "").strip()
            report.atem_verification = (
                VerificationStatus.CONFIGURED_NOT_VERIFIED if report.atem_ip
                else VerificationStatus.NOT_CONFIGURED
            )
        else:
            report.atem_verification = VerificationStatus.NOT_APPLICABLE

    def _populate_from_preflight(self, report: NetworkHandoverReport, preflight_report) -> None:
        """Enrich report with doctor check results."""
        from application.diagnostics_service import Status

        # Map check name -> status for quick lookup
        check_map = {c.name: c for c in preflight_report.checks}

        # Overall preflight summary
        overall = preflight_report.overall
        if overall == Status.OK:
            report.preflight_summary = "PASS"
        elif overall == Status.WARNING:
            report.preflight_summary = "PASS_WITH_WARNINGS"
        else:
            report.preflight_summary = "FAIL"

        # Pi subnet verification
        pi_check = check_map.get("pi_subnet")
        if pi_check is not None:
            if pi_check.status == Status.OK:
                report.pi_subnet_verification = VerificationStatus.VERIFIED
                # Extract Pi IP from evidence if present
                report.pi_ip = pi_check.evidence.get("local_ip", report.pi_ip)
            elif pi_check.status == Status.WARNING:
                report.pi_subnet_verification = VerificationStatus.WARNING
            else:
                report.pi_subnet_verification = VerificationStatus.FAILED

        # Camera verification
        for cam in report.cameras:
            check_name = f"camera_{cam.device_id}_reachable"
            cam_check = check_map.get(check_name)
            if cam_check is None:
                continue
            if cam_check.status == Status.OK:
                cam.verification_status = VerificationStatus.VERIFIED
            elif cam_check.status == Status.WARNING:
                cam.verification_status = VerificationStatus.WARNING
            else:
                cam.verification_status = VerificationStatus.FAILED

        # ATEM verification
        if report.atem_enabled:
            atem_check = check_map.get("atem_reachable")
            if atem_check is not None:
                if atem_check.status == Status.OK:
                    report.atem_verification = VerificationStatus.VERIFIED
                elif atem_check.status == Status.WARNING:
                    report.atem_verification = VerificationStatus.WARNING
                else:
                    report.atem_verification = VerificationStatus.FAILED
