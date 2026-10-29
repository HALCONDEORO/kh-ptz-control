#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# config/settings.py — typed application configuration models
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class CameraSettings:
    """Configuration for one PTZ camera."""
    id: str
    role: str
    ip: str
    visca_id: str
    name: str = ""


@dataclass
class PiPNudgeSettings:
    """Small platform-camera pan movement when ATEM PiP changes."""
    camera_role: str = "platform"
    pan_speed: int = 0
    direction: str = "right"
    duration_ms: int = 0


@dataclass
class ATEMSettings:
    """ATEM switcher configuration — Phase 1 canonical schema (#550)."""
    ip: str = ""
    installed: bool = False
    enabled: bool = False
    disabled_reason: str = ""
    me_index: int = 0
    input_labels: dict = field(default_factory=dict)
    connect_timeout_secs: int = 10
    reconnect_timeout_secs: int = 30
    automation_disabled: bool = True
    pip_nudge: PiPNudgeSettings = field(default_factory=PiPNudgeSettings)


@dataclass
class SiteSettings:
    """Installation metadata."""
    name: str = ""
    contact: str = ""
    installation_profile: str = ""
    installation_id: str = ""


@dataclass
class RuntimeSettings:
    """Runtime parameters."""
    data_dir: str = ""
    connectivity_mode: str = "offline"
    mode: str = "production"


@dataclass
class FeaturesSettings:
    """Installation feature flags."""
    atem_enabled: bool = False
    simulation: bool = False
    allow_real_hardware_in_demo: bool = False


@dataclass
class NetworkSettings:
    """Optional installation network profile with safe legacy defaults."""
    profile: str = "unknown"
    av_subnet: str = ""
    av_vlan_id: str = ""
    guest_access_allowed: bool | None = None
    internet_required: bool = False
    static_ips: bool | None = None
    notes: str = ""


# NOTE: profile-from-camera-count lives in domain.installation_profile
# (derive_installation_profile). This module stays pure data models.


@dataclass
class AppSettings:
    """Root of the configuration tree produced by ``load_config``."""
    site: SiteSettings
    cameras: List[CameraSettings]
    atem: ATEMSettings
    runtime: RuntimeSettings
    features: FeaturesSettings
    network: NetworkSettings = field(default_factory=NetworkSettings)
