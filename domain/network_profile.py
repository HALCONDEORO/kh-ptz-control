#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# domain/network_profile.py — Network profile schema and validation rules.
#
# Pure domain module — no I/O. Validates network profile fields from config.
# Does not store credentials or secrets.
# Existing installs without network profile data load safely (all fields optional).
#
# See docs/NETWORK_ARCHITECTURE.md.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── NetworkProfile enum ───────────────────────────────────────────────────────

class NetworkProfile(str, Enum):
    """
    Describes the network isolation model of the installation site.

    isolated_av_vlan — recommended: dedicated AV VLAN, no guest access
    flat_lan         — shared customer LAN, elevated risk
    unknown          — not configured or not determinable
    """
    ISOLATED_AV_VLAN = "isolated_av_vlan"
    FLAT_LAN         = "flat_lan"
    UNKNOWN          = "unknown"


KNOWN_PROFILE_VALUES: frozenset[str] = frozenset(m.value for m in NetworkProfile)

_SAFE_PROFILES = frozenset({NetworkProfile.ISOLATED_AV_VLAN})
_RISK_PROFILES = frozenset({NetworkProfile.FLAT_LAN, NetworkProfile.UNKNOWN})


def parse_network_profile(value: str) -> NetworkProfile | None:
    """Return NetworkProfile for *value*, or None if unrecognised."""
    try:
        return NetworkProfile(value.strip().lower())
    except ValueError:
        return None


def is_safe_profile(profile: NetworkProfile) -> bool:
    """Return True only if the profile is the recommended isolated AV VLAN."""
    return profile in _SAFE_PROFILES


def is_risk_profile(profile: NetworkProfile) -> bool:
    """Return True if the profile is flat or unknown (elevated risk)."""
    return profile in _RISK_PROFILES


# ── NetworkProfileConfig ──────────────────────────────────────────────────────

_IPV4_CIDR_RE = re.compile(
    r"^(25[0-5]|2[0-4]\d|[01]?\d\d?)\."
    r"(25[0-5]|2[0-4]\d|[01]?\d\d?)\."
    r"(25[0-5]|2[0-4]\d|[01]?\d\d?)\."
    r"(25[0-5]|2[0-4]\d|[01]?\d\d?)"
    r"(?:/([0-9]|[12]\d|3[0-2]))?$"
)

_VLAN_ID_RE = re.compile(r"^\d{1,4}$")


@dataclass
class NetworkProfileConfig:
    """
    A parsed network profile entry from config.yaml.

    All fields are optional — missing values are represented as None or 'unknown'.
    Existing installs without this section load safely.
    """
    profile: NetworkProfile = NetworkProfile.UNKNOWN
    av_subnet: str | None = None         # e.g. "192.168.30.0/24"
    av_vlan_id: str | None = None        # e.g. "30"
    guest_access_allowed: bool | None = None
    internet_required: bool = False
    static_ips: bool | None = None
    notes: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.value,
            "av_subnet": self.av_subnet,
            "av_vlan_id": self.av_vlan_id,
            "guest_access_allowed": self.guest_access_allowed,
            "internet_required": self.internet_required,
            "static_ips": self.static_ips,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> NetworkProfileConfig:
        """Parse a dict (from config.yaml network section). Returns safe defaults for missing keys."""
        raw_profile = str(data.get("profile", "unknown")).strip().lower()
        profile = parse_network_profile(raw_profile) or NetworkProfile.UNKNOWN
        return cls(
            profile=profile,
            av_subnet=data.get("av_subnet") or None,
            av_vlan_id=str(data.get("av_vlan_id", "")) or None,
            guest_access_allowed=data.get("guest_access_allowed"),
            internet_required=bool(data.get("internet_required", False)),
            static_ips=data.get("static_ips"),
            notes=str(data.get("notes", "")),
        )


# ── Validation ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NetworkProfileIssue:
    """A problem detected in the network profile config."""
    field: str
    message: str


def validate_network_profile(cfg: NetworkProfileConfig) -> list[NetworkProfileIssue]:
    """
    Validate a NetworkProfileConfig.

    Returns a list of issues. An empty list means no problems found.
    Pure function — no I/O, no network probing.
    """
    issues: list[NetworkProfileIssue] = []

    if cfg.profile == NetworkProfile.UNKNOWN:
        issues.append(NetworkProfileIssue(
            field="network.profile",
            message=(
                "Network profile is not configured. "
                "Set network.profile to 'isolated_av_vlan' or 'flat_lan' in config.yaml."
            ),
        ))

    if cfg.av_subnet is not None and not _IPV4_CIDR_RE.match(cfg.av_subnet.strip()):
        issues.append(NetworkProfileIssue(
            field="network.av_subnet",
            message=f"Invalid subnet format: {cfg.av_subnet!r}. Expected dotted-quad with optional /prefix.",
        ))

    if cfg.av_vlan_id is not None:
        vid = cfg.av_vlan_id.strip()
        if not _VLAN_ID_RE.match(vid):
            issues.append(NetworkProfileIssue(
                field="network.av_vlan_id",
                message=f"Invalid VLAN ID: {vid!r}. Expected a numeric string (1–4094).",
            ))
        else:
            vlan_int = int(vid)
            if not (1 <= vlan_int <= 4094):
                issues.append(NetworkProfileIssue(
                    field="network.av_vlan_id",
                    message=f"VLAN ID {vlan_int} out of range (1–4094).",
                ))

    if cfg.guest_access_allowed is True:
        issues.append(NetworkProfileIssue(
            field="network.guest_access_allowed",
            message=(
                "Guest access is marked as allowed. "
                "This increases risk — isolate HALLPTZ devices in a dedicated AV VLAN."
            ),
        ))

    return issues


# ── Flat-network warning ──────────────────────────────────────────────────────

_FLAT_NETWORK_WARNING = (
    "HALLPTZ appears to be running on a flat or unverified network. "
    "Recommended: isolate Raspberry Pi, cameras and ATEM in a dedicated AV VLAN. "
    "Do not allow guest WiFi to access HALLPTZ devices."
)

_FLAT_NETWORK_ACTION = (
    "Configure a dedicated AV VLAN and set network.profile: isolated_av_vlan in config.yaml. "
    "See docs/NETWORK_ARCHITECTURE.md."
)


def flat_network_warning_message() -> str:
    """Return the standard flat/unknown network warning message."""
    return _FLAT_NETWORK_WARNING


def flat_network_action() -> str:
    """Return the standard remediation action for flat-network warnings."""
    return _FLAT_NETWORK_ACTION
